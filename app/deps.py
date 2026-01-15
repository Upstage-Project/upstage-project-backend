from __future__ import annotations

import os
from functools import lru_cache
from typing import Dict, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from firebase_admin import auth as fb_auth

from app.core.logger import logger
from app.db.session import get_db
from app.service.agent_service import AgentService
from app.agents.ticker_resolver import TickerResolver
from app.service.vector_service import VectorService
from app.service.embedding_service import EmbeddingService
from app.repository.vector.vector_repo import ChromaDBRepository
from app.core.db import engine

bearer = HTTPBearer(auto_error=False)


def _raise_401(detail: str):
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


# =========================
# DB Dependency (re-export)
# =========================
# 기존 코드 호환: from app.deps import get_db
# 실제 구현은 app.db.session.get_db를 그대로 씀
# (여기서 래핑하지 말고 그대로 노출)
__all__ = [
    "get_db",
    "get_current_claims",
    "get_agent_service",
    "get_ticker_resolver",
    "get_vector_service",
    "get_db_engine",
]


# =========================
# Auth: claims dependency
# =========================
def get_current_claims(
    request: Request,
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
) -> Dict:
    """
    Firebase ID Token을 검증하고 claims(dict)를 반환.
    예전 users.py 같은 곳에서 Depends(get_current_claims)로 쓰던 흐름 유지.

    Authorization: Bearer <ID_TOKEN> 필수
    """
    auth_header = request.headers.get("authorization")
    if not auth_header:
        logger.warning("[AUTH] Missing Authorization header")
        _raise_401("Missing Authorization header")

    if creds is None:
        logger.warning(f"[AUTH] Invalid Authorization header format: {auth_header!r}")
        _raise_401("Invalid Authorization header format")

    if (creds.scheme or "").lower() != "bearer":
        logger.warning(f"[AUTH] Authorization scheme is not Bearer: {creds.scheme!r}")
        _raise_401("Authorization scheme must be Bearer")

    token = (creds.credentials or "").strip()
    if not token:
        logger.warning("[AUTH] Empty bearer token")
        _raise_401("Empty bearer token")

    try:
        claims = fb_auth.verify_id_token(token)
        return claims
    except Exception as e:
        logger.warning(f"[AUTH] verify_id_token failed: {type(e).__name__}: {e}")
        _raise_401(f"Invalid ID token: {type(e).__name__}")


# =========================
# Ticker Resolver Dependency
# =========================
@lru_cache(maxsize=1)
def get_ticker_resolver() -> TickerResolver:
    """
    TickerResolver를 싱글톤으로 유지.
    company_master.json을 로드하여 회사명/티커 검색 제공.
    """
    resolver = TickerResolver()
    resolver.ensure_loaded()
    return resolver


# =========================
# Vector Service Dependencies
# =========================
@lru_cache(maxsize=1)
def get_vector_repository() -> ChromaDBRepository:
    """ChromaDBRepository 싱글톤"""
    return ChromaDBRepository()


@lru_cache(maxsize=1)
def get_embedding_service() -> EmbeddingService:
    """EmbeddingService 싱글톤"""
    return EmbeddingService()


@lru_cache(maxsize=1)
def get_vector_service() -> VectorService:
    """VectorService 싱글톤 - VectorRepository와 EmbeddingService를 조합"""
    return VectorService(
        vector_repository=get_vector_repository(),
        embedding_service=get_embedding_service()
    )


# =========================
# DB Engine Dependency
# =========================
def get_db_engine():
    """DB Engine 반환 (app.core.db.engine)"""
    return engine


# =========================
# AgentService Dependency
# =========================
@lru_cache(maxsize=1)
def _agent_service_singleton() -> AgentService:
    """
    AgentService를 싱글톤으로 유지.
    (매 요청마다 초기화 비용/리소스 재생성 방지)
    """
    return AgentService()


def get_agent_service() -> AgentService:
    """
    agent_routers.py 에서 Depends(get_agent_service)로 주입받기 위한 함수.
    """
    return _agent_service_singleton()
