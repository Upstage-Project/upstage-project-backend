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
