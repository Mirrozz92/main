"""Repository for EndUser."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db.models import EndUser


class EndUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_tg_id(self, user_tg_id: int) -> EndUser | None:
        result = await self.session.execute(
            select(EndUser).where(EndUser.user_tg_id == user_tg_id)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        user_tg_id: int,
        gender: str | None,
        age_range: str | None,
        country_code: str | None,
        country_other: str | None,
        onboarded_via_bot_id: int | None,
    ) -> EndUser:
        now = datetime.now(timezone.utc)
        user = EndUser(
            user_tg_id=user_tg_id,
            gender=gender,
            age_range=age_range,
            country_code=country_code,
            country_other=country_other,
            consent_at=now,
            onboarded_via_bot_id=onboarded_via_bot_id,
            first_seen_at=now,
            last_active_at=now,
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def touch(self, user: EndUser) -> None:
        user.last_active_at = datetime.now(timezone.utc)
