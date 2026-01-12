import os
import firebase_admin
from firebase_admin import credentials, auth

def init_firebase() -> None:
    if firebase_admin._apps:
        return

    cred_path = os.getenv("FIREBASE_CREDENTIALS_FILE")
    if not cred_path:
        raise RuntimeError("FIREBASE_CREDENTIALS_FILE not set")

    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)

def verify_id_token(id_token: str) -> dict:
    return auth.verify_id_token(id_token)
