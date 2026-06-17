"""Middlewares for publisher bot: DB session, throttling, publisher injection.

Unlike advertiser middleware, here we don't auto-create a Publisher on every
message — registration happens explicitly via /start FSM flow.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from redis.asyncio import Redis

from src.core.db import async_session_factory
from src.core.logging import get_logger
from src.domain.publishers import PublisherRepository
from src.domain.publishers.service import PublisherBannedError

log = get_logger("publisher.middleware")


class DbSessionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with async_session_factory() as session:
            data["session"] = session
            try:
                result = await handler(event, data)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise


class PublisherMiddleware(BaseMiddleware):
    """Look up Publisher by TG user id; inject `publisher` or None.

    Handlers can check `publisher is None` to require registration.
    Banned publishers are blocked entirely.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = None
        if isinstance(event, Message):
            tg_user = event.from_user
        elif isinstance(event, CallbackQuery):
            tg_user = event.from_user

        if tg_user is None or tg_user.is_bot:
            return await handler(event, data)

        session = data.get("session")
        if session is None:
            return await handler(event, data)

        repo = PublisherRepository(session)
        publisher = await repo.get_by_tg_id(tg_user.id)

        if publisher is not None and publisher.is_banned:
            if isinstance(event, Message):
                try:
                    await event.answer("Ваш аккаунт заблокирован.")
                except Exception:
                    pass
            elif isinstance(event, CallbackQuery):
                try:
                    await event.answer("Аккаунт заблокирован", show_alert=True)
                except Exception:
                    pass
            return None

        # Update username/full_name if changed
        if publisher is not None:
            if tg_user.username and publisher.tg_username != tg_user.username:
                publisher.tg_username = tg_user.username
            if tg_user.full_name and publisher.full_name != tg_user.full_name:
                publisher.full_name = tg_user.full_name

        data["publisher"] = publisher # may be None
        return await handler(event, data)


class ThrottlingMiddleware(BaseMiddleware):
    """Simple per-user rate limit via Redis."""

    def __init__(
        self,
        redis: Redis,
        *,
        rate: int = 8,
        window_seconds: int = 2,
    ) -> None:
        self.redis = redis
        self.rate = rate
        self.window = window_seconds

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

        key = f"throttle:pub:{tg_user_id}"
        try:
            count = await self.redis.incr(key)
            if count == 1:
                await self.redis.expire(key, self.window)
        except Exception:
            return await handler(event, data)

        if count > self.rate:
            return None
        return await handler(event, data)
