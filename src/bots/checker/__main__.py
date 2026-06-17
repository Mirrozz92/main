"""Checker bots pool entry point.

On startup:
1. Auto-register each token's identity in DB (checker_bots table).
2. Initialize the in-process CheckerBotPool (for use by API/workers if needed).
3. Start polling for all bots (chat_member, chat_join_request, /start).
"""

from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message

from src.bots.checker.handlers.chat_member import router as chat_member_router
from src.bots.checker.middlewares import DbSessionMiddleware
from src.core.config import get_settings
from src.core.db import async_session_factory
from src.core.logging import configure_logging, get_logger
from src.domain.checker_bots import CheckerBotService
from src.integrations.telegram import get_checker_pool

configure_logging()
log = get_logger("checker_pool")


async def cmd_start(message: Message) -> None:
    await message.answer(
        "Это служебный бот FastSub.\n"
        "Добавьте меня админом в свой канал, чтобы я мог проверять подписки.\n\n"
        "Управление кампаниями — в @Fast_Subs_Bot."
    )


async def run_one_bot(token: str, index: int) -> None:
    bot = Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    # Inject DB session into all handlers
    db_mw = DbSessionMiddleware()
    dp.message.outer_middleware(db_mw)
    dp.chat_member.outer_middleware(db_mw)
    dp.chat_join_request.outer_middleware(db_mw)
    dp.my_chat_member.outer_middleware(db_mw)

    # Routers
    dp.include_router(chat_member_router)

    # Simple /start
    dp.message.register(cmd_start, CommandStart())

    log.info("checker_bot_starting", index=index)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(
            bot,
            handle_signals=False,
            allowed_updates=[
                "message","chat_member","chat_join_request","my_chat_member",
            ],
        )
    finally:
        await bot.session.close()


async def register_in_db() -> None:
    """Sync CHECKER_BOT_TOKENS into the DB at startup."""
    async with async_session_factory() as session:
        try:
            svc = CheckerBotService(session)
            count = await svc.sync_from_config()
            await session.commit()
            log.info("checker_bots_synced", count=count)
        except Exception as e:
            await session.rollback()
            log.error("checker_bots_sync_failed", error=str(e))
            raise


async def main() -> None:
    settings = get_settings()
    tokens = [t.get_secret_value() for t in settings.checker_bot_tokens_list]
    if not tokens:
        log.error("no_checker_tokens_configured")
        return

    # Step 1: register identities in DB
    await register_in_db()

    # Step 2: initialize in-process pool (used by API/workers for getChat/getChatMember)
    pool = get_checker_pool()
    await pool.initialize()

    log.info("checker_pool_starting", bots=len(tokens))

    # Step 3: start polling all bots in parallel
    tasks = [run_one_bot(t, i) for i, t in enumerate(tokens)]
    try:
        await asyncio.gather(*tasks)
    finally:
        await pool.close()


if __name__ =="__main__":
    asyncio.run(main())
