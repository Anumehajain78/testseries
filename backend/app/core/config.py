"""Application settings.

Everything environment-dependent is read here and nowhere else, so deploying to
the college LAN is a matter of environment variables rather than code edits.

No secret has a usable production default. ``jwt_secret`` deliberately ships a
value that is obviously a placeholder, and :meth:`Settings.check_production`
refuses to start with it once the environment is not development.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "insecure-development-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="EXAM_",
        extra="ignore",
    )

    environment: Literal["development", "test", "staging", "production"] = "development"

    # Port 5433 matches docker-compose: a college machine may already be running
    # Postgres on the default port.
    database_url: PostgresDsn = Field(
        default="postgresql+psycopg://exam:exam_local_dev@localhost:5433/exam_control"
    )
    database_echo: bool = False

    jwt_secret: str = DEV_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = Field(default=30, ge=1, le=720)
    # Long enough to outlast a three-hour paper plus overrun, so a candidate is
    # never logged out mid-exam.
    refresh_token_hours: int = Field(default=12, ge=1, le=168)
    machine_token_hours: int = Field(default=24, ge=1, le=168)

    # Liveness thresholds. A workstation is 'warning' once it misses a couple of
    # beats and 'offline' when it has clearly gone away, rather than flickering
    # red on a single dropped packet.
    heartbeat_interval_seconds: int = Field(default=10, ge=1)
    heartbeat_warning_seconds: int = Field(default=30, ge=1)
    heartbeat_offline_seconds: int = Field(default=90, ge=1)

    cors_origins: list[str] = Field(default=["http://localhost:3000", "http://localhost:3001"])

    @field_validator("heartbeat_offline_seconds")
    @classmethod
    def _offline_after_warning(cls, value: int, info) -> int:
        warning = info.data.get("heartbeat_warning_seconds")
        if warning is not None and value <= warning:
            raise ValueError("heartbeat_offline_seconds must exceed heartbeat_warning_seconds")
        return value

    @property
    def is_production(self) -> bool:
        return self.environment in ("staging", "production")

    def check_production(self) -> None:
        """Fail fast rather than serve an exam with a known signing key."""
        if self.is_production and self.jwt_secret == DEV_JWT_SECRET:
            raise RuntimeError(
                "EXAM_JWT_SECRET is still the development default. "
                "Set a real secret before running outside development."
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
