# app/deps.py
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.firebase import verify_firebase_token

security = HTTPBearer(auto_error=False)

def get_current_claims(
    cred: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    if not cred or not cred.credentials:
        raise HTTPException(status_code=401, detail="Missing bearer token")

    try:
        return verify_firebase_token(cred.credentials)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
