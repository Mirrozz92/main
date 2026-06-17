"""Repository for CheckerBot — pool of bots used to verify subscriptions."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db.models import CheckerBot


class CheckerBotRepository:
    """Data-access for checker bots pool."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, bot_id: int) -> CheckerBot | None:
        result = await self.session.execute(
            select(CheckerBot).where(CheckerBot.id == bot_id)
        )
        return result.scalar_one_or_none()

    async def get_by_tg_id(self, tg_bot_id: int) -> CheckerBot | None:
        result = await self.session.execute(
            select(CheckerBot).where(CheckerBot.tg_bot_id == tg_bot_id)
        )
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> CheckerBot | None:
        result = await self.session.execute(
            select(CheckerBot).where(CheckerBot.username == username.lstrip("@"))
        )
        return result.scalar_one_or_none()

    async def list_active(self) -> list[CheckerBot]:
        result = await self.session.execute(
            select(CheckerBot)
            .where(CheckerBot.is_active.is_(True))
            .order_by(CheckerBot.active_resources_count.asc())
        )
        return list(result.scalars().all())

    async def pick_least_loaded(self) -> CheckerBot | None:
        """Pick the active bot with the fewest assigned resources, with capacity."""
        result = await self.session.execute(
            select(CheckerBot)
            .where(
                CheckerBot.is_active.is_(True),
                CheckerBot.active_resources_count < CheckerBot.max_resources,
            )
            .order_by(CheckerBot.active_resources_count.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        *,
        tg_bot_id: int,
        username: str,
        token_index: int,
    ) -> CheckerBot:
        """Create or update bot record by tg_bot_id.

        Used at startup to register tokens from CHECKER_BOT_TOKENS.
        """
        existing = await self.get_by_tg_id(tg_bot_id)
        if existing is not None:
            existing.username = username
            existing.token_index = token_index
            existing.is_active = True
            return existing

        bot = CheckerBot(
            tg_bot_id=tg_bot_id,
            username=username,
            token_index=token_index,
            is_active=True,
        )
        self.session.add(bot)
        await self.session.flush()
        return bot
