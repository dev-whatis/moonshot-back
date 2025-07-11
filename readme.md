file paths:

app/middleware/auth.py
app/routers/enrich.py
app/routers/history.py
app/routers/product_discovery.py
app/routers/quick_decisions.py
app/routers/paths.py
app/routers/share.py

app/services/enrichment_service.py
app/services/history_service.py
app/services/llm_calls.py
app/services/location_service.py
app/services/logging_service.py
app/services/parsing_service.py
app/services/product_discovery_service.py
app/services/quick_decision_service.py
app/services/search_functions.py
app/services/share_service.py

app/config.py
app/main.py
app/prompts.py
app/schemas.py

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