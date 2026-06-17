"""Main bot entry point — combined advertiser + publisher."""

from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage

from src.bots.main.handlers import get_root_router
from src.bots.main.middlewares import (
    DbSessionMiddleware,
    DualRoleMiddleware,
    ThrottlingMiddleware,
)
from src.core.config import get_settings
from src.core.logging import configure_logging, get_logger
from src.core.redis import make_cache_client
from src.integrations.telegram import get_checker_pool
from src.workers.broker import broker

configure_logging()
log = get_logger("main_bot")


async def main() -> None:
    settings = get_settings()

    bot = Bot(
        token=settings.main_bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    redis_storage = RedisStorage.from_url(settings.redis_url_cache)
    dp = Dispatcher(storage=redis_storage)
    cache_redis = make_cache_client()

    throttling = ThrottlingMiddleware(cache_redis, rate=8, window_seconds=2)
    db_mw = DbSessionMiddleware()
    dual_mw = DualRoleMiddleware()

    for observer in (dp.message, dp.callback_query, dp.chat_member):
        observer.outer_middleware(throttling)
        observer.outer_middleware(db_mw)
        observer.outer_middleware(dual_mw)

    dp.include_router(get_root_router())

    # Advertiser side: checker pool for chat validation in campaign-create flow
    pool = get_checker_pool()
    try:
        await pool.initialize()
    except Exception as e:
        log.warning("checker_pool_init_failed", error=str(e))

    # Publisher side: TaskIQ broker for kiq()-ing background tasks
    if not broker.is_worker_process:
        await broker.startup()

    log.info("main_bot_starting")
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
        await cache_redis.aclose()
        await redis_storage.close()
        log.info("main_bot_stopped")


if __name__ == "__main__":
    asyncio.run(main())
