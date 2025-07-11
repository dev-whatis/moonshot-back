"""
(recommendation_service.py) Contains the long-running business logic for the
recommendation generation process. This is designed to be run as a background task.
This service now contains a universal turn processor for any conversational turn.
"""
import datetime
from typing import List, Dict, Any

# Import services, handlers, and schemas
from app.services import llm_calls, search_functions, logging_service
from app.services.parsing_service import extract_product_names
from app.schemas import TurnRequest

# Import dependent services for fetching history
from google.cloud import firestore
from google.genai import types as genai_types

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
        ### **System Prompt: The Decisive Expert**

        You are The Decisive Expert. Your sole purpose is to help the user make a final purchasing decision by providing intelligent, authoritative follow-up answers.

        **1. Core Principle: Be the Decision Engine**
        Your job is not to list options; it is to forge a final, confident recommendation or answer. Synthesize all available information—the user's needs, real-world reviews, and the existing conversation—into a clear path forward. Make a gut-driven call to get the user to a choice or conclusion.

        **2. The Mandate for Context-Aware Searching**
        Your primary value comes from analyzing fresh, real-world information tailored to the user's specific constraints. You must use the `web_search` tool to gather the data needed to make an expert recommendation.

        *   **Rule #1 (CRITICAL - The Context Rule):** You **must** integrate the user's explicit constraints (like price, use case, etc.) and the [Current Year - {mtyr}] into your search queries.
        *   **Rule #2 (Search Concepts, Not Specific Products):** Unless the user explicitly asks you to look up a specific product by name, you **must not** search for it directly.
        *   **Rule #3 (Synthesize and Connect):** It is your job to process the information from your context-aware searches. You must analyze the results, identify the top contenders yourself, and draw connections that the user might have missed.
        *   **Rule #4 (Search Limit):** You can include a maximum of 3 search queries.

        **3. Your Role and Response Logic**
        You will always enter a conversation after an initial recommendation has been made by a different system. That initial turn will always use a specific format:

        ---Begin Markdown---
        ✨ The One to Actually Buy:
        [Product Name]

        🤔 The Alternatives
        [Alternative Product 1 Name]
        **Why it's not the winner:** [Reason]
        ---End Markdown---

        **Your primary directive is to recognize this structure as a signal that the initial conversation turn is over.**

        Your job as the follow-up expert begins now.

        *  **CRITICAL RULE: Discern the User's Intent. The ✨ The One to Actually Buy / 🤔 The Alternatives format is a powerful tool specifically for product discovery. Your primary task is to avoid using it for direct follow-ups about an already recommended product.
            However, you should use the discovery format if the user's follow-up query is about exploring new products or alternatives. In that case, you can use the format to introduce new recommendations.

        *   **YOUR GOAL:** Demonstrate your expertise through adaptability. Analyze the user's new, follow-up query and **invent a custom structure** that best answers their specific question. Let the function of their query dictate the form of your response. Be direct, clear, custom-tailored, and most importantly, decisive.

        **4. Final Machine-Readable Block Logic**
        The purpose of this block is to capture **newly introduced recommendations only**. It must appear at the absolute end of your response, but *only* if the conditions below are met.

        *   **Rule #1 (The Novelty Rule - CRITICAL):** This list must *only* contain products you are recommending for the *first time* in this conversation. If your response is a follow-up on a product that has already been discussed (e.g., a deep-dive or comparison), that product **must not** appear in this list.
        *   **Rule #2 (The Omission Rule):** If you are not introducing any *new* products in your current response, you **MUST OMIT THIS ENTIRE SECTION**. Do not print the `### RECOMMENDATIONS` header or an empty list.
        *   **Rule #3 (Strict Formatting):** When you *do* include this section, every item must be an exact, searchable product (e.g., `Brand Name Model Name/Number`). Do not list vague categories.

        **(Begin exact format if Rule #1 and #2 are met)**
        ### RECOMMENDATIONS
        - [Brand Name] [Model Name/Number]
        - [Brand Name] [Model Name/Number]
        **(End exact format)**
        """
    current_year = datetime.datetime.now().year
    system_prompt = system_prompt.replace("{mtyr}", str(current_year))

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
    *** This version is corrected for robust function call handling. ***
    """
    print(f"User {user_id} | Processing Follow-up Turn | ConvID: {conversation_id}, TurnID: {turn_id}")

    # 1. Fetch conversation context from Firestore (This part is correct)
    firestore_client = firestore.Client()
    turns_ref = firestore_client.collection("histories").document(conversation_id).collection("turns")
    all_turns_query = turns_ref.order_by("turnIndex", direction=firestore.Query.ASCENDING).stream()
    all_turns_data = [turn.to_dict() for turn in all_turns_query]

    if not all_turns_data:
        raise ValueError("Cannot process follow-up: No turns found for this conversation.")

    initial_turn = all_turns_data[0]
    previous_followup_turns = all_turns_data[1:-1]

    # 2. Build the LLM history (This part is correct)
    llm_history = _build_llm_history(
        initial_user_query=initial_turn.get("userQuery", ""),
        initial_model_response=initial_turn.get("modelResponse", ""),
        previous_turns=previous_followup_turns,
        new_user_query=full_request.user_query
    )

    # 3. First call to the model
    response = llm_calls.run_chat_turn(
        history=llm_history,
        tools=[llm_calls.WEB_SEARCH_TOOL_DECLARATION]
    )
    
    # *** THE FIX: Use the top-level `response.function_calls` accessor ***
    # This is a list, so we check if it's populated.
    if response.function_calls:
        print(f"LLM requested {len(response.function_calls)} tool call(s).")
        
        # We'll just handle the first one for our use case.
        function_call = response.function_calls[0]
        
        if function_call.name == "web_search":
            # Execute the tool
            search_queries = function_call.args.get("search_queries", [])
            print(f"Executing web_search with queries: {search_queries}")
            tool_result_json_string = search_functions.execute_parallel_searches(search_queries)

            # Append the model's original response (which contains the function_call)
            llm_history.append(response.candidates[0].content)

            # Append the tool's result for the model to synthesize
            llm_history.append(
                 genai_types.Content(
                    role="function", # Using 'function' role is also a common convention
                    parts=[
                        genai_types.Part.from_function_response(
                            name="web_search",
                            response={"result": tool_result_json_string},
                        )
                    ]
                )
            )

            # Make the second LLM call with the new search context
            print("Making second LLM call with search results...")
            second_response = llm_calls.run_chat_turn(
                history=llm_history,
                tools=[llm_calls.WEB_SEARCH_TOOL_DECLARATION] # Pass tools again
            )
            # The final response should be pure text
            return second_response.text
        else:
            # Handle case where a different, unexpected tool is called
            return "I'm sorry, I tried to use a tool I don't recognize."

    else:
        # The model answered directly without needing to search
        print("LLM answered directly without a tool call.")
        # This is now the safe way to get the text, as we've confirmed no function call exists.
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
    
    # Step 2: Generate Fast Search Queries
    fast_search_strategy = llm_calls.generate_fast_search_queries(
        user_query=user_query,
        user_answers=user_answers_dict,
    )
    fast_search_queries = fast_search_strategy.get("searchQueries", [])

    # Step 3: Execute Fast Searches
    fast_search_results = search_functions.search_product_recommendations(fast_search_queries)

    # Step 4: Synthesize Final Recommendations
    final_recommendations = llm_calls.synthesize_fast_recommendations(
        user_query=user_query,
        user_answers=user_answers_dict,
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
        
        print(f"BACKGROUND JOB SUCCEEDED for Turn {turn_index}, ConvID: {conversation_id}")

    except Exception as e:
        error_message = f"An unexpected error occurred during turn processing: {e}"
        print(f"BACKGROUND JOB FAILED for Turn {turn_index}, ConvID: {conversation_id}. Reason: {error_message}")
        
        failure_payload = {"error": error_message}
        
        final_status = "failed" # Set status for failure case
        logging_service.update_turn_status(conversation_id, turn_id, final_status, failure_payload)

    finally:
        # This block will run after the try/except block, regardless of outcome.
        # We only care about updating the parent document for the very first turn.
        if turn_index == 0 and final_status in ["complete", "failed"]:
            logging_service.update_parent_conversation_status(
                conversation_id=conversation_id,
                initial_turn_status=final_status
            )