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
    GEMINI_API_KEY, HIGH_MODEL_NAME, LOW_MODEL_NAME, DEFAULT_TEMPERATURE, THINKING_BUDGET
)
from app.prompts import (
    STEP0_GUARDRAIL_PROMPT,
    STEP3_MCQ_GENERATION_PROMPT,
    STEP4_SEARCH_QUERY_PROMPT,
    STEP5_WEBSITE_SELECTION_PROMPT,
    STEP6_FINAL_RECOMMENDATIONS_PROMPT,
    IMAGE_CURATION_PROMPT,
    SHOPPING_CURATION_PROMPT
)
from app.schemas import (
    GUARDRAIL_RESPONSE_SCHEMA,
    MCQ_QUESTIONS_SCHEMA,
    REC_SEARCH_TERMS_SCHEMA,
    REC_SEARCH_URLS_SCHEMA,
    IMAGE_CURATION_SCHEMA,
    SHOPPING_CURATION_SCHEMA
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

def generate_mcq_questions(user_query: str) -> list[dict]:
    """
    Step 3: Generate MCQ questions using the LLM's internal knowledge (with thinking mode).
    """
    prompt = STEP3_MCQ_GENERATION_PROMPT.format(user_query=user_query)
    result = _make_stateless_call_json(HIGH_MODEL_NAME, prompt, MCQ_QUESTIONS_SCHEMA, use_thinking=True)
    return result.get("questions", [])

def generate_search_queries(user_query: str, user_answers: list[dict]) -> list[str]:
    """
    Step 4: Generate search queries based on user's initial query and MCQ answers.
    """
    current_year = datetime.datetime.now().year
    prompt = STEP4_SEARCH_QUERY_PROMPT.format(
        user_query=user_query,
        user_answers_json=json.dumps(user_answers, indent=2),
        current_year=current_year
    )
    result = _make_stateless_call_json(HIGH_MODEL_NAME, prompt, REC_SEARCH_TERMS_SCHEMA)
    return result.get("rec_search_terms", [])

def select_recommendation_urls(user_query: str, user_answers: list[dict], rec_search_results: list) -> list[dict]:
    """
    Step 5: Select 3-5 best URLs from recommendation search results based on user context.
    """
    current_year = datetime.datetime.now().year
    previous_year = current_year - 1
    prompt = STEP5_WEBSITE_SELECTION_PROMPT.format(
        user_query=user_query,
        user_answers_json=json.dumps(user_answers, indent=2),
        rec_search_results_json=json.dumps(rec_search_results, indent=2),
        current_year=current_year,
        previous_year=previous_year
    )
    result = _make_stateless_call_json(HIGH_MODEL_NAME, prompt, REC_SEARCH_URLS_SCHEMA)
    return result.get("rec_search_urls", [])

def generate_final_recommendations(user_query: str, user_answers: list[dict], rec_scraped_contents: list) -> str:
    """
    Step 6: Generate final product recommendations (with thinking mode).
    This call expects a raw text response and handles it directly.
    """
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = STEP6_FINAL_RECOMMENDATIONS_PROMPT.format(
            user_query=user_query,
            user_answers_json=json.dumps(user_answers, indent=2),
            rec_scraped_contents_json=json.dumps(rec_scraped_contents, indent=2)
        )
        
        config = types.GenerateContentConfig(
            temperature=DEFAULT_TEMPERATURE,
            thinking_config=types.ThinkingConfig(thinking_budget=THINKING_BUDGET)
        )
        
        response = client.models.generate_content(
            model=HIGH_MODEL_NAME,
            contents=prompt,
            config=config
        )
        raw_response_text = response.text

        # Fail-safe to extract content if the LLM returns a JSON object
        try:
            data = json.loads(raw_response_text)
            if isinstance(data, dict) and data:
                print("INFO: LLM returned JSON for final recommendation. Extracting content.")
                return str(list(data.values())[0])
            else:
                return raw_response_text
        except json.JSONDecodeError:
            print("INFO: LLM returned plain text for final recommendation as expected.")
            return raw_response_text
            
    except Exception as e:
        print(f"ERROR: Final recommendation generation failed: {e}")
        raise

# ==============================================================================
# Enrichment Flow Functions (Stateless)
# ==============================================================================

def curate_images(image_data: List[Dict[str, Any]]) -> Dict:
    """
    Makes a stateless call to Gemini to curate the best images for a list of products.
    """
    print(f"Sending image data for {len(image_data)} products to Gemini for curation.")
    prompt = IMAGE_CURATION_PROMPT.format(
        image_data_json=json.dumps(image_data, indent=2)
    )
    return _make_stateless_call_json(LOW_MODEL_NAME, prompt, IMAGE_CURATION_SCHEMA)


def curate_shopping_links(shopping_data: List[Dict[str, Any]]) -> Dict:
    """
    Makes a stateless call to Gemini to curate the best shopping links for a list of products.
    """
    print(f"Sending shopping data for {len(shopping_data)} products to Gemini for curation.")
    prompt = SHOPPING_CURATION_PROMPT.format(
        shopping_data_json=json.dumps(shopping_data, indent=2)
    )
    return _make_stateless_call_json(LOW_MODEL_NAME, prompt, SHOPPING_CURATION_SCHEMA)