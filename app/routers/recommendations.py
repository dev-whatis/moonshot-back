"""
(recommendations.py) Defines the API routes for the product recommendation flow.
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from concurrent.futures import ThreadPoolExecutor, as_completed

# Import services and handlers
from app.services import llm_calls, search_functions
from app.services.logging_service import log_step, create_history_document, save_rejected_query
from app.services.parsing_service import extract_product_names_by_category

# Import schemas (Pydantic models)
from app.schemas import (
    StartRequest,
    FinalizeRequest,
    StartResponse,
    RecommendationsResponse,
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


@router.post("/finalize", response_model=RecommendationsResponse)
async def finalize_recommendation(
    request: FinalizeRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user)
):
    """
    Finalizes the recommendation flow using the state provided by the client.
    On full success, logs the entire flow to GCS and creates a history document in Firestore.
    """
    conv_id = request.conversation_id
    print(f"Finalizing recommendation for user: {user_id}, conv_id: {conv_id}")
    
    finalize_log_payload = {}
    
    try:
        # The .dict() method on the new UserAnswer model correctly serializes it for logging and LLM calls
        user_answers_dict = [answer.model_dump(by_alias=True) for answer in request.user_answers]
        finalize_log_payload["userAnswers"] = user_answers_dict
        user_query = request.user_query

        # Step 4: Generate search queries for recommendations
        rec_search_terms = llm_calls.generate_search_queries(
            user_query=user_query, 
            user_answers=user_answers_dict
        )
        finalize_log_payload["recSearchTerms"] = rec_search_terms
        print(f"User {user_id} | Step 4 | Generated {len(rec_search_terms)} search queries")

        # Step 4.5: Search for product recommendations
        rec_search_results = search_functions.search_product_recommendations(rec_search_terms)

        # Step 5: Select best recommendation URLs
        rec_urls = llm_calls.select_recommendation_urls(
            user_query=user_query,
            user_answers=user_answers_dict,
            rec_search_results=rec_search_results
        )
        finalize_log_payload["selectedRecUrls"] = rec_urls
        print(f"User {user_id} | Step 5 | Selected {len(rec_urls)} recommendation sources")

        # Step 5.5: Scrape recommendation content
        rec_scraped_contents = search_functions.scrape_recommendation_urls(rec_urls)

        # Step 6: Generate final recommendations
        final_recommendations = llm_calls.generate_final_recommendations(
            user_query=user_query,
            user_answers=user_answers_dict,
            rec_scraped_contents=rec_scraped_contents
        )
        finalize_log_payload["finalRecommendation"] = final_recommendations
        print(f"User {user_id} | Step 6 | Generated final recommendations")
        
        # Step 6.5: Post-process the markdown to extract product names by category
        parsed_products = extract_product_names_by_category(final_recommendations)
        product_names = parsed_products.get("productNames", [])
        strategic_alternatives = parsed_products.get("strategicAlternatives", [])
        
        finalize_log_payload["extractedProductNames"] = product_names
        finalize_log_payload["extractedStrategicAlternatives"] = strategic_alternatives
        print(f"User {user_id} | Post-processing | Extracted {len(product_names)} top products and {len(strategic_alternatives)} alternatives.")

        # --- LOGGING ON SUCCESS ---
        background_tasks.add_task(log_step, conv_id, "02_finalize", finalize_log_payload)
        
        initial_history_payload = {
            "userId": user_id,
            "userQuery": user_query,
            "finalRecommendation": final_recommendations,
            "productNames": product_names,
            "strategicAlternatives": strategic_alternatives,
        }
        background_tasks.add_task(create_history_document, conv_id, initial_history_payload)
        # --- END LOGGING ---

        return {
            "recommendations": final_recommendations,
            "productNames": product_names,
            "strategicAlternatives": strategic_alternatives
        }

    except Exception as e:
        print(f"ERROR in /finalize for user {user_id}, conv_id: {conv_id}: {e}")
        finalize_log_payload["error"] = str(e)
        background_tasks.add_task(log_step, conv_id, "02_finalize_failure", finalize_log_payload)

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred during the finalize process: {e}"
        )