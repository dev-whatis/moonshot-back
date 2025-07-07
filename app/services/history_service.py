"""
(history_service.py) Contains the business logic for fetching and managing
user conversation history.
"""

from typing import Dict, Any, Tuple, List, Optional

from google.cloud import firestore

# Reuse the initialized Firestore client from the logging service
# This assumes the client is initialized successfully at startup.
from app.services.logging_service import firestore_client

# --- Custom Exceptions for the router layer ---
class HistoryNotFound(Exception):
    """Raised when a specific history document is not found."""
    pass

class NotOwnerOfHistory(Exception):
    """Raised when a user tries to modify a history item they do not own."""
    pass


def get_history_for_user(
    user_id: str,
    limit: int = 20,
    start_after_id: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Fetches a paginated list of COMPLETED conversation history summaries for a specific user.
    """
    if not firestore_client:
        raise Exception("Firestore client is not initialized. Cannot fetch history.")

    query = (
        firestore_client.collection("histories")
        .where("userId", "==", user_id)
        .where("isDeleted", "==", False)
        .where("status", "==", "complete")
        .order_by("createdAt", direction=firestore.Query.DESCENDING)
    )

    if start_after_id:
        try:
            start_after_doc = firestore_client.collection("histories").document(start_after_id).get()
            if start_after_doc.exists:
                query = query.start_after(start_after_doc)
            else:
                print(f"Warning: start_after_id '{start_after_id}' not found. Fetching from the beginning.")
        except Exception as e:
            print(f"Error fetching start_after document '{start_after_id}': {e}. Defaulting to first page.")

    # Fetch one more than the limit to determine if a next page exists
    query = query.limit(limit + 1)
    
    docs = [doc for doc in query.stream()]
    
    # --- REVISED AND CORRECTED PAGINATION LOGIC ---
    
    # 1. Determine if there are more results than the page limit
    has_more = len(docs) > limit
    
    # 2. If so, trim the extra document used for the check
    if has_more:
        docs.pop() # Removes the last element

    # 3. Now that `docs` has the correct items for the *current* page,
    #    determine the cursor for the *next* page.
    #    The cursor is the ID of the last document on the current page.
    next_cursor = docs[-1].id if has_more else None
    
    # --- END OF REVISED LOGIC ---

    history_summaries = []
    for doc in docs:
        data = doc.to_dict()
        history_summaries.append({
            "conversation_id": doc.id,
            "title": data.get("title", data.get("userQuery", "Untitled Conversation")),
            "created_at": data.get("createdAt"),
            "status": data.get("status", "complete")
        })

    return history_summaries, next_cursor


def get_conversation_snapshot(user_id: str, conversation_id: str) -> Dict[str, Any]:
    """
    Retrieves a complete snapshot of a single conversation.
    """
    if not firestore_client:
        raise Exception("Firestore client is not initialized. Cannot retrieve shared data.")

    history_doc_ref = firestore_client.collection("histories").document(conversation_id)
    history_doc = history_doc_ref.get()

    if not history_doc.exists:
        raise HistoryNotFound(f"Conversation with ID '{conversation_id}' not found.")

    history_data = history_doc.to_dict()

    if history_data.get("userId") != user_id:
        raise NotOwnerOfHistory("User does not have permission to access this conversation.")

    
    response_payload = {
        "user_query": history_data.get("userQuery", "Original query not found."),
        "recommendations": history_data.get("recommendations", "No recommendation report found."),
        "product_names": history_data.get("productNames", []),
        "enriched_products": history_data.get("enrichedProducts", []),
    }

    return response_payload


def update_history_title(user_id: str, conversation_id: str, new_title: str) -> Dict[str, Any]:
    """
    Updates the title of a specific conversation history item.
    """
    if not firestore_client:
        raise Exception("Firestore client is not initialized.")

    doc_ref = firestore_client.collection("histories").document(conversation_id)
    doc = doc_ref.get()

    if not doc.exists:
        raise HistoryNotFound(f"History with ID '{conversation_id}' not found.")

    data = doc.to_dict()
    if data.get("userId") != user_id:
        raise NotOwnerOfHistory("User does not have permission to modify this history item.")

    doc_ref.update({"title": new_title})

    return {
        "conversation_id": doc.id,
        "title": new_title,
        "created_at": data.get("createdAt"),
        "status": data.get("status", "unknown")
    }


def delete_history_item(user_id: str, conversation_id: str):
    """
    Performs a soft delete on a specific history item by setting 'isDeleted' to True.
    """
    if not firestore_client:
        raise Exception("Firestore client is not initialized.")

    doc_ref = firestore_client.collection("histories").document(conversation_id)
    doc = doc_ref.get()

    if not doc.exists:
        raise HistoryNotFound(f"History with ID '{conversation_id}' not found.")

    if doc.to_dict().get("userId") != user_id:
        raise NotOwnerOfHistory("User does not have permission to delete this history item.")

    doc_ref.update({"isDeleted": True})

    return