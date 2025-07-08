"""
(history.py) Defines the API routes for fetching and managing user conversation history.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Optional

# Import the service functions that contain the business logic
from app.services import history_service

# Import schemas for request and response validation
from app.schemas import (
    HistoryListResponse,
    HistoryUpdateRequest,
    ShareDataResponse,
    ConversationResponse
)

# Import the dependency for authentication
from app.middleware.auth import get_current_user


# ==============================================================================
# Router Setup
# ==============================================================================

router = APIRouter(
    prefix="/api/history",
    tags=["History"]
)

# ==============================================================================
# API Endpoints
# ==============================================================================

@router.get(
    "",
    response_model=HistoryListResponse,
    summary="Get user's conversation history"
)
async def get_history_list(
    user_id: str = Depends(get_current_user),
    limit: int = Query(20, gt=0, le=50, description="Number of history items to return per page."),
    cursor: Optional[str] = Query(None, description="The cursor (conversationId) to start fetching from for pagination.")
):
    """
    Retrieves a paginated list of the authenticated user's conversation history.
    Results are sorted from newest to oldest.
    """
    try:
        # CORRECTED: Call the sync function directly and unpack the resulting tuple.
        history_items, next_cursor = history_service.get_history_for_user(
            user_id=user_id,
            limit=limit,
            start_after_id=cursor
        )
        return {"history": history_items, "next_cursor": next_cursor}
        
    except Exception as e:
        print(f"ERROR: Unexpected error fetching history for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while fetching conversation history."
        )

@router.get(
    "/{conversation_id}",
    response_model=ConversationResponse,
    summary="Get a full conversation snapshot"
)
async def get_history_detail(
    conversation_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Retrieves the complete data snapshot for a single conversation, including
    all of its turns, metadata, and any enriched data.
    """
    try:
        snapshot = history_service.get_conversation_snapshot(
            user_id=user_id,
            conversation_id=conversation_id
        )
        return snapshot
    except history_service.HistoryNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except history_service.NotOwnerOfHistory as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        print(f"ERROR: Unexpected error fetching snapshot for conv_id {conversation_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while fetching the conversation snapshot."
        )


@router.patch(
    "/{conversation_id}/title",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Update a history item's title"
)
async def update_history_title(
    conversation_id: str,
    request: HistoryUpdateRequest,
    user_id: str = Depends(get_current_user)
):
    """
    Updates the title of a specific conversation in the user's history.
    """
    try:
        # CORRECTED: Call the sync function directly.
        history_service.update_history_title(
            user_id=user_id,
            conversation_id=conversation_id,
            new_title=request.title
        )
        return

    except history_service.HistoryNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except history_service.NotOwnerOfHistory as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        print(f"ERROR: Unexpected error updating history title for conv_id {conversation_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while updating the conversation."
        )


@router.delete(
    "/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a history item"
)
async def delete_history_item(
    conversation_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Performs a soft delete on a specific conversation in the user's history.
    """
    try:
        # CORRECTED: Call the sync function directly.
        history_service.delete_history_item(
            user_id=user_id,
            conversation_id=conversation_id
        )
        return
        
    except history_service.HistoryNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except history_service.NotOwnerOfHistory as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        print(f"ERROR: Unexpected error deleting history item for conv_id {conversation_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while deleting the conversation."
        )