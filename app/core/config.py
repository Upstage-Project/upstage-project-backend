from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    ENV: str = "local"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    HOST: str = "0.0.0.0"
    PORT: int = 8000

    SERPER_API_KEY: str
    UPSTAGE_API_KEY: str
    DART_API_KEY: str

    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "upstage"
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "postgres"

settings = Settings()
