"""CheckerBot — пул ботов для верификации подписок.

На старте у нас один бот, но архитектура заложена под несколько:
- Каждый ресурс привязан к конкретному checker_bot_id
- При добавлении нового ресурса выбираем бота с минимальной нагрузкой
- Лимит Telegram ~500 чатов на бота — детектим и переключаем
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.core.db.base import Base, TimestampMixin


class CheckerBot(Base, TimestampMixin):
    __tablename__ = "checker_bots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Telegram bot identity
    tg_bot_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # Токен НЕ храним в БД — только индекс в .env (CHECKER_BOT_TOKENS)
    token_index: Mapped[int] = mapped_column(Integer, nullable=False)

    # Load tracking
    active_resources_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # Soft limit (закладываем 400, чтобы запас был до 500)
    max_resources: Mapped[int] = mapped_column(
        Integer, nullable=False, default=400, server_default="400"
    )

    # Status
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true", nullable=False)
    last_health_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)

    def __repr__(self) -> str:
        return f"<CheckerBot id={self.id} @{self.username} load={self.active_resources_count}/{self.max_resources}>"
