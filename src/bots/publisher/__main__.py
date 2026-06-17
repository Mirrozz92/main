"""Publisher bot entry point."""

from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage

from src.bots.publisher.handlers import get_root_router
from src.bots.publisher.middlewares import (
    DbSessionMiddleware,
    PublisherMiddleware,
    ThrottlingMiddleware,
)
from src.core.config import get_settings
from src.core.logging import configure_logging, get_logger
from src.core.redis import make_cache_client
from src.workers.broker import broker

configure_logging()
log = get_logger("publisher_bot")


async def main() -> None:
    settings = get_settings()

    if settings.publisher_bot_token is None:
        log.error("publisher_bot_token_missing", hint="Add PUBLISHER_BOT_TOKEN to .env")
        return

    bot = Bot(
        token=settings.publisher_bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    redis_storage = RedisStorage.from_url(settings.redis_url_cache)
    dp = Dispatcher(storage=redis_storage)
    cache_redis = make_cache_client()

    throttling = ThrottlingMiddleware(cache_redis, rate=8, window_seconds=2)
    db_mw = DbSessionMiddleware()
    pub_mw = PublisherMiddleware()
    for observer in (dp.message, dp.callback_query):
        observer.outer_middleware(throttling)
        observer.outer_middleware(db_mw)
        observer.outer_middleware(pub_mw)

    dp.include_router(get_root_router())

    # TaskIQ broker startup (needed to .kiq() tasks from handlers)
    if not broker.is_worker_process:
        await broker.startup()

    log.info("publisher_bot_starting")
    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dp.start_polling(
            bot,
            handle_signals=False,
            allowed_updates=dp.resolve_used_update_types(),
        )
    finally:
        if not broker.is_worker_process:
            await broker.shutdown()
        await bot.session.close()
        await cache_redis.aclose()
        await redis_storage.close()
        log.info("publisher_bot_stopped")


if __name__ =="__main__":
    asyncio.run(main())
