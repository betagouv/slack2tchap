"""Application configuration using pydantic-settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_INSECURE_SECRET_KEY = "32_bytes_super_secret_master_key_for_aes_gcm!!"


class Settings(BaseSettings):
    """Application configuration loaded from environment variables or .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database connection (PostgreSQL with asyncpg or SQLite for tests)
    database_url: str = Field(
        default="postgresql+asyncpg://slack2tchap:postgres_dev_password@localhost:5436/slack2tchap_dev",
        description="Async database connection string",
    )

    # Cryptographic master key for AES-256-GCM credentials encryption at rest
    secret_encryption_key: SecretStr = Field(
        default=SecretStr(DEFAULT_INSECURE_SECRET_KEY),
        description="Master encryption key used for AES-256-GCM encryption of sensitive database fields",
    )

    # Default Admin account seeded by Alembic / startup
    admin_email: str | None = Field(
        default="admin@tchap.gouv.fr",
        description="Default administrator email to seed into database",
    )
    admin_api_key: SecretStr | None = Field(
        default=None,
        description="Raw API key for the default administrator (hashed upon seeding in database)",
    )

    # Base public URL used to display webhook endpoints
    public_base_url: str = Field(
        default="http://localhost:8000",
        description="Public gateway base URL for webhook link generation",
    )

    # Matrix homeserver connection
    matrix_homeserver: str = Field(
        default="https://matrix.agent.tchap.gouv.fr",
        description="URL of the Matrix / Tchap homeserver",
    )
    matrix_auto_join: bool = Field(
        default=True,
        description="Whether to automatically join rooms upon invitation",
    )

    # Server configuration
    host: str = Field(default="0.0.0.0", description="Server bind host")
    port: int = Field(default=8000, description="Server bind port")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Logging level",
    )
    environment: str = Field(
        default="production",
        description="Application environment (development, staging, production)",
    )

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        """Disallow default insecure encryption key when running in production."""
        if (
            self.environment.strip().lower() == "production"
            and self.secret_encryption_key.get_secret_value() == DEFAULT_INSECURE_SECRET_KEY
        ):
            raise ValueError(
                "SECRET_ENCRYPTION_KEY must be explicitly set to a secure 256-bit key in production environment. "
                "The default development key is rejected."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings singleton."""
    return Settings()
