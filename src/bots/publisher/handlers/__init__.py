"""Aggregate router for publisher bot handlers."""

from __future__ import annotations

from aiogram import Router

from src.bots.publisher.handlers import (
    balance,
    bot_card,
    bot_settings,
    integration,
    menu,
    sell_traffic,
    start,
)


def get_root_router() -> Router:
    root = Router(name="publisher_root")
    # Specific FSM-driven routers first
    root.include_router(start.router)
    root.include_router(sell_traffic.router)
    root.include_router(bot_card.router)
    root.include_router(bot_settings.router)
    root.include_router(integration.router)
    root.include_router(balance.router)
    root.include_router(menu.router)
    return root
