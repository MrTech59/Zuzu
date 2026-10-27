"""Zuzu application configuration.

All configuration comes from environment variables (12-factor). Secrets are never
logged; see zuzu.logging for the redaction filter that complements this.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Environments in which an unset ZUZU_API_KEY is tolerated (localhost-only dev).
DEV_ENVIRONMENTS = frozenset({"development", "dev", "test"})


class Settings(BaseSettings):
    """Zuzu settings loaded from environment (.env supported)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = Field(default="development")
    app_host: str = Field(default="127.0.0.1")
    app_port: int = Field(default=8000)
    log_level: str = Field(default="INFO")

    # --- Auth ---------------------------------------------------------------
    # Bearer token for /api/v1 endpoints. Required whenever set, or whenever the
    # app is not running in a development environment.
    zuzu_api_key: str | None = Field(default=None)

    # --- NVIDIA provider -----------------------------------------------------
    nvidia_api_key: str | None = Field(default=None)
    nvidia_base_url: str = Field(default="https://integrate.api.nvidia.com/v1")
    nvidia_model: str | None = Field(default=None)
    # Which provider implementation to use: "nvidia" (real) or "mock".
    ai_provider: str = Field(default="nvidia")
    nvidia_timeout_seconds: float = Field(default=60.0, ge=1.0, le=600.0)
    nvidia_max_retries: int = Field(default=2, ge=0, le=10)
    nvidia_connect_timeout_seconds: float = Field(default=10.0, ge=1.0, le=120.0)

    # --- Database -------------------------------------------------------------
    # Postgres in real deployments (postgresql+psycopg://...); SQLite is
    # supported only for unit tests / offline development convenience.
    database_url: str = Field(default="sqlite+aiosqlite:///./zuzu-dev.db")

    # --- MCP ------------------------------------------------------------------
    mcp_enabled: bool = Field(default=False, alias="ZUZU_MCP_ENABLED")
    mcp_server_url: str = Field(default="", alias="ZUZU_MCP_SERVER_URL")
    mcp_transport: str = Field(default="", alias="ZUZU_MCP_TRANSPORT")
    mcp_connect_timeout_seconds: float = Field(
        default=10.0, alias="ZUZU_MCP_CONNECT_TIMEOUT_SECONDS", ge=1.0, le=120.0
    )
    mcp_request_timeout_seconds: float = Field(
        default=30.0, alias="ZUZU_MCP_REQUEST_TIMEOUT_SECONDS", ge=1.0, le=300.0
    )

    # --- Task / orchestration limits -------------------------------------------
    task_max_steps: int = Field(default=12, ge=1, le=200)
    task_timeout_seconds: int = Field(default=600, ge=5, le=36000)
    approval_ttl_seconds: int = Field(default=900, ge=5, le=86400)

    # --- Chat limits ------------------------------------------------------------
    chat_max_message_chars: int = Field(default=32000, ge=1, le=1_000_000)
    chat_history_limit: int = Field(default=40, ge=1, le=200)

    # --- Memory -----------------------------------------------------------------
    memory_max_chars: int = Field(default=4000, ge=1, le=100000)

    @field_validator("ai_provider")
    @classmethod
    def _validate_provider(cls, v: str) -> str:
        allowed = {"nvidia", "mock"}
        if v not in allowed:
            raise ValueError(f"AI_PROVIDER must be one of {sorted(allowed)}")
        return v

    @field_validator("app_env")
    @classmethod
    def _validate_env(cls, v: str) -> str:
        allowed = {"development", "dev", "test", "production", "prod"}
        if v not in allowed:
            raise ValueError("APP_ENV must be one of development|dev|test|production|prod")
        return v.lower()

    @property
    def is_dev(self) -> bool:
        return self.app_env in DEV_ENVIRONMENTS

    @property
    def auth_enforced(self) -> bool:
        """Auth is enforced when a key is configured OR outside dev mode."""
        return bool(self.zuzu_api_key) or not self.is_dev

    @property
    def resolved_nvidia_model(self) -> str:
        return self.nvidia_model or "meta/llama-3.3-70b-instruct"

    def assert_runnable(self) -> None:
        """Refuse to serve protected API surface without authentication in prod."""
        if not self.auth_enforced:
            # Only reachable when api key unset AND env is dev; dev is allowed.
            return
        if self.is_dev is False and not self.zuzu_api_key:
            raise RuntimeError("ZUZU_API_KEY must be set when APP_ENV is production.")


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor used by the application."""
    return Settings()  # type: ignore[call-arg]


def reset_settings_cache() -> None:
    """Clear the cached settings (used by tests)."""
    get_settings.cache_clear()
