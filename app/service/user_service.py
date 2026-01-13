from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import User


def get_or_create_user(db: Session, firebase_uid: str, email: str) -> User:
    """
    - firebase_uid로 먼저 조회
    - 없으면 생성
    - 이미 존재/경합이면 다시 조회해서 반환
    """
    user = db.execute(select(User).where(User.firebase_uid == firebase_uid)).scalar_one_or_none()
    if user:
        # 이메일이 토큰과 다르면 갱신(거의 없지만 방어)
        if email and user.email != email:
            user.email = email
            db.commit()
            db.refresh(user)
        return user

    user = User(firebase_uid=firebase_uid, email=email)
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
        return user
    except IntegrityError:
        # 동시에 같은 유저가 생성되는 레이스 대비
        db.rollback()
        user = db.execute(select(User).where(User.firebase_uid == firebase_uid)).scalar_one()
        return user
