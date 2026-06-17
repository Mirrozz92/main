"""Per-user throttling via Redis.

Drops or silently skips updates that come faster than allowed rate.
Simple sliding window: max N messages per WINDOW seconds.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from redis.asyncio import Redis

from src.core.logging import get_logger

log = get_logger("middleware.throttling")


class ThrottlingMiddleware(BaseMiddleware):
    """Drop excessive updates per (user_id) within a time window."""

    def __init__(
        self,
        redis: Redis,
        *,
        rate: int = 5, # max updates
        window_seconds: int = 2,
        warn_message: str ="Слишком часто. Подождите немного.",
    ) -> None:
        self.redis = redis
        self.rate = rate
        self.window = window_seconds
        self.warn_message = warn_message

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user_id: int | None = None
        if isinstance(event, Message) and event.from_user:
            tg_user_id = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            tg_user_id = event.from_user.id

        if tg_user_id is None:
            return await handler(event, data)

        key = f"throttle:adv:{tg_user_id}"
        try:
            count = await self.redis.incr(key)
            if count == 1:
                await self.redis.expire(key, self.window)
        except Exception as e:
            log.warning("redis_unavailable", error=str(e))
            return await handler(event, data)

        if count > self.rate:
            if isinstance(event, Message):
                # Не отвечаем каждый раз — только на первое превышение
                if count == self.rate + 1:
                    try:
                        await event.answer(self.warn_message)
                    except Exception:
                        pass
            elif isinstance(event, CallbackQuery):
                try:
                    await event.answer(self.warn_message, show_alert=False)
                except Exception:
                    pass
            return None # drop update

        return await handler(event, data)
