"""
(llm_handler.py) Handles all Gemini interactions.
Includes a stateless guardrail function and a stateful class for conversations.
"""
import json
import datetime
from google import genai
from google.genai import types
from typing import List, Dict, Any

from app.config import GEMINI_API_KEY, MODEL_NAME, GUARDRAIL_MODEL_NAME, DEFAULT_TEMPERATURE, MAX_TOKENS, THINKING_BUDGET
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
# Stateless Guardrail Function (The Bouncer)
# ==============================================================================

def run_query_guardrail(user_query: str) -> dict:
    """
    Step 0: A stateless, one-shot call to classify the user's intent.
    This acts as a bouncer before a full conversation session is created.

    Args:
        user_query (str): The user's original query.

    Returns:
        dict: A dictionary with 'is_product_request' and 'reason'.
    """
    try:
        # Create a temporary, one-shot client for this stateless check
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        prompt = STEP0_GUARDRAIL_PROMPT.format(user_query=user_query)
        
        # Use the generate_content method for a single, non-chat call
        response = client.models.generate_content(
            model=GUARDRAIL_MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=GUARDRAIL_RESPONSE_SCHEMA,
                temperature=DEFAULT_TEMPERATURE
            )
        )
        
        return json.loads(response.text)
        
    except Exception as e:
        print(f"ERROR: Guardrail check failed with exception: {e}")
        # In case of an API error, default to rejecting the query for safety.
        return {
            "is_product_request": False,
            "reason": "Could not process the request due to an internal error."
        }


# ==============================================================================
# Stateful Conversation Handler Class
# ==============================================================================

class LLMHandler:
    def __init__(self):
        """
        Initializes the handler for a stateful conversation.
        This should only be instantiated AFTER the guardrail check has passed.
        """
        client = genai.Client(api_key=GEMINI_API_KEY)
        # This creates a persistent chat session for the conversation.
        self.chat = client.chats.create(
            model=MODEL_NAME,
            config=types.GenerateContentConfig(
                temperature=DEFAULT_TEMPERATURE,
                max_output_tokens=MAX_TOKENS
            )
        )
        if not self.chat:
             raise RuntimeError("Failed to create a new chat session with the Gemini API.")

    def _send_message_with_schema(self, prompt, schema, use_thinking=False):
        """
        Sends a message within the stateful chat session, expecting a JSON response.
        """
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema
        )
        if use_thinking:
            config.thinking_config = types.ThinkingConfig(thinking_budget=THINKING_BUDGET)
        response = self.chat.send_message(prompt, config=config)
        return json.loads(response.text)

    def _send_message_text_only(self, prompt, use_thinking=False):
        """
        Sends a message within the stateful chat session, expecting a text response.
        """
        config = None
        if use_thinking:
            config = types.GenerateContentConfig(thinking_config=types.ThinkingConfig(thinking_budget=THINKING_BUDGET))
        response = self.chat.send_message(prompt, config=config)
        return response.text

    def generate_mcq_questions(self, user_query: str) -> list[dict]:
        """
        Step 3: Generate MCQ questions using the LLM's internal knowledge (with thinking mode).

        Args:
            user_query (str): The original user query for budget analysis and context.

        Returns:
            list: List of question objects.
        """
        prompt = STEP3_MCQ_GENERATION_PROMPT.format(user_query=user_query)
        result = self._send_message_with_schema(prompt, MCQ_QUESTIONS_SCHEMA, use_thinking=True)
        return result["questions"]

    def generate_search_queries(self, user_answers: list[dict]) -> list[str]:
        """
        Step 4: Generate search queries based on user MCQ answers.

        Args:
            user_answers (list): List of user answer objects.

        Returns:
            list: List of search query strings.
        """
        current_year = datetime.datetime.now().year
        prompt = STEP4_SEARCH_QUERY_PROMPT.format(
            user_answers_json=json.dumps(user_answers, indent=2),
            current_year=current_year
        )
        result = self._send_message_with_schema(prompt, REC_SEARCH_TERMS_SCHEMA)
        return result["rec_search_terms"]

    def select_recommendation_urls(self, rec_search_results: list) -> list[dict]:
        """
        Step 5: Select 3-5 best URLs from recommendation search results.

        Args:
            rec_search_results (list): Search results from product recommendation searches.

        Returns:
            list: List of selected URL objects with title and url.
        """
        current_year = datetime.datetime.now().year
        previous_year = current_year - 1
        prompt = STEP5_WEBSITE_SELECTION_PROMPT.format(
            rec_search_results_json=json.dumps(rec_search_results, indent=2),
            current_year=current_year,
            previous_year=previous_year
        )
        result = self._send_message_with_schema(prompt, REC_SEARCH_URLS_SCHEMA)
        return result["rec_search_urls"]

    def generate_final_recommendations(self, rec_scraped_contents: list) -> str:
        """
        Step 6: Generate final product recommendations (with thinking mode).
        This includes a fail-safe to handle cases where the LLM wraps the
        Markdown output in a single-key JSON object.

        Args:
            rec_scraped_contents (list): Scraped content from recommendation URLs.

        Returns:
            str: Final recommendations in Markdown format.
        """
        prompt = STEP6_FINAL_RECOMMENDATIONS_PROMPT.format(
            rec_scraped_contents_json=json.dumps(rec_scraped_contents, indent=2)
        )
        # Get the raw text response from the LLM
        raw_response_text = self._send_message_text_only(prompt, use_thinking=True)

        # Fail-safe to extract content if the LLM returns a JSON object
        try:
            # Attempt to parse the response as JSON
            data = json.loads(raw_response_text)
            
            # Check if it's a dictionary with at least one key
            if isinstance(data, dict) and data:
                # Extract the value of the first key, regardless of the key's name
                print("INFO: LLM returned JSON for final recommendation. Extracting content.")
                return str(list(data.values())[0])
            else:
                # It's valid JSON but not the expected format (e.g., a list or empty dict)
                # Fallback to returning the raw text
                return raw_response_text
                
        except json.JSONDecodeError:
            # This is the expected case: the response is plain text/Markdown
            print("INFO: LLM returned plain text for final recommendation as expected.")
            return raw_response_text


