"""Admin bot entry point."""

from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage

from src.bots.admin.handlers import get_root_router
from src.bots.admin.middlewares import AdminAuthMiddleware, DbSessionMiddleware
from src.core.config import get_settings
from src.core.logging import configure_logging, get_logger
from src.integrations.telegram import get_checker_pool
from src.workers.broker import broker

configure_logging()
log = get_logger("admin_bot")


async def main() -> None:
    settings = get_settings()

    bot = Bot(
        token=settings.admin_bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    redis_storage = RedisStorage.from_url(settings.redis_url_cache)
    dp = Dispatcher(storage=redis_storage)

    # Outer middlewares (DB admin auth)
    db_mw = DbSessionMiddleware()
    auth_mw = AdminAuthMiddleware()
    for observer in (dp.message, dp.callback_query):
        observer.outer_middleware(db_mw)
        observer.outer_middleware(auth_mw)

    dp.include_router(get_root_router())

    # TaskIQ broker startup (needed to .kiq() tasks from handlers)
    if not broker.is_worker_process:
        await broker.startup()

    # Initialize checker bot pool (admin uses it to create invite links)
    pool = get_checker_pool()
    try:
        await pool.initialize()
    except Exception as e:
        log.warning("checker_pool_init_failed", error=str(e))

    log.info("admin_bot_starting")
    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dp.start_polling(
            bot,
            handle_signals=False,
            allowed_updates=dp.resolve_used_update_types(),
        )
    finally:
        await pool.close()
        if not broker.is_worker_process:
            await broker.shutdown()
        await bot.session.close()
        await redis_storage.close()
        log.info("admin_bot_stopped")


if __name__ =="__main__":
    asyncio.run(main())
