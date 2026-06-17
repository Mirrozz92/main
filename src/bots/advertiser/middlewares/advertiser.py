"""Middleware that gets/creates Advertiser entity per update.

Must run AFTER DbSessionMiddleware (which provides `session`).
Injects `advertiser` into handler data, or rejects the update if user is banned.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from src.bots.advertiser import texts
from src.core.logging import get_logger
from src.domain.advertisers import AdvertiserService
from src.domain.exceptions import AdvertiserBannedError

log = get_logger("middleware.advertiser")


class AdvertiserMiddleware(BaseMiddleware):
    """Resolve Advertiser from incoming TG user."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # Извлекаем from_user из разных типов событий
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

        service = AdvertiserService(session)
        try:
            advertiser = await service.get_or_create(
                tg_user_id=tg_user.id,
                tg_username=tg_user.username,
                full_name=tg_user.full_name,
            )
        except AdvertiserBannedError:
            if isinstance(event, Message):
                await event.answer(texts.ERROR_BANNED)
            elif isinstance(event, CallbackQuery):
                await event.answer(texts.ERROR_BANNED, show_alert=True)
            return None

        data["advertiser"] = advertiser
        return await handler(event, data)
