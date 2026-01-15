from __future__ import annotations

import os
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from firebase_admin import auth as fb_auth

from app.core.logger import logger
from app.db.session import get_db
from app.db.models import User

bearer = HTTPBearer(auto_error=False)

# ✅ 테스트 모드: .env에서 DISABLE_AUTH=true 설정 시 인증 우회
DISABLE_AUTH = os.getenv("DISABLE_AUTH", "false").lower() == "true"


def _raise_401(detail: str):
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _get_or_create_user(db: Session, claims: dict) -> User:
    uid = claims.get("uid")
    email = claims.get("email")

    if not uid:
        _raise_401("Invalid token: missing uid")

    user = db.query(User).filter(User.firebase_uid == uid).first()
    if user:
        # email이 바뀌었으면 갱신(선택)
        if email and getattr(user, "email", None) != email:
            user.email = email
            db.commit()
            db.refresh(user)
        return user

    user = User(firebase_uid=uid, email=email)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
) -> User:
    # ✅ 테스트 모드: 인증 우회하고 user_id=5 반환
    if DISABLE_AUTH:
        logger.warning("[AUTH] DISABLE_AUTH=true - Using test user (id=5)")
        user = db.query(User).filter(User.id == 5).first()
        if not user:
            logger.error("[AUTH] Test user (id=5) not found in database")
            _raise_401("Test user not configured")
        return user
    
    # 1) Authorization 헤더 자체가 없거나 파싱 실패
    auth_header = request.headers.get("authorization")
    logger.info(f"[AUTH] Request from {request.client.host if request.client else 'unknown'} to {request.url.path}")
    logger.info(f"[AUTH] Authorization header present: {bool(auth_header)}")
    
    if not auth_header:
        logger.warning("[AUTH] Missing Authorization header")
        logger.info(f"[AUTH] All headers: {dict(request.headers)}")
        _raise_401("Missing Authorization header")

    # 2) HTTPBearer가 creds를 못 만들었으면 형식 문제
    if creds is None:
        logger.warning(f"[AUTH] Invalid Authorization header format: {auth_header!r}")
        _raise_401("Invalid Authorization header format")

    # 3) Bearer 스킴 확인
    if (creds.scheme or "").lower() != "bearer":
        logger.warning(f"[AUTH] Authorization scheme is not Bearer: {creds.scheme!r}")
        _raise_401("Authorization scheme must be Bearer")

    token = (creds.credentials or "").strip()
    if not token:
        logger.warning("[AUTH] Empty bearer token")
        _raise_401("Empty bearer token")

    # 4) Firebase ID token 검증
    try:
        claims = fb_auth.verify_id_token(token)
    except Exception as e:
        # ✅ 여기 로그가 401의 진짜 이유
        logger.warning(f"[AUTH] verify_id_token failed: {type(e).__name__}: {e}")
        _raise_401(f"Invalid ID token: {type(e).__name__}")

    return _get_or_create_user(db, claims)
