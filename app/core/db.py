# app/core/db.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# ✅ settings.database_url (pydantic field) 사용
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/upstage"
)

engine = create_engine(
    settings.database_url,
    echo=False,          # 디버깅 필요하면 True
    pool_pre_ping=True,  # 끊긴 커넥션 자동 감지
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)

def get_db():
    """FastAPI dependency: request마다 DB 세션을 열고 닫는다."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
