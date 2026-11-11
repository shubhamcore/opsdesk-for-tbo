"""Application configuration — environment driven, no credentials in source."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent          # .../OpsDesk
BACKEND_DIR = BASE_DIR / "backend"


class Settings:
    """Lightweight settings object (no external dependency required)."""

    def __init__(self) -> None:
        self.app_name: str = os.getenv("OPSDESK_APP_NAME", "OpsDesk for TBO")
        self.secret_key: str = os.getenv("OPSDESK_SECRET_KEY", "dev-insecure-change-me")
        self.database_url: str = os.getenv(
            "OPSDESK_DATABASE_URL", f"sqlite:///{BASE_DIR / 'database' / 'opsdesk.db'}"
        )
        self.token_ttl_minutes: int = int(os.getenv("OPSDESK_TOKEN_TTL_MINUTES", "720"))
        self.enable_demo_role_switch: bool = os.getenv(
            "OPSDESK_ENABLE_ROLE_SWITCH", "true"
        ).lower() in {"1", "true", "yes"}
        # Demo-only affordance: a single documented password for the seeded
        # synthetic identities. Gate with OPSDESK_ENABLE_ROLE_SWITCH=false and
        # set OPSDESK_DEMO_PASSWORD to something else for any shared deployment.
        self.demo_password: str = os.getenv("OPSDESK_DEMO_PASSWORD", "OpsDesk#2026")
        self.export_dir: Path = Path(os.getenv("OPSDESK_EXPORT_DIR", BASE_DIR / "exports"))
        self.model_path: Path = Path(
            os.getenv(
                "OPSDESK_MODEL_PATH",
                BASE_DIR / "ai_models" / "saved_models" / "intent_pipeline.joblib",
            )
        )
        self.frontend_dist: Path = BACKEND_DIR / "static"
        self.export_batch_size: int = int(os.getenv("OPSDESK_EXPORT_BATCH_SIZE", "5000"))
        # Production knobs
        self.rate_limit_per_minute: int = int(os.getenv("OPSDESK_RATE_LIMIT_PER_MINUTE", "60"))
        self.environment: str = os.getenv("OPSDESK_ENV", "development")
        # Extension point for a future hosted model. Unimplemented on purpose:
        # the platform does not claim a capability it does not ship.
        self.llm_endpoint: str | None = os.getenv("OPSDESK_LLM_ENDPOINT") or None
        self.cors_origins: list[str] = os.getenv(
            "OPSDESK_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
