"""
(logging_service.py) Handles writing conversation data to Firestore.
This version supports the multi-turn conversational data model.
"""

import uuid
from typing import Tuple, Dict, Any

from google.cloud import firestore

from app.config import GCP_PROJECT_ID

# ==============================================================================
# Client Initialization
# ==============================================================================

# Initialize clients once when the module is imported.
try:
    firestore_client = firestore.Client(project=GCP_PROJECT_ID)
    print("Successfully initialized Firestore client.")
except Exception as e:
    firestore_client = None
    print(f"ERROR: Failed to initialize Google Cloud client (Firestore): {e}")
    print("WARNING: Conversation persistence will be disabled.")


# ==============================================================================
# Firestore "Write Path" Functions
# ==============================================================================

@firestore.transactional
def _create_conversation_and_first_turn_transaction(
    transaction: firestore.Transaction,
    user_id: str,
    user_query: str,
    conversation_type: str
) -> Tuple[str, str]:
    """
    Executes the creation of a new conversation and its first turn within a transaction.
    This is an internal helper function.
    """
    conversation_id = str(uuid.uuid4())
    turn_id = str(uuid.uuid4())
    
    # 1. Create the main conversation document
    history_ref = firestore_client.collection("histories").document(conversation_id)
    history_data = {
        "userId": user_id,
        "title": user_query,  # Default title is the first query
        "createdAt": firestore.SERVER_TIMESTAMP,
        "updatedAt": firestore.SERVER_TIMESTAMP,
        "isDeleted": False,
        "conversationType": conversation_type
    }
    transaction.set(history_ref, history_data)
    
    # 2. Create the first turn document in the subcollection
    turn_ref = history_ref.collection("turns").document(turn_id)
    turn_data = {
        "turnIndex": 0,
        "status": "processing",
        "createdAt": firestore.SERVER_TIMESTAMP,
        "userQuery": user_query,
        "productNames": [],
        "enrichedProducts": []
    }
    transaction.set(turn_ref, turn_data)
    
    return conversation_id, turn_id


def create_conversation_and_first_turn(
    user_id: str,
    user_query: str,
    conversation_type: str
) -> Tuple[str, str]:
    """
    Creates a new conversation with its first turn atomically.

    Returns:
        A tuple containing the new (conversation_id, turn_id).
    """
    if not firestore_client:
        raise Exception("Firestore client is not initialized. Cannot create conversation.")
    
    transaction = firestore_client.transaction()
    conv_id, turn_id = _create_conversation_and_first_turn_transaction(
        transaction, user_id, user_query, conversation_type
    )
    print(f"Successfully CREATED new conversation '{conv_id}' ({conversation_type}) and first turn '{turn_id}'.")
    return conv_id, turn_id


@firestore.transactional
def _create_subsequent_turn_transaction(
    transaction: firestore.Transaction,
    conversation_id: str,
    user_query: str,
    next_turn_index: int
) -> str:
    """
    Executes the creation of a subsequent turn and updates the parent timestamp
    within a transaction. This is an internal helper function.
    """
    turn_id = str(uuid.uuid4())
    history_ref = firestore_client.collection("histories").document(conversation_id)
    
    # 1. Create the new turn document
    turn_ref = history_ref.collection("turns").document(turn_id)
    turn_data = {
        "turnIndex": next_turn_index,
        "status": "processing",
        "createdAt": firestore.SERVER_TIMESTAMP,
        "userQuery": user_query,
        "productNames": [],
        "enrichedProducts": []
    }
    transaction.set(turn_ref, turn_data)
    
    # 2. Update the parent document's timestamp
    transaction.update(history_ref, {"updatedAt": firestore.SERVER_TIMESTAMP})
    
    return turn_id


def create_subsequent_turn(
    conversation_id: str,
    user_query: str,
    next_turn_index: int
) -> str:
    """
    Creates a new turn within an existing conversation atomically.

    Returns:
        The new turn_id.
    """
    if not firestore_client:
        raise Exception("Firestore client is not initialized. Cannot create subsequent turn.")
        
    transaction = firestore_client.transaction()
    turn_id = _create_subsequent_turn_transaction(transaction, conversation_id, user_query, next_turn_index)
    print(f"Successfully CREATED subsequent turn '{turn_id}' for conversation '{conversation_id}'.")
    return turn_id

def update_parent_conversation_status(conversation_id: str, initial_turn_status: str):
    """Updates a new status field on the main history document."""
    if not firestore_client:
        return
    try:
        doc_ref = firestore_client.collection("histories").document(conversation_id)
        # We'll call this field 'initialTurnStatus' for clarity
        doc_ref.update({"initialTurnStatus": initial_turn_status})
        print(f"Updated parent conv {conversation_id} with initialTurnStatus: {initial_turn_status}")
    except Exception as e:
        print(f"ERROR updating parent conversation status: {e}")

def update_turn_status(
    conversation_id: str,
    turn_id: str,
    final_status: str, # "complete" or "failed"
    payload: Dict[str, Any]
):
    """
    Updates a turn document when a background job finishes (successfully or not)
    and updates the parent conversation's timestamp.
    """
    if not firestore_client:
        print(f"Skipping Firestore update for turn {turn_id}, client not initialized.")
        return

    try:
        history_ref = firestore_client.collection("histories").document(conversation_id)
        turn_ref = history_ref.collection("turns").document(turn_id)
        
        update_payload = {
            "status": final_status,
            **payload  # Unpack modelResponse/error, productNames etc.
        }

        # Use a transaction to update both documents atomically
        transaction = firestore_client.transaction()
        @firestore.transactional
        def _update_in_transaction(trans):
            trans.update(turn_ref, update_payload)
            trans.update(history_ref, {"updatedAt": firestore.SERVER_TIMESTAMP})

        _update_in_transaction(transaction)
        print(f"Successfully updated turn '{turn_id}' status to '{final_status}'.")

    except Exception as e:
        print(f"ERROR: Failed to update turn status for conv {conversation_id}, turn {turn_id}: {e}")


def update_turn_with_enrichment(
    conversation_id: str,
    turn_id: str,
    enriched_products: list
):
    """
    Updates a specific turn document with enriched product data.
    """
    if not firestore_client:
        print(f"Skipping Firestore enrichment update for turn {turn_id}, client not initialized.")
        return

    try:
        history_ref = firestore_client.collection("histories").document(conversation_id)
        turn_ref = history_ref.collection("turns").document(turn_id)
        
        update_payload = {
            "enrichedProducts": enriched_products
        }

        # Use a transaction to ensure parent timestamp is also updated
        transaction = firestore_client.transaction()
        @firestore.transactional
        def _update_in_transaction(trans):
            trans.update(turn_ref, update_payload)
            trans.update(history_ref, {"updatedAt": firestore.SERVER_TIMESTAMP})

        _update_in_transaction(transaction)
        print(f"Successfully added enrichment data to turn '{turn_id}'.")

    except Exception as e:
        print(f"ERROR: Failed to update turn with enrichment for conv {conversation_id}, turn {turn_id}: {e}")