"""Middlewares for admin bot.

- AdminAuthMiddleware: drops updates from non-admin users.
- DbSessionMiddleware: provides session per update (same logic as advertiser).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from src.core.config import get_settings
from src.core.db import async_session_factory
from src.core.logging import get_logger

log = get_logger("admin.middleware")


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


class AdminAuthMiddleware(BaseMiddleware):
    """Drop updates from non-admin users.

    Admins are configured via ADMIN_USERNAMES (comma-separated) and/or
    ADMIN_USER_IDS in .env.
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
            return None

        settings = get_settings()
        admin_usernames = {
            u.lstrip("@").lower() for u in settings.admin_usernames_list
        }
        admin_ids = set(settings.admin_user_ids_list)

        is_admin = (
            tg_user.id in admin_ids
            or (tg_user.username and tg_user.username.lower() in admin_usernames)
        )

        if not is_admin:
            log.warning("non_admin_access_blocked", tg_user_id=tg_user.id, username=tg_user.username)
            if isinstance(event, Message):
                try:
                    await event.answer("Доступ только для администраторов.")
                except Exception:
                    pass
            elif isinstance(event, CallbackQuery):
                try:
                    await event.answer("Доступ запрещён", show_alert=True)
                except Exception:
                    pass
            return None

        # Inject admin info
        data["admin_tg_id"] = tg_user.id
        data["admin_username"] = tg_user.username
        return await handler(event, data)
