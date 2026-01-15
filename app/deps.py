# app/api/user_deps.py
from fastapi import Depends, HTTPException, Header
from sqlalchemy.orm import Session
from firebase_admin import auth as firebase_auth

from app.db.session import get_db
from app.db.models import User


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    # Authorization: Bearer <token>
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization Bearer token")

    token = authorization.split(" ", 1)[1].strip()

    try:
        decoded = firebase_auth.verify_id_token(token)
        uid = decoded.get("uid") or decoded.get("sub")
    except Exception as e:
        print(f"Token verification failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid authentication token")

    if not uid:
        raise HTTPException(status_code=401, detail="Token missing uid")

    user = db.query(User).filter(User.firebase_uid == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found. Please login first.")

    return user


# =========================
# Agent Service Dependency
# =========================

from functools import lru_cache
from app.service.agent_service import AgentService


@lru_cache(maxsize=1)
def _agent_service_singleton() -> AgentService:
    return AgentService()


def get_agent_service() -> AgentService:
    return _agent_service_singleton()




