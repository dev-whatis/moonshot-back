"""
(recommendations.py) Defines the API routes for the product recommendation flow.
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from typing import Dict

# Import services and handlers
from app.services.llm_handler import LLMHandler
from app.services import search_functions
from app.services.logging_service import save_completed_conversation

# Import schemas (Pydantic models)
from app.schemas import (
    StartRequest,
    FinalizeRequest,
    QuestionsResponse,
    RecommendationsResponse,
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

ACTIVE_SESSIONS: Dict[str, Dict] = {}


# ==============================================================================
# API Endpoints
# ==============================================================================

@router.post("/start", response_model=QuestionsResponse)
async def start_recommendation(
    request: StartRequest,
    user_id: str = Depends(get_current_user)
):
    """
    Starts a new recommendation flow, creating a session and accumulating a trace.
    """
    print(f"Starting new session for user: {user_id}")

    session_data = {
        "llm": LLMHandler(),
        "conversation_id": str(uuid.uuid4()),
        "trace": {
            "conversationId": str(uuid.uuid4()),
            "userId": user_id,
            "userQuery": request.user_query
        }
    }
    ACTIVE_SESSIONS[user_id] = session_data
    
    try:
        llm = session_data["llm"]
        trace = session_data["trace"]

        # Step 1: Generate search term for buying guides
        guide_search_term = llm.generate_search_term(request.user_query)
        trace["guideSearchTerm"] = guide_search_term
        print(f"User {user_id} | Step 1 | Generated search term: {guide_search_term}")

        # Step 1.5: Search for buying guides
        search_results_json = search_functions.search_buying_guides(guide_search_term)
        # --- MODIFICATION: Omit large search results from log ---
        trace["guideSearchResults"] = "Content too large, omitted from in-memory trace."

        # Step 2: Select best guide URLs (use the in-memory variable)
        guide_urls = llm.select_guide_urls(search_results_json)
        trace["selectedGuideUrls"] = guide_urls
        print(f"User {user_id} | Step 2 | Selected {len(guide_urls)} guide URLs")

        # Step 2.5: Scrape guide content
        scraped_contents = search_functions.scrape_guide_urls(guide_urls)
        # --- MODIFICATION: Omit large scraped content from log ---
        trace["scrapedGuideContent"] = "Content too large, omitted from in-memory trace."
        if not scraped_contents:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not scrape content from buying guides. Please try again."
            )

        # Step 3: Generate MCQ questions (use the in-memory variable)
        questions = llm.generate_mcq_questions(request.user_query, scraped_contents)
        trace["generatedQuestions"] = questions
        print(f"User {user_id} | Step 3 | Generated {len(questions)} questions")
        
        return {"questions": questions}

    except Exception as e:
        # If start fails, do not try to clean up the session to avoid race conditions.
        # Let the user call /stop or start a new flow to overwrite it.
        print(f"ERROR in /start for user {user_id}: {e}")
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
    
    llm = session_data["llm"]
    trace = session_data["trace"]

    try:
        user_answers_dict = [answer.dict(by_alias=True) for answer in request.user_answers]
        trace["userAnswers"] = user_answers_dict
        
        # Step 4: Generate search queries for recommendations
        rec_search_terms = llm.generate_search_queries(user_answers_dict)
        trace["recSearchTerms"] = rec_search_terms
        print(f"User {user_id} | Step 4 | Generated {len(rec_search_terms)} search queries")

        # Step 4.5: Search for product recommendations
        rec_search_results = search_functions.search_product_recommendations(rec_search_terms)
        # --- MODIFICATION: Omit large search results from log ---
        trace["recSearchResults"] = "Content too large, omitted from in-memory trace."

        # Step 5: Select best recommendation URLs (use the in-memory variable)
        rec_urls = llm.select_recommendation_urls(rec_search_results)
        trace["selectedRecUrls"] = rec_urls
        print(f"User {user_id} | Step 5 | Selected {len(rec_urls)} recommendation sources")

        # Step 5.5: Scrape recommendation content
        rec_scraped_contents = search_functions.scrape_recommendation_urls(rec_urls)
        # --- MODIFICATION: Omit large scraped content from log ---
        trace["scrapedRecContent"] = "Content too large, omitted from in-memory trace."

        # Step 6: Generate final recommendations (use the in-memory variable)
        final_recommendations = llm.generate_final_recommendations(rec_scraped_contents)
        trace["finalRecommendation"] = final_recommendations
        print(f"User {user_id} | Step 6 | Generated final recommendations")

        # --- LOGGING ON SUCCESS ---
        trace["status"] = "completed"
        background_tasks.add_task(save_completed_conversation, trace.copy())
        # --- END LOGGING ---

        return {"recommendations": final_recommendations}

    except Exception as e:
        print(f"ERROR in /finalize for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred during the finalize process: {e}"
        )
    finally:
        # ALWAYS clean up the session from memory after the request is finished.
        if user_id in ACTIVE_SESSIONS:
            del ACTIVE_SESSIONS[user_id]
            print(f"Cleaned up active session for user: {user_id}")