"""
(auth.py) Authentication middleware to verify Firebase ID tokens.
Includes a bypass for local testing.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import firebase_admin
from firebase_admin import auth, credentials
from typing import Optional

from app.config import AUTH_ENABLED

# This scheme will look for an "Authorization: Bearer <token>" header.
# The tokenUrl is a dummy value; we are not using FastAPI's built-in OAuth2 flow,
# but this is the standard way to require a Bearer token.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

# --- Firebase Initialization ---
# This part of the code will run once when the application starts.
# The initialization logic will be called from main.py.
def initialize_firebase():
    """Initializes the Firebase Admin SDK. Should be called at app startup."""
    try:
        # The service account key is loaded from the path specified in config.py
        # You would typically load this from an environment variable for security.
        from app.config import FIREBASE_SERVICE_ACCOUNT_KEY_PATH
        cred = credentials.Certificate(FIREBASE_SERVICE_ACCOUNT_KEY_PATH)
        firebase_admin.initialize_app(cred)
        print("Firebase Admin SDK initialized successfully.")
    except Exception as e:
        print(f"ERROR: Failed to initialize Firebase Admin SDK: {e}")
        # If Firebase can't initialize, we should probably exit in a real app,
        # but here we'll print a warning and continue, which might be useful
        # if auth is disabled.
        # --- MODIFICATION START ---
        # Re-raise the exception to be caught by the application's lifespan manager.
        # This will allow the app to exit gracefully instead of running in a broken state.
        raise
        # --- MODIFICATION END ---

# --- Authentication Dependency ---

async def get_current_user(token: Optional[str] = Depends(oauth2_scheme)) -> str:
    """
    This function is a FastAPI dependency that verifies the user's token.
    It's called for every request to a protected endpoint.

    - If AUTH_ENABLED is False, it bypasses validation and returns a dummy ID.
    - If AUTH_ENABLED is True, it validates the Firebase ID token.

    Returns:
        str: The user's unique ID (UID) from Firebase or a dummy ID.

    Raises:
        HTTPException: If authentication fails when it's enabled.
    """
    # First, check if authentication is globally disabled.
    if not AUTH_ENABLED:
        print("AUTH DISABLED: Bypassing token check and returning dummy user ID.")
        return "test-user-local-123"

    # If auth is enabled, we must have a token.
    if token is None:
        # This will now be triggered if auth is on and no token is provided.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # If auth is enabled AND we have a token, proceed with verification.
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    if not firebase_admin._apps:
        print("ERROR: Firebase not initialized. Cannot authenticate user.")
        raise credentials_exception

    try:
        decoded_token = auth.verify_id_token(token)
        uid = decoded_token['uid']
        print(f"Successfully authenticated user: {uid}")
        return uid
    except auth.ExpiredIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except auth.InvalidIdTokenError:
        raise credentials_exception
    except Exception as e:
        print(f"An unexpected error occurred during token verification: {e}")
        raise credentials_exception