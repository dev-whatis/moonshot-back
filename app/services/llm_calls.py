"""
(llm_calls.py) Handles all Gemini interactions via stateless function calls.
Each function is self-contained and does not rely on chat history.
"""
import json
import datetime
from google import genai
from google.genai import types
from typing import List, Dict, Any

from app.config import (
    GEMINI_API_KEY, HIGH_MODEL_NAME, MID_MODEL_NAME, LOW_MODEL_NAME, DEFAULT_TEMPERATURE, THINKING_BUDGET
)
from app.prompts import (
    STEP0_GUARDRAIL_PROMPT,
    STEP3A_BUDGET_PROMPT,
    STEP3B_DIAGNOSTIC_QUESTIONS_PROMPT,
    STEP_DR1_URL_SELECTOR_PROMPT,
    STEP_DR2_SYNTHESIS_PROMPT,
    STEP_FS1_FAST_SEARCH_QUERY_GENERATOR_PROMPT,
    STEP_FS2_FAST_SEARCH_SYNTHESIZER_PROMPT,
)
from app.schemas import (
    GUARDRAIL_RESPONSE_SCHEMA,
    BUDGET_QUESTION_SCHEMA,
    DIAGNOSTIC_QUESTIONS_SCHEMA,
    DEEP_RESEARCH_URL_SELECTION_SCHEMA,
    FAST_SEARCH_QUERIES_SCHEMA,
)

# ==============================================================================
# Internal Helper Function
# ==============================================================================

def _make_stateless_call_json(model_name: str, prompt: str, schema: Dict, use_thinking: bool = False) -> Dict:
    """
    A private helper to make a stateless Gemini call expecting a JSON response.
    Initializes the client, makes the call, and parses the JSON response.
    """
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
            temperature=DEFAULT_TEMPERATURE
        )
        if use_thinking:
            config.thinking_config = types.ThinkingConfig(thinking_budget=THINKING_BUDGET)

        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=config
        )
        
        return json.loads(response.text)
    except Exception as e:
        # Propagate exception to be handled by the calling service
        print(f"ERROR: Stateless call to model '{model_name}' failed: {e}")
        raise

# ==============================================================================
# Recommendation Flow Functions (Stateless)
# ==============================================================================

def run_query_guardrail(user_query: str) -> dict:
    """
    Step 0: A stateless, one-shot call to classify the user's intent.
    This acts as a bouncer before a full conversation session is created.
    """
    try:
        prompt = STEP0_GUARDRAIL_PROMPT.format(user_query=user_query)
        # Use the dedicated helper for this specific call pattern
        return _make_stateless_call_json(LOW_MODEL_NAME, prompt, GUARDRAIL_RESPONSE_SCHEMA)
    except Exception as e:
        print(f"ERROR: Guardrail check failed with exception: {e}")
        # In case of an API error, default to rejecting the query for safety.
        return {
            "is_product_request": False,
            "reason": "Could not process the request due to an internal error."
        }

def generate_budget_question(user_query: str) -> dict:
    """
    Step 3a: Generates a single budget question by analyzing the user's query.
    Uses a low-cost model for this simple, focused task.
    """
    prompt = STEP3A_BUDGET_PROMPT.format(user_query=user_query)
    return _make_stateless_call_json(LOW_MODEL_NAME, prompt, BUDGET_QUESTION_SCHEMA)


def generate_diagnostic_questions(user_query: str) -> list[dict]:
    """
    Step 3b: Generates 3-4 educational, non-budget diagnostic questions.
    Uses a high-cost model with thinking mode for this complex reasoning task.
    """
    prompt = STEP3B_DIAGNOSTIC_QUESTIONS_PROMPT.format(user_query=user_query)
    result = _make_stateless_call_json(LOW_MODEL_NAME, prompt, DIAGNOSTIC_QUESTIONS_SCHEMA)
    return result.get("questions", [])


def generate_fast_search_queries(
    user_query: str,
    user_answers: list[dict],
    recon_search_results: list[dict]
) -> dict:
    """
    Step FS1: Generates a portfolio of 4-6 concise, high-yield search queries
    for the Fast Search flow.
    """
    current_year = datetime.datetime.now().year
    prompt = STEP_FS1_FAST_SEARCH_QUERY_GENERATOR_PROMPT.format(
        user_query=user_query,
        user_answers_json=json.dumps(user_answers, indent=2),
        recon_search_results_json=json.dumps(recon_search_results, indent=2),
        current_year=current_year
    )
    # This task is complex enough to benefit from thinking mode.
    return _make_stateless_call_json(MID_MODEL_NAME, prompt, FAST_SEARCH_QUERIES_SCHEMA)


