"""Admin bot handler routers."""

from __future__ import annotations

from aiogram import Router

from src.bots.admin.handlers import bot_moderation, moderation, start, withdrawals


def get_root_router() -> Router:
    root = Router(name="admin_root")
    root.include_router(start.router)
    root.include_router(bot_moderation.router)
    root.include_router(moderation.router)
    root.include_router(withdrawals.router)
    return root
