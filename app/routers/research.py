"""
(research.py) Defines the API routes for the Deep Research feature.
"""

import uuid # Import uuid to generate unique IDs
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks

# Import services and schemas
from app.services import research_service
from app.services.logging_service import create_research_job_document
from app.schemas import (
    DeepResearchRequest,
    DeepResearchResponse,
    StatusResponse,
    DeepResearchResultResponse
)

# Import the dependency for authentication
from app.middleware.auth import get_current_user

# Import a direct Firestore client for reading status/results
from google.cloud import firestore
try:
    firestore_client = firestore.Client()
except Exception as e:
    firestore_client = None
    print(f"ERROR: research.py router failed to initialize its own Firestore client: {e}")


# ==============================================================================
# Router Setup
# ==============================================================================

router = APIRouter(
    prefix="/api/research",
    tags=["Research"]
)

# ==============================================================================
# API Endpoints
# ==============================================================================

@router.post(
    "",
    response_model=DeepResearchResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start a new Deep Research job"
)
async def start_deep_research(
    request: DeepResearchRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user)
):
    """
    Accepts a product name and conversation ID to start a deep research analysis
    as a background job. This endpoint returns immediately with a unique `researchId`
    to be used for polling.
    """
    conv_id = request.conversation_id
    # --- THIS IS THE KEY CHANGE ---
    research_id = str(uuid.uuid4())
    
    print(f"Deep Research job accepted. User: {user_id}, Conv_ID: {conv_id}, New Research_ID: {research_id}, Product: '{request.product_name}'.")
    
    # Optional: Verify user owns the conversation ID before proceeding
    if firestore_client:
        history_doc_ref = firestore_client.collection("histories").document(conv_id)
        history_doc = history_doc_ref.get()
        if not history_doc.exists or history_doc.to_dict().get("userId") != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User does not have permission to start research for this conversation."
            )

    # 1. Create the initial document in Firestore to track the job's state.
    initial_job_payload = {
        "userId": user_id,
        "conversationId": conv_id, # Store the parent conversation ID
        "productName": request.product_name
    }
    create_research_job_document(research_id, initial_job_payload)

    # 2. Schedule the long-running task to execute in the background.
    background_tasks.add_task(research_service.run_deep_research_flow, request, research_id, user_id)

    # 3. Return immediately to the client with the new unique ID.
    return {"research_id": research_id}


@router.get(
    "/status/{research_id}",
    response_model=StatusResponse,
    summary="Get the status of a Deep Research job"
)
async def get_research_job_status(
    research_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Poll this endpoint with the unique research_id to get the job's status.
    """
    try:
        if not firestore_client:
            raise HTTPException(status_code=503, detail="Database service not available.")

        doc_ref = firestore_client.collection("research").document(research_id)
        doc = doc_ref.get()

        if not doc.exists:
            raise HTTPException(status_code=404, detail="Research job not found.")

        # Ensure the user requesting status is the one who created the job
        if doc.to_dict().get("userId") != user_id:
             raise HTTPException(status_code=403, detail="Forbidden")

        return {"status": doc.to_dict().get("status", "unknown")}

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        print(f"ERROR fetching research status for research_id {research_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve job status.")


@router.get(
    "/result/{research_id}",
    response_model=DeepResearchResultResponse,
    summary="Get the result of a completed Deep Research job"
)
async def get_research_job_result(
    research_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Fetch the final report of a completed deep research job using its unique ID.
    """
    try:
        if not firestore_client:
            raise HTTPException(status_code=503, detail="Database service not available.")

        doc_ref = firestore_client.collection("research").document(research_id)
        doc = doc_ref.get()

        if not doc.exists:
            raise HTTPException(status_code=404, detail="Research job not found.")

        data = doc.to_dict()

        if data.get("userId") != user_id:
            raise HTTPException(status_code=403, detail="Forbidden")

        if data.get("status") != "complete":
            raise HTTPException(status_code=422, detail=f"Job status is '{data.get('status')}'. Result is not ready.")

        return {
            "report": data.get("report", "Report not found in completed job."),
        }

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        print(f"ERROR fetching research result for research_id {research_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve job result.")