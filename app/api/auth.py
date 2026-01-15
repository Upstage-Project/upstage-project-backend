# app/api/auth.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from firebase_admin import auth as firebase_auth

from app.db.session import get_db
from app.db.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    token: str  # 프론트가 보내는 Firebase ID Token


@router.post("/login")
def login(
    request: LoginRequest,
    db: Session = Depends(get_db),
):
    # 1) Body로 받은 토큰 검증
    try:
        decoded = firebase_auth.verify_id_token(request.token)
        uid = decoded.get("uid") or decoded.get("sub")
        email = decoded.get("email")
    except Exception as e:
        print(f"Token verification failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid authentication token")

    if not uid:
        raise HTTPException(status_code=401, detail="Token missing uid")
    if not email:
        raise HTTPException(status_code=400, detail="Token missing email")

    # 재조회 helper (IntegrityError 이후에도 동일 로직 사용)
    def _get_user():
        u = db.query(User).filter(User.firebase_uid == uid).first()
        if not u:
            u = db.query(User).filter(User.email == email).first()
        return u

    user = _get_user()

    if user:
        # ✅ uid 기준 유저면 email 최신화
        if user.firebase_uid == uid and user.email != email:
            user.email = email

        # ✅ email 기준 유저면 uid 연결(갱신)
        if user.email == email and user.firebase_uid != uid:
            user.firebase_uid = uid
    else:
        # ✅ 둘 다 없을 때만 생성
        user = User(firebase_uid=uid, email=email)
        db.add(user)

    try:
        db.commit()
    except IntegrityError:
        # ✅ 레이스/중복 요청이면 여기로 떨어짐 → rollback 후 재조회해서 정상 응답
        db.rollback()
        user = _get_user()
        if not user:
            raise HTTPException(status_code=409, detail="User already exists (unique constraint)")

    db.refresh(user)

    return {
        "accessToken": request.token,  # 필요하면 여기서 우리 JWT로 교체 가능
        "user": {
            "id": user.id,
            "firebase_uid": user.firebase_uid,
            "email": user.email,
        },
    }
