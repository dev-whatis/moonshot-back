"""
(llm_handler.py) Handles all Gemini interactions using the new google-genai SDK with chat sessions.
Each instance of LLMHandler represents a single, self-contained conversation.
"""
import json
import datetime
from google import genai
from google.genai import types

from app.config import GEMINI_API_KEY, MODEL_NAME, DEFAULT_TEMPERATURE, MAX_TOKENS
from app.prompts import (
    STEP0_GUARDRAIL_PROMPT,
    STEP1_SEARCH_TERM_PROMPT,
    STEP2_LINK_SELECTION_PROMPT,
    STEP3_MCQ_GENERATION_PROMPT,
    STEP4_SEARCH_QUERY_PROMPT,
    STEP5_WEBSITE_SELECTION_PROMPT,
    STEP6_FINAL_RECOMMENDATIONS_PROMPT
)
from app.schemas import (
    GUARDRAIL_RESPONSE_SCHEMA,
    GUIDE_SEARCH_TERM_SCHEMA,
    GUIDE_SEARCH_URLS_SCHEMA,
    MCQ_QUESTIONS_SCHEMA,
    REC_SEARCH_TERMS_SCHEMA,
    REC_SEARCH_URLS_SCHEMA
)

class LLMHandler:
    def __init__(self):
        """
        Initializes the handler and starts a new chat session immediately.
        """
        client = genai.Client(api_key=GEMINI_API_KEY)
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
        Send message with structured output schema using chat session.

        Args:
            prompt (str): The prompt to send to the model.
            schema (dict): OpenAPI schema for structured output.
            use_thinking (bool): Whether to enable thinking mode.

        Returns:
            dict: Parsed JSON response.
        """
        # Create config for this specific message
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema
        )

        if use_thinking:
            config.thinking_config = types.ThinkingConfig()

        # Send message with config
        response = self.chat.send_message(prompt, config=config)

        return json.loads(response.text)

    def _send_message_text_only(self, prompt, use_thinking=False):
        """
        Send message for plain text response using chat session.

        Args:
            prompt (str): The prompt to send to the model.
            use_thinking (bool): Whether to enable thinking mode.

        Returns:
            str: Plain text response.
        """
        config = None

        if use_thinking:
            config = types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig()
            )

        response = self.chat.send_message(prompt, config=config)

        return response.text

    # --- MODIFICATION START ---
    def check_query_intent(self, user_query: str) -> dict:
        """
        Step 0: Use a guardrail to classify the user's intent.

        Args:
            user_query (str): The user's original query.

        Returns:
            dict: A dictionary with 'is_product_request' and 'reason'.
        """
        prompt = STEP0_GUARDRAIL_PROMPT.format(user_query=user_query)
        result = self._send_message_with_schema(prompt, GUARDRAIL_RESPONSE_SCHEMA)
        return result
    # --- MODIFICATION END ---

    def generate_search_term(self, user_query: str) -> str:
        """
        Step 1: Generate search term for buying guides.

        Args:
            user_query (str): User's original query.

        Returns:
            str: Guide search term.
        """
        prompt = STEP1_SEARCH_TERM_PROMPT.format(user_query=user_query)
        result = self._send_message_with_schema(prompt, GUIDE_SEARCH_TERM_SCHEMA)
        return result["guide_search_term"]

    def select_guide_urls(self, search_results_json: dict) -> list[str]:
        """
        Step 2: Select 2 best URLs from search results.

        Args:
            search_results_json (dict): Search results from buying guide search.

        Returns:
            list: List of 2 selected URLs.
        """
        prompt = STEP2_LINK_SELECTION_PROMPT.format(
            search_results_json=json.dumps(search_results_json, indent=2)
        )
        result = self._send_message_with_schema(prompt, GUIDE_SEARCH_URLS_SCHEMA)
        return result["guide_search_urls"]

    def generate_mcq_questions(self, user_query: str, scraped_contents: str) -> list[dict]:
        """
        Step 3: Generate MCQ questions (with thinking mode).

        Args:
            user_query (str): The original user query for budget analysis.
            scraped_contents (str): Scraped content from buying guides.

        Returns:
            list: List of question objects.
        """
        prompt = STEP3_MCQ_GENERATION_PROMPT.format(
            user_query=user_query, 
            scraped_contents=scraped_contents
        )
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

        Args:
            rec_scraped_contents (list): Scraped content from recommendation URLs.

        Returns:
            str: Final recommendations in plain text.
        """
        prompt = STEP6_FINAL_RECOMMENDATIONS_PROMPT.format(
            rec_scraped_contents_json=json.dumps(rec_scraped_contents, indent=2)
        )
        return self._send_message_text_only(prompt, use_thinking=True)