file paths:
app/config.py
app/main.py
app/prompts.py
app/schemas.py
app/middleware/auth.py
app/routers/enrich.py
app/routers/history.py
app/routers/recommendations.py
app/routers/research.py
app/routers/share.py
app/services/enrichment_service.py
app/services/history_service.py
app/services/llm_calls.py
app/services/logging_service.py
app/services/parsing_service.py
app/services/recommendation_service.py
app/services/research_service.py
app/services/search_functions.py
app/services/share_service.py


requirements.txt
firebase-service-account.json
.env

other files that are there, but not uploaded:
firebase-service-account.json
.env



How to run locally:

- Set AUTH_ENABLED to False
- Set CONVERSATION_ID_ENABLED to False
- Set FIREBASE_SERVICE_ACCOUNT_KEY_PATH to "firebase-service-account.json" in config.py

Finally,
uvicorn app.main:app --reload


To run the dummy backend:

uvicorn dummy_main:app --reload