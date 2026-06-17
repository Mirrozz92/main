"""Aggregate router for all advertiser-bot handlers."""

from __future__ import annotations

from aiogram import Router

from src.bots.advertiser.handlers import (
    campaign_create,
    campaign_list,
    menu,
    start,
    topup,
)


def get_root_router() -> Router:
    """Combine all handler routers. Order matters — more specific first."""
    root = Router(name="advertiser_root")
    # Specific FSM-driven routers first (their state filters narrow the match)
    root.include_router(start.router)
    root.include_router(topup.router)
    root.include_router(campaign_create.router) # FSM CampaignCreate.*
    root.include_router(campaign_list.router) # overrides CB_CAMPAIGNS
    root.include_router(menu.router)
    return root
