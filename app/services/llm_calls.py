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
    STEP_R2_RESEARCH_STRATEGIST_PROMPT,
    STEP_R4_EVIDENCE_CURATOR_PROMPT,
    STEP6_FINAL_RECOMMENDATIONS_PROMPT,
    IMAGE_CURATION_PROMPT,
    SHOPPING_CURATION_PROMPT,
    STEP_DR1_URL_SELECTOR_PROMPT,
    STEP_DR2_SYNTHESIS_PROMPT,
)
from app.schemas import (
    GUARDRAIL_RESPONSE_SCHEMA,
    BUDGET_QUESTION_SCHEMA,
    DIAGNOSTIC_QUESTIONS_SCHEMA,
    RESEARCH_STRATEGY_SCHEMA,
    REC_SEARCH_URLS_SCHEMA,
    IMAGE_CURATION_SCHEMA,
    SHOPPING_CURATION_SCHEMA,
    DEEP_RESEARCH_URL_SELECTION_SCHEMA
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
    result = _make_stateless_call_json(LOW_MODEL_NAME, prompt, DIAGNOSTIC_QUESTIONS_SCHEMA, use_thinking=True)
    return result.get("questions", [])

def generate_research_strategy(user_query: str, user_answers: list[dict], recon_search_results: list[dict]) -> dict:
    """
    Step R2: Analyzes initial search results against user needs to generate a set of targeted search terms.
    """
    current_year = datetime.datetime.now().year
    prompt = STEP_R2_RESEARCH_STRATEGIST_PROMPT.format(
        user_query=user_query,
        user_answers_json=json.dumps(user_answers, indent=2),
        recon_search_results_json=json.dumps(recon_search_results, indent=2),
        current_year=current_year
    )
    return _make_stateless_call_json(LOW_MODEL_NAME, prompt, RESEARCH_STRATEGY_SCHEMA, use_thinking=True)


def select_final_evidence_urls(
    user_query: str,
    user_answers: list[dict],
    recon_search_results: list[dict],
    deep_dive_search_results: list[dict]
) -> list[dict]:
    """
    Step R4: Selects the best 3-5 URLs from all available search evidence.
    """
    current_year = datetime.datetime.now().year
    previous_year = current_year - 1
    prompt = STEP_R4_EVIDENCE_CURATOR_PROMPT.format(
        user_query=user_query,
        user_answers_json=json.dumps(user_answers, indent=2),
        recon_search_results_json=json.dumps(recon_search_results, indent=2),
        deep_dive_search_results_json=json.dumps(deep_dive_search_results, indent=2),
        current_year=current_year,
        previous_year=previous_year
    )
    result = _make_stateless_call_json(LOW_MODEL_NAME, prompt, REC_SEARCH_URLS_SCHEMA, use_thinking=True)
    return result.get("rec_search_urls", [])


def generate_final_recommendations(
    user_query: str,
    user_answers: list[dict],
    recon_search_results: list[dict],
    deep_dive_search_results: list[dict],
    rec_scraped_contents: list[dict]
) -> str:
    """
    Step R6: Generate final product recommendations (with thinking mode).
    The prompt is now informed by the research strategy.
    """
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = STEP6_FINAL_RECOMMENDATIONS_PROMPT.format(
            user_query=user_query,
            user_answers_json=json.dumps(user_answers, indent=2),
            recon_search_results_json=json.dumps(recon_search_results, indent=2),
            deep_dive_search_results_json=json.dumps(deep_dive_search_results, indent=2),
            rec_scraped_contents_json=json.dumps(rec_scraped_contents, indent=2)
        )
        
        config = types.GenerateContentConfig(
            temperature=DEFAULT_TEMPERATURE,
            thinking_config=types.ThinkingConfig(thinking_budget=THINKING_BUDGET)
        )
        
        response = client.models.generate_content(
            model=MID_MODEL_NAME,
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
    result = _make_stateless_call_json(LOW_MODEL_NAME, prompt, DEEP_RESEARCH_URL_SELECTION_SCHEMA, use_thinking=True)
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
            thinking_config=types.ThinkingConfig(thinking_budget=THINKING_BUDGET)
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