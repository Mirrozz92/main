"""Transaction — double-entry бухгалтерия для всех денежных операций.

Каждое движение денег в системе создаёт запись. Это даёт нам:
- Полный аудит
- Возможность пересчитать балансы из истории
- Дебаг (что/когда/откуда/куда)
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.core.db.base import Base, TimestampMixin
from src.core.db.types import pg_enum
from src.core.db.models.enums import TransactionStatus, TransactionType


class Transaction(Base, TimestampMixin):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    type: Mapped[TransactionType] = mapped_column(
        pg_enum(TransactionType, "transaction_type"),
        nullable=False,
        index=True,
    )
    status: Mapped[TransactionStatus] = mapped_column(
        pg_enum(TransactionStatus, "transaction_status"),
        nullable=False,
        default=TransactionStatus.COMPLETED,
        server_default=TransactionStatus.COMPLETED.value,
    )

    # Сумма (положительная — приход, отрицательная — расход для владельца счёта)
    amount_rub: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)

    # Один из двух subject'ов (advertiser ИЛИ publisher, не оба)
    advertiser_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("advertisers.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    publisher_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("publishers.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    # Связанные сущности (опциональные)
    campaign_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("campaigns.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    resource_issue_link_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("resource_issues.link_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # External reference (например, invoice_id из CryptoBot)
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    # Описание для админки и аудита
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    # Идемпотентность: при retry мы не создаём дубль
    idempotency_key: Mapped[str | None] = mapped_column(
        String(128), nullable=True, unique=True, index=True
    )

    __table_args__ = (
        CheckConstraint(
            "(advertiser_id IS NOT NULL) OR (publisher_id IS NOT NULL)",
            name="subject_required",
        ),
        CheckConstraint(
            "NOT (advertiser_id IS NOT NULL AND publisher_id IS NOT NULL)",
            name="single_subject",
        ),
        Index("ix_transactions_advertiser_time", "advertiser_id", "created_at"),
        Index("ix_transactions_publisher_time", "publisher_id", "created_at"),
    )
