"""
(recommendations.py) Defines the API routes for the product recommendation flow.
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from typing import Dict

# Import services and handlers
# --- MODIFICATION: Import the new stateless llm_calls module ---
from app.services import llm_calls, search_functions
from app.services.logging_service import save_completed_conversation, save_rejected_query
from app.services.parsing_service import extract_product_names_from_markdown

# Import schemas (Pydantic models)
from app.schemas import (
    StartRequest,
    FinalizeRequest,
    QuestionsResponse,
    RecommendationsResponse,
    RejectionResponse,
    StopResponse
)

# Import the dependency for authentication
from app.middleware.auth import get_current_user

# ==============================================================================
# Router Setup
# ==============================================================================

router = APIRouter(
    prefix="/api/recommendations",
    tags=["Recommendations"]
)

# In-memory store for active sessions. The value is now just the trace dictionary.
ACTIVE_SESSIONS: Dict[str, Dict] = {}


# ==============================================================================
# API Endpoints
# ==============================================================================

@router.post(
    "/start",
    response_model=QuestionsResponse,
    responses={
        422: {"model": RejectionResponse, "description": "Query is out-of-scope for the API"}
    }
)
async def start_recommendation(
    request: StartRequest,
    user_id: str = Depends(get_current_user)
):
    """
    Starts a new recommendation flow. It first runs a stateless guardrail check.
    If the query is valid, it creates a session and returns a questionnaire.
    If invalid, it logs the rejection and returns a 422 error without creating a session.
    """
    print(f"User {user_id} | Step 0 | Performing guardrail check for query: '{request.user_query}'")
    
    # --- STEP 0: STATELESS GUARDRAIL (THE BOUNCER) ---
    guardrail_result = llm_calls.run_query_guardrail(request.user_query)
    
    if not guardrail_result.get("is_product_request"):
        print(f"User {user_id} | REJECTED | Reason: {guardrail_result.get('reason')}")
        
        # Log the rejected query. A 'rejectionId' is used as no conversation has started.
        rejection_log = {
            "rejectionId": str(uuid.uuid4()),
            "userId": user_id,
            "userQuery": request.user_query,
            "reason": guardrail_result.get("reason")
        }
        save_rejected_query(rejection_log)
        
        # Raise a structured HTTP exception and exit. No session is created.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "I can only help with physical product recommendations.",
                "reason": guardrail_result.get("reason", "The query is not a valid product request.")
            }
        )
    
    print(f"User {user_id} | PASSED | Guardrail check passed. Creating new session.")
    
    # --- GUARDRAIL PASSED: PROCEED TO CREATE SESSION ---
    
    conversation_id = str(uuid.uuid4())
    # The session no longer holds a stateful LLM object, just the trace.
    session_data = {
        "conversation_id": conversation_id,
        "trace": {
            "conversationId": conversation_id,
            "userId": user_id,
            "userQuery": request.user_query,
            "guardrailResult": guardrail_result # Log the pass result
        }
    }
    ACTIVE_SESSIONS[user_id] = session_data
    
    try:
        trace = session_data["trace"]

        # Step 3: Generate MCQ questions using a stateless LLM call.
        print(f"User {user_id} | Step 3 | Generating questions from internal knowledge...")
        questions = llm_calls.generate_mcq_questions(request.user_query)
        trace["generatedQuestions"] = questions
        print(f"User {user_id} | Step 3 | Generated {len(questions)} questions")
        
        return {"questions": questions}

    except Exception as e:
        # This block now only catches errors that happen *after* a session is created.
        print(f"ERROR in /start for user {user_id} after session creation: {e}")
        trace = ACTIVE_SESSIONS.get(user_id, {}).get("trace", {})
        if trace:
             trace["status"] = "failed"
             trace["error"] = str(e)
        
        # Clean up the session that was created before the error occurred.
        if user_id in ACTIVE_SESSIONS:
            del ACTIVE_SESSIONS[user_id]
            print(f"Cleaned up failed session for user: {user_id}")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred during the start process: {e}"
        )


@router.post("/stop", response_model=StopResponse)
async def stop_recommendation(
    user_id: str = Depends(get_current_user)
):
    """
    Interrupts and terminates the user's active recommendation session.
    The session and its trace are discarded and NOT saved.
    """
    if user_id in ACTIVE_SESSIONS:
        del ACTIVE_SESSIONS[user_id]
        print(f"Session terminated by user and discarded: {user_id}")
        return {"status": "stopped", "message": "Your session has been terminated."}
    else:
        print(f"Stop request for non-existent session from user: {user_id}")
        return {"status": "stopped", "message": "No active session was found to terminate."}


@router.post("/finalize", response_model=RecommendationsResponse)
async def finalize_recommendation(
    request: FinalizeRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user)
):
    """
    Finalizes the recommendation flow. On full success, the entire conversation
    trace is saved to Firestore and GCS via a background task.
    """
    print(f"Finalizing session for user: {user_id}")
    
    session_data = ACTIVE_SESSIONS.get(user_id)
    if not session_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active session not found. Please start a new recommendation via the /start endpoint."
        )
    
    trace = session_data["trace"]

    try:
        user_answers_dict = [answer.dict(by_alias=True) for answer in request.user_answers]
        trace["userAnswers"] = user_answers_dict
        user_query = trace["userQuery"] # Retrieve initial query from trace for stateless calls

        # Step 4: Generate search queries for recommendations
        rec_search_terms = llm_calls.generate_search_queries(
            user_query=user_query, 
            user_answers=user_answers_dict
        )
        trace["recSearchTerms"] = rec_search_terms
        print(f"User {user_id} | Step 4 | Generated {len(rec_search_terms)} search queries")

        # Step 4.5: Search for product recommendations
        rec_search_results = search_functions.search_product_recommendations(rec_search_terms)
        trace["recSearchResults"] = "Content too large, omitted from in-memory trace."

        # Step 5: Select best recommendation URLs
        rec_urls = llm_calls.select_recommendation_urls(
            user_query=user_query,
            user_answers=user_answers_dict,
            rec_search_results=rec_search_results
        )
        trace["selectedRecUrls"] = rec_urls
        print(f"User {user_id} | Step 5 | Selected {len(rec_urls)} recommendation sources")

        # Step 5.5: Scrape recommendation content
        rec_scraped_contents = search_functions.scrape_recommendation_urls(rec_urls)
        trace["scrapedRecContent"] = "Content too large, omitted from in-memory trace."

        # Step 6: Generate final recommendations
        final_recommendations = llm_calls.generate_final_recommendations(
            user_query=user_query,
            user_answers=user_answers_dict,
            rec_scraped_contents=rec_scraped_contents
        )
        trace["finalRecommendation"] = final_recommendations
        print(f"User {user_id} | Step 6 | Generated final recommendations")
        
        # Step 6.5: Post-process the markdown to extract product names
        product_names = extract_product_names_from_markdown(final_recommendations)
        trace["extractedProductNames"] = product_names # Also log the extracted names
        print(f"User {user_id} | Post-processing | Extracted {len(product_names)} product names.")

        # --- LOGGING ON SUCCESS ---
        trace["status"] = "completed"
        background_tasks.add_task(save_completed_conversation, trace.copy())
        # --- END LOGGING ---

        return {
            "recommendations": final_recommendations,
            "productNames": product_names  # Use the camelCase key for the response
        }

    except Exception as e:
        print(f"ERROR in /finalize for user {user_id}: {e}")
        # Log the failure if a trace exists
        if "trace" in locals() and trace:
            trace["status"] = "failed"
            trace["error"] = str(e)
            # We can still try to save the failed trace for debugging
            background_tasks.add_task(save_completed_conversation, trace.copy())

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred during the finalize process: {e}"
        )
    finally:
        # ALWAYS clean up the session from memory after the request is finished.
        if user_id in ACTIVE_SESSIONS:
            del ACTIVE_SESSIONS[user_id]
            print(f"Cleaned up active session for user: {user_id}")