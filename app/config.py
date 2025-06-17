"""
(config.py) Configuration settings for the Product Recommendation API.
"""

import os

# Helper function to read boolean values from environment variables
def get_bool_from_env(key, default_value):
    value = os.getenv(key, str(default_value))
    return value.lower() in ('true', '1', 't')



# Configuration values that are deployment-specific but not secret are now hardcoded.
# Secrets like API keys are still loaded from environment variables.

# --- Firebase Configuration ---
# Set to False for local testing to bypass token verification.
# In production, this should be True.
AUTH_ENABLED = True

# Path to your Firebase service account key JSON file.

# For production environments (using Google Cloud Secret Manager)

FIREBASE_SERVICE_ACCOUNT_KEY_PATH = "/secrets/firebase-service-account.json"

# For local testing
# The `firebase-service-account.json` file should be in the root directory.
# Uncomment the line below to use a local service account key file.

# FIREBASE_SERVICE_ACCOUNT_KEY_PATH = "firebase-service-account.json"



# --- Serper API Configuration ---
# This is a secret and should be set in your .env file
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "your_serper_api_key_here") 

# --- Gemini API Configuration ---
# This is a secret and should be set in your .env file
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "your_gemini_api_key_here")
MODEL_NAME = "gemini-2.5-flash-preview-05-20"

# --- Model Configuration ---
DEFAULT_TEMPERATURE = 0.7
MAX_TOKENS = 8192

# --- Google Cloud Project Configuration ---
# Your Google Cloud Project ID
GCP_PROJECT_ID = "moonshot-69420"
# The name of the GCS bucket for storing raw trace logs
GCS_BUCKET_NAME = "moonshot-69420-llm-traces"

# --- Application Settings ---
# These settings can be used to add validation in the future if needed.
MAX_GUIDE_URLS = 2
MIN_MCQ_QUESTIONS = 3
MAX_MCQ_QUESTIONS = 6
MIN_REC_SEARCH_TERMS = 1
MAX_REC_SEARCH_TERMS = 3
MIN_REC_URLS = 3
MAX_REC_URLS = 5
# Maximum number of concurrent requests for parallel scraping/searching
MAX_CONCURRENT_REQUESTS = 5


# --- Validation and Warnings ---
# This part runs when the module is imported, providing immediate feedback.
if GEMINI_API_KEY == "your_gemini_api_key_here":
    print("WARNING: GEMINI_API_KEY is not set. Please update your .env file or Cloud Run secret mapping.")

if SERPER_API_KEY == "your_serper_api_key_here":
    print("WARNING: SERPER_API_KEY is not set. Please update your .env file or Cloud Run secret mapping.")

if AUTH_ENABLED:
    # In a Cloud Run environment, this check might not be useful at build time,
    # but it remains crucial for local development and debugging.
    if not os.path.exists(FIREBASE_SERVICE_ACCOUNT_KEY_PATH):
        print(f"WARNING: AUTH_ENABLED is True, but the Firebase service account key was not found at '{FIREBASE_SERVICE_ACCOUNT_KEY_PATH}'. This is expected during local runs if you haven't mounted the secret. Chamge path to \"firebase-service-account.json\" for local runs.")
else:
    print("INFO: Authentication is disabled (AUTH_ENABLED=False). API will not require a token.")