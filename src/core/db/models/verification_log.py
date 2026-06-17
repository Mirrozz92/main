"""VerificationLog — лог всех проверок подписок (для аудита и аналитики).

Таблица растёт быстро (потенциально миллионы строк/день), поэтому
партиционируем по дате (`created_at`) на уровне миграции.

Note: реальный составной PK (id, created_at) для партиционированной таблицы
создаётся через `CREATE TABLE ... PARTITION BY RANGE (created_at)` в миграции.
В ORM используем `(id, created_at)` как mapper_args primary_key — это нужно
SQLAlchemy чтобы построить mapper, но не влияет на DDL (его делает миграция).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.core.db.base import Base


class VerificationLog(Base):
    """Лог одной верификации (вызова Telegram API для проверки)."""

    __tablename__ = "verification_logs"

    # Составной PK: для партиционированной таблицы PostgreSQL требует,
    # чтобы все колонки partition key входили в PK.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
        server_default=func.now(),
        nullable=False,
    )

    # Что проверяли
    resource_issue_link_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    campaign_resource_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    user_tg_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checker_bot_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("checker_bots.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Результат
    is_subscribed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    member_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Timing (для мониторинга latency)
    duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    raw_response: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # NB: __table_args__ не используем, т.к. таблица создаётся вручную через
    # raw SQL в миграции (PARTITION BY RANGE). ORM здесь — только для запросов.
