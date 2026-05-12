"""StockAI v2 — Configuration

Central config using pydantic-settings.
All secrets loaded from environment variables.
"""

from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── App ──
    app_name: str = "StockAI v2"
    app_version: str = "2.0.0"
    debug: bool = False

    # ── Server ──
    host: str = "0.0.0.0"
    port: int = int(os.getenv("PORT", "8080"))

    # ── Database ──
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/stockai",
    )

    # ── Redis ──
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # ── Security ──
    jwt_secret_key: str = os.getenv(
        "JWT_SECRET_KEY",
        "change-me-in-production-use-a-strong-random-key",
    )
    jwt_algorithm: str = "RS256"  # RS256 for production, HS256 fallback
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7
    bcrypt_rounds: int = 12

    # ── CORS ──
    cors_origins: list[str] = ["*"]

    # ── Rate Limit ──
    rate_limit_auth: int = 5  # requests per minute
    rate_limit_stock: int = 60  # requests per minute

    # ── Paths ──
    frontend_dir: Path = Path(__file__).parent.parent.parent / "frontend"
    audit_log_dir: Path = Path(__file__).parent.parent / "data" / "audit"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
