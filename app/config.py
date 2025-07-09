"""
(config.py) Configuration settings for the Product Recommendation API.
"""

import os

# Configuration values that are deployment-specific but not secret are now hardcoded.
# Secrets like API keys are still loaded from environment variables.

# --- Development & Testing Flags ---
# Set to True for production to enforce conversationId and enable logging.
# Set to False for local testing to make conversationId optional and disable logging.
CONVERSATION_ID_ENABLED = True

# --- Firebase Configuration ---
# Set to False for local testing to bypass token verification.
# In production, this should be True.
AUTH_ENABLED = True


# For GCP environment
FIREBASE_SERVICE_ACCOUNT_KEY_PATH = "/secrets/firebase-service-account.json"


# For local development
# FIREBASE_SERVICE_ACCOUNT_KEY_PATH = "firebase-service-account.json"



# --- Tavily API Configuration ---
# This is a secret and should be set in your .env file
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "your_tavily_api_key_here")

# --- Serper API Configuration ---
# This is a secret and should be set in your .env file
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "your_serper_api_key_here") 

# --- Gemini API Configuration ---
# This is a secret and should be set in your .env file
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "your_gemini_api_key_here")
HIGH_MODEL_NAME = "gemini-2.5-pro"
MID_MODEL_NAME = "gemini-2.5-flash"
LOW_MODEL_NAME = "gemini-2.5-flash-lite-preview-06-17"

# --- Model Configuration ---
DEFAULT_TEMPERATURE = 1
THINKING_BUDGET = -1

# --- Google Cloud Project Configuration ---
# Your Google Cloud Project ID
GCP_PROJECT_ID = "moonshot-69420"
# The name of the GCS bucket for storing raw trace logs
GCS_BUCKET_NAME = "moonshot-69420-llm-traces"

# Maximum number of concurrent requests for parallel scraping/searching Tavily
MAX_CONCURRENT_REQUESTS = 5

# For the LLM enrichment process Serper API
# PRODUCT_CHUNK_SIZE: How many products to include in a single LLM call.
# LLM_TASK_CONCURRENCY: How many LLM API calls to run in parallel at once.
PRODUCT_CHUNK_SIZE = 1
LLM_TASK_CONCURRENCY = 6


# --- Validation and Warnings ---
# This part runs when the module is imported, providing immediate feedback.
if GEMINI_API_KEY == "your_gemini_api_key_here":
    print("WARNING: GEMINI_API_KEY is not set. Please update your .env file or Cloud Run secret mapping.")

if SERPER_API_KEY == "your_serper_api_key_here":
    print("WARNING: SERPER_API_KEY is not set. Please update your .env file or Cloud Run secret mapping.")

if TAVILY_API_KEY == "your_tavily_api_key_here":
    print("WARNING: TAVILY_API_KEY is not set. Please update your .env file or Cloud Run secret mapping.")

if AUTH_ENABLED:
    # In a Cloud Run environment, this check might not be useful at build time,
    # but it remains crucial for local development and debugging.
    if not os.path.exists(FIREBASE_SERVICE_ACCOUNT_KEY_PATH):
        print(f"WARNING: AUTH_ENABLED is True, but the Firebase service account key was not found at '{FIREBASE_SERVICE_ACCOUNT_KEY_PATH}'. This is expected during local runs if you haven't mounted the secret. Chamge path to \"firebase-service-account.json\" for local runs.")
else:
    print("INFO: Authentication is disabled (AUTH_ENABLED=False). API will not require a token.")