# --- MODIFICATION START: Functions for the new Dual-LLM Enrichment feature ---

def curate_images(image_data: List[Dict[str, Any]]) -> Dict:
    """
    Makes a stateless call to Gemini to curate the best images for a list of products.

    Args:
        image_data: A list of objects, each with productName and raw imageData.

    Returns:
        A dictionary containing the curated image information.
    """
    print(f"Sending image data for {len(image_data)} products to Gemini for curation.")
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = IMAGE_CURATION_PROMPT.format(
            image_data_json=json.dumps(image_data, indent=2)
        )
        
        response = client.models.generate_content(
            model=GUARDRAIL_MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=IMAGE_CURATION_SCHEMA,
                temperature=DEFAULT_TEMPERATURE
            )
        )
        return json.loads(response.text)
        
    except Exception as e:
        # Propagate exception to be handled by the calling service
        print(f"ERROR: Image curation call failed with exception: {e}")
        raise

def curate_shopping_links(shopping_data: List[Dict[str, Any]]) -> Dict:
    """
    Makes a stateless call to Gemini to curate the best shopping links for a list of products.

    Args:
        shopping_data: A list of objects, each with productName and raw shoppingData.

    Returns:
        A dictionary containing the curated shopping link information.
    """
    print(f"Sending shopping data for {len(shopping_data)} products to Gemini for curation.")
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = SHOPPING_CURATION_PROMPT.format(
            shopping_data_json=json.dumps(shopping_data, indent=2)
        )
        
        response = client.models.generate_content(
            model=GUARDRAIL_MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=SHOPPING_CURATION_SCHEMA,
                temperature=DEFAULT_TEMPERATURE
            )
        )
        return json.loads(response.text)
        
    except Exception as e:
        # Propagate exception to be handled by the calling service
        print(f"ERROR: Shopping link curation call failed with exception: {e}")
        raise

# --- MODIFICATION END ---