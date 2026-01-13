# app/api/users.py
from fastapi import APIRouter, Depends
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
    uid = claims["uid"]
    user = db.query(User).filter(User.firebase_uid == uid).first()
    if not user:
        # 로그인 API를 안쳤거나, DB에 아직 없으면 여기서 만들어도 됨(선택)
        return {"user": None}
    return {"user": {"id": user.id, "firebase_uid": user.firebase_uid, "email": user.email}}
