"""Service layer for checker bots pool."""

from __future__ import annotations

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.logging import get_logger
from src.domain.checker_bots.repository import CheckerBotRepository

log = get_logger("checker_bots")


class CheckerBotService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = CheckerBotRepository(session)

    async def sync_from_config(self) -> int:
        """Sync DB checker_bots from CHECKER_BOT_TOKENS in .env.

        For each token: call getMe to discover bot identity, then upsert
        the record (by tg_bot_id). Returns number of bots synced.
        """
        settings = get_settings()
        tokens = [t.get_secret_value() for t in settings.checker_bot_tokens_list]

        if not tokens:
            log.warning("no_checker_tokens_configured")
            return 0

        synced = 0
        for idx, token in enumerate(tokens):
            bot = Bot(
                token=token,
                default=DefaultBotProperties(parse_mode=ParseMode.HTML),
            )
            try:
                me = await bot.get_me()
            except Exception as e:
                log.error("checker_getme_failed", token_index=idx, error=str(e))
                continue
            finally:
                await bot.session.close()

            await self.repo.upsert(
                tg_bot_id=me.id,
                username=me.username or "",
                token_index=idx,
            )
            synced += 1
            log.info(
                "checker_bot_registered",
                tg_bot_id=me.id,
                username=me.username,
                token_index=idx,
            )

        return synced
