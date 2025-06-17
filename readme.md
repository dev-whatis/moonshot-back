file paths:
app/config.py
app/main.py
app/prompts.py
app/schemas.py
app/middleware/auth.py
app/routers/recommendations.py
app/services/llm_handler.py
app/services/search_functions.py
app/services/logging_service.py

requirements.txt
firebase-service-account.json
.env

other files that are there, but not uploaded:
firebase-service-account.json
.env




How to run locally:

- Set AUTH_ENABLED to False
- Set FIREBASE_SERVICE_ACCOUNT_KEY_PATH to "firebase-service-account.json" in config.py



uvicorn app.main:app --reload