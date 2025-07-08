"""
(logging_service.py) Handles writing conversation data to Firestore and GCS.
This version supports the multi-turn conversational data model.
"""

import json
import datetime
import uuid
from typing import Optional, Dict, Any, Tuple
from google.cloud import firestore, storage

from app.config import GCP_PROJECT_ID, GCS_BUCKET_NAME, CONVERSATION_ID_ENABLED

# ==============================================================================
# Client Initialization
# ==============================================================================

# Initialize clients once when the module is imported.
try:
    firestore_client = firestore.Client(project=GCP_PROJECT_ID)
    storage_client = storage.Client(project=GCP_PROJECT_ID)
    gcs_bucket = storage_client.bucket(GCS_BUCKET_NAME)
    print("Successfully initialized Firestore and GCS clients.")
except Exception as e:
    firestore_client = None
    storage_client = None
    gcs_bucket = None
    print(f"ERROR: Failed to initialize Google Cloud clients: {e}")
    print("WARNING: Conversation logging will be disabled.")


# ==============================================================================
# GCS Logging Functions
# ==============================================================================

def log_step(
    conversation_id: Optional[str],
    turn_id: Optional[str],
    step_name: str,
    step_data: Dict[str, Any]
):
    """
    Logs the data for a single step of a conversation turn to GCS for debugging.

    Args:
        conversation_id: The unique ID for the conversation.
        turn_id: The unique ID for the specific turn within the conversation.
        step_name: The name of the file to be created (e.g., "01_start").
        step_data: A dictionary containing the JSON-serializable data for this step.
    """
    if not all([CONVERSATION_ID_ENABLED, conversation_id, turn_id]):
        print(f"INFO: GCS logging for step '{step_name}' skipped (disabled or missing IDs).")
        return

    if not gcs_bucket:
        print(f"Skipping log for conv {conversation_id}, turn {turn_id} because GCS client is not initialized.")
        return

    try:
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        
        # Add metadata to the log payload
        step_data["_log_timestamp_utc"] = now_utc.isoformat()
        step_data["_step_name"] = step_name
        step_data["_conversation_id"] = conversation_id
        step_data["_turn_id"] = turn_id
        
        # Construct the partitioned GCS object path with turn_id
        year, month, day = now_utc.strftime("%Y"), now_utc.strftime("%m"), now_utc.strftime("%d")
        gcs_path = f"traces/{year}/{month}/{day}/{conversation_id}/{turn_id}/{step_name}.json"
        
        blob = gcs_bucket.blob(gcs_path)
        log_json = json.dumps(step_data, indent=2, ensure_ascii=False)
        blob.upload_from_string(log_json, content_type="application/json")
        
        print(f"Successfully saved GCS log to: {gcs_path}")

    except Exception as e:
        print(f"ERROR: Failed to save GCS log for conv {conversation_id}, turn {turn_id}, step {step_name}: {e}")


def save_rejected_query(rejection_data: dict):
    """
    Saves a record of a rejected query to a dedicated location in GCS.
    (This function is pre-conversation and remains unchanged).
    """
    if not gcs_bucket:
        print("Skipping rejection logging because GCS client is not initialized.")
        return

    try:
        rejection_id = rejection_data.get("rejectionId", "unknown-rejection-id")
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        year, month, day = now_utc.strftime("%Y"), now_utc.strftime("%m"), now_utc.strftime("%d")
        gcs_path = f"traces/{year}/{month}/{day}/{rejection_id}/00_rejection.json"
        
        blob = gcs_bucket.blob(gcs_path)
        rejection_data["_log_timestamp_utc"] = now_utc.isoformat()
        rejection_data["_conversation_id"] = rejection_id
        rejection_data["_step_name"] = "00_rejection"
        log_json = json.dumps(rejection_data, indent=2, ensure_ascii=False)
        blob.upload_from_string(log_json, content_type="application/json")
        
        print(f"Successfully saved rejected query log for id '{rejection_id}' to GCS.")

    except Exception as e:
        rejection_id_for_error = rejection_data.get("rejectionId")
        print(f"ERROR: Failed to save rejected query log to GCS for id '{rejection_id_for_error}': {e}")


# ==============================================================================
# Firestore "Write Path" Functions
# ==============================================================================

@firestore.transactional
def _create_conversation_and_first_turn_transaction(
    transaction: firestore.Transaction,
    user_id: str,
    user_query: str
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
        "isDeleted": False
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


def create_conversation_and_first_turn(user_id: str, user_query: str) -> Tuple[str, str]:
    """
    Creates a new conversation with its first turn atomically.

    Returns:
        A tuple containing the new (conversation_id, turn_id).
    """
    if not firestore_client:
        raise Exception("Firestore client is not initialized. Cannot create conversation.")
    
    transaction = firestore_client.transaction()
    conv_id, turn_id = _create_conversation_and_first_turn_transaction(transaction, user_id, user_query)
    print(f"Successfully CREATED new conversation '{conv_id}' and first turn '{turn_id}'.")
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