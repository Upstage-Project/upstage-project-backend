from fastapi import APIRouter, Header, HTTPException
from app.core.firebase import verify_id_token

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/login")
def login(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")

    id_token = authorization.split(" ", 1)[1].strip()

    try:
        decoded = verify_id_token(id_token)
        # decoded 안에 uid, email 등이 들어있음 (email은 계정 설정에 따라 없을 수도)
        return {
            "firebase_uid": decoded.get("uid"),
            "email": decoded.get("email"),
        }
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
