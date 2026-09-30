from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    app_name: str = os.getenv("APP_NAME", "AI Video Workflow")
    api_prefix: str = os.getenv("API_PREFIX", "/api/v1")
    secret_key: str = os.getenv("SECRET_KEY", "local-development-secret")
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "720"))

    db_host: str = os.getenv("DB_HOST", "127.0.0.1")
    db_port: int = int(os.getenv("DB_PORT", "3306"))
    db_name: str = os.getenv("DB_NAME", "ai_video")
    db_user: str = os.getenv("DB_USER", "root")
    db_password: str = os.getenv("DB_PASSWORD", "")
    db_charset: str = os.getenv("DB_CHARSET", "utf8mb4")

    storage_path_value: str = os.getenv("STORAGE_PATH", "./storage")
    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "500"))
    auto_create_tables: bool = _as_bool(os.getenv("AUTO_CREATE_TABLES"), False)
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    cors_origins_value: str = os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    )

    @property
    def database_url(self) -> str:
        explicit_url = os.getenv("DATABASE_URL")
        if explicit_url:
            return explicit_url
        password = quote_plus(self.db_password)
        return (
            f"mysql+pymysql://{self.db_user}:{password}@{self.db_host}:"
            f"{self.db_port}/{self.db_name}?charset={self.db_charset}"
        )

    @property
    def storage_path(self) -> Path:
        path = Path(self.storage_path_value)
        return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()

    @property
    def cors_origins(self) -> list[str]:
        return [item.strip() for item in self.cors_origins_value.split(",") if item.strip()]


settings = Settings()

