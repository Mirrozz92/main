"""ResourceIssue — факт выдачи конкретного ресурса конкретному юзеру.

Это центральная таблица системы. Один issue = один link_id, выданный
одному юзеру одного паблишера для одного ресурса одной кампании.

Pipeline:
    pending → subscribed → verified → paid
            ↘ expired
            ↘ unsubscribed → reverted
            ↘ invalid
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.core.db.base import Base, TimestampMixin
from src.core.db.models.enums import IssueStatus
from src.core.db.types import pg_enum


class ResourceIssue(Base, TimestampMixin):
    __tablename__ = "resource_issues"

    # link_id — публичный идентификатор для API, formato: "lnk_<24hex>"
    link_id: Mapped[str] = mapped_column(String(32), primary_key=True)

    # task_id — группа issue-ов, выданных одним запросом /request-op
    task_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    # Кому выдан
    publisher_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("publishers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # ID API-токена, которым был сделан запрос (для аудита)
    publisher_token_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("publisher_api_tokens.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # ID PublisherBot — бот партнёра, выдавший задачу (добавлено в 3a v2)
    publisher_bot_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("publisher_bots.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    # TG ID конечного юзера (от паблишера)
    user_tg_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Что выдано
    campaign_resource_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("campaign_resources.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # Финансы: фиксируем snapshot цены и нашей комиссии на момент выдачи
    reward_rub: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    publisher_payout_rub: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    platform_commission_rub: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    # Retention-бонус (если паблишер квалифицируется)
    retention_bonus_rub: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )

    # Status machine
    status: Mapped[IssueStatus] = mapped_column(
        pg_enum(IssueStatus, name="issue_status"),
        nullable=False,
        default=IssueStatus.PENDING,
        server_default=IssueStatus.PENDING.value,
        index=True,
    )

    # Timestamps жизненного цикла
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    subscribed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # hold_until фиксируется в момент subscribed_at на основе текущего retention паблишера
    hold_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    unsubscribed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Snapshot контекста юзера (premium, lang, etc) на момент выдачи — для аналитики
    user_context: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    # Сколько раз вызвался /check-resource (для идемпотентности и анти-абуза)
    check_calls_count: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )

    __table_args__ = (
        # Глобальный constraint: один юзер не может получить ресурс дважды
        # (даже через разных паблишеров) — первый, кто выдал, "застолбил" юзера.
        UniqueConstraint(
            "user_tg_id", "campaign_resource_id",
            name="uq_user_resource_global",
        ),
        CheckConstraint("expires_at > issued_at", name="expires_after_issued"),
        CheckConstraint("reward_rub >= 0", name="reward_non_negative"),
        CheckConstraint("publisher_payout_rub >= 0", name="payout_non_negative"),
        CheckConstraint("platform_commission_rub >= 0", name="commission_non_negative"),
        # Hot index: для воркера, проверяющего отписки
        Index(
            "ix_resource_issues_hold_pending",
            "hold_until",
            postgresql_where=(status == IssueStatus.SUBSCRIBED),
        ),
        # Hot index: для воркера, истекающего pending
        Index(
            "ix_resource_issues_expiring",
            "expires_at",
            postgresql_where=(status == IssueStatus.PENDING),
        ),
        # Для запросов истории юзера
        Index("ix_resource_issues_user_history", "user_tg_id", "publisher_id", "issued_at"),
        # Для запросов статистики паблишера
        Index("ix_resource_issues_publisher_status", "publisher_id", "status", "issued_at"),
        # Для запросов по task_id (получить все resources одного задания)
        Index("ix_resource_issues_task", "task_id"),
    )
