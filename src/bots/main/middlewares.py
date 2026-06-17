"""Middlewares for the combined main bot.

Stack (outer → inner per observer):
  1. ThrottlingMiddleware  — drop floods
  2. DbSessionMiddleware   — open AsyncSession per update, commit/rollback
  3. DualRoleMiddleware    — inject `advertiser` (auto-create) + `publisher` (None if unregistered)
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from redis.asyncio import Redis

from src.core.db import async_session_factory
from src.core.logging import get_logger
from src.domain.advertisers import AdvertiserService
from src.domain.exceptions import AdvertiserBannedError
from src.domain.publishers import PublisherRepository

log = get_logger("main.middleware")


class ThrottlingMiddleware(BaseMiddleware):
    """Drop excessive updates per user within a sliding window."""

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

        key = f"throttle:main:{tg_user_id}"
        try:
            count = await self.redis.incr(key)
            if count == 1:
                await self.redis.expire(key, self.window)
        except Exception:
            return await handler(event, data)

        if count > self.rate:
            if isinstance(event, CallbackQuery):
                try:
                    await event.answer("Слишком часто. Подождите.", show_alert=False)
                except Exception:
                    pass
            return None
        return await handler(event, data)


class DbSessionMiddleware(BaseMiddleware):
    """Open an AsyncSession per update; commit on success, rollback on error."""

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


class DualRoleMiddleware(BaseMiddleware):
    """Inject both roles into handler data.

    - `advertiser`: always present (auto-created on first message).
      Blocks the update if the advertiser is banned.
    - `publisher`: may be None if the user has not registered as a publisher yet.
      Blocks the update if the publisher is banned.
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
            log.warning("no_session_in_data")
            return await handler(event, data)

        # --- Advertiser (auto-create) ---
        adv_service = AdvertiserService(session)
        try:
            advertiser = await adv_service.get_or_create(
                tg_user_id=tg_user.id,
                tg_username=tg_user.username,
                full_name=tg_user.full_name,
            )
        except AdvertiserBannedError:
            if isinstance(event, Message):
                try:
                    await event.answer("Ваш аккаунт заблокирован.")
                except Exception:
                    pass
            elif isinstance(event, CallbackQuery):
                try:
                    await event.answer("Аккаунт заблокирован.", show_alert=True)
                except Exception:
                    pass
            return None
        data["advertiser"] = advertiser

        # --- Publisher (lookup only; None until /start registration) ---
        pub_repo = PublisherRepository(session)
        publisher = await pub_repo.get_by_tg_id(tg_user.id)

        if publisher is not None and publisher.is_banned:
            if isinstance(event, Message):
                try:
                    await event.answer("Ваш аккаунт заблокирован.")
                except Exception:
                    pass
            elif isinstance(event, CallbackQuery):
                try:
                    await event.answer("Аккаунт заблокирован.", show_alert=True)
                except Exception:
                    pass
            return None

        if publisher is not None:
            if tg_user.username and publisher.tg_username != tg_user.username:
                publisher.tg_username = tg_user.username
            if tg_user.full_name and publisher.full_name != tg_user.full_name:
                publisher.full_name = tg_user.full_name

        data["publisher"] = publisher  # may be None
        return await handler(event, data)
