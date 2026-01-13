from fastapi import APIRouter, Header, HTTPException, Depends
from sqlalchemy.orm import Session

from app.core.firebase import verify_firebase_token
from app.core.db import get_db
from app.service.user_service import get_or_create_user

router = APIRouter(prefix="/auth", tags=["auth"])

def _extract_bearer_token(authorization: str | None, authorization2: str | None) -> str:
    auth_header = authorization or authorization2
    if not auth_header:
        raise HTTPException(status_code=401, detail="Authorization header missing")

    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid Authorization header")

    return auth_header.split(" ", 1)[1].strip()


@router.post("/login")
def login(
    authorization: str | None = Header(default=None, alias="Authorization"),
    authorization2: str | None = Header(default=None, alias="authorization"),
    db: Session = Depends(get_db),
):
    """
    프론트에서 Firebase 로그인 후 받은 ID 토큰을 Bearer로 보내면:
    1) 토큰 검증
    2) users 테이블에 (firebase_uid, email) upsert
    3) 우리 서비스의 user_id(PK) 반환
    """
    token = _extract_bearer_token(authorization, authorization2)
    decoded = verify_firebase_token(token)

    firebase_uid = decoded.get("uid")
    email = decoded.get("email")

    if not firebase_uid:
        raise HTTPException(status_code=401, detail="Token missing uid")

    if not email:
        raise HTTPException(status_code=400, detail="Token missing email (Google login required)")

    user = get_or_create_user(db, firebase_uid=firebase_uid, email=email)

    return {
        "ok": True,
        "user": {
            "id": user.id,
            "firebase_uid": user.firebase_uid,
            "email": user.email,
        },
    }


# 기존 엔드포인트 호환: /auth/verify 도 동일하게 동작하게 유지
@router.post("/verify")
def verify(
    authorization: str | None = Header(default=None, alias="Authorization"),
    authorization2: str | None = Header(default=None, alias="authorization"),
    db: Session = Depends(get_db),
):
    token = _extract_bearer_token(authorization, authorization2)
    decoded = verify_firebase_token(token)

    firebase_uid = decoded.get("uid")
    email = decoded.get("email")

    if not firebase_uid:
        raise HTTPException(status_code=401, detail="Token missing uid")
    if not email:
        raise HTTPException(status_code=400, detail="Token missing email (Google login required)")

    user = get_or_create_user(db, firebase_uid=firebase_uid, email=email)

    return {"uid": firebase_uid, "email": email, "user_id": user.id}
