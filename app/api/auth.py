# app/api/auth.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.deps import get_current_claims
from app.db.models import User

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/login")
def login(
    db: Session = Depends(get_db),
    claims: dict = Depends(get_current_claims),
):
    uid = claims.get("uid")
    email = claims.get("email")

    if not uid:
        raise HTTPException(status_code=401, detail="Token missing uid")
    if not email:
        # 이메일이 없으면 우리 서비스에서 사용자 식별/연락에 문제가 생김
        raise HTTPException(status_code=400, detail="Token missing email")

    user = db.query(User).filter(User.firebase_uid == uid).first()

    if not user:
        user = User(firebase_uid=uid, email=email)
        db.add(user)
    else:
        # 이메일이 바뀌는 케이스(구글 계정 변경 등) 반영
        if user.email != email:
            user.email = email

    db.commit()
    db.refresh(user)

    return {
        "user": {
            "id": user.id,
            "firebase_uid": user.firebase_uid,
            "email": user.email,
        }
    }
@router.get("/verify")
def verify_token(
    db: Session = Depends(get_db),
    claims: dict = Depends(get_current_claims),
):
    """
    Authorization: Bearer <Firebase ID Token>
    - 토큰 유효성 검증 결과 + 유저정보 반환
    """
    uid = claims.get("uid")
    email = claims.get("email")

    # DB에 유저가 있으면 가져오고, 없으면 None (원하면 여기서 생성도 가능)
    user = db.query(User).filter(User.firebase_uid == uid).first()

    return {
        "valid": True,
        "uid": uid,
        "email": email,
        "user": None if not user else {
            "id": user.id,
            "firebase_uid": user.firebase_uid,
            "email": user.email,
        }
    }