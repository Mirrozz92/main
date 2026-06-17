"""Webhook endpoints (per publisher) and delivery log."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.core.db.base import Base, TimestampMixin
from src.core.db.models.enums import WebhookDeliveryStatus, WebhookEventType
from src.core.db.types import pg_enum


class WebhookEndpoint(Base, TimestampMixin):
    __tablename__ = "webhook_endpoints"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    publisher_bot_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("publisher_bots.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    url: Mapped[str] = mapped_column(String(500), nullable=False)
    # Секрет для подписи HMAC-SHA256 в заголовке X-Signature
    secret: Mapped[str] = mapped_column(String(128), nullable=False)

    # Какие события слушаем (если пусто — все)
    enabled_events: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )

    is_active: Mapped[bool] = mapped_column(default=True, server_default="true", nullable=False)
    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_failure_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )


class WebhookDelivery(Base, TimestampMixin):
    __tablename__ = "webhook_deliveries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    endpoint_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("webhook_endpoints.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    event_type: Mapped[WebhookEventType] = mapped_column(
        pg_enum(WebhookEventType, "webhook_event_type"),
        nullable=False,
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    status: Mapped[WebhookDeliveryStatus] = mapped_column(
        pg_enum(WebhookDeliveryStatus, "webhook_delivery_status"),
        nullable=False,
        default=WebhookDeliveryStatus.PENDING,
        server_default=WebhookDeliveryStatus.PENDING.value,
        index=True,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_webhook_deliveries_pending", "status", "next_attempt_at"),
    )
