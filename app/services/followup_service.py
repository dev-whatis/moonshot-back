"""
(followup_service.py) Contains the business logic for the stateful
follow-up chat feature. Each function call represents a single,
self-contained, stateless chat turn.
"""
import json
from typing import List, Dict, Any

from google.cloud import firestore
from google.genai import types

# Import dependent services and schemas
from app.services import llm_calls, search_functions, logging_service

# Initialize a direct Firestore client to fetch conversation context
try:
    firestore_client = firestore.Client()
except Exception as e:
    firestore_client = None
    print(f"ERROR: followup_service failed to initialize its own Firestore client: {e}")

# --- Custom Exceptions for the router layer ---

class ConversationNotFound(Exception):
    """Raised when a specific conversation document is not found."""
    pass

class NotOwnerOfConversation(Exception):
    """Raised when a user tries to access a conversation they do not own."""
    pass


# --- Internal Helper Functions ---

def _get_conversation_context(conversation_id: str, user_id: str) -> Dict[str, Any]:
    """
    Fetches the full conversation document from Firestore and validates ownership.
    """
    if not firestore_client:
        raise Exception("Firestore client is not available in followup_service.")

    doc_ref = firestore_client.collection("histories").document(conversation_id)
    doc = doc_ref.get()

    if not doc.exists:
        raise ConversationNotFound(f"Conversation with ID '{conversation_id}' not found.")

    context = doc.to_dict()

    if context.get("userId") != user_id:
        raise NotOwnerOfConversation("User does not have permission to access this conversation.")

    return context


def _build_llm_history(context: Dict[str, Any], new_user_query: str) -> List[Dict[str, Any]]:
    """
    Constructs the complete conversation history in the format required by the Gemini API.
    """
    # The system prompt that guides the model's behavior for the follow-up chat.
    # In app/services/followup_service.py, inside the _build_llm_history function

    # The system prompt that guides the model's behavior for the follow-up chat.
    # This version incorporates the expert research strategies from the initial query generation.
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
        {"role": "user", "parts": [{"text": f"Original Request: {context.get('userQuery', 'N/A')}"}]},
        {"role": "model", "parts": [{"text": context.get('recommendations', 'N/A')}]},
    ]

    # Add any previous follow-up turns
    past_followups = context.get("followupHistory", [])
    for message in past_followups:
        # Convert the simple {'role': '...', 'content': '...'} format to the required one
        llm_history.append({
            "role": message.get("role"),
            "parts": [{"text": message.get("content")}]
        })

    # Finally, add the current user's query
    llm_history.append({"role": "user", "parts": [{"text": new_user_query}]})

    return llm_history


# --- Main Service Function ---

def handle_chat_turn(conversation_id: str, user_id: str, new_user_query: str) -> str:
    """
    Orchestrates a single, self-contained follow-up chat turn.

    1. Reads the full conversation context from Firestore.
    2. Prepares the history for the LLM.
    3. Calls the LLM, potentially using the web_search tool in a multi-step process.
    4. Persists the new turn back to Firestore.
    5. Returns the final, user-facing text response.
    """
    print(f"Follow-up turn started for user: {user_id}, conv_id: {conversation_id}")

    # Step 1: READ - Get the full conversation context
    context = _get_conversation_context(conversation_id, user_id)

    # Step 2: PREPARE - Build the complete history for the LLM
    llm_history = _build_llm_history(context, new_user_query)

    # Step 3: PROCESS - The LLM interaction loop
    # Initial call to the LLM with the prepared history and the search tool
    print("Making initial LLM call with search tool enabled...")
    response = llm_calls.run_chat_turn(
        history=llm_history,
        tools=[llm_calls.WEB_SEARCH_TOOL_DECLARATION]
    )

    final_model_response_text = ""
    candidate = response.candidates[0]

    # Check if the model decided to call the function
    if candidate.content.parts and candidate.content.parts[0].function_call:
        print("LLM requested a tool call to `web_search`.")
        function_call = candidate.content.parts[0].function_call

        # Execute the tool
        search_queries = function_call.args.get("search_queries", [])
        tool_result_json_string = search_functions.execute_parallel_searches(search_queries)

        # Append the model's request and the tool's result to the history
        llm_history.append(candidate.content) # Append the function_call part
        llm_history.append(
             types.Content(
                role="user", # In the tool-use flow, the tool response is from the 'user'
                parts=[
                    types.Part.from_function_response(
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
            tools=[llm_calls.WEB_SEARCH_TOOL_DECLARATION]
        )
        final_model_response_text = second_response.text

    else:
        # The model answered directly without needing to search
        print("LLM answered directly without a tool call.")
        final_model_response_text = response.text

    # Step 4: WRITE - Persist the new turn to Firestore
    if final_model_response_text:
        # Get the existing history to append to it
        current_followup_history = context.get("followupHistory", [])
        
        # Append the latest user query and the final model response
        current_followup_history.append({"role": "user", "content": new_user_query})
        current_followup_history.append({"role": "model", "content": final_model_response_text})

        # Update the document in Firestore
        logging_service.update_chat_history(conversation_id, current_followup_history)
        print(f"Successfully updated chat history for conv_id: {conversation_id}")
    else:
        print(f"WARNING: No final model response generated for conv_id: {conversation_id}. Not updating history.")
        # Return a generic error message if something went wrong
        return "I'm sorry, I encountered a problem and can't respond right now. Please try again later."


    # Step 5: RESPOND - Return the final text
    return final_model_response_text