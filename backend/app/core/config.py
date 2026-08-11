"""Application settings loaded from environment variables / .env files."""

from decimal import Decimal
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the Nuotao AI OS backend.

    Values are read from environment variables (mapped case-insensitively,
    e.g. ``DATABASE_URL`` -> ``database_url``) or from ``.env`` files in the
    current working directory or its parent.
    """

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Nuotao AI OS"
    app_version: str = "0.1.0"
    environment: str = "development"  # development | staging | production
    debug: bool = False
    api_prefix: str = "/api/v1"
    log_level: str = "INFO"

    database_url: str = (
        "postgresql+asyncpg://nuotao:nuotao_dev_password@localhost:5432/nuotao"
    )
    redis_url: str = "redis://localhost:6379/0"

    # WooCommerce webhook consumer secret (HMAC-SHA256 signature verification).
    # MUST be overridden in staging/production environments.
    woocommerce_webhook_secret: str = "dev-webhook-secret-change-me"

    # Payment fee estimation used when the payment provider fee is unknown.
    payment_fee_rate: Decimal = Decimal("0.029")
    payment_fee_fixed: Decimal = Decimal("0.30")

    @property
    def is_production(self) -> bool:
        """Return True when running in a production environment."""
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings singleton."""
    return Settings()
