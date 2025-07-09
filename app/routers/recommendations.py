"""
(recommendations.py) Defines the API routes for the product recommendation flow.
This version uses a unified, turn-based conversational model.
"""

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Query
from typing import Optional
import asyncio

# Import services and handlers
from app.services import llm_calls, logging_service
from app.services.recommendation_service import process_turn_background_job
from app.services.history_service import get_conversation_snapshot # For ownership check

# Import the new, refactored Pydantic schemas
from app.schemas import (
    StartRequest,
    TurnRequest,
    StartResponse,
    TurnCreationResponse,
    TurnStatusResponse,
    ConversationResponse,
    RejectionResponse
)

# Import the dependency for authentication
from app.middleware.auth import get_current_user

# Import a direct firestore client for lightweight status checks
from google.cloud import firestore

# ==============================================================================
# Router Setup
# ==============================================================================

# Create two separate routers for better organization in the OpenAPI docs
rec_router = APIRouter(
    prefix="/api/recommendations",
    tags=["Recommendations"]
)

convo_router = APIRouter(
    prefix="/api/conversations",
    tags=["Conversations"]
)

# ==============================================================================
# Recommendation Initiation Endpoint (Stateless)
# ==============================================================================

@rec_router.post(
    "/start",
    response_model=StartResponse,
    responses={
        422: {"model": RejectionResponse, "description": "Query is out-of-scope for the API"}
    }
)
async def start_recommendation_questionnaire(
    request: StartRequest,
    user_id: str = Depends(get_current_user)
):
    """
    Starts a new recommendation flow by generating a questionnaire.
    This is a stateless endpoint that does NOT create a conversation in the database.
    It runs a guardrail check and then generates budget and diagnostic questions.
    """
    print(f"User {user_id} | Step 0 | Performing guardrail check for query: '{request.user_query}'")
    
    # --- STEP 0: STATELESS GUARDRAIL (THE BOUNCER) ---
    guardrail_result = llm_calls.run_query_guardrail(request.user_query)
    
    if not guardrail_result.get("is_product_request"):
        # This logic is simplified as we no longer log rejections with a conv_id
        print(f"User {user_id} | REJECTED | Reason: {guardrail_result.get('reason')}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "I can only help with physical product recommendations.",
                "reason": guardrail_result.get("reason", "The query is not a valid product request.")
            }
        )
    
    print(f"User {user_id} | PASSED | Guardrail check passed. Generating questions.")
    
    try:
        # The llm_calls functions are synchronous (blocking).
        # We use asyncio.to_thread to run them in a separate thread without
        # blocking the main FastAPI event loop.
        budget_task = asyncio.to_thread(
            llm_calls.generate_budget_question, request.user_query
        )
        diagnostics_task = asyncio.to_thread(
            llm_calls.generate_diagnostic_questions, request.user_query
        )

        # asyncio.gather runs both tasks concurrently and waits for them to complete.
        # The results will be returned in the same order.
        print(f"User {user_id} | Generating budget and diagnostic questions in parallel...")
        budget_question, diagnostic_questions = await asyncio.gather(
            budget_task,
            diagnostics_task
        )
        print(f"User {user_id} | Both questions generated.")

        return {
            # No conversation_id is returned here, as none is created yet.
            # The client will hold the questions and pass them back to the /turn endpoint.
            "budget_question": budget_question,
            "diagnostic_questions": diagnostic_questions
        }

    except Exception as e:
        print(f"ERROR in /start for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred while generating questions: {e}"
        )


# ==============================================================================
# Conversational Turn Endpoints
# ==============================================================================

@convo_router.post(
    "/turn",
    response_model=TurnCreationResponse,
    status_code=status.HTTP_202_ACCEPTED
)
async def process_conversation_turn(
    request: TurnRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user)
):
    """
    Processes a single turn in a conversation.
    - If `conversationId` is null, creates a new conversation and the first turn.
    - If `conversationId` is provided, adds a new turn to the existing conversation.
    
    This endpoint starts a background job and returns immediately.
    """
    conv_id = request.conversation_id
    
    if conv_id:
        # This is a follow-up turn. First, verify ownership and get turn count.
        try:
            # We fetch the snapshot to check ownership and get the turn count for the index.
            # This is a read-before-write, which is acceptable here.
            snapshot = get_conversation_snapshot(user_id, conv_id)
            next_turn_index = len(snapshot.turns)
            
            # Create the new "processing" turn document in Firestore
            turn_id = logging_service.create_subsequent_turn(
                conversation_id=conv_id,
                user_query=request.user_query,
                next_turn_index=next_turn_index
            )
            print(f"Follow-up turn accepted for user: {user_id}, conv_id: {conv_id}. Starting background task.")

        except Exception as e:
            # Catches HistoryNotFound, NotOwnerOfHistory, etc.
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Conversation not found or access denied: {e}")
    
    else:
        # This is the first turn. Create the conversation and the turn document.
        conv_id, turn_id = logging_service.create_conversation_and_first_turn(
            user_id=user_id,
            user_query=request.user_query
        )
        next_turn_index = 0
        print(f"Initial turn accepted for user: {user_id}. New conv_id: {conv_id}. Starting background task.")

    # Schedule the universal background job
    background_tasks.add_task(
        process_turn_background_job,
        conversation_id=conv_id,
        turn_id=turn_id,
        turn_index=next_turn_index,
        user_id=user_id,
        full_request=request
    )
    
    return {"conversation_id": conv_id, "turn_id": turn_id, "status": "processing"}


@convo_router.get(
    "/turn_status/{turn_id}",
    response_model=TurnStatusResponse
)
async def get_turn_status(
    turn_id: str,
    # ADD THE ALIAS HERE
    conversation_id: str = Query(..., alias="conversationId", description="The parent conversation ID for the turn."),
    user_id: str = Depends(get_current_user)
):
    """
    Poll this endpoint to get the current status of a specific turn's processing job.
    """
    try:
        firestore_client = firestore.Client()
        
        # Verify ownership by checking the parent conversation document first.
        history_ref = firestore_client.collection("histories").document(conversation_id)
        history_doc = history_ref.get()

        if not history_doc.exists or history_doc.to_dict().get("userId") != user_id:
             raise HTTPException(status_code=403, detail="Forbidden: You do not have access to this conversation.")

        # Now fetch the specific turn document
        turn_ref = history_ref.collection("turns").document(turn_id)
        turn_doc = turn_ref.get()

        if not turn_doc.exists:
            raise HTTPException(status_code=404, detail="Turn not found.")

        turn_data = turn_doc.to_dict()
        
        response_payload = {
            "status": turn_data.get("status", "unknown"),
            "model_response": turn_data.get("modelResponse"), # Will be None if not complete
            "product_names": turn_data.get("productNames"),   # Will be None or [] if not complete
            "error": turn_data.get("error")                   # Will be None if not failed
        }

        return response_payload

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        print(f"ERROR fetching status for turn_id {turn_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve job status.")