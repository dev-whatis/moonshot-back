"""
(recommendation_service.py) Contains the long-running business logic for the
recommendation generation process. This is designed to be run as a background task.
This service now contains a universal turn processor for any conversational turn.
"""
import json
from typing import List, Dict, Any

# Import services, handlers, and schemas
from app.services import llm_calls, search_functions, logging_service
from app.services.parsing_service import extract_product_names
from app.schemas import TurnRequest

# Import dependent services for fetching history
from google.cloud import firestore

# ==============================================================================
# Internal Helper Functions
# ==============================================================================

def _build_llm_history(
    initial_user_query: str,
    initial_model_response: str,
    previous_turns: List[Dict[str, Any]],
    new_user_query: str
) -> List[Dict[str, Any]]:
    """
    Constructs the complete conversation history in the format required by the Gemini API
    for subsequent (non-initial) turns.
    """
    # This is the system prompt that guides the model's behavior for follow-up chat.
    system_prompt = """
        You are an expert shopping assistant and a decisive advisor. You are in a follow-up conversation with a user for whom you have already provided an initial product recommendation report. Your entire purpose is to help the user make a confident final purchasing decision as quickly as possible.

        **Your Core Directives:**

        1.  **Zero Product Knowledge:** This is your most important rule. You must act as if you have **zero prior knowledge about specific products, models, prices, or specs.** Your only valid sources of product information are:
            a) The existing conversation history.
            b) The real-time results from the `web_search` tool.
            You can use your general knowledge for concepts (e.g., explaining what an OLED screen is), but **never** for product-specific details. If you don't know, you **must** search.

        2.  **Stay Laser-Focused (The 'Relevance Guardrail'):**
            *   Your world is defined by the original product category (e.g., laptops, headphones) and the products discussed.
            *   If the user asks about a completely different product category (e.g., "now find me a phone"), you **MUST** politely decline, state it's outside this conversation's scope, and suggest they start a new one.
            *   For any other off-topic, harmful, or nonsensical query, state "I can't answer that" and steer the conversation back to the product.

        3.  **Be a Decisive Engine, Not a Search Engine:**
            *   Your goal is not just to provide information, but to provide **clarity and a final verdict.** Frame your answers around the key trade-offs the user needs to consider to make a decision.

        **Your Process for Using the `web_search` Tool:**

        If you determine the answer is not in our conversation history, you **MUST** use the `web_search` tool. When you do, you must follow this expert thought process:

        # 1. Deconstruct the User's Question
        First, analyze the user's follow-up question. What is the core uncertainty they are trying to resolve?

        # 2. Formulate Internal Research Questions
        Based on your analysis, formulate the 1-3 most critical questions you would need to ask an expert to get a definitive answer.

        # 3. Generate 1-3 High-Yield Search Queries
        Finally, translate your internal research questions into a portfolio of 1 to 3 concise, pragmatic search queries. Your queries should be short, human-like, and may include modifiers like "reddit" or the current year to find fresh, real-world sentiment.

        After the `web_search` tool runs, you will receive the results. Your main task is to **synthesize these results into a single, decisive, conversational answer** that directly addresses the user's original follow-up question.

        ---
        **Final Response Formatting:**

        At the absolute end of your conversational response, you **MUST** include the following machine-readable section.

        ### **Rules for the RECOMMENDATIONS section:**
        1.  Only list product names if you are **newly recommending them as a viable alternative** in *this specific turn*.
        2.  **DO NOT** list products that have already been mentioned in the previous conversation history.
        3.  If your response is just a clarification about an existing product and you are not recommending any new alternatives, then the list under the heading **MUST be empty**.

        **(Begin exact format for the summary section)**
        ### RECOMMENDATIONS
        - [Brand Name] [Model Name/Number]
        - [Brand Name] [Model Name/Number]
        **(End exact format for the summary section)**
        """

    llm_history = [
        # Start with the system prompt to set the context
        {"role": "user", "parts": [{"text": system_prompt}]},
        {"role": "model", "parts": [{"text": "Understood. I'm ready to help. What's the user's question?"}]},
        # Add the original user query and the recommendation report
        {"role": "user", "parts": [{"text": f"Original Request: {initial_user_query}"}]},
        {"role": "model", "parts": [{"text": initial_model_response}]},
    ]

    # Add any intermediate follow-up turns
    for turn in previous_turns:
        llm_history.append({"role": "user", "parts": [{"text": turn.get("userQuery", "")}]})
        llm_history.append({"role": "model", "parts": [{"text": turn.get("modelResponse", "")}]})

    # Finally, add the current user's query
    llm_history.append({"role": "user", "parts": [{"text": new_user_query}]})

    return llm_history


def _run_followup_turn(
    conversation_id: str,
    turn_id: str,
    user_id: str,
    full_request: TurnRequest
) -> str:
    """
    Handles the logic for processing a follow-up turn (turn_index > 0).
    Fetches context, builds history, and runs the chat model.
    """
    print(f"User {user_id} | Processing Follow-up Turn | ConvID: {conversation_id}, TurnID: {turn_id}")

    # 1. Fetch the full conversation context from Firestore
    firestore_client = firestore.Client()
    turns_ref = firestore_client.collection("histories").document(conversation_id).collection("turns")
    
    # Fetch all turns to build the history
    all_turns_query = turns_ref.order_by("turnIndex", direction=firestore.Query.ASCENDING).stream()
    all_turns_data = [turn.to_dict() for turn in all_turns_query]

    if not all_turns_data:
        raise ValueError("Cannot process follow-up: No turns found for this conversation.")

    initial_turn = all_turns_data[0]
    # Previous turns are all turns between the first and the one before the current.
    # The current turn is not included as it's still being processed.
    previous_followup_turns = all_turns_data[1:-1] 

    # 2. Build the LLM history for the chat model
    llm_history = _build_llm_history(
        initial_user_query=initial_turn.get("userQuery", ""),
        initial_model_response=initial_turn.get("modelResponse", ""),
        previous_turns=previous_followup_turns,
        new_user_query=full_request.user_query
    )

    # 3. Call the LLM with the search tool
    # This logic is moved directly from the old `followup_service`
    response = llm_calls.run_chat_turn(
        history=llm_history,
        tools=[llm_calls.WEB_SEARCH_TOOL_DECLARATION]
    )

    candidate = response.candidates[0]
    if candidate.content.parts and candidate.content.parts[0].function_call:
        function_call = candidate.content.parts[0].function_call
        search_queries = function_call.args.get("search_queries", [])
        tool_result_json_string = search_functions.execute_parallel_searches(search_queries)

        llm_history.append(candidate.content) # Append the function_call
        llm_history.append(
             firestore.types.Content(
                role="user",
                parts=[
                    firestore.types.Part.from_function_response(
                        name="web_search",
                        response={"result": tool_result_json_string},
                    )
                ]
            )
        )
        
        second_response = llm_calls.run_chat_turn(
            history=llm_history,
            tools=[llm_calls.WEB_SEARCH_TOOL_DECLARATION]
        )
        return second_response.text
    else:
        return response.text


def _run_initial_turn(
    conversation_id: str,
    turn_id: str,
    user_id: str,
    full_request: TurnRequest
) -> str:
    """
    Handles the logic for processing the very first turn (turn_index == 0).
    Runs the "Fast Search" flow to generate the initial recommendation report.
    """
    print(f"User {user_id} | Processing Initial Turn | ConvID: {conversation_id}, TurnID: {turn_id}")
    
    user_answers_dict = [answer.model_dump(by_alias=True) for answer in full_request.user_answers]
    user_query = full_request.user_query

    # Step 1: Reconnaissance Search
    recon_search_results = search_functions.search_product_recommendations([user_query])
    
    # Step 2: Generate Fast Search Queries
    fast_search_strategy = llm_calls.generate_fast_search_queries(
        user_query=user_query,
        user_answers=user_answers_dict,
        recon_search_results=recon_search_results
    )
    fast_search_queries = fast_search_strategy.get("searchQueries", [])

    # Step 3: Execute Fast Searches
    fast_search_results = search_functions.search_product_recommendations(fast_search_queries)

    # Step 4: Synthesize Final Recommendations
    final_recommendations = llm_calls.synthesize_fast_recommendations(
        user_query=user_query,
        user_answers=user_answers_dict,
        recon_search_results=recon_search_results,
        fast_search_results=fast_search_results
    )
    return final_recommendations


# ==============================================================================
# Main Universal Background Task
# ==============================================================================

# In recommendation_service.py

def process_turn_background_job(
    conversation_id: str,
    turn_id: str,
    turn_index: int,
    user_id: str,
    full_request: TurnRequest
):
    """
    The main, universal, long-running function for processing any conversational turn.
    This function is executed as a background task.

    On success, it updates the Firestore turn document with the final report and 'complete' status.
    On failure, it updates the turn document with an error and 'failed' status.
    
    Crucially, if this is the first turn, it also updates the parent conversation
    document with the final status of this initial turn.
    """
    log_payload = {"userId": user_id, "request": full_request.model_dump(by_alias=True)}
    logging_service.log_step(conversation_id, turn_id, f"00_turn_{turn_index}_start", log_payload)

    final_status = "" # Variable to hold the final status

    try:
        final_model_response = ""
        if turn_index == 0:
            # Logic for the initial recommendation
            if not full_request.user_answers:
                raise ValueError("User answers are required for the initial turn.")
            final_model_response = _run_initial_turn(conversation_id, turn_id, user_id, full_request)
        else:
            # Logic for all subsequent, follow-up turns
            final_model_response = _run_followup_turn(conversation_id, turn_id, user_id, full_request)

        # Post-processing for any successful turn
        product_names = extract_product_names(final_model_response)
        
        success_payload = {
            "modelResponse": final_model_response,
            "productNames": product_names,
        }
        
        final_status = "complete" # Set status for success case
        logging_service.update_turn_status(conversation_id, turn_id, final_status, success_payload)
        
        logging_service.log_step(conversation_id, turn_id, f"99_turn_{turn_index}_complete", success_payload)
        print(f"BACKGROUND JOB SUCCEEDED for Turn {turn_index}, ConvID: {conversation_id}")

    except Exception as e:
        error_message = f"An unexpected error occurred during turn processing: {e}"
        print(f"BACKGROUND JOB FAILED for Turn {turn_index}, ConvID: {conversation_id}. Reason: {error_message}")
        
        failure_payload = {"error": error_message}
        
        final_status = "failed" # Set status for failure case
        logging_service.update_turn_status(conversation_id, turn_id, final_status, failure_payload)
        
        logging_service.log_step(conversation_id, turn_id, f"99_turn_{turn_index}_failed", failure_payload)

    finally:
        # This block will run after the try/except block, regardless of outcome.
        # We only care about updating the parent document for the very first turn.
        if turn_index == 0 and final_status in ["complete", "failed"]:
            logging_service.update_parent_conversation_status(
                conversation_id=conversation_id,
                initial_turn_status=final_status
            )