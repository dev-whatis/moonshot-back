"""
(product_discovery.py) Defines the API routes for an ongoing product recommendation conversation.
This router handles the creation and polling of individual conversational turns.
"""

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Query

# Import services and handlers
from app.services import logging_service
from app.services.product_discovery_service import process_product_discovery_turn_job
from app.services.history_service import get_conversation_snapshot # For ownership check

# Import the Pydantic schemas relevant to conversational turns
from app.schemas import (
    TurnRequest,
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

# This single router now handles all product discovery related endpoints.
router = APIRouter(
    prefix="/api/product-discovery",
    tags=["Product Discovery"]
)

# ==============================================================================
# Conversational Turn Endpoints
# ==============================================================================

@router.post(
    "/turn",
    response_model=TurnCreationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Process a product discovery conversational turn"
)
async def create_turn(
    request: TurnRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user)
):
    """
    Processes a single turn in a "Product Discovery" conversation.

    - If `conversationId` is null, it creates a new conversation and its first turn.
      This happens after the user answers the questionnaire from the `/routes/start` endpoint.
    - If `conversationId` is provided, it adds a new turn to the existing conversation for follow-up questions.

    This endpoint immediately returns a 202 Accepted response and triggers a
    long-running background job to generate the recommendation or answer.
    """
    conv_id = request.conversation_id

    if conv_id:
        # This is a follow-up turn. First, verify ownership and get the turn count.
        try:
            # We fetch a snapshot to check ownership and get the current turn count for the index.
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
            # This will catch HistoryNotFound, NotOwnerOfHistory, etc.
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Conversation not found or access denied: {e}")

    else:
        # This is the first turn. Create the conversation and the turn document.
        conv_id, turn_id = logging_service.create_conversation_and_first_turn(
            user_id=user_id,
            user_query=request.user_query,
            conversation_type="PRODUCT_DISCOVERY"
        )
        next_turn_index = 0
        print(f"Initial turn accepted for user: {user_id}. New conv_id: {conv_id}. Starting background task.")

    # Schedule the universal background job to handle the actual processing
    background_tasks.add_task(
        process_product_discovery_turn_job,
        conversation_id=conv_id,
        turn_id=turn_id,
        turn_index=next_turn_index,
        user_id=user_id,
        full_request=request
    )

    return {"conversation_id": conv_id, "turn_id": turn_id, "status": "processing"}


@router.get(
    "/turn_status/{turn_id}",
    response_model=TurnStatusResponse,
    summary="Get the status of a specific product discovery turn"
)
async def get_turn(
    turn_id: str,
    conversation_id: str = Query(..., alias="conversationId", description="The parent conversation ID for the turn."),
    user_id: str = Depends(get_current_user)
):
    """
    Poll this endpoint to get the current status of a specific product discovery turn's processing job.

    Once the status is 'complete', the response will include the 'modelResponse'
    and 'productNames'. If the status is 'failed', it will include an 'error' message.
    """
    try:
        firestore_client = firestore.Client()

        # Verify ownership by checking the parent conversation document first.
        # This is a critical security check.
        history_ref = firestore_client.collection("histories").document(conversation_id)
        history_doc = history_ref.get()

        if not history_doc.exists or history_doc.to_dict().get("userId") != user_id:
             raise HTTPException(status_code=403, detail="Forbidden: You do not have access to this conversation.")

        # If ownership is verified, fetch the specific turn document
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