def synthesize_fast_recommendations(
    user_query: str,
    user_answers: list[dict],
    recon_search_results: list[dict],
    fast_search_results: list[dict]
) -> str:
    """
    Step FS2: Generates the final recommendation report for the Fast Search
    flow by synthesizing from search result snippets only.
    """
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = STEP_FS2_FAST_SEARCH_SYNTHESIZER_PROMPT.format(
            user_query=user_query,
            user_answers_json=json.dumps(user_answers, indent=2),
            recon_search_results_json=json.dumps(recon_search_results, indent=2),
            fast_search_results_json=json.dumps(fast_search_results, indent=2),
        )

        config = types.GenerateContentConfig(
            temperature=DEFAULT_TEMPERATURE,
            thinking_config=types.ThinkingConfig(thinking_budget=0)
        )

        response = client.models.generate_content(
            model=MID_MODEL_NAME, # Use a capable model for this synthesis task
            contents=prompt,
            config=config
        )
        # The prompt asks for raw Markdown, so we just return the text.
        return response.text

    except Exception as e:
        print(f"ERROR: Fast Search recommendation synthesis failed: {e}")
        raise

def select_deep_research_urls(
    product_name: str, 
    search_results: List[Dict],
    user_query: str,
    user_answers: List[Dict]
) -> List[Dict]:
    """
    Step DR1: Selects the best 3-5 expert review URLs for deep analysis.
    """
    prompt = STEP_DR1_URL_SELECTOR_PROMPT.format(
        user_query=user_query,
        user_answers_json=json.dumps(user_answers, indent=2),
        product_name=product_name,
        search_results_json=json.dumps(search_results, indent=2)
    )
    result = _make_stateless_call_json(MID_MODEL_NAME, prompt, DEEP_RESEARCH_URL_SELECTION_SCHEMA)
    return result.get("selected_urls", [])


def generate_deep_research_report(
    user_query: str,
    user_answers: List[Dict],
    product_name: str,
    scraped_contents: List[Dict]
) -> str:
    """
    Step DR2: Generates the final, comprehensive deep research report.
    """
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = STEP_DR2_SYNTHESIS_PROMPT.format(
            user_query=user_query,
            user_answers_json=json.dumps(user_answers, indent=2),
            product_name=product_name,
            scraped_contents_json=json.dumps(scraped_contents, indent=2)
        )
        
        config = types.GenerateContentConfig(
            temperature=DEFAULT_TEMPERATURE,
            thinking_config=types.ThinkingConfig(thinking_budget=0)
        )
        
        # Use a high-capability model for this complex synthesis task
        response = client.models.generate_content(
            model=MID_MODEL_NAME, 
            contents=prompt,
            config=config,
        )
        
        # The response should be raw Markdown, so we just return the text
        return response.text
            
    except Exception as e:
        print(f"ERROR: Deep research report generation failed for product '{product_name}': {e}")
        raise

# --- NEW CONSTANTS AND FUNCTIONS for the Follow-up Chat Feature ---

# Define the single tool's schema for the LLM.
# This tells the model what function it can call and what parameters to provide.
WEB_SEARCH_TOOL_DECLARATION = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="web_search",
            description=(
                "Performs a web search to find up-to-date information when the answer "
                "is not in the conversation history. Use this to find new product alternatives, "
                "verify specific, time-sensitive facts (like specs or availability of a latest model), "
                "or answer questions about technology concepts."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "search_queries": types.Schema(
                        type=types.Type.ARRAY,
                        items=types.Schema(type=types.Type.STRING),
                        description="A list of 1 to 3 concise, targeted search queries."
                    )
                },
                required=["search_queries"]
            )
        )
    ]
)


def run_chat_turn(history: List[Dict[str, Any]], tools: List[types.Tool]) -> types.GenerateContentResponse:
    """
    Runs a single turn of a multi-turn chat conversation using the stateless
    `generate_content` method, which is ideal for this application's architecture.

    This function takes a prepared history and a list of available tools, makes
    a single call to the Gemini API, and returns the entire response object for
    the calling service to inspect for tool calls.

    Args:
        history: A list of message objects representing the conversation history.
        tools: A list of `types.Tool` objects available to the model.

    Returns:
        The full `GenerateContentResponse` object from the Gemini API.
    """
    try:
        # 1. Create the low-level client.
        client = genai.Client(api_key=GEMINI_API_KEY)

        # 2. Create the generation configuration, which includes the tools.
        config = types.GenerateContentConfig(
            tools=tools,
            temperature=DEFAULT_TEMPERATURE,
            thinking_config=types.ThinkingConfig(thinking_budget=0)
        )

        # 3. Make the single, stateless call to the model.
        #    This pattern exactly matches the Gemini documentation for a single turn.
        response = client.models.generate_content(
            model=MID_MODEL_NAME,
            contents=history, # Pass the entire conversation history here
            config=config
        )

        # 4. Return the entire response object for inspection.
        return response

    except Exception as e:
        print(f"ERROR: Chat turn failed with exception: {e}")
        # Propagate the exception to be handled by the calling service
        raise