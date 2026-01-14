# app/api/auth.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

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
        raise HTTPException(status_code=400, detail="Token missing email")

    # 1) uid로 먼저 찾기
    user = db.query(User).filter(User.firebase_uid == uid).first()

    # 2) uid로 없으면 email로도 찾아서 "계정 연결"
    if not user:
        user = db.query(User).filter(User.email == email).first()
        if user:
            # 기존 이메일 유저가 있으면 uid를 갱신해서 연결
            user.firebase_uid = uid
        else:
            user = User(firebase_uid=uid, email=email)
            db.add(user)
    else:
        # uid 유저는 email 변경 반영
        if user.email != email:
            user.email = email

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="User already exists (unique constraint)")

    db.refresh(user)
    return {"user": {"id": user.id, "firebase_uid": user.firebase_uid, "email": user.email}}
