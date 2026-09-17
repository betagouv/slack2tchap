"""Configuration settings for slack2tchap-stateless via pydantic-settings."""

from functools import lru_cache

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_INSECURE_SECRET_KEY = (
    "insecure-dev-master-key-must-be-changed-in-production-0123456789abcdef"
)


class Settings(BaseSettings):
    """Stateless micro-service configuration loaded from environment variables or .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # General
    environment: str = Field(
        default="production",
        description="Application environment (development, staging, production)",
    )
    log_level: str = Field(default="INFO")
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    public_base_url: str = Field(default="http://localhost:8000")

    # Cryptography
    secret_encryption_key: SecretStr = Field(
        default=SecretStr(DEFAULT_INSECURE_SECRET_KEY),
        description="Master encryption key used for stateless AES-256-GCM tokens.",
    )

    # Matrix default homeserver
    matrix_homeserver: str = Field(
        default="https://matrix.agent.tchap.gouv.fr",
        description="Default Matrix homeserver URL if domain cannot be resolved.",
    )
    matrix_auto_join: bool = Field(
        default=True,
        description="Whether ephemeral bot automatically joins room if not already joined.",
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
    """Cached settings instance."""
    return Settings()
