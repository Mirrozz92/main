"""Pool of aiogram Bot instances for checker tokens.

Used to call Telegram API from non-bot contexts (API server, workers) — e.g.
to verify that our checker-bot is admin in some chat.

Each token maps to one Bot instance, reused across calls (don't create new
Bot objects per-request: each one opens its own aiohttp ClientSession).
"""

from __future__ import annotations

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from src.core.config import get_settings
from src.core.logging import get_logger

log = get_logger("checker_pool")


class CheckerBotPool:
    """Singleton-ish pool. Use get_checker_pool() to access."""

    def __init__(self) -> None:
        self._bots_by_index: dict[int, Bot] = {}
        self._bots_by_tg_id: dict[int, Bot] = {}
        self._initialized = False

    async def initialize(self) -> None:
        """Eagerly create Bot objects for each token. Idempotent."""
        if self._initialized:
            return
        settings = get_settings()
        tokens = [t.get_secret_value() for t in settings.checker_bot_tokens_list]

        for idx, token in enumerate(tokens):
            bot = Bot(
                token=token,
                default=DefaultBotProperties(parse_mode=ParseMode.HTML),
            )
            try:
                me = await bot.get_me()
            except Exception as e:
                log.error("checker_pool_getme_failed", token_index=idx, error=str(e))
                await bot.session.close()
                continue

            self._bots_by_index[idx] = bot
            self._bots_by_tg_id[me.id] = bot
            log.info("checker_pool_bot_ready", index=idx, tg_id=me.id, username=me.username)

        self._initialized = True

    def get_by_index(self, idx: int) -> Bot | None:
        return self._bots_by_index.get(idx)

    def get_by_tg_id(self, tg_id: int) -> Bot | None:
        return self._bots_by_tg_id.get(tg_id)

    def get_any(self) -> Bot | None:
        """Return any bot (first one). Used when we don't need a specific token."""
        if not self._bots_by_index:
            return None
        return next(iter(self._bots_by_index.values()))

    async def close(self) -> None:
        """Close all underlying aiohttp sessions."""
        for bot in self._bots_by_index.values():
            try:
                await bot.session.close()
            except Exception as e:
                log.warning("checker_pool_close_error", error=str(e))
        self._bots_by_index.clear()
        self._bots_by_tg_id.clear()
        self._initialized = False


_pool: CheckerBotPool | None = None


def get_checker_pool() -> CheckerBotPool:
    """Get or create the global pool. Caller MUST await pool.initialize() first."""
    global _pool
    if _pool is None:
        _pool = CheckerBotPool()
    return _pool
