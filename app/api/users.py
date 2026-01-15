# app/api/users.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import User
from app.api.user_deps import get_current_user  # ✅ 여기로 변경

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me")
def me(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # get_current_user에서 이미 DB 조회까지 끝났으니 그대로 리턴
    return {
        "user": {
            "id": current_user.id,
            "firebase_uid": current_user.firebase_uid,
            "email": current_user.email,
        }
    }
