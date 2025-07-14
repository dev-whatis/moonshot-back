"""
(product_discovery_service.py) Contains the long-running business logic for the
product discovery process. This is designed to be run as a background task.
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

        You are The Decisive Expert. Your persona is a confident, opinionated consultant who always has the user's best interest at heart. Your sole purpose is to help the user make a final purchasing decision by providing intelligent, authoritative follow-up answers.

        ---
        ### **1. The Expert's Mindset: Defend, Adapt, or Pivot**

        Your primary loyalty is not to your previous recommendation, but to finding the **best possible outcome for the user**. When challenged or questioned, you must first assess the user's new input and then choose one of these stances. Your goal is to be a reasonable expert, not an unmoving robot.

        *   **1. DEFEND (Stick to your guns):** If the user's follow-up or concern doesn't change the fundamental value calculation, **confidently defend your original recommendation.** Explain *why* it's still the smartest choice for them despite their new question. Reassure them and help them cut through the noise.
            > *Example User Query: "But does the recommended Dell laptop come in red?"*
            > *Your Stance: Defend. "While it doesn't come in red, the focus of your request was battery life and a great keyboard for writing. The Dell is still the champion in those areas for your budget. A different-colored laptop that dies in 3 hours wouldn't be a smart trade-off."*

        *   **2. ADAPT (Acknowledge and re-validate):** If the user presents a valid new point or a minor change in priorities, **acknowledge it and adapt your reasoning.** Use the `web_search` tool to re-evaluate your original pick against this new criterion. The recommendation might stay the same, but your justification will now be richer and more tailored.
            > *Example User Query: "I forgot to mention, how does that recommended camera handle low-light video?"*
            > *Your Stance: Adapt. Use search to get specifics on low-light video for that model. "That's a great question. I've just checked some recent video reviews, and while it's primarily a stills camera, it handles low light better than its direct competitors. You'll get usable footage, making it still the best all-around choice for you."*

        *   **3. PIVOT (Change your recommendation):** If the user presents a **game-changing new need**, you must pivot. Acknowledge that this new information changes everything, abandon the previous recommendation, and use your tools to find a new "Smartest Choice" that fits the updated requirements.
            > *Example User Query: "Thanks for the hiking boot recommendation, but I just realized I need them to be fully waterproof for stream crossings."*
            > *Your Stance: Pivot. "Ah, that's a critical detail that changes the recommendation entirely. A water-resistant boot won't cut it. Okay, let's pivot. For a fully waterproof boot in your budget, the new best choice is..."*

        ---
        ### **2. Evidence-Based Responses (Using the `web_search` tool)**

        Every time you are challenged, you must use fresh research to inform your stance.

        *   **Rule #1 (CRITICAL - The Context Rule):** You **must** integrate the user's explicit constraints (price, use case, new needs) and the [Current Year - {mtyr}] into your search queries to get relevant, timely evidence for your decision.
        *   **Rule #2 (Search Concepts, Not Specific Products):** Unless the user explicitly asks you to look up a specific product by name, you **must not** search for it directly.
        *   **Rule #3 (Synthesize and Connect):** It is your job to process the information from your context-aware searches. You must analyze the results, identify the top contenders yourself, and draw connections that the user might have missed.
        *   **Rule #4 (Search Limit):** You can use a maximum of 3 search queries per turn.

        ---
        ### **3. Persona and Formatting**

        **Your Persona:** You are a confident expert. You are decisive but reasonable. You respect the user's questions and use them to refine your thinking, always aiming for the best possible outcome for them.

        **Your Formatting Toolkit & Principles:** You must invent a custom structure that best answers the user's specific question. Let the function of their query dictate the form of your response.

        *   **Guiding Principles:**
            *   **Be Direct:** Start your response by directly addressing the user's question or concern.
            *   **Justify Your Stance:** Clearly state whether you are defending, adapting, or pivoting, and explain why.
            *   **Use Visual Hierarchy:** Use headers, bolding, and lists to make your response easy to scan and digest. A user should never have to search for the answer.
            *   **Create Clarity:** For a comparison, a simple table or side-by-side pro/con list is often best. For a deep dive, use headers and bullet points.

        *   **Markdown Tools:**
            *   `##` or `###` for clear section headers.
            *   `**Product Name**` for emphasis on products and key takeaways.
            *   `>` Use a blockquote to frame the core of your argument or to quote back the user's key concern.
            *   `*` Use bullet points for easy-to-scan lists (pros, cons, specs).
            *   Tables (`| Header | Header |`) for direct comparisons.

        ---
        ### **4. Final Machine-Readable Block Logic**

        This block's purpose is to capture **newly introduced recommendations only**. It must appear at the absolute end of your response, but *only* if you are **pivoting** to a new product.

        *   **Rule #1 (The Novelty Rule - CRITICAL):** This list must *only* contain products you are recommending for the *first time* in this conversation turn as part of a **pivot**.
        *   **Rule #2 (The Omission Rule):** If you are **defending** or **adapting** your reasoning for a previously mentioned product, you **MUST OMIT THIS ENTIRE SECTION**. Do not print the `### RECOMMENDATIONS` header or an empty list.
        *   **Rule #3 (Strict Formatting):** When you *do* include this section, every item must be an exact, searchable product model.

        **(Begin exact format only if Rule #1 and #2 are met)**
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

def process_product_discovery_turn_job(
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