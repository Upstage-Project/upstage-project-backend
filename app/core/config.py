# app/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ✅ .env에서 쓰는 키를 "필드로 선언" (이게 없으면 extra로 취급됨)
    database_url: str
    firebase_credentials_file: str

    # ✅ Alembic 같은 도구 실행 시 .env 키 추가되어도 안 죽게
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",   # 핵심: forbid -> ignore 로 바꿔야 함
    )


settings = Settings()
