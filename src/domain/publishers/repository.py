"""Repository for Publisher entity."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db.models import Publisher


class PublisherRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, publisher_id: int) -> Publisher | None:
        result = await self.session.execute(
            select(Publisher).where(Publisher.id == publisher_id)
        )
        return result.scalar_one_or_none()

    async def get_by_tg_id(self, tg_user_id: int) -> Publisher | None:
        result = await self.session.execute(
            select(Publisher).where(Publisher.tg_user_id == tg_user_id)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        tg_user_id: int,
        tg_username: str | None,
        full_name: str | None,
        project_name: str,
    ) -> Publisher:
        publisher = Publisher(
            tg_user_id=tg_user_id,
            tg_username=tg_username,
            full_name=full_name,
            project_name=project_name,
        )
        self.session.add(publisher)
        await self.session.flush()
        return publisher
