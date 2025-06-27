"""
(share_service.py) Contains the business logic for creating and retrieving
publicly shareable recommendation links.
"""

import secrets
from typing import Optional, Dict, Any

from google.cloud import firestore

# Reuse the initialized Firestore client from the logging service to avoid multiple clients.
# This assumes the client is initialized successfully at startup.
from app.services.logging_service import firestore_client

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

    Raises:
        ConversationNotFound: If the conversation_id is invalid.
        NotOwnerOfConversation: If the user_id does not match the owner of the conversation.
        Exception: If the Firestore client is not available.
    """
    if not firestore_client:
        raise Exception("Firestore client is not initialized. Cannot create share link.")

    # 1. Verify ownership of the conversation
    history_doc_ref = firestore_client.collection("histories").document(conversation_id)
    history_doc = history_doc_ref.get()

    if not history_doc.exists:
        raise ConversationNotFound(f"Conversation with ID '{conversation_id}' not found.")

    if history_doc.to_dict().get("userId") != user_id:
        raise NotOwnerOfConversation("User does not have permission to share this conversation.")

    # 2. Check if a link already exists to prevent duplicates
    shares_collection = firestore_client.collection("shares")
    existing_shares_query = shares_collection.where("conversationId", "==", conversation_id).limit(1).stream()
    
    for existing_share in existing_shares_query:
        print(f"Found existing share link '{existing_share.id}' for conversation '{conversation_id}'.")
        return existing_share.id # Return the ID of the existing share document

    # 3. If no link exists, create a new one
    print(f"No existing share link found. Creating a new one for conversation '{conversation_id}'.")
    
    # Generate a new, secure, URL-safe random ID
    new_share_id = secrets.token_urlsafe(16)
    
    share_doc_ref = shares_collection.document(new_share_id)
    
    share_data = {
        "conversationId": conversation_id,
        "ownerId": user_id,
        "createdAt": firestore.SERVER_TIMESTAMP,
        "isEnabled": True,
        "viewCount": 0
    }
    
    share_doc_ref.set(share_data)
    print(f"Successfully created new share link '{new_share_id}'.")
    
    return new_share_id


def get_shared_data(share_id: str) -> Dict[str, Any]:
    """
    Retrieves the necessary data to render a shared recommendation page.

    It also increments the view count for the share link in a non-blocking way.

    Args:
        share_id: The public, unique ID of the share link.

    Returns:
        A dictionary containing the recommendation report, product names,
        and enriched product data.

    Raises:
        ShareLinkNotFound: If the share link is invalid, not found, or disabled.
        ConversationNotFound: If the underlying history document is missing.
        Exception: If the Firestore client is not available.
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

    # 3. Fetch the underlying history document with the actual data
    history_doc_ref = firestore_client.collection("histories").document(conversation_id)
    history_doc = history_doc_ref.get()

    if not history_doc.exists:
        # This indicates a data inconsistency, but from the user's perspective, the link is broken.
        raise ConversationNotFound(f"The data for this share link could not be found.")

    history_data = history_doc.to_dict()

    # 4. Increment the view count (fire-and-forget)
    try:
        share_doc_ref.update({"viewCount": firestore.Increment(1)})
    except Exception as e:
        # Log this error but don't block the user from getting the data.
        # This is a non-critical part of the read operation.
        print(f"WARNING: Failed to increment view count for share_id '{share_id}': {e}")
    
    # 5. Assemble and return the payload for the frontend
    # Use .get() with defaults to handle cases where a field might be missing
    # (e.g., enrichment was never run for this conversation).
    response_payload = {
        "recommendations": history_data.get("recommendations", "No recommendation report found."),
        "productNames": history_data.get("productNames", []),
        "enrichedProducts": history_data.get("enrichedProducts", [])
    }

    return response_payload