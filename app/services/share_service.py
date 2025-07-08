"""
(share_service.py) Contains the business logic for creating and retrieving
publicly shareable recommendation links, compatible with the multi-turn data model.
"""

import secrets
from typing import Dict, Any

from google.cloud import firestore

# Reuse the initialized Firestore client
from app.services.logging_service import firestore_client

# Import the new Pydantic response model and the history service
from app.schemas import ConversationResponse
from app.services import history_service


# --- Custom Exceptions for clarity in the router layer ---
class ShareLinkNotFound(Exception):
    """Raised when a share link does not exist or is disabled."""
    pass

class ConversationNotFound(Exception):
    """Raised when the referenced conversation document doesn't exist."""
    pass

class NotOwnerOfConversation(Exception):
    """Raised when a user tries to share a conversation they do not own."""
    pass


def create_share_link(conversation_id: str, user_id: str) -> str:
    """
    Creates a new, unique, and permanent share link for a given conversation.

    This function is idempotent: if a share link for this conversation already
    exists and is owned by the same user, it returns the existing link.

    Args:
        conversation_id: The ID of the conversation in the 'histories' collection.
        user_id: The UID of the authenticated user requesting the share.

    Returns:
        The unique 'shareId' for the public URL.
    """
    if not firestore_client:
        raise Exception("Firestore client is not initialized. Cannot create share link.")

    # 1. Verify ownership of the conversation
    history_doc_ref = firestore_client.collection("histories").document(conversation_id)
    history_doc = history_doc_ref.get()

    if not history_doc.exists:
        raise ConversationNotFound(f"Conversation with ID '{conversation_id}' not found.")

    history_data = history_doc.to_dict()
    if history_data.get("userId") != user_id:
        raise NotOwnerOfConversation("User does not have permission to share this conversation.")

    # 2. Check if a link already exists to prevent duplicates
    # We can now check the field on the history document directly for efficiency.
    if history_data.get("shareId"):
        print(f"Found existing share link '{history_data['shareId']}' for conversation '{conversation_id}'.")
        return history_data['shareId']

    # 3. If no link exists, create a new one
    print(f"No existing share link found. Creating a new one for conversation '{conversation_id}'.")
    
    new_share_id = secrets.token_urlsafe(16)
    shares_collection = firestore_client.collection("shares")
    share_doc_ref = shares_collection.document(new_share_id)
    
    share_data = {
        "conversationId": conversation_id,
        "userId": user_id,
        "createdAt": firestore.SERVER_TIMESTAMP,
        "isEnabled": True,
        "viewCount": 0
    }
    
    # Use a transaction to write to both collections atomically
    transaction = firestore_client.transaction()
    @firestore.transactional
    def _create_share_in_transaction(trans):
        # Create the document in the 'shares' collection
        trans.set(share_doc_ref, share_data)
        # Update the 'histories' document with the new shareId
        trans.update(history_doc_ref, {"shareId": new_share_id})

    _create_share_in_transaction(transaction)
    
    print(f"Successfully created new share link '{new_share_id}'.")
    
    return new_share_id


def get_shared_data(share_id: str) -> ConversationResponse:
    """
    Retrieves all necessary data to render a shared recommendation page.
    It validates the share link and then reuses the history_service to fetch
    the full conversation data.

    Args:
        share_id: The public, unique ID of the share link.

    Returns:
        A ConversationResponse object containing the full conversation snapshot.
    """
    if not firestore_client:
        raise Exception("Firestore client is not initialized. Cannot retrieve shared data.")

    # 1. Fetch the share document
    share_doc_ref = firestore_client.collection("shares").document(share_id)
    share_doc = share_doc_ref.get()

    # 2. Validate the share link
    if not share_doc.exists or not share_doc.to_dict().get("isEnabled", False):
        raise ShareLinkNotFound("This share link is either invalid or has been disabled.")

    share_data = share_doc.to_dict()
    conversation_id = share_data.get("conversationId")
    user_id = share_data.get("userId") # We need the owner's ID to fetch the snapshot

    # 3. Increment the view count (fire-and-forget)
    try:
        share_doc_ref.update({"viewCount": firestore.Increment(1)})
    except Exception as e:
        print(f"WARNING: Failed to increment view count for share_id '{share_id}': {e}")
    
    # 4. Reuse the history service to get the full conversation snapshot
    # This keeps the data-fetching logic in one place.
    # The history service already handles all the assembly of the ConversationResponse.
    try:
        # We pass the owner's user_id to satisfy the permission check in get_conversation_snapshot
        conversation_snapshot = history_service.get_conversation_snapshot(
            user_id=user_id,
            conversation_id=conversation_id
        )
        return conversation_snapshot
    except history_service.HistoryNotFound:
        # If the underlying history is gone, the share link is effectively broken.
        raise ConversationNotFound(f"The data for this share link could not be found.")
    except Exception as e:
        print(f"ERROR: Unexpected error in get_shared_data while fetching snapshot for conv {conversation_id}: {e}")
        raise