"""
(recommendation_service.py) Contains the long-running business logic for the
recommendation generation process. This is designed to be run as a background task.
"""

# Import services, handlers, and schemas
from app.services import llm_calls, search_functions
from app.services.logging_service import log_step, set_job_complete, set_job_failed
# --- MODIFICATION: Import the new parsing function ---
from app.services.parsing_service import extract_product_names
from app.schemas import FinalizeRequest


def run_recommendation_flow(request: FinalizeRequest, user_id: str):
    """
    The main, long-running function to generate product recommendations.
    This function orchestrates all the steps from query generation to the final
    report, and is intended to be run in the background.

    On success, it updates the Firestore document with the final report and status.
    On failure, it updates the Firestore document with an error and 'failed' status.
    """
    conv_id = request.conversation_id
    print(f"BACKGROUND JOB STARTED for user: {user_id}, conv_id: {conv_id}")

    # This dictionary will be used for GCS logging at the end.
    finalize_log_payload = {}

    try:
        # The .dict() method on the Pydantic model correctly serializes it for logging and LLM calls
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
            rec_search_results=rec_search_results,
            rec_scraped_contents=rec_scraped_contents
        )
        finalize_log_payload["finalRecommendation"] = final_recommendations
        print(f"User {user_id} | Step 6 | Generated final recommendations")

        # --- MODIFICATION: Simplified post-processing step ---
        # Step 6.5: Post-process the markdown to extract the unified list of product names
        product_names = extract_product_names(final_recommendations)
        
        finalize_log_payload["extractedProductNames"] = product_names
        print(f"User {user_id} | Post-processing | Extracted {len(product_names)} product names.")
        # --- End of modification ---

        # --- On Success ---

        # 1. Log the full successful trace to GCS
        log_step(conv_id, "02_finalize", finalize_log_payload)

        # 2. Update the Firestore document with the results and 'complete' status
        # --- MODIFICATION: Payload no longer contains strategicAlternatives ---
        final_result_payload = {
            "recommendations": final_recommendations,
            "productNames": product_names,
        }
        set_job_complete(conv_id, final_result_payload)

        print(f"BACKGROUND JOB SUCCEEDED for user: {user_id}, conv_id: {conv_id}")

    except Exception as e:
        # --- On Failure ---
        error_message = f"An unexpected error occurred during the finalize process: {e}"
        print(f"BACKGROUND JOB FAILED for user: {user_id}, conv_id: {conv_id}. Reason: {error_message}")

        # 1. Add the error to the GCS log payload
        finalize_log_payload["error"] = str(e)
        log_step(conv_id, "02_finalize_failure", finalize_log_payload)

        # 2. Update the Firestore document with the error and 'failed' status
        set_job_failed(conv_id, error_message)