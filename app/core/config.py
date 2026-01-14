# app/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    firebase_credentials_file: str
    firebase_web_api_key: str  # ✅ 추가

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    HOST: str = "0.0.0.0"
    PORT: int = 8000

    SERPER_API_KEY: str
    UPSTAGE_API_KEY: str
    DART_API_KEY: str
    NAVER_CLIENT_ID: str
    NAVER_CLIENT_SECRET: str

    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "upstage"
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "postgres"

    # ✅ [수정] 개별 DB 정보를 조합하여 DATABASE_URL 생성
    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

settings = Settings()
