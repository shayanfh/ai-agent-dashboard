from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    APP_NAME: str = "AI Agent Dashboard"
    APP_ENV: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"

    # Security
    SECRET_KEY: str = "change-me-in-production-use-a-long-random-string"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    INTERNAL_API_KEY: str = "change-internal-api-key-in-production"
    WEBSITE_API_KEY: str = ""
    EMAIL_VERIFICATION_EXPIRE_HOURS: int = 24
    PASSWORD_RESET_EXPIRE_MINUTES: int = 30
    TRIAL_DAYS: int = 14
    MAX_FAILED_LOGIN_ATTEMPTS: int = 5
    LOGIN_LOCK_MINUTES: int = 15

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_agent_dashboard"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # Email
    EMAIL_PROVIDER: str = "console"
    EMAIL_FROM: str = "no-reply@example.com"
    WEBSITE_NOTIFICATION_EMAIL: str = ""
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = True
    FRONTEND_URL: str = "http://localhost:5173"

    # Encryption
    CREDENTIAL_ENCRYPTION_KEY: str = "change-me-generate-with-fernet-keygen"

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]

    # Storage (MinIO / S3)
    STORAGE_ENDPOINT: str = "http://localhost:9000"
    STORAGE_PUBLIC_ENDPOINT: str | None = None
    STORAGE_ACCESS_KEY: str = "minioadmin"
    STORAGE_SECRET_KEY: str = "minioadmin"
    STORAGE_BUCKET: str = "ai-agent-dashboard"
    MAX_RECORDING_UPLOAD_BYTES: int = 50 * 1024 * 1024
    RECORDING_PRESIGNED_URL_EXPIRE_SECONDS: int = 900

    # LiveKit telephony provisioning
    LIVEKIT_URL: str = ""
    LIVEKIT_API_KEY: str = ""
    LIVEKIT_API_SECRET: str = ""
    LIVEKIT_SIP_ENDPOINT: str = ""
    LIVEKIT_AGENT_NAME: str = "ai-agent-dashboard-inbound"

    # Shared Asterisk gateway provisioning
    ASTERISK_PROVISIONER_URL: str = ""
    ASTERISK_PROVISIONER_API_KEY: str = ""
    ASTERISK_PUBLIC_SIP_URI: str = ""
    ASTERISK_REQUEST_TIMEOUT_SECONDS: float = 15.0


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
