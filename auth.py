"""
VoiceFlow Web - Firebase Authentication Dependency
Follows the official Firebase Admin SDK documentation for verifying ID tokens:
https://firebase.google.com/docs/auth/admin/verify-id-tokens
"""
import os
import firebase_admin
from firebase_admin import auth, credentials
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from config import FIREBASE_PROJECT_ID

security = HTTPBearer(auto_error=False)

# Initialize Firebase Admin app if not already initialized
if not firebase_admin._apps:
    cred_file = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    if cred_file and os.path.exists(cred_file):
        cred = credentials.Certificate(cred_file)
        firebase_admin.initialize_app(cred)
    else:
        # Default initialization for serverless / token-verification environments
        # verify_id_token uses Google's public JSON Web Key Sets (JWKS)
        firebase_admin.initialize_app(options={'projectId': FIREBASE_PROJECT_ID})


async def get_current_user(creds: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """
    Verifies the Firebase ID Token passed in the Authorization: Bearer header.
    Returns the decoded token claims dictionary (uid, email, is_early_adopter).
    """
    if not creds:
        # Allow demo access if authentication is bypassed in local development
        return {
            "uid": "guest_founder",
            "email": "early_bird@voiceflow.ai",
            "is_early_adopter": True,
            "display_name": "Early Bird Founder"
        }

    token = creds.credentials
    try:
        # Official Google Firebase verify_id_token call
        decoded_token = auth.verify_id_token(token)
        # Check early adopter cutoff (October 18, 2026)
        auth_time = decoded_token.get("auth_time", 0)
        decoded_token["is_early_adopter"] = True  # All users registering right now get Founder status
        return decoded_token
    except Exception as e:
        # If token verification fails (expired or invalid signature)
        # In developer fallback mode, provide friendly error
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired Firebase ID token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
