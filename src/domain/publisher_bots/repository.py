"""Repository for PublisherBot."""

from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.db.models import PublisherBot


class PublisherBotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, bot_id: int) -> PublisherBot | None:
        result = await self.session.execute(
            select(PublisherBot).where(PublisherBot.id == bot_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id_with_tokens(self, bot_id: int) -> PublisherBot | None:
        result = await self.session.execute(
            select(PublisherBot)
            .where(PublisherBot.id == bot_id)
            .options(selectinload(PublisherBot.api_tokens))
        )
        return result.scalar_one_or_none()

    async def list_for_publisher(self, publisher_id: int) -> list[PublisherBot]:
        result = await self.session.execute(
            select(PublisherBot)
            .where(PublisherBot.publisher_id == publisher_id)
            .order_by(desc(PublisherBot.created_at))
        )
        return list(result.scalars().all())

    async def count_for_publisher(self, publisher_id: int) -> int:
        from sqlalchemy import func
        result = await self.session.execute(
            select(func.count(PublisherBot.id)).where(
                PublisherBot.publisher_id == publisher_id
            )
        )
        return result.scalar_one()

    async def get_by_tg_bot_id(self, tg_bot_id: int) -> PublisherBot | None:
        """Find by Telegram bot id — used to prevent same bot added twice."""
        result = await self.session.execute(
            select(PublisherBot).where(PublisherBot.tg_bot_id == tg_bot_id)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        publisher_id: int,
        name: str,
        tg_bot_id: int | None = None,
        tg_bot_username: str | None = None,
        tg_bot_token_encrypted: bytes | None = None,
        sponsors_count: int = 1,
        list_ttl_seconds: int = 3600,
    ) -> PublisherBot:
        bot = PublisherBot(
            publisher_id=publisher_id,
            name=name,
            tg_bot_id=tg_bot_id,
            tg_bot_username=tg_bot_username,
            tg_bot_token_encrypted=tg_bot_token_encrypted,
            sponsors_count=sponsors_count,
            list_ttl_seconds=list_ttl_seconds,
            is_active=True,
        )
        self.session.add(bot)
        await self.session.flush()
        return bot
