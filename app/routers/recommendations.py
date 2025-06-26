"""
(recommendations.py) Defines the API routes for the product recommendation flow.
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from concurrent.futures import ThreadPoolExecutor, as_completed
from google.cloud import firestore

# Import services and handlers
from app.services import llm_calls
from app.services.logging_service import log_step, create_history_document, save_rejected_query
# --- MODIFICATION: Import the new service and schemas ---
from app.services.recommendation_service import run_recon_and_deep_dive_flow
from app.schemas import (
    StartRequest,
    FinalizeRequest,
    StartResponse,
    FinalizeResponse,
    StatusResponse,
    ResultResponse,
    RejectionResponse
)

# Import the dependency for authentication
from app.middleware.auth import get_current_user

# ==============================================================================
# Router Setup
# ==============================================================================

router = APIRouter(
    prefix="/api/recommendations",
    tags=["Recommendations"]
)

# ==============================================================================
# API Endpoints
# ==============================================================================

@router.post(
    "/start",
    response_model=StartResponse,
    responses={
        422: {"model": RejectionResponse, "description": "Query is out-of-scope for the API"}
    }
)
async def start_recommendation(
    request: StartRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user)
):
    """
    Starts a new recommendation flow.
    1.  Runs a stateless guardrail check on the user's query.
    2.  If valid, it runs two parallel LLM calls:
        - One to generate a budget-specific question.
        - One to generate a set of educational, diagnostic questions.
    3.  Combines the results and returns them with a new conversationId.
    4.  If invalid, it logs the rejection and returns a 422 error.
    """
    print(f"User {user_id} | Step 0 | Performing guardrail check for query: '{request.user_query}'")
    
    # --- STEP 0: STATELESS GUARDRAIL (THE BOUNCER) ---
    guardrail_result = llm_calls.run_query_guardrail(request.user_query)
    
    if not guardrail_result.get("is_product_request"):
        print(f"User {user_id} | REJECTED | Reason: {guardrail_result.get('reason')}")
        
        rejection_id = str(uuid.uuid4())
        rejection_log = {
            "rejectionId": rejection_id,
            "userId": user_id,
            "userQuery": request.user_query,
            "reason": guardrail_result.get("reason")
        }
        save_rejected_query(rejection_log)
        
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "I can only help with physical product recommendations.",
                "reason": guardrail_result.get("reason", "The query is not a valid product request.")
            }
        )
    
    print(f"User {user_id} | PASSED | Guardrail check passed. Generating questions in parallel.")
    
    conversation_id = str(uuid.uuid4())
    
    try:
        # Step 3: Generate budget and diagnostic questions in parallel
        budget_question_result = None
        diagnostic_questions_result = None

        with ThreadPoolExecutor(max_workers=2) as executor:
            # Map a unique identifier to each function call
            future_to_task = {
                executor.submit(llm_calls.generate_budget_question, request.user_query): "budget",
                executor.submit(llm_calls.generate_diagnostic_questions, request.user_query): "diagnostic"
            }

            for future in as_completed(future_to_task):
                task_name = future_to_task[future]
                try:
                    result = future.result()
                    if task_name == "budget":
                        budget_question_result = result
                        print(f"User {user_id} | Step 3a | Generated budget question for conv_id: {conversation_id}")
                    elif task_name == "diagnostic":
                        diagnostic_questions_result = result
                        print(f"User {user_id} | Step 3b | Generated {len(result)} diagnostic questions for conv_id: {conversation_id}")
                except Exception as exc:
                    print(f"ERROR: Task '{task_name}' generated an exception: {exc}")
                    # Re-raise the exception to be caught by the outer try-except block
                    raise exc

        if not budget_question_result or not diagnostic_questions_result:
            raise Exception("Failed to generate one or both sets of questions.")

        # Assemble the final response payload
        response_payload = {
            "conversation_id": conversation_id,
            "budget_question": budget_question_result,
            "diagnostic_questions": diagnostic_questions_result
        }
        
        # Log the successful start step to GCS
        start_log_payload = {
            "userId": user_id,
            "userQuery": request.user_query,
            "guardrailResult": guardrail_result,
            "generatedQuestions": response_payload # Log the entire combined payload
        }
        background_tasks.add_task(log_step, conversation_id, "01_start", start_log_payload)
        
        return response_payload

    except Exception as e:
        print(f"ERROR in /start for user {user_id}: {e}")
        failure_log = {"userId": user_id, "userQuery": request.user_query, "error": str(e)}
        background_tasks.add_task(log_step, conversation_id, "01_start_failure", failure_log)
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred during the start process: {e}"
        )


# --- MODIFICATION START: The /finalize endpoint is now asynchronous ---

@router.post(
    "/finalize",
    response_model=FinalizeResponse,
    status_code=status.HTTP_202_ACCEPTED
)
async def finalize_recommendation(
    request: FinalizeRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user)
):
    """
    Accepts the user's answers and starts the recommendation generation as a
    background job. This endpoint returns immediately with a 202 Accepted
    response, providing the conversationId to be used for polling.
    """
    conv_id = request.conversation_id
    print(f"Finalize job accepted for user: {user_id}, conv_id: {conv_id}. Starting background task.")

    # 1. Create the initial document in Firestore to track the job's state.
    initial_history_payload = {
        "userId": user_id,
        "userQuery": request.user_query
    }
    create_history_document(conv_id, initial_history_payload)

    # 2. Schedule the long-running task to execute in the background.
    background_tasks.add_task(run_recon_and_deep_dive_flow, request, user_id)

    # 3. Return immediately to the client.
    return {"conversation_id": conv_id}


# --- NEW ENDPOINT: Poll for job status ---
@router.get(
    "/status/{conversation_id}",
    response_model=StatusResponse
)
async def get_job_status(
    conversation_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Poll this endpoint to get the current status of a recommendation job.
    """
    try:
        # We need a direct Firestore client instance here to read the status
        firestore_client = firestore.Client()
        doc_ref = firestore_client.collection("histories").document(conversation_id)
        doc = doc_ref.get()

        if not doc.exists:
            raise HTTPException(status_code=404, detail="Conversation not found.")

        # Ensure the user requesting status is the one who created the job
        if doc.to_dict().get("userId") != user_id:
             raise HTTPException(status_code=403, detail="Forbidden")

        return {"status": doc.to_dict().get("status", "unknown")}

    except HTTPException as http_exc:
        raise http_exc # Re-raise FastAPI's own exceptions
    except Exception as e:
        print(f"ERROR fetching status for conv_id {conversation_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve job status.")


# --- NEW ENDPOINT: Fetch the final results ---
@router.get(
    "/result/{conversation_id}",
    response_model=ResultResponse
)
async def get_job_result(
    conversation_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Fetch the final results of a completed recommendation job.
    """
    try:
        firestore_client = firestore.Client()
        doc_ref = firestore_client.collection("histories").document(conversation_id)
        doc = doc_ref.get()

        if not doc.exists:
            raise HTTPException(status_code=404, detail="Conversation not found.")

        data = doc.to_dict()

        # Ensure the user requesting the result is the one who created the job
        if data.get("userId") != user_id:
            raise HTTPException(status_code=403, detail="Forbidden")

        # Check if the job is actually complete
        if data.get("status") != "complete":
            raise HTTPException(status_code=422, detail=f"Job status is '{data.get('status')}'. Result is not ready.")

        # --- MODIFICATION: Construct the simpler final result ---
        # Construct and return the final result
        return {
            "recommendations": data.get("recommendations", ""),
            "productNames": data.get("productNames", []),
        }

    except HTTPException as http_exc:
        raise http_exc # Re-raise FastAPI's own exceptions
    except Exception as e:
        print(f"ERROR fetching result for conv_id {conversation_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve job result.")