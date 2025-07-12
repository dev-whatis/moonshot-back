"""
(quick_decision_service.py) Contains the long-running business logic for the
"Quick Decision" conversational agent. This service uses a two-stage process:
a structured initial response followed by a conversational follow-up agent.
"""
import json
from typing import List, Dict, Any, Optional

# Import services, handlers, and schemas
from app.services import llm_calls, search_functions, logging_service
from app.schemas import QuickDecisionTurnRequest

# Import the new prompt for the initial turn
from app.prompts import STEP_QD2_INITIAL_RESPONSE_PROMPT

# Import dependencies for fetching history and handling tool calls
from google.cloud import firestore
from google.genai import types as genai_types

# ==============================================================================
# Internal Helper Functions
# ==============================================================================

def _build_qd_followup_history(
    initial_user_query: str,
    initial_model_response: str,
    previous_turns: List[Dict[str, Any]],
    new_user_query: str
) -> List[Dict[str, Any]]:
    """
    Constructs the complete conversation history for follow-up turns (turn > 0)
    in the Quick Decision flow.
    """
    # This is the system prompt that guides the model's behavior for follow-up chat.
    system_prompt = """
    ### **Your Persona: The Decisive Oracle (In Conversation)**

    You are a decisive, all-knowing guide. You have already made an initial decision for the user. Your authority comes from your access to real-world data and your ability to make connections the user cannot. You are now in a conversation. Your goal is to maintain your authority, handle challenges gracefully, and guide the user to action, all without losing your core persona.

    **Your Core Mission:** Analyze the user's follow-up message in the context of the entire conversation history. Uphold, elaborate on, or gracefully pivot from your original decision based on new information. Your tone remains confident, concise, and final.

    **What You Are NOT:**
    - You are NOT a chatbot that makes small talk.
    - You do NOT apologize or use phrases like "You're right" or "I was wrong."
    - You do NOT get into a debate. You state your reasoning and stand by it.

    ---

    ### **Your Method: The Conversational Playbook**

    Your first step is ALWAYS to review the entire conversation history to re-anchor yourself in your original decision and the logic behind it. Then, classify the user's latest message and execute the correct play from the list below.

    **Play #1: The Elaboration (The user asks "Why?")**
    - **Trigger:** The user questions your reasoning or asks for more detail.
    - **Your Goal:** Reinforce your authority by revealing deeper insight. This is an opportunity to impress.
    - **Your Action:**
        1. Re-examine your original reasoning from the conversation history.
        2. Use the `web_search` tool to find *even more* supporting data. Dig deeper. If you used weather, now check humidity, wind, or pollen. If you used reviews, find a specific quote.
        3. Deliver a more detailed, data-driven justification that proves your initial decision was more insightful than it first appeared.

    **Play #2: The Graceful Pivot (The user introduces a hard constraint)**
    - **Trigger:** The user provides a new, unavoidable fact that makes the original decision impossible (e.g., "I don't own a car," "That ingredient is expired," "My jeans have a hole in them").
    - **Your Goal:** Adapt to the new data without losing credibility. The original *logic* was correct, but a variable was missing.
    - **Your Action:**
        1. Acknowledge the new fact without apology. Start with "Understood." or "Noted."
        2. Identify the *core principle* of your original decision (e.g., "The goal was warmth," not "the goal was the blue jacket").
        3. Apply that same principle to the remaining options and issue a NEW, decisive command.

    **Play #3: The Firm Stance (The user states a mere preference)**
    - **Trigger:** The user expresses a subjective feeling or desire that contradicts your data-driven decision (e.g., "But I feel like pizza," "I don't want to go to the gym").
    - **Your Goal:** Uphold your data-driven decision over the user's whim.
    - **Your Action:**
        1. Briefly acknowledge their feeling ("I understand the preference.").
        2. Re-state the core, data-driven reason for your decision in one sentence.
        3. Re-affirm your original command. Example: "My recommendation stands for the optimal outcome."

    **Play #4: The Critical Question (The user asks a new, dependent question)**
    - **THIS IS THE ONLY TIME YOU ARE PERMITTED TO ASK A QUESTION.**
    - **Trigger:** The user accepts your decision and asks a follow-up question that requires new *internal context* (e.g., "Okay, I'll cook. What should I make?").
    - **Your Goal:** Gather the single piece of missing internal information needed to make the next decision.
    - **Your Action:**
        1. Your entire response must BE the question.
        2. Make it concise and, if possible, multiple-choice.
        3. Do not add any other text. You are waiting for their input to make the next move.
        - *Example Response:* "What do you have more of in your pantry: pasta, rice, or canned goods?"
        - *Example Response:* "What is your main goal for the workout: strength, cardio, or flexibility?"

    ---

    ### **How to Use the `web_search` Tool**

    You have access to the `web_search` tool to deepen your justifications or adapt your decisions.

    1.  **When to Use It:**
        - **For Elaboration (Play #1):** To find more granular data to support your original decision.
        - **For Pivoting (Play #2):** To find information about the user's *new* options.
    2.  **How to Use It:** The tool takes a list of up to 3 specific `search_queries`.
    3.  After the tool call, you will receive the search results and will be invoked again to formulate your final response based on the correct play.

    ---

    ### **Final Instruction**

    The user's entire conversation history is provided below. Analyze their latest message and execute your role with precision.
    """
    # --- END OF PROMPT ---

    llm_history = [
        # Start with the system prompt to set the context for the follow-up agent.
        {"role": "user", "parts": [{"text": system_prompt}]},
        {"role": "model", "parts": [{"text": "Understood. I'm ready to help. What's the user's question?"}]},
        # Add the original user query and the initial response to anchor the conversation.
        {"role": "user", "parts": [{"text": f"Original Request: {initial_user_query}"}]},
        {"role": "model", "parts": [{"text": initial_model_response}]},
    ]

    # Add any intermediate follow-up turns.
    for turn in previous_turns:
        llm_history.append({"role": "user", "parts": [{"text": turn.get("userQuery", "")}]})
        llm_history.append({"role": "model", "parts": [{"text": turn.get("modelResponse", "")}]})

    # Finally, add the current user's query.
    llm_history.append({"role": "user", "parts": [{"text": new_user_query}]})

    return llm_history

def _run_agentic_loop(history: List[Dict[str, Any]]) -> str:
    """
    A generic helper to run the agentic loop with tool-calling capabilities.
    """
    # First call to the model
    response = llm_calls.run_chat_turn(
        history=history,
        tools=[llm_calls.WEB_SEARCH_TOOL_DECLARATION]
    )
    
    if response.function_calls:
        print(f"QD Agent requested a tool call: {response.function_calls[0].name}")
        function_call = response.function_calls[0]
        
        if function_call.name == "web_search":
            search_queries = function_call.args.get("search_queries", [])
            print(f"Executing web_search for QD agent with queries: {search_queries}")
            tool_result_json_string = search_functions.execute_parallel_searches(search_queries)

            # Append the model's request and the tool's result to the history.
            history.append(response.candidates[0].content)
            history.append(
                 genai_types.Content(
                    role="function",
                    parts=[
                        genai_types.Part.from_function_response(
                            name="web_search",
                            response={"result": tool_result_json_string},
                        )
                    ]
                )
            )

            # Make the second LLM call with the new search context.
            print("Making second LLM call for QD agent with search results...")
            second_response = llm_calls.run_chat_turn(history=history, tools=[])
            return second_response.text
        else:
            return "I'm sorry, I tried to use a tool I don't recognize."
    else:
        # The model answered directly without needing to search.
        print("QD Agent answered directly without a tool call.")
        return response.text

