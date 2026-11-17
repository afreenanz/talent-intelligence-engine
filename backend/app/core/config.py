"""Application settings, loaded from environment variables (and a local .env file).

Every secret and every environment-specific value lives here. Nothing else in the codebase
reads os.environ directly, so this file is the full list of what the app can be configured with.
"""

from enum import StrEnum
from functools import lru_cache

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_JWT_SECRET = "dev-only-insecure-secret-change-me-0123456789"  # noqa: S105


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # backend/.env first, then the repo-root .env (where docker compose also reads it)
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Environment = Environment.DEVELOPMENT
    app_name: str = "Talent Intelligence Engine"

    database_url: str = "postgresql+psycopg://tie:tie_dev_password@localhost:5433/tie"
    redis_url: str = "redis://localhost:6380/0"

    jwt_secret: SecretStr = SecretStr(_DEV_JWT_SECRET)
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "talent-engine"
    access_token_ttl_minutes: int = Field(default=15, ge=1, le=120)
    refresh_token_ttl_days: int = Field(default=14, ge=1, le=90)

    cors_origins: list[str] = ["http://localhost:5173"]
    log_level: str = "INFO"
    log_json: bool = False

    @model_validator(mode="after")
    def _refuse_weak_secrets(self) -> "Settings":
        secret = self.jwt_secret.get_secret_value()
        if len(secret) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        if self.environment is Environment.PRODUCTION and secret == _DEV_JWT_SECRET:
            raise ValueError("JWT_SECRET must be set to a random value in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
