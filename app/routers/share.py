"""
(share.py) Defines the API routes for creating and viewing shared recommendations.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request

# Import the service functions that contain the business logic
from app.services import share_service

# Import schemas for request and response validation
from app.schemas import (
    ShareCreateRequest,
    ShareCreateResponse,
    ShareDataResponse,
)

# Import the dependency for authentication
from app.middleware.auth import get_current_user


# ==============================================================================
# Router Setup
# ==============================================================================

router = APIRouter(
    prefix="/api/share",
    tags=["Sharing"]
)

# ==============================================================================
# API Endpoints
# ==============================================================================

@router.post(
    "", # The path is just the prefix "/api/share"
    response_model=ShareCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a permanent share link"
)
async def create_share_link_endpoint(
    http_request: Request, # Used to construct the full URL
    request: ShareCreateRequest,
    user_id: str = Depends(get_current_user)
):
    """
    Creates a unique, permanent, and publicly accessible URL for a given
    recommendation conversation.

    - This endpoint is authenticated and requires ownership of the conversation.
    - If a share link for this conversation already exists, it will return
      the existing URL instead of creating a new one.
    """
    print(f"User '{user_id}' requesting to share conversation '{request.conversation_id}'.")
    try:
        share_id = share_service.create_share_link(
            conversation_id=request.conversation_id,
            user_id=user_id
        )

        # Construct the full, absolute URL to return to the client
        # This is better than returning a relative path.
        base_url = str(http_request.base_url)
        # Assuming the frontend URL structure is like `https://domain.com/share/...`
        # We replace the API's base URL with the intended frontend root.
        # A more robust solution might get the frontend URL from config.
        # For now, this is a reasonable approach.
        frontend_base_url = base_url.replace(http_request.scope.get('root_path', ''), '').rstrip('/')
        
        # In a real-world scenario, you might have a config variable for the frontend URL
        # For example: `share_url = f"https://www.recmonkey.com/share/{share_id}"`
        share_url = f"{frontend_base_url}/share/{share_id}"


        return {"shareUrl": share_url}

    except share_service.ConversationNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except share_service.NotOwnerOfConversation as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        print(f"ERROR: Unexpected error creating share link for conv_id {request.conversation_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while creating the share link."
        )


@router.get(
    "/{share_id}",
    response_model=ShareDataResponse,
    summary="Get data for a shared recommendation"
)
async def get_shared_data_endpoint(share_id: str):
    """
    Retrieves all the necessary data to render a shared recommendation page.

    - This is a **public** endpoint and does not require authentication.
    - It returns a 404 error if the link is invalid or has been disabled.
    """
    print(f"Public request for shared data with ID: {share_id}")
    try:
        shared_data = share_service.get_shared_data(share_id)
        return shared_data
        
    except share_service.ShareLinkNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except share_service.ConversationNotFound as e:
        # We still return 404 to the public to not leak internal state info.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="The data for this link could not be found.")
    except Exception as e:
        print(f"ERROR: Unexpected error retrieving shared data for share_id {share_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while retrieving the shared data."
        )