def _run_initial_qd_turn(
    conversation_id: str,
    turn_id: str,
    user_id: str,
    full_request: QuickDecisionTurnRequest,
    location_context: Optional[Dict[str, Any]],
    user_local_time: Optional[str]
) -> str:
    """
    Handles the logic for the first turn (turn_index == 0), using the
    structured initial response prompt.
    """
    print(f"User {user_id} | Processing Initial QD Turn | ConvID: {conversation_id}, TurnID: {turn_id}")
    
    user_answers_dict = [answer.model_dump(by_alias=True) for answer in full_request.user_answers] if full_request.user_answers else None
    
    # Format the prompt with the user's specific data, including location and time.
    prompt = STEP_QD2_INITIAL_RESPONSE_PROMPT.format(
        user_query=full_request.user_query,
        user_answers_json=json.dumps(user_answers_dict, indent=2) if user_answers_dict else "None",
        location_json=json.dumps(location_context, indent=2) if location_context else "Not available",
        user_local_time_context=user_local_time if user_local_time else "Not provided"
    )

    # The "history" for this one-shot agentic call is just a single user message.
    initial_history = [{"role": "user", "parts": [{"text": prompt}]}]
    
    return _run_agentic_loop(initial_history)


def _run_followup_qd_turn(
    conversation_id: str,
    turn_id: str,
    user_id: str,
    full_request: QuickDecisionTurnRequest
) -> str:
    """
    Handles logic for all subsequent turns (turn_index > 0), using the
    conversational follow-up agent.
    """
    print(f"User {user_id} | Processing Follow-up QD Turn | ConvID: {conversation_id}, TurnID: {turn_id}")

    # 1. Fetch conversation context from Firestore.
    firestore_client = firestore.Client()
    turns_ref = firestore_client.collection("histories").document(conversation_id).collection("turns")
    all_turns_query = turns_ref.order_by("turnIndex", direction=firestore.Query.ASCENDING).stream()
    all_turns_data = [turn.to_dict() for turn in all_turns_query]

    if not all_turns_data:
        raise ValueError("Cannot process follow-up: No turns found for this conversation.")

    initial_turn = all_turns_data[0]
    previous_followup_turns = all_turns_data[1:-1]

    # 2. Build the LLM history for the conversational agent.
    llm_history = _build_qd_followup_history(
        initial_user_query=initial_turn.get("userQuery", ""),
        initial_model_response=initial_turn.get("modelResponse", ""),
        previous_turns=previous_followup_turns,
        new_user_query=full_request.user_query
    )
    
    return _run_agentic_loop(llm_history)


# ==============================================================================
# Main Universal Background Task
# ==============================================================================

def process_quick_decision_turn_background_job(
    conversation_id: str,
    turn_id: str,
    turn_index: int,
    user_id: str,
    full_request: QuickDecisionTurnRequest,
    location_context: Optional[Dict[str, Any]] = None,
    user_local_time: Optional[str] = None
):
    """
    The main, long-running function for processing a Quick Decision turn.
    This function is executed as a background task and dispatches to the
    appropriate handler based on the turn index.
    """
    # Add location to the log payload if it exists
    log_request_data = full_request.model_dump(by_alias=True)
    if location_context:
        log_request_data["_inferredLocation"] = location_context

    final_status = ""

    try:
        final_model_response = ""
        # Dispatch based on the turn index.
        if turn_index == 0:
            final_model_response = _run_initial_qd_turn(
                conversation_id, turn_id, user_id, full_request, location_context, user_local_time
            )
        else:
            final_model_response = _run_followup_qd_turn(
                conversation_id, turn_id, user_id, full_request
            )

        # On success, prepare the payload.
        success_payload = {
            "modelResponse": final_model_response,
            "productNames": [],
        }
        
        final_status = "complete"
        logging_service.update_turn_status(conversation_id, turn_id, final_status, success_payload)
        
        print(f"QUICK DECISION JOB SUCCEEDED for Turn {turn_index}, ConvID: {conversation_id}")

    except Exception as e:
        error_message = f"An unexpected error occurred during quick decision turn processing: {e}"
        print(f"QUICK DECISION JOB FAILED for Turn {turn_index}, ConvID: {conversation_id}. Reason: {error_message}")
        
        failure_payload = {"error": error_message}
        
        final_status = "failed"
        logging_service.update_turn_status(conversation_id, turn_id, final_status, failure_payload)

    finally:
        if turn_index == 0 and final_status in ["complete", "failed"]:
            logging_service.update_parent_conversation_status(
                conversation_id=conversation_id,
                initial_turn_status=final_status
            )