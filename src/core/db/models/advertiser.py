"""Advertiser model — пользователи, заказывающие рекламу."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import BigInteger, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.db.base import Base, TimestampMixin


class Advertiser(Base, TimestampMixin):
    __tablename__ = "advertisers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Telegram identity
    tg_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    tg_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Balances в рублях (NUMERIC(18, 4))
    balance_rub: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    reserved_rub: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    total_spent_rub: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )

    # Status
    is_banned: Mapped[bool] = mapped_column(default=False, server_default="false", nullable=False)
    ban_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<Advertiser id={self.id} tg={self.tg_user_id} balance={self.balance_rub}>"
