"""
(quick_decision_service.py) Contains the long-running business logic for the
"Quick Decision" conversational agent. This service uses a two-stage process:
a structured initial response followed by a conversational follow-up agent.
"""
import json
from typing import List, Dict, Any, Optional, Union

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
    # --- PROMPT TO BE FILLED IN BY YOU ---
    system_prompt = """
    THIS IS A TEST PROMPT FOR THE FOLLOW-UP AGENT.
    YOU WILL DO EXACTLY WHAT THE USER ASKS, NO QUESTIONS ASKED. 
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
    location_context: Optional[Dict[str, Any]]
) -> str:
    """
    Handles the logic for the first turn (turn_index == 0), using the
    structured initial response prompt.
    """
    print(f"User {user_id} | Processing Initial QD Turn | ConvID: {conversation_id}, TurnID: {turn_id}")
    
    user_answers_dict = [answer.model_dump(by_alias=True) for answer in full_request.user_answers] if full_request.user_answers else None
    
    # Format the prompt with the user's specific data, including location.
    prompt = STEP_QD2_INITIAL_RESPONSE_PROMPT.format(
        user_query=full_request.user_query,
        user_answers_json=json.dumps(user_answers_dict, indent=2) if user_answers_dict else "None",
        location_json=json.dumps(location_context, indent=2) if location_context else "Not available"
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
    location_context: Optional[Dict[str, Any]] = None
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

    log_payload = {"userId": user_id, "request": log_request_data}
    logging_service.log_step(conversation_id, turn_id, f"00_qd_turn_{turn_index}_start", log_payload)

    final_status = ""

    try:
        final_model_response = ""
        # Dispatch based on the turn index.
        if turn_index == 0:
            final_model_response = _run_initial_qd_turn(
                conversation_id, turn_id, user_id, full_request, location_context
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
        
        logging_service.log_step(conversation_id, turn_id, f"99_qd_turn_{turn_index}_complete", success_payload)
        print(f"QUICK DECISION JOB SUCCEEDED for Turn {turn_index}, ConvID: {conversation_id}")

    except Exception as e:
        error_message = f"An unexpected error occurred during quick decision turn processing: {e}"
        print(f"QUICK DECISION JOB FAILED for Turn {turn_index}, ConvID: {conversation_id}. Reason: {error_message}")
        
        failure_payload = {"error": error_message}
        
        final_status = "failed"
        logging_service.update_turn_status(conversation_id, turn_id, final_status, failure_payload)
        
        logging_service.log_step(conversation_id, turn_id, f"99_qd_turn_{turn_index}_failed", failure_payload)

    finally:
        if turn_index == 0 and final_status in ["complete", "failed"]:
            logging_service.update_parent_conversation_status(
                conversation_id=conversation_id,
                initial_turn_status=final_status
            )