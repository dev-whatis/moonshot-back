"""
(main.py) The main entry point for the FastAPI application.
This file initializes the app, includes routers, and sets up middleware.
"""
# IMPORTANT: Load environment variables at the very beginning
from dotenv import load_dotenv
load_dotenv()

import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

# Import routers and middleware initializers
from app.routers import recommendations
from app.routers import enrich
from app.routers import share
from app.routers import history
from app.routers import paths
from app.middleware.auth import initialize_firebase
from app.config import AUTH_ENABLED

# ==============================================================================
# Lifespan Events
# ==============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Code to run on application startup
    print("--- Application Startup ---")
    if AUTH_ENABLED:
        # Only initialize Firebase if authentication is actually enabled
        try:
            initialize_firebase()
        except Exception as e:
            # If initialization fails, log a fatal error and exit.
            # The app is not functional if auth is on but Firebase is down.
            print("\n=====================================================================")
            print("FATAL ERROR: Firebase initialization failed. Application cannot start.")
            print(f"  Reason: {e}")
            print("  - Is the `firebase-service-account.json` file present and valid?")
            print("  - Are the Firebase project permissions configured correctly?")
            print("=====================================================================\n")
            sys.exit(1)
    else:
        print("Authentication is disabled. Skipping Firebase initialization.")
    
    yield
    
    # Code to run on application shutdown
    print("--- Application Shutdown ---")


# ==============================================================================
# FastAPI App Initialization
# ==============================================================================

app = FastAPI(
    title="Product Recommendation API",
    description="An API that provides personalized product recommendations and data enrichment using a multi-step AI-driven process.",
    version="1.3.0", # Bump version number to reflect new sharing feature
    lifespan=lifespan  # Use the lifespan manager for startup/shutdown events
)

# ==============================================================================
# CORS middleware
# ==============================================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",        # local dev url
        "https://www.recmonkey.com"    # website url
    ],
    allow_origin_regex=r"^https://[A-Za-z0-9-]+\.moonshot-front-f4u\.pages\.dev$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==============================================================================
# Include Routers
# ==============================================================================

# Include the recommendation routes from the router file
app.include_router(paths.router)              # Handles initial query routing (e.g., /api/paths/start)
app.include_router(recommendations.router)    # Handles ongoing conversations (e.g., /api/conversations/turn)
app.include_router(enrich.router)             # Handles product enrichment
app.include_router(share.router)              # Handles sharing functionality
app.include_router(history.router)            # Handles conversation history


# ==============================================================================
# Root Endpoint
# ==============================================================================

@app.get("/", tags=["Health Check"])
async def root():
    """
    A simple health check endpoint to confirm the API is running.
    """
    return {"status": "ok", "message": "Welcome to the Product Recommendation API!"}


# To run this application:
# 1. Make sure you have a .env file with your API keys.
# 2. Make sure you have your firebase-service-account.json file.
# 3. In your terminal, run: uvicorn app.main:app --reload