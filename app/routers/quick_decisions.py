"""
(quick_decisions.py) Defines API routes for the Quick Decision conversational flow.
This router handles creating and polling conversational turns for simple, agentic chat.
"""

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Query, Request
from typing import Union

# Import the service function for the new background job
from app.services.quick_decision_service import process_quick_decision_turn_background_job
from app.services import location_service

# Import shared services and schemas
from app.services import logging_service
from app.services.history_service import get_conversation_snapshot # For ownership check
from app.schemas import (
    QuickDecisionTurnRequest,
    TurnCreationResponse,
    TurnStatusResponse,
)

# Import the dependency for authentication
from app.middleware.auth import get_current_user

# Import a direct firestore client for lightweight status checks
from google.cloud import firestore

# ==============================================================================
# Router Setup
# ==============================================================================

router = APIRouter(
    prefix="/api/quick-decisions",
    tags=["Quick Decisions"]
)

# ==============================================================================
# Conversational Turn Endpoints
# ==============================================================================

@router.post(
    "/turn",
    response_model=TurnCreationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Process a quick decision conversational turn"
)
async def process_quick_decision_turn(
    request: QuickDecisionTurnRequest,
    background_tasks: BackgroundTasks,
    fastapi_request: Request,
    user_id: str = Depends(get_current_user)
):
    """
    Processes a single turn in a "Quick Decision" conversation.

    - If `conversationId` is null, it creates a new conversation and its first turn.
    - If `conversationId` is provided, it adds a new turn for a follow-up question.

    This endpoint immediately returns a 202 Accepted response and triggers a
    long-running background job to generate the agent's response.
    """
    conv_id = request.conversation_id
    location_context = None

    # Case 1: This is a follow-up turn for an existing conversation.
    if conv_id:
        try:
            snapshot = get_conversation_snapshot(user_id, conv_id)
            next_turn_index = len(snapshot.turns)
            turn_id = logging_service.create_subsequent_turn(
                conversation_id=conv_id,
                user_query=request.user_query,
                next_turn_index=next_turn_index
            )
            print(f"Follow-up quick decision turn accepted for user: {user_id}, conv_id: {conv_id}.")
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Conversation not found or access denied: {e}")

    # Case 2: This is the first turn, creating a new conversation.
    else:
        next_turn_index = 0
        # Fetch location ONLY on the first turn if the flag is true.
        if request.need_location:
            print(f"Location is needed for user {user_id}. Fetching from IP.")
            location_context = await location_service.get_location_from_request(fastapi_request)
        
        conv_id, turn_id = logging_service.create_conversation_and_first_turn(
            user_id=user_id,
            user_query=request.user_query,
            conversation_type="QUICK_DECISION" 
        )
        print(f"Initial quick decision turn accepted for user: {user_id}. New conv_id: {conv_id}.")

    # Schedule the universal background job, passing the appropriate context.
    background_tasks.add_task(
        process_quick_decision_turn_background_job,
        conversation_id=conv_id,
        turn_id=turn_id,
        turn_index=next_turn_index,
        user_id=user_id,
        full_request=request,
        location_context=location_context
    )

    return {"conversation_id": conv_id, "turn_id": turn_id, "status": "processing"}


@router.get(
    "/turn_status/{turn_id}",
    response_model=TurnStatusResponse,
    summary="Get the status of a specific quick decision turn"
)
async def get_quick_decision_turn_status(
    turn_id: str,
    conversation_id: str = Query(..., alias="conversationId", description="The parent conversation ID for the turn."),
    user_id: str = Depends(get_current_user)
):
    """
    Poll this endpoint to get the status of a quick decision turn's processing job.

    Once the status is 'complete', the response will include the 'modelResponse'.
    This flow will not populate 'productNames'.
    """
    try:
        firestore_client = firestore.Client()

        # Verify ownership by checking the parent conversation document first.
        # This is a critical security check and is identical to the other flow.
        history_ref = firestore_client.collection("histories").document(conversation_id)
        history_doc = history_ref.get()

        if not history_doc.exists or history_doc.to_dict().get("userId") != user_id:
             raise HTTPException(status_code=403, detail="Forbidden: You do not have access to this conversation.")

        # If ownership is verified, fetch the specific turn document.
        turn_ref = history_ref.collection("turns").document(turn_id)
        turn_doc = turn_ref.get()

        if not turn_doc.exists:
            raise HTTPException(status_code=404, detail="Turn not found.")

        turn_data = turn_doc.to_dict()

        # The response structure is identical, so we can reuse the same model.
        # 'product_names' will simply be null/empty, which is expected.
        response_payload = {
            "status": turn_data.get("status", "unknown"),
            "model_response": turn_data.get("modelResponse"),
            "product_names": turn_data.get("productNames"),
            "error": turn_data.get("error")
        }

        return response_payload

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        print(f"ERROR fetching status for quick decision turn_id {turn_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve job status.")