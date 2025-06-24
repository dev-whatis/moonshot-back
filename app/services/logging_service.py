"""
(logging_service.py) Handles writing conversation data to Firestore and GCS.
"""

import json
import datetime
from typing import Optional, Dict, Any
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
# Service Functions
# ==============================================================================

def log_step(conversation_id: Optional[str], step_name: str, step_data: Dict[str, Any]):
    """
    Logs the data for a single step of a conversation to GCS for debugging.
    This function will do nothing if CONVERSATION_ID_ENABLED is False or if
    no conversation_id is provided.

    Args:
        conversation_id: The unique ID for the entire conversation.
        step_name: The name of the file to be created (e.g., "01_start", "02_finalize").
        step_data: A dictionary containing the JSON-serializable data for this step.
    """
    if not CONVERSATION_ID_ENABLED or not conversation_id:
        print(f"INFO: GCS logging for step '{step_name}' skipped (disabled by config or no ID).")
        return

    if not gcs_bucket:
        print(f"Skipping log for conv_id {conversation_id} because GCS client is not initialized.")
        return

    try:
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        
        # Add metadata to the log payload
        step_data["_log_timestamp_utc"] = now_utc.isoformat()
        step_data["_conversation_id"] = conversation_id
        step_data["_step_name"] = step_name
        
        # Construct the partitioned GCS object path
        year, month, day = now_utc.strftime("%Y"), now_utc.strftime("%m"), now_utc.strftime("%d")
        gcs_path = f"traces/{year}/{month}/{day}/{conversation_id}/{step_name}.json"
        
        blob = gcs_bucket.blob(gcs_path)
        log_json = json.dumps(step_data, indent=2, ensure_ascii=False)
        blob.upload_from_string(log_json, content_type="application/json")
        
        print(f"Successfully saved GCS log for conv_id {conversation_id}, step {step_name}.")

    except Exception as e:
        print(f"ERROR: Failed to save GCS log for conv_id {conversation_id}, step {step_name}: {e}")

def create_history_document(conversation_id: Optional[str], initial_data: Dict[str, Any]):
    """
    Creates the initial user-facing history document in Firestore.
    This function will do nothing if CONVERSATION_ID_ENABLED is False or if
    no conversation_id is provided.
    """
    if not CONVERSATION_ID_ENABLED or not conversation_id:
        print("INFO: Firestore history creation skipped (disabled by config or no ID).")
        return

    if not firestore_client:
        print(f"Skipping Firestore create for conv_id {conversation_id}, client not initialized.")
        return
        
    try:
        doc_ref = firestore_client.collection("histories").document(conversation_id)
        # Add creation timestamp and conversation ID to the document
        initial_data["createdAt"] = firestore.SERVER_TIMESTAMP
        initial_data["conversationId"] = conversation_id
        doc_ref.set(initial_data, merge=True)
        print(f"Successfully UPSERTED initial history for conv_id {conversation_id} in Firestore.")
    except Exception as e:
        print(f"ERROR: Failed to CREATE history doc in Firestore for conv_id {conversation_id}: {e}")

def update_history_with_enrichment(conversation_id: Optional[str], enriched_products: list):
    """
    Updates an existing history document with enriched product data.
    This function will do nothing if CONVERSATION_ID_ENABLED is False or if
    no conversation_id is provided.
    """
    if not CONVERSATION_ID_ENABLED or not conversation_id:
        print("INFO: Firestore history update skipped (disabled by config or no ID).")
        return

    if not firestore_client:
        print(f"Skipping Firestore update for conv_id {conversation_id}, client not initialized.")
        return

    try:
        doc_ref = firestore_client.collection("histories").document(conversation_id)
        update_payload = {
            "enrichedProducts": enriched_products,
            "updatedAt": firestore.SERVER_TIMESTAMP
        }
        doc_ref.set(update_payload, merge=True)
        print(f"Successfully UPSERTED enrichment data for conv_id {conversation_id} in Firestore.")
    except Exception as e:
        print(f"ERROR: Failed to UPDATE history doc in Firestore for conv_id {conversation_id}: {e}")

def save_rejected_query(rejection_data: dict):
    """

    Saves a record of a rejected query to a dedicated location in GCS.
    This operates independently of the CONVERSATION_ID_ENABLED flag as it's for
    pre-conversation rejections.
    """
    if not gcs_bucket:
        print("Skipping rejection logging because GCS client is not initialized.")
        return

    try:
        rejection_id = rejection_data.get("rejectionId", "unknown-rejection-id")
        user_id = rejection_data.get("userId", "unknown-user")
        
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        year, month, day = now_utc.strftime("%Y"), now_utc.strftime("%m"), now_utc.strftime("%d")

        # Use a different top-level folder for rejected queries
        # The file name is now the step name for consistency.
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