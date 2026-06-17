"""Repository for Advertiser entity."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db.models import Advertiser


class AdvertiserRepository:
    """Data-access for advertisers. Pure CRUD, no business logic."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_tg_id(self, tg_user_id: int) -> Advertiser | None:
        """Returns Advertiser or None."""
        result = await self.session.execute(
            select(Advertiser).where(Advertiser.tg_user_id == tg_user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, advertiser_id: int) -> Advertiser | None:
        result = await self.session.execute(
            select(Advertiser).where(Advertiser.id == advertiser_id)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        tg_user_id: int,
        tg_username: str | None,
        full_name: str | None,
    ) -> Advertiser:
        advertiser = Advertiser(
            tg_user_id=tg_user_id,
            tg_username=tg_username,
            full_name=full_name,
        )
        self.session.add(advertiser)
        await self.session.flush()
        return advertiser
