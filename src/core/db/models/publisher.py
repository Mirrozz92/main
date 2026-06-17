"""Publisher — владельцы ботов, использующие наш API.

Иерархия:
  Publisher (1 на TG-юзера)
   └── PublisherBot (N)            # каждый бот партнёра — отдельная сущность
        └── PublisherApiToken (1, активный)  # текущий API-ключ для бота
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, LargeBinary, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.db.base import Base, TimestampMixin


class Publisher(Base, TimestampMixin):
    __tablename__ = "publishers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Telegram identity (владелец)
    tg_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    tg_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Display name / project (legacy field — теперь mostly unused)
    project_name: Mapped[str] = mapped_column(String(128), nullable=False, default="Default", server_default="Default")

    # Balances (рубли)
    balance_rub: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    hold_rub: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    total_earned_rub: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    total_paid_out_rub: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )

    # Reputation
    retention_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("100"), server_default="100"
    )
    verified_subs_in_window: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    retention_calculated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Reputation rating 0.0..10.0 (cold-start default 8.0)
    rating: Mapped[Decimal] = mapped_column(
        Numeric(3, 1), nullable=False, default=Decimal("8.0"), server_default="8.0"
    )
    rating_calculated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Total verified subs across all time (volume score for rating)
    verified_subs_total: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )

    # Flags
    is_vip: Mapped[bool] = mapped_column(default=False, server_default="false", nullable=False)
    is_banned: Mapped[bool] = mapped_column(default=False, server_default="false", nullable=False)
    ban_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Cumulative counters
    total_subscriptions: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    total_unsubscriptions: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )

    bots: Mapped[list["PublisherBot"]] = relationship(
        "PublisherBot", back_populates="publisher", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Publisher id={self.id} balance={self.balance_rub}>"


class PublisherBot(Base, TimestampMixin):
    """A bot owned by a Publisher — the unit of integration with FastSub.

    Each PublisherBot has its own API token, settings, and statistics.
    """

    __tablename__ = "publisher_bots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    publisher_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("publishers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Human-readable name (always required; visible in publisher's UI)
    name: Mapped[str] = mapped_column(String(128), nullable=False)

    # Optional: real Telegram bot identity (filled if user provided TG bot token)
    tg_bot_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    tg_bot_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Bot Token encrypted with Fernet; raw bytes
    tg_bot_token_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    # Settings
    sponsors_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1",
        comment="How many sponsors to issue per request-op call (1..10)",
    )
    list_ttl_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3600, server_default="3600",
        comment="Sponsor list TTL in seconds (300..604800, default 1h)",
    )

    # Moderation (added in migration 0009)
    is_moderated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false",
        comment="True if moderator approved this bot",
    )

    # Extra publisher-side settings (added in migration 0010)
    get_links: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false",
        comment="True = return links via API; False = send OP block ourselves",
    )
    show_quiz: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false",
        comment="Show onboarding quiz to end users for targeting",
    )
    excluded_themes: Mapped[Any] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]",
        comment="Ad themes excluded from this bot (JSON array of strings)",
    )

    # Status
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    # Aggregated stats (могут обновляться триггерами/cron'ом в этапах 3c-3d)
    total_requests: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    total_issued: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    total_verified: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    total_earned_rub: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )

    publisher: Mapped[Publisher] = relationship("Publisher", back_populates="bots")
    api_tokens: Mapped[list["PublisherApiToken"]] = relationship(
        "PublisherApiToken", back_populates="publisher_bot", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_publisher_bots_active", "is_active", "publisher_id"),
    )

    def __repr__(self) -> str:
        return f"<PublisherBot id={self.id} name={self.name}>"


class PublisherApiToken(Base, TimestampMixin):
    """API token, attached to a PublisherBot.

    Each PublisherBot has exactly one ACTIVE token at a time.
    Regenerating creates a new active token and revokes the old one.
    """

    __tablename__ = "publisher_api_tokens"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    publisher_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("publishers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Nullable for backwards compat (migration sets this on existing rows)
    publisher_bot_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("publisher_bots.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    token_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    label: Mapped[str] = mapped_column(String(128), nullable=False, default="Default")

    is_active: Mapped[bool] = mapped_column(default=True, server_default="true", nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    requests_count: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )

    publisher: Mapped[Publisher] = relationship("Publisher")
    publisher_bot: Mapped["PublisherBot | None"] = relationship("PublisherBot", back_populates="api_tokens")

    __table_args__ = (
        Index("ix_publisher_api_tokens_active", "is_active", "publisher_id"),
        Index("ix_publisher_api_tokens_bot_active", "publisher_bot_id", "is_active"),
    )
