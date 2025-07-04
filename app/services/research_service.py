"""
(research_service.py) Contains the long-running business logic for the
deep research feature. This is designed to be run as a background task.
"""

from google.cloud import firestore

# Import services, handlers, and schemas
from app.services import llm_calls, search_functions
from app.services.logging_service import (
    log_step,
    set_research_job_complete,
    set_research_job_failed
)
from app.schemas import DeepResearchRequest

# Initialize a direct Firestore client to fetch context
# This is safe as the main app's logging_service also initializes one at startup.
try:
    firestore_client = firestore.Client()
except Exception as e:
    firestore_client = None
    print(f"ERROR: research_service failed to initialize its own Firestore client: {e}")


def run_deep_research_flow(request: DeepResearchRequest, research_id: str, user_id: str):
    """
    The main, long-running function to generate a deep research report for a single product.
    This function orchestrates all steps from search to synthesis.

    On success, it updates the Firestore document in the 'research' collection.
    On failure, it updates the document with an error and 'failed' status.

    Args:
        request: The original request payload containing conversationId and productName.
        research_id: The unique ID generated for this specific research job.
        user_id: The ID of the user who initiated the request.
    """
    conv_id = request.conversation_id
    product_name = request.product_name
    print(f"BACKGROUND JOB STARTED for Deep Research. User: {user_id}, Research_ID: {research_id}, Product: '{product_name}'.")

    # This dictionary will be used for GCS logging at the end.
    research_log_payload = {
        "userId": user_id,
        "researchId": research_id,
        "conversationId": conv_id,
        "productName": product_name
    }

    try:
        if not firestore_client:
            raise Exception("Firestore client not available in research_service.")

        # === STEP DR0: FETCH CONTEXT ===
        print(f"User {user_id} | Step DR0 | Fetching original conversation context for Conv_ID: {conv_id}")
        history_doc_ref = firestore_client.collection("histories").document(conv_id)
        history_doc = history_doc_ref.get()

        if not history_doc.exists:
            raise FileNotFoundError(f"Original conversation history for ID '{conv_id}' not found.")

        history_data = history_doc.to_dict()
        user_query = history_data.get("userQuery")
        # For this to work, the original 'finalize' flow must save the user answers to the 'histories' doc.
        user_answers_dict = history_data.get("userAnswers", {})
        research_log_payload["userContext"] = {"userQuery": user_query, "userAnswers": user_answers_dict}


        # === STEP DR1: TARGETED SEARCH ===
        search_query = f'{product_name} reviews and rating'
        print(f"User {user_id} | Step DR1 | Performing Targeted Search for query: '{search_query}'")
        search_results_list = search_functions.search_product_recommendations(
            rec_search_terms=[search_query],
            max_results_per_term=20
        )
        search_results_for_product = search_results_list[0].get('results', []) if search_results_list else []
        research_log_payload["searchResults"] = search_results_for_product


        # === STEP DR2: EVIDENCE URL SELECTION ===
        print(f"User {user_id} | Step DR2 | Curating final evidence URLs...")
        selected_urls = llm_calls.select_deep_research_urls(
            product_name=product_name,
            search_results=search_results_for_product,
            user_query=user_query,
            user_answers=user_answers_dict
        )
        research_log_payload["selectedEvidenceUrls"] = selected_urls
        print(f"User {user_id} | Step DR2 | Selected {len(selected_urls)} URLs for deep analysis.")

        if not selected_urls:
            raise ValueError("No suitable URLs were selected for scraping. Cannot proceed.")


        # === STEP DR3: SCRAPE CONTENT ===
        print(f"User {user_id} | Step DR3 | Scraping content from {len(selected_urls)} sources...")
        scraped_contents = search_functions.scrape_recommendation_urls(selected_urls)


        # === STEP DR4: FINAL SYNTHESIS LLM ===
        print(f"User {user_id} | Step DR4 | Synthesizing final deep research report...")
        final_report = llm_calls.generate_deep_research_report(
            user_query=user_query,
            user_answers=user_answers_dict,
            product_name=product_name,
            scraped_contents=scraped_contents
        )
        research_log_payload["finalReport"] = final_report
        print(f"User {user_id} | Step DR4 | Generated final report for '{product_name}'.")

        # --- On Success ---
        # --- THIS CALL IS CHANGED ---
        # 1. Log the full successful trace to GCS, passing the conv_id as the parent.
        log_step(
            primary_id=research_id, 
            step_name="dr_synthesis_success", 
            step_data=research_log_payload,
            parent_conversation_id=conv_id
        )

        # 2. Update the Firestore document in the 'research' collection.
        final_result_payload = {"report": final_report}
        set_research_job_complete(research_id, final_result_payload)

        print(f"BACKGROUND JOB SUCCEEDED for Deep Research. Research_ID: {research_id}, Product: '{product_name}'")

    except Exception as e:
        # --- On Failure ---
        error_message = f"An unexpected error occurred during the deep research flow: {e}"
        print(f"BACKGROUND JOB FAILED for Deep Research. Research_ID: {research_id}. Reason: {error_message}")

        # 1. Add the error to the GCS log payload
        research_log_payload["error"] = str(e)
        
        # --- THIS CALL IS ALSO CHANGED ---
        log_step(
            primary_id=research_id,
            step_name="dr_synthesis_failure",
            step_data=research_log_payload,
            parent_conversation_id=conv_id
        )

        # 2. Update the Firestore document with the error and 'failed' status
        set_research_job_failed(research_id, error_message)