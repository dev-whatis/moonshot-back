"""
(recommendations.py) Defines the API routes for the product recommendation flow.
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from typing import Dict

# Import services and handlers
from app.services import llm_calls, search_functions
from app.services.logging_service import log_step, create_history_document, save_rejected_query
from app.services.parsing_service import extract_product_names_from_markdown

# Import schemas (Pydantic models)
from app.schemas import (
    StartRequest,
    FinalizeRequest,
    StartResponse,  # --- MODIFICATION: Use the new StartResponse model
    RecommendationsResponse,
    RejectionResponse
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

# --- MODIFICATION: The in-memory session store is no longer needed. ---
# ACTIVE_SESSIONS: Dict[str, Dict] = {}


# ==============================================================================
# API Endpoints
# ==============================================================================

@router.post(
    "/start",
    response_model=StartResponse,  # --- MODIFICATION: Use the new StartResponse model
    responses={
        422: {"model": RejectionResponse, "description": "Query is out-of-scope for the API"}
    }
)
async def start_recommendation(
    request: StartRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user)
):
    """
    Starts a new recommendation flow. It first runs a stateless guardrail check.
    If the query is valid, it generates a questionnaire and returns it along
    with a new conversationId. If invalid, it logs the rejection and returns a 422 error.
    """
    print(f"User {user_id} | Step 0 | Performing guardrail check for query: '{request.user_query}'")
    
    # --- STEP 0: STATELESS GUARDRAIL (THE BOUNCER) ---
    guardrail_result = llm_calls.run_query_guardrail(request.user_query)
    
    if not guardrail_result.get("is_product_request"):
        print(f"User {user_id} | REJECTED | Reason: {guardrail_result.get('reason')}")
        
        # Log the rejected query. A 'rejectionId' is used as the correlation ID.
        rejection_id = str(uuid.uuid4())
        rejection_log = {
            "rejectionId": rejection_id,
            "userId": user_id,
            "userQuery": request.user_query,
            "reason": guardrail_result.get("reason")
        }
        # This call is independent of the conversation flow
        save_rejected_query(rejection_log)
        
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "I can only help with physical product recommendations.",
                "reason": guardrail_result.get("reason", "The query is not a valid product request.")
            }
        )
    
    print(f"User {user_id} | PASSED | Guardrail check passed. Generating questions.")
    
    # --- MODIFICATION: No server-side session is created. ---
    conversation_id = str(uuid.uuid4())
    
    try:
        # Step 3: Generate MCQ questions using a stateless LLM call.
        print(f"User {user_id} | Step 3 | Generating questions for conv_id: {conversation_id}...")
        questions = llm_calls.generate_mcq_questions(request.user_query)
        print(f"User {user_id} | Step 3 | Generated {len(questions)} questions")
        
        # Log the successful start step to GCS
        start_log_payload = {
            "userId": user_id,
            "userQuery": request.user_query,
            "guardrailResult": guardrail_result,
            "generatedQuestions": questions
        }
        background_tasks.add_task(log_step, conversation_id, "01_start", start_log_payload)
        
        # Return the conversation ID and questions to the client
        return {"conversation_id": conversation_id, "questions": questions}

    except Exception as e:
        print(f"ERROR in /start for user {user_id}: {e}")
        # Log the failure if it occurs
        failure_log = {"userId": user_id, "userQuery": request.user_query, "error": str(e)}
        background_tasks.add_task(log_step, conversation_id, "01_start_failure", failure_log)
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred during the start process: {e}"
        )


# --- MODIFICATION: The /stop endpoint is removed as there's no server-side session to stop. ---


@router.post("/finalize", response_model=RecommendationsResponse)
async def finalize_recommendation(
    request: FinalizeRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user)
):
    """
    Finalizes the recommendation flow using the state provided by the client.
    On full success, logs the entire flow to GCS and creates a history document in Firestore.
    """
    # The conversation ID from the request is now the primary identifier for logging.
    conv_id = request.conversation_id
    print(f"Finalizing recommendation for user: {user_id}, conv_id: {conv_id}")
    
    # --- MODIFICATION: No server-side session lookup. All data comes from the request. ---
    
    # Prepare a dictionary for logging data throughout the process
    finalize_log_payload = {}
    
    try:
        user_answers_dict = [answer.dict(by_alias=True) for answer in request.user_answers]
        finalize_log_payload["userAnswers"] = user_answers_dict
        user_query = request.user_query  # Get user_query from the request

        # Step 4: Generate search queries for recommendations
        rec_search_terms = llm_calls.generate_search_queries(
            user_query=user_query, 
            user_answers=user_answers_dict
        )
        finalize_log_payload["recSearchTerms"] = rec_search_terms
        print(f"User {user_id} | Step 4 | Generated {len(rec_search_terms)} search queries")

        # Step 4.5: Search for product recommendations
        rec_search_results = search_functions.search_product_recommendations(rec_search_terms)
        # We omit the large search results from the log for brevity.

        # Step 5: Select best recommendation URLs
        rec_urls = llm_calls.select_recommendation_urls(
            user_query=user_query,
            user_answers=user_answers_dict,
            rec_search_results=rec_search_results
        )
        finalize_log_payload["selectedRecUrls"] = rec_urls
        print(f"User {user_id} | Step 5 | Selected {len(rec_urls)} recommendation sources")

        # Step 5.5: Scrape recommendation content
        rec_scraped_contents = search_functions.scrape_recommendation_urls(rec_urls)
        # We omit the large scraped content from the log for brevity.

        # Step 6: Generate final recommendations
        final_recommendations = llm_calls.generate_final_recommendations(
            user_query=user_query,
            user_answers=user_answers_dict,
            rec_scraped_contents=rec_scraped_contents
        )
        finalize_log_payload["finalRecommendation"] = final_recommendations
        print(f"User {user_id} | Step 6 | Generated final recommendations")
        
        # Step 6.5: Post-process the markdown to extract product names
        product_names = extract_product_names_from_markdown(final_recommendations)
        finalize_log_payload["extractedProductNames"] = product_names
        print(f"User {user_id} | Post-processing | Extracted {len(product_names)} product names.")

        # --- LOGGING ON SUCCESS ---
        # Log the full finalize step trace to GCS
        background_tasks.add_task(log_step, conv_id, "02_finalize", finalize_log_payload)
        
        # Create the initial history document in Firestore
        initial_history_payload = {
            "userId": user_id,
            "userQuery": user_query,
            "finalRecommendation": final_recommendations,
            "productNames": product_names,
        }
        background_tasks.add_task(create_history_document, conv_id, initial_history_payload)
        # --- END LOGGING ---

        return {
            "recommendations": final_recommendations,
            "productNames": product_names
        }

    except Exception as e:
        print(f"ERROR in /finalize for user {user_id}, conv_id: {conv_id}: {e}")
        # Log the failure with the context we have
        finalize_log_payload["error"] = str(e)
        background_tasks.add_task(log_step, conv_id, "02_finalize_failure", finalize_log_payload)

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred during the finalize process: {e}"
        )