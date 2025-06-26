"""
(recommendation_service.py) Contains the long-running business logic for the
recommendation generation process. This is designed to be run as a background task.
"""

# Import services, handlers, and schemas
from app.services import llm_calls, search_functions
from app.services.logging_service import log_step, set_job_complete, set_job_failed
from app.services.parsing_service import extract_product_names
from app.schemas import FinalizeRequest


def run_recon_and_deep_dive_flow(request: FinalizeRequest, user_id: str):
    """
    The main, long-running function to generate product recommendations using the
    "Recon & Deep-Dive" methodology. This function orchestrates all the steps
    from an initial search to a final, synthesized report.

    On success, it updates the Firestore document with the final report and status.
    On failure, it updates the Firestore document with an error and 'failed' status.
    """
    conv_id = request.conversation_id
    print(f"BACKGROUND JOB STARTED for user: {user_id}, conv_id: {conv_id}. Using Recon & Deep-Dive flow.")

    # This dictionary will be used for GCS logging at the end.
    finalize_log_payload = {}

    try:
        # Prepare initial data
        user_answers_dict = [answer.model_dump(by_alias=True) for answer in request.user_answers]
        for answer in user_answers_dict:
            if answer.get("questionType") == "price":
                if answer.get("min") is None:
                    answer["min"] = "no minimum budget constraint"
                if answer.get("max") is None:
                    answer["max"] = "no maximum budget constraint"
        finalize_log_payload["userAnswers"] = user_answers_dict
        user_query = request.user_query

        # === STEP R1: RECONNAISSANCE SEARCH ===
        print(f"User {user_id} | Step R1 | Performing Reconnaissance Search for query: '{user_query}'")
        recon_search_results = search_functions.search_product_recommendations([user_query])
        finalize_log_payload["reconSearchResults"] = recon_search_results

        # === STEP R2: RESEARCH STRATEGIST LLM ===
        print(f"User {user_id} | Step R2 | Generating Research Strategy...")
        research_strategy = llm_calls.generate_research_strategy(
            user_query=user_query,
            user_answers=user_answers_dict,
            recon_search_results=recon_search_results
        )
        finalize_log_payload["researchStrategy"] = research_strategy
        deep_dive_queries = research_strategy.get("deepDiveQueries", [])
        print(f"User {user_id} | Step R2 | Strategy generated. Identified {len(research_strategy.get('identifiedGaps', []))} gaps. New queries: {deep_dive_queries}")

        # === STEP R3: DEEP-DIVE SEARCH ===
        print(f"User {user_id} | Step R3 | Performing {len(deep_dive_queries)} Deep-Dive Searches...")
        deep_dive_search_results = search_functions.search_product_recommendations(deep_dive_queries)
        finalize_log_payload["deepDiveSearchResults"] = deep_dive_search_results

        # === STEP R4: EVIDENCE CURATOR LLM ===
        print(f"User {user_id} | Step R4 | Curating final evidence URLs...")
        curated_urls = llm_calls.select_final_evidence_urls(
            user_query=user_query,
            user_answers=user_answers_dict,
            research_strategy=research_strategy,
            recon_search_results=recon_search_results,
            deep_dive_search_results=deep_dive_search_results
        )
        finalize_log_payload["selectedEvidenceUrls"] = curated_urls
        print(f"User {user_id} | Step R4 | Selected {len(curated_urls)} URLs for final analysis.")

        # === STEP R5: SCRAPE CONTENT ===
        print(f"User {user_id} | Step R5 | Scraping content from {len(curated_urls)} sources...")
        scraped_contents = search_functions.scrape_recommendation_urls(curated_urls)
        # Note: We don't log the full scraped content to the main trace for brevity,
        # but it could be logged to a separate file if needed for debugging.

        # === STEP R6: FINAL SYNTHESIZER LLM ===
        print(f"User {user_id} | Step R6 | Synthesizing final recommendations...")
        final_recommendations = llm_calls.generate_final_recommendations(
            user_query=user_query,
            user_answers=user_answers_dict,
            recon_search_results=recon_search_results,
            deep_dive_search_results=deep_dive_search_results,
            rec_scraped_contents=scraped_contents
        )
        finalize_log_payload["finalRecommendation"] = final_recommendations
        print(f"User {user_id} | Step R6 | Generated final recommendations report.")

        # === STEP R7: POST-PROCESSING & FINALIZATION ===
        product_names = extract_product_names(final_recommendations)
        finalize_log_payload["extractedProductNames"] = product_names
        print(f"User {user_id} | Post-processing | Extracted {len(product_names)} product names.")

        # --- On Success ---
        # 1. Log the full successful trace to GCS
        log_step(conv_id, "02_finalize", finalize_log_payload)

        # 2. Update the Firestore document with the results and 'complete' status
        final_result_payload = {
            "recommendations": final_recommendations,
            "productNames": product_names,
        }
        set_job_complete(conv_id, final_result_payload)

        print(f"BACKGROUND JOB SUCCEEDED for user: {user_id}, conv_id: {conv_id}")

    except Exception as e:
        # --- On Failure ---
        error_message = f"An unexpected error occurred during the recommendation flow: {e}"
        print(f"BACKGROUND JOB FAILED for user: {user_id}, conv_id: {conv_id}. Reason: {error_message}")

        # 1. Add the error to the GCS log payload
        finalize_log_payload["error"] = str(e)
        log_step(conv_id, "02_finalize_failure", finalize_log_payload)

        # 2. Update the Firestore document with the error and 'failed' status
        set_job_failed(conv_id, error_message)