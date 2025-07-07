"""
(recommendation_service.py) Contains the long-running business logic for the
recommendation generation process. This is designed to be run as a background task.
"""

# Import services, handlers, and schemas
from app.services import llm_calls, search_functions
from app.services.logging_service import log_step, set_job_complete, set_job_failed
from app.services.parsing_service import extract_product_names
from app.schemas import FinalizeRequest


def run_fast_search_flow(request: FinalizeRequest, user_id: str):
    """
    The main, long-running function for the "Fast Search" recommendation flow.
    This version skips URL curation and scraping, relying on LLM synthesis from
    search snippets alone for speed and reduced cost.

    On success, it updates the Firestore document with the final report and status.
    On failure, it updates the Firestore document with an error and 'failed' status.
    """
    conv_id = request.conversation_id
    print(f"BACKGROUND JOB STARTED for user: {user_id}, conv_id: {conv_id}. Using FAST SEARCH flow.")

    # This dictionary will be used for GCS logging at the end.
    fast_search_log_payload = {
        "userId": user_id,
        "userQuery": request.user_query,
        "title": request.user_query,
        "isDeleted": False,
    }

    try:
        # Prepare initial data (same as the deep dive flow)
        user_answers_dict = [answer.model_dump(by_alias=True) for answer in request.user_answers]
        for answer in user_answers_dict:
            if answer.get("questionType") == "price":
                if answer.get("min") is None:
                    answer["min"] = "no minimum budget constraint"
                if answer.get("max") is None:
                    answer["max"] = "no maximum budget constraint"
        fast_search_log_payload["userAnswers"] = user_answers_dict
        user_query = request.user_query

        # === STEP R1: RECONNAISSANCE SEARCH ===
        print(f"User {user_id} | Step R1 (Fast) | Performing Reconnaissance Search for query: '{user_query}'")
        recon_search_results = search_functions.search_product_recommendations([user_query])
        fast_search_log_payload["reconSearchResults"] = recon_search_results

        # === STEP FS1: FAST SEARCH QUERY GENERATION LLM ===
        print(f"User {user_id} | Step FS1 | Generating Fast Search queries...")
        fast_search_strategy = llm_calls.generate_fast_search_queries(
            user_query=user_query,
            user_answers=user_answers_dict,
            recon_search_results=recon_search_results
        )
        fast_search_log_payload["fastSearchStrategy"] = fast_search_strategy
        fast_search_queries = fast_search_strategy.get("searchQueries", [])
        print(f"User {user_id} | Step FS1 | Strategy generated. New queries: {fast_search_queries}")

        # === STEP FS2: FAST SEARCH EXECUTION ===
        print(f"User {user_id} | Step FS2 | Performing {len(fast_search_queries)} Fast Searches...")
        fast_search_results = search_functions.search_product_recommendations(fast_search_queries)
        fast_search_log_payload["fastSearchResults"] = fast_search_results

        # === STEP FS3: FAST SYNTHESIZER LLM ===
        print(f"User {user_id} | Step FS3 | Synthesizing fast recommendations from snippets...")
        final_recommendations = llm_calls.synthesize_fast_recommendations(
            user_query=user_query,
            user_answers=user_answers_dict,
            recon_search_results=recon_search_results,
            fast_search_results=fast_search_results
        )
        fast_search_log_payload["finalRecommendation"] = final_recommendations
        print(f"User {user_id} | Step FS3 | Generated final recommendations report.")

        # === STEP FS4: POST-PROCESSING & FINALIZATION ===
        product_names = extract_product_names(final_recommendations)
        fast_search_log_payload["extractedProductNames"] = product_names
        print(f"User {user_id} | Post-processing (Fast) | Extracted {len(product_names)} product names.")

        # --- On Success ---
        # 1. Log the full successful trace to GCS (using a distinct step name)
        log_step(conv_id, "02_fast_search_finalize", fast_search_log_payload)

        # 2. Update the Firestore document with the results and 'complete' status
        final_result_payload = {
            "recommendations": final_recommendations,
            "productNames": product_names,
        }
        set_job_complete(conv_id, final_result_payload)

        print(f"BACKGROUND JOB SUCCEEDED (Fast Search) for user: {user_id}, conv_id: {conv_id}")

    except Exception as e:
        # --- On Failure ---
        error_message = f"An unexpected error occurred during the fast search flow: {e}"
        print(f"BACKGROUND JOB FAILED (Fast Search) for user: {user_id}, conv_id: {conv_id}. Reason: {error_message}")

        # 1. Add the error to the GCS log payload
        fast_search_log_payload["error"] = str(e)
        log_step(conv_id, "02_fast_search_failure", fast_search_log_payload)

        # 2. Update the Firestore document with the error and 'failed' status
        set_job_failed(conv_id, error_message)