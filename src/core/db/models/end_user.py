"""EndUser model — конечные пользователи (юзеры партнёрских ботов).

Хранит минимум PII для будущего таргетинга:
- Пол (опционально)
- Возрастной диапазон
- Страна
- Согласие на обработку (timestamp)

IP, точная дата рождения, имя — НЕ собираются (152-ФЗ / GDPR compliance).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from src.core.db.base import Base


class EndUser(Base):
    __tablename__ = "end_users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Telegram identity (юзер в партнёрском боте)
    user_tg_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False, index=True,
    )

    # Demographics — все опциональные, юзер может пропустить
    gender: Mapped[str | None] = mapped_column(
        String(20), nullable=True,
        comment="male | female | undisclosed",
    )
    age_range: Mapped[str | None] = mapped_column(
        String(10), nullable=True,
        comment="under_14 | 14_16 | 16_18 | 18_plus",
    )
    country_code: Mapped[str | None] = mapped_column(
        String(8), nullable=True,
        comment="RU | UA | BY | KZ | OTHER",
    )
    country_other: Mapped[str | None] = mapped_column(
        String(64), nullable=True,
        comment="Свободный текст, если country_code='OTHER'",
    )

    # GDPR/152-ФЗ — фиксируем момент согласия
    consent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )

    # Audience signals reported by publisher (NULL = not reported).
    # Used for advertiser audience filters (require_premium etc.).
    has_telegram_premium: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    has_profile_photo: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    has_username: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    has_bio: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    has_stories: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    audience_reported_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # Какой партнёрский бот привёл юзера (для аналитики)
    onboarded_via_bot_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("publisher_bots.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )

    __table_args__ = (
        Index("ix_end_users_gender", "gender"),
        Index("ix_end_users_age_range", "age_range"),
        Index("ix_end_users_country", "country_code"),
    )

    def __repr__(self) -> str:
        return f"<EndUser id={self.id} tg={self.user_tg_id} country={self.country_code}>"
