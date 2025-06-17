import firebase_admin
from firebase_admin import credentials, auth
import requests
import json
import os

def get_firebase_jwt_token_via_rest_api():
    """
    Get Firebase JWT token using the REST API authentication method.
    This is more appropriate for client-side authentication.
    """
    
    # Firebase Web API Key - you'll need to get this from your Firebase console
    # Go to Project Settings > General > Web API Key
    WEB_API_KEY = "AIzaSyC_uOkG9PxmrGCeOTa8ltTXQfBm0O8hvoQ"
    
    # User credentials - NEVER hardcode these in production!
    email = "venkateshxd10@gmail.com"  # Replace with your test email
    password = "doordie123"        # Replace with your test password
    
    # Firebase Auth REST API endpoint
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={WEB_API_KEY}"
    
    payload = {
        "email": email,
        "password": password,
        "returnSecureToken": True
    }
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        
        data = response.json()
        
        # Extract the ID token (JWT)
        id_token = data.get('idToken')
        refresh_token = data.get('refreshToken')
        expires_in = data.get('expiresIn')
        
        print("Authentication successful!")
        print(f"JWT Token: {id_token}")
        print(f"Refresh Token: {refresh_token}")
        print(f"Expires in: {expires_in} seconds")
        
        return id_token
        
    except requests.exceptions.RequestException as e:
        print(f"Error during authentication: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}")
        return None


def main():
    """
    Main function to demonstrate both methods
    """
    print("Method 1: Using REST API (recommended for client authentication)")
    print("-" * 60)
    
    # Get JWT token using REST API method
    jwt_token = get_firebase_jwt_token_via_rest_api()
    
    if jwt_token:
        print("\n✅ Successfully obtained JWT token!")
        # You can now use this token for authenticated requests
        print("You can use this token in your Authorization header:")
        print(f"Authorization: Bearer {jwt_token}")
    else:
        print("\n❌ Failed to obtain JWT token")

if __name__ == "__main__":
    main()