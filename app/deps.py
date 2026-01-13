# app/deps.py
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.firebase import verify_firebase_token

security = HTTPBearer(auto_error=False)
# =========================
# DB
# =========================
from app.core.db import engine


def get_db_engine():
    """
    SQLAlchemy Engine DI
    - Tool(get_portfolio_stocks)에서 engine.connect()로 사용
    """
    return engine


# =========================
# Vector / Embedding
# =========================
from app.repository.vector.vector_repo import (
    VectorRepository,
    ChromaDBRepository,
)
from app.service.vector_service import VectorService
from app.service.embedding_service import EmbeddingService

def get_current_claims(
    cred: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    if not cred or not cred.credentials:
        raise HTTPException(status_code=401, detail="Missing bearer token")

    try:
        return verify_firebase_token(cred.credentials)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
def get_vector_repository() -> VectorRepository:
    return ChromaDBRepository()


def get_embedding_service() -> EmbeddingService:
    return EmbeddingService()


def get_vector_service(
    vector_repo: VectorRepository = Depends(get_vector_repository),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
) -> VectorService:
    return VectorService(
        vector_repository=vector_repo,
        embedding_service=embedding_service,
    )


# =========================
# Ticker Resolver
# =========================
# ⚠️ 실제 클래스 경로는 네 프로젝트에 맞게 수정
from app.agents.ticker_resolver import TickerResolver

_ticker_resolver_singleton: TickerResolver | None = None


def get_ticker_resolver() -> TickerResolver:
    """
    회사명 / 티커 / 종목코드 정규화 Resolver
    - 싱글톤으로 유지 (내부에 종목 마스터 캐시 가질 가능성 높음)
    """
    global _ticker_resolver_singleton
    if _ticker_resolver_singleton is None:
        _ticker_resolver_singleton = TickerResolver()
        if hasattr(_ticker_resolver_singleton, "ensure_loaded"):
            _ticker_resolver_singleton.ensure_loaded()
    return _ticker_resolver_singleton


# =========================
# Agent Services
# =========================
from app.service.agents.info_collector_service import InfoCollectorService


def get_info_collector_service() -> InfoCollectorService:
    """
    InfoCollectorService DI
    - 현재는 stateless지만
    - 추후 repo/service 의존성 생겨도 확장 가능
    """
    return InfoCollectorService()
