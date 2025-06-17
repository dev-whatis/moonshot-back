import firebase_admin
from firebase_admin import credentials, auth
import json

# Initialize Firebase Admin SDK
cred = credentials.Certificate("firebase-service-account.json")
firebase_admin.initialize_app(cred)

# Get UID from user
uid = input("Enter UID: ")

try:
    # Get user data
    user = auth.get_user(uid)
    
    # Convert to dict and print JSON
    user_dict = {
        'uid': user.uid,
        'email': user.email,
        'displayName': user.display_name,
        'phoneNumber': user.phone_number,
        'photoURL': user.photo_url,
        'emailVerified': user.email_verified,
        'disabled': user.disabled,
        'creationTime': user.user_metadata.creation_timestamp,
        'lastSignInTime': user.user_metadata.last_sign_in_timestamp,
        'customClaims': user.custom_claims,
        'providerData': [
            {
                'uid': provider.uid,
                'displayName': provider.display_name,
                'email': provider.email,
                'phoneNumber': provider.phone_number,
                'photoURL': provider.photo_url,
                'providerId': provider.provider_id
            } for provider in user.provider_data
        ]
    }
    
    print(json.dumps(user_dict, indent=2, default=str))
    
except Exception as e:
    print(f"Error: {e}")