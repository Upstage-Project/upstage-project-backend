# app/api/users.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_current_claims
from app.db.models import User

router = APIRouter(prefix="/users", tags=["users"])

@router.get("/me")
def me(
    db: Session = Depends(get_db),
    claims: dict = Depends(get_current_claims),
):
    uid = claims.get("uid")
    email = claims.get("email")

    if not uid:
        raise HTTPException(status_code=401, detail="Token missing uid")
    if not email:
        raise HTTPException(status_code=400, detail="Token missing email")

    user = db.query(User).filter(User.firebase_uid == uid).first()

    # ✅ 로그인 API를 안 치더라도 /me만으로 복구 가능하게 upsert
    if not user:
        user = User(firebase_uid=uid, email=email)
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
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
