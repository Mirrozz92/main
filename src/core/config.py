"""Centralized configuration loaded from environment variables.

All settings are typed and validated at startup. If any required value is
missing or malformed, the application will fail fast with a clear error.
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import computed_field, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from .env and environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Project ---
    project_name: str = Field(default="fastsub")
    env: Literal["production", "development", "test"] = Field(default="development")
    debug: bool = Field(default=False)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")
    tz: str = Field(default="Europe/Moscow")

    # --- API ---
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    api_public_host: str = Field(default="95.85.251.42")
    api_workers: int = Field(default=4)

    # --- PostgreSQL ---
    postgres_host: str
    postgres_port: int = Field(default=5432)
    postgres_db: str
    postgres_user: str
    postgres_password: SecretStr

    pgbouncer_host: str = Field(default="pgbouncer")
    pgbouncer_port: int = Field(default=6432)

    # --- Redis ---
    redis_host: str = Field(default="redis")
    redis_port: int = Field(default=6379)
    redis_password: SecretStr
    redis_db_cache: int = Field(default=0)
    redis_db_taskiq: int = Field(default=1)
    redis_db_ratelimit: int = Field(default=2)

    # --- Public web URL (used in onboarding links etc) ---
    public_base_url: str = Field(
        default="https://fastsub.95-85-251-42.sslip.io",
        description="Public HTTPS base URL of FastSub (no trailing slash)",
    )

    # --- Telegram bots ---
    main_bot_token: SecretStr                                    # combined advertiser+publisher bot
    admin_bot_token: SecretStr
    advertiser_bot_token: SecretStr | None = Field(default=None)  # legacy: separate advertiser bot
    publisher_bot_token: SecretStr | None = Field(default=None)   # legacy: separate publisher bot
    checker_bot_tokens: str = Field(default="", description="Comma-separated tokens")

    # --- Admins ---
    admin_usernames: str = Field(default="", description="Comma-separated")
    admin_user_ids: str = Field(default="", description="Comma-separated")

    # --- CryptoBot ---
    cryptobot_token: SecretStr
    cryptobot_api_url: str = Field(default="https://pay.crypt.bot/api")
    cryptobot_webhook_secret: SecretStr

    # --- Crypto (для шифрования секретов в БД, например TG bot tokens партнёров) ---
    fernet_key: SecretStr | None = Field(default=None, description="Base64-encoded 32-byte key for Fernet")

    # --- Exchange rates ---
    exchange_rate_source: Literal["coingecko", "binance"] = Field(default="coingecko")
    exchange_rate_cache_ttl_seconds: int = Field(default=300)

    # --- Business rules ---
    min_campaign_topup_rub: Decimal = Field(default=Decimal("500"))
    min_payout_rub: Decimal = Field(default=Decimal("100"))
    platform_commission_percent: Decimal = Field(default=Decimal("25"))
    vip_commission_percent: Decimal = Field(default=Decimal("20"))
    retention_bonus_percent: Decimal = Field(default=Decimal("5"))
    retention_bonus_threshold: Decimal = Field(default=Decimal("90"))
    link_id_ttl_seconds: int = Field(default=3600)
    cold_start_hold_hours: int = Field(default=8)
    cold_start_min_subs: int = Field(default=50)
    retention_window_days: int = Field(default=7)

    # --- Subscription verification ---
    subscription_check_interval_hours: int = Field(default=4)
    hold_check_interval_minutes: int = Field(default=15)

    # --- Rate limiting ---
    rate_limit_per_second: int = Field(default=50)
    rate_limit_per_minute: int = Field(default=2000)

    # --- Webhooks ---
    webhook_timeout_seconds: int = Field(default=10)
    webhook_max_retries: int = Field(default=5)
    webhook_retry_backoff_seconds: int = Field(default=60)

    # --- Security ---
    secret_key: SecretStr

    # --- Backups ---
    backup_local_dir: str = Field(default="/var/backups/postgres")
    backup_local_retention_hours: int = Field(default=24)
    backup_remote_host: str = Field(default="")
    backup_remote_user: str = Field(default="")
    backup_remote_path: str = Field(default="")
    backup_remote_ssh_key: str = Field(default="/root/.ssh/backup_key")
    backup_tg_chat_id: str = Field(default="")

    # --- Monitoring ---
    prometheus_port: int = Field(default=9090)
    sentry_dsn: str = Field(default="")

    # --- Validators ---




    # --- Computed properties ---

    @property
    def postgres_dsn(self) -> str:
        """Direct connection to PostgreSQL (for migrations)."""
        pwd = self.postgres_password.get_secret_value()
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{pwd}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def postgres_dsn_sync(self) -> str:
        """Sync DSN for Alembic."""
        pwd = self.postgres_password.get_secret_value()
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{pwd}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def pgbouncer_dsn(self) -> str:
        """Pooled connection via pgbouncer (for application use)."""
        pwd = self.postgres_password.get_secret_value()
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{pwd}"
            f"@{self.pgbouncer_host}:{self.pgbouncer_port}/{self.postgres_db}"
        )

    @property
    def redis_url_cache(self) -> str:
        pwd = self.redis_password.get_secret_value()
        return f"redis://:{pwd}@{self.redis_host}:{self.redis_port}/{self.redis_db_cache}"

    @property
    def redis_url_taskiq(self) -> str:
        pwd = self.redis_password.get_secret_value()
        return f"redis://:{pwd}@{self.redis_host}:{self.redis_port}/{self.redis_db_taskiq}"

    @property
    def redis_url_ratelimit(self) -> str:
        pwd = self.redis_password.get_secret_value()
        return f"redis://:{pwd}@{self.redis_host}:{self.redis_port}/{self.redis_db_ratelimit}"

    @property
    def is_production(self) -> bool:
        return self.env == "production"



    @computed_field  # type: ignore[prop-decorator]
    @property
    def checker_bot_tokens_list(self) -> list[SecretStr]:
        if not self.checker_bot_tokens.strip():
            return []
        return [SecretStr(t.strip()) for t in self.checker_bot_tokens.split(",") if t.strip()]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def admin_usernames_list(self) -> list[str]:
        if not self.admin_usernames.strip():
            return []
        return [u.strip().lstrip("@") for u in self.admin_usernames.split(",") if u.strip()]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def admin_user_ids_list(self) -> list[int]:
        if not self.admin_user_ids.strip():
            return []
        return [int(i.strip()) for i in self.admin_user_ids.split(",") if i.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()  # type: ignore[call-arg]
