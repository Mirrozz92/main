"""Aiogram middleware that injects an AsyncSession into handler data.

Each update gets its own session; commit happens automatically if no exception.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from src.core.db import async_session_factory
from src.core.logging import get_logger

log = get_logger("middleware.db")


class DbSessionMiddleware(BaseMiddleware):
    """Open an AsyncSession per update, commit on success, rollback on error."""

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
