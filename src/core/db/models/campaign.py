"""Campaign и CampaignResource — рекламные кампании и их ресурсы."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.db.base import Base, TimestampMixin
from src.core.db.types import pg_enum
from src.core.db.models.enums import (
    CampaignStatus,
    ResourceStatus,
    ResourceType,
    VerificationMethod,
)


class Campaign(Base, TimestampMixin):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    advertiser_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("advertisers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[CampaignStatus] = mapped_column(
        pg_enum(CampaignStatus, "campaign_status"),
        nullable=False,
        default=CampaignStatus.DRAFT,
        server_default=CampaignStatus.DRAFT.value,
        index=True,
    )

    # Бюджет (в рублях)
    budget_total_rub: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    budget_spent_rub: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    budget_reserved_rub: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )

    # Targeting (JSONB для гибкости — можно расширять без миграций)
    # Структура: {"countries": ["RU","UA"], "premium": true/false/null,
    #             "has_avatar": bool, "min_account_age_days": int, ...}
    targeting: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    # Moderation
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    moderated_by_admin_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    moderated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Schedule
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    resources: Mapped[list[CampaignResource]] = relationship(
        "CampaignResource",
        back_populates="campaign",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint("budget_total_rub > 0", name="budget_total_positive"),
        CheckConstraint("budget_spent_rub >= 0", name="budget_spent_non_negative"),
        CheckConstraint("budget_reserved_rub >= 0", name="budget_reserved_non_negative"),
        CheckConstraint(
            "budget_spent_rub + budget_reserved_rub <= budget_total_rub",
            name="budget_not_overdrawn",
        ),
        Index("ix_campaigns_advertiser_status", "advertiser_id", "status"),
    )


class CampaignResource(Base, TimestampMixin):
    """Конкретный ресурс (канал/группа/бот) в кампании."""

    __tablename__ = "campaign_resources"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    campaign_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Назначенный checker-бот (из пула)
    checker_bot_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("checker_bots.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    type: Mapped[ResourceType] = mapped_column(
        pg_enum(ResourceType, "resource_type"),
        nullable=False,
    )

    # Telegram identity
    tg_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_private: Mapped[bool] = mapped_column(default=False, server_default="false", nullable=False)

    # Invite link, созданная нашим checker-ботом (уникальная, для трекинга)
    invite_link: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    invite_link_name: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Для bot_start — реф-параметр
    start_param: Mapped[str | None] = mapped_column(String(64), nullable=True)

    verify_method: Mapped[VerificationMethod] = mapped_column(
        pg_enum(VerificationMethod, "verification_method"),
        nullable=False,
    )

    # Цена за подписчика
    reward_rub: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)

    # Целевые подписчики
    target_subscribers: Mapped[int] = mapped_column(BigInteger, nullable=False)
    actual_subscribers: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )

    status: Mapped[ResourceStatus] = mapped_column(
        pg_enum(ResourceStatus, "resource_status"),
        nullable=False,
        default=ResourceStatus.PENDING,
        server_default=ResourceStatus.PENDING.value,
        index=True,
    )

    # Per-resource targeting overrides (опционально, иначе берём из campaign.targeting)
    targeting_override: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    campaign: Mapped[Campaign] = relationship("Campaign", back_populates="resources")

    __table_args__ = (
        CheckConstraint("reward_rub > 0", name="reward_positive"),
        CheckConstraint("target_subscribers > 0", name="target_positive"),
        CheckConstraint("actual_subscribers >= 0", name="actual_non_negative"),
        Index("ix_campaign_resources_active", "status", "checker_bot_id"),
        Index(
            "ix_campaign_resources_rotation",
            "status",
            "reward_rub",
            postgresql_where=(status == ResourceStatus.ACTIVE),
        ),
    )
