"""
(logging_service.py) Handles writing conversation data to Firestore and GCS.
"""

import json
import datetime
from google.cloud import firestore, storage

from app.config import GCP_PROJECT_ID, GCS_BUCKET_NAME

# ==============================================================================
# Client Initialization
# ==============================================================================

# Initialize clients once when the module is imported.
# They will be reused across function calls.
try:
    # When deployed, the service account associated with Cloud Run will be used automatically.
    # For local development, `gcloud auth application-default login` provides credentials.
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

def _save_trace_to_gcs(full_trace: dict):
    """
    Uploads the full conversation trace as a JSON file to Google Cloud Storage.
    """
    try:
        # Extract necessary fields for partitioning
        conversation_id = full_trace.get("conversationId", "unknown-id")
        user_id = full_trace.get("userId", "unknown-user")
        
        # Get the current time in UTC for partitioning
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        year = now_utc.strftime("%Y")
        month = now_utc.strftime("%m")
        day = now_utc.strftime("%d")

        # Construct the partitioned GCS object path
        # Example: traces/2023/10/28/user-A-123/abc-123.json
        gcs_path = f"traces/{year}/{month}/{day}/{user_id}/{conversation_id}.json"
        
        # Get a "blob" (the GCS object reference)
        blob = gcs_bucket.blob(gcs_path)
        
        # Serialize the trace dictionary to a JSON string and upload
        # `ensure_ascii=False` is good practice for handling non-English text
        trace_json = json.dumps(full_trace, indent=2, ensure_ascii=False)
        blob.upload_from_string(trace_json, content_type="application/json")
        
        print(f"Successfully saved trace for conv_id {conversation_id} to GCS at {gcs_path}")

    except Exception as e:
        # Log the error but don't crash the background task.
        print(f"ERROR: Failed to save trace to GCS for conv_id {full_trace.get('conversationId')}: {e}")

def _save_history_to_firestore(full_trace: dict):
    """
    Saves a small, user-facing chat history document to Firestore.
    """
    try:
        conversation_id = full_trace.get("conversationId")
        if not conversation_id:
            print("ERROR: Cannot save to Firestore without a conversationId.")
            return

        # Construct the small chat history document
        history_doc = {
            "userId": full_trace.get("userId"),
            "userQuery": full_trace.get("userQuery"),
            "finalRecommendation": full_trace.get("finalRecommendation"),
            "productNames": full_trace.get("extractedProductNames", []),
            "createdAt": firestore.SERVER_TIMESTAMP,  # Let Firestore set the timestamp
            "conversationId": conversation_id
        }

        # Set the document in the 'histories' collection with the conversationId as the document ID
        doc_ref = firestore_client.collection("histories").document(conversation_id)
        doc_ref.set(history_doc)
        
        print(f"Successfully saved history for conv_id {conversation_id} to Firestore.")

    except Exception as e:
        print(f"ERROR: Failed to save history to Firestore for conv_id {conversation_id}: {e}")

def save_rejected_query(rejection_data: dict):
    """
    Saves a record of a rejected query to a dedicated location in GCS.
    This is designed for stateless guardrail rejections and expects a 'rejectionId'.
    """
    if not gcs_bucket:
        print("Skipping rejection logging because GCS client is not initialized.")
        return

    try:
        # For stateless rejections, we expect a 'rejectionId' from the router.
        rejection_id = rejection_data.get("rejectionId", "unknown-rejection-id")
        user_id = rejection_data.get("userId", "unknown-user")
        
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        year = now_utc.strftime("%Y")
        month = now_utc.strftime("%m")
        day = now_utc.strftime("%d")

        # Use a different subfolder for rejected queries
        gcs_path = f"rejected_queries/{year}/{month}/{day}/{user_id}/{rejection_id}.json"
        
        blob = gcs_bucket.blob(gcs_path)
        
        # Add a server timestamp to the log
        rejection_data["rejectedAt"] = now_utc.isoformat()

        log_json = json.dumps(rejection_data, indent=2, ensure_ascii=False)
        blob.upload_from_string(log_json, content_type="application/json")
        
        print(f"Successfully saved rejected query log for rejection_id '{rejection_id}' to GCS at {gcs_path}")

    except Exception as e:
        rejection_id_for_error = rejection_data.get("rejectionId")
        print(f"ERROR: Failed to save rejected query log to GCS for rejection_id '{rejection_id_for_error}': {e}")


def save_completed_conversation(full_trace: dict):
    """
    The main public function to be called as a background task.
    Orchestrates saving the full trace to GCS and the history to Firestore.
    
    Args:
        full_trace (dict): A dictionary containing the entire conversation trace.
    """
    if not firestore_client or not gcs_bucket:
        print("Skipping logging because Google Cloud clients are not initialized.")
        return

    print(f"Saving completed conversation log for conv_id: {full_trace.get('conversationId')}")
    
    # Run the save operations
    _save_history_to_firestore(full_trace)
    _save_trace_to_gcs(full_trace)