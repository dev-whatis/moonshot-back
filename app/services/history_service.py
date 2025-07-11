"""
(history_service.py) Contains the business logic for fetching and managing
user conversation history, compatible with the multi-turn data model.
"""

from typing import Tuple, List, Optional

from google.cloud import firestore

# Reuse the initialized Firestore client from the logging service
from app.services.logging_service import firestore_client

# Import the new Pydantic response models to validate the output
from app.schemas import ConversationResponse, Turn, EnrichedProduct, HistorySummaryItem

# --- Custom Exceptions for the router layer ---
class HistoryNotFound(Exception):
    """Raised when a specific history document is not found."""
    pass

class NotOwnerOfHistory(Exception):
    """Raised when a user tries to access or modify a history item they do not own."""
    pass


def get_history_for_user(
    user_id: str,
    limit: int = 20,
    start_after_id: Optional[str] = None
) -> Tuple[List[HistorySummaryItem], Optional[str]]:
    """
    Fetches a paginated list of conversation history summaries for a specific user.
    This version correctly filters to only show conversations where the initial
    recommendation (turn 0) was successfully completed.
    """
    if not firestore_client:
        raise Exception("Firestore client is not initialized. Cannot fetch history.")

    # THE CORE FIX IS HERE: Add a new .where() clause
    query = (
        firestore_client.collection("histories")
        .where("userId", "==", user_id)
        .where("isDeleted", "==", False)
        .where("initialTurnStatus", "==", "complete") # Only show successful conversations
        .order_by("updatedAt", direction=firestore.Query.DESCENDING)
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
    docs = list(query.stream())
    
    has_more = len(docs) > limit
    if has_more:
        docs.pop() # Removes the extra document used for the check

    next_cursor = docs[-1].id if has_more else None
    
    history_summaries = []
    for doc in docs:
        data = doc.to_dict()
        # Use Pydantic model for validation and consistency
        summary_item = HistorySummaryItem(
            conversation_id=doc.id,
            title=data.get("title", "Untitled Conversation"),
            created_at=data.get("createdAt"),
            status="complete" 
        )
        history_summaries.append(summary_item)

    return history_summaries, next_cursor


def get_conversation_snapshot(user_id: str, conversation_id: str) -> ConversationResponse:
    """
    Retrieves a complete snapshot of a single conversation, including all of its turns.
    Assembles the data into the main ConversationResponse model.
    """
    if not firestore_client:
        raise Exception("Firestore client is not initialized. Cannot retrieve conversation snapshot.")

    # 1. Fetch the main history document and validate ownership
    history_doc_ref = firestore_client.collection("histories").document(conversation_id)
    history_doc = history_doc_ref.get()

    if not history_doc.exists:
        raise HistoryNotFound(f"Conversation with ID '{conversation_id}' not found.")

    history_data = history_doc.to_dict()

    if history_data.get("userId") != user_id:
        raise NotOwnerOfHistory("User does not have permission to access this conversation.")
        
    # 2. Fetch all associated turns from the subcollection
    turns_query = history_doc_ref.collection("turns").order_by("turnIndex", direction=firestore.Query.ASCENDING)
    turn_docs = list(turns_query.stream())
    
    # 3. Assemble the list of Turn objects
    turns_list = []
    for turn_doc in turn_docs:
        turn_data = turn_doc.to_dict()
        
        # Manually construct EnrichedProduct objects to satisfy the Pydantic model
        enriched_products_data = turn_data.get("enrichedProducts", [])
        enriched_products_list = [EnrichedProduct(**ep) for ep in enriched_products_data]
        
        turn_obj = Turn(
            turn_id=turn_doc.id,
            turn_index=turn_data.get("turnIndex"),
            status=turn_data.get("status", "unknown"),
            user_query=turn_data.get("userQuery", ""),
            model_response=turn_data.get("modelResponse"),
            product_names=turn_data.get("productNames", []),
            enriched_products=enriched_products_list,
            created_at=turn_data.get("createdAt"),
            error=turn_data.get("error")
        )
        turns_list.append(turn_obj)

    # 4. Assemble the final ConversationResponse object
    conversation_snapshot = ConversationResponse(
        conversation_id=history_doc.id,
        user_id=history_data.get("userId"),
        title=history_data.get("title", "Untitled Conversation"),
        conversation_type=history_data.get("conversationType", "UNKNOWN"),
        created_at=history_data.get("createdAt"),
        updated_at=history_data.get("updatedAt"),
        turns=turns_list
    )

    return conversation_snapshot


def update_history_title(user_id: str, conversation_id: str, new_title: str):
    """
    Updates the title of a specific conversation history item.
    This operation remains on the parent document.
    """
    if not firestore_client:
        raise Exception("Firestore client is not initialized.")

    doc_ref = firestore_client.collection("histories").document(conversation_id)
    doc = doc_ref.get()

    if not doc.exists:
        raise HistoryNotFound(f"History with ID '{conversation_id}' not found.")

    if doc.to_dict().get("userId") != user_id:
        raise NotOwnerOfHistory("User does not have permission to modify this history item.")

    doc_ref.update({"title": new_title, "updatedAt": firestore.SERVER_TIMESTAMP})


def delete_history_item(user_id: str, conversation_id: str):
    """

    Performs a soft delete on a specific history item by setting 'isDeleted' to True.
    This operation remains on the parent document.
    """
    if not firestore_client:
        raise Exception("Firestore client is not initialized.")

    doc_ref = firestore_client.collection("histories").document(conversation_id)
    doc = doc_ref.get()

    if not doc.exists:
        raise HistoryNotFound(f"History with ID '{conversation_id}' not found.")

    if doc.to_dict().get("userId") != user_id:
        raise NotOwnerOfHistory("User does not have permission to delete this history item.")

    doc_ref.update({"isDeleted": True, "updatedAt": firestore.SERVER_TIMESTAMP})