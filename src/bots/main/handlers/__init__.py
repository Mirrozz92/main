"""Combined root router: advertiser + publisher handlers, unified /start."""

from __future__ import annotations

from aiogram import Router

from src.bots.advertiser.handlers import campaign_create, campaign_list
from src.bots.advertiser.handlers import menu as adv_menu
from src.bots.advertiser.handlers import topup
from src.bots.main.handlers import start
from src.bots.publisher.handlers import balance, bot_card, bot_settings, integration, stats
from src.bots.publisher.handlers import menu as pub_menu
from src.bots.publisher.handlers import sell_traffic


def get_root_router() -> Router:
    """Build the combined dispatcher router.

    Order matters — more specific routers (FSM state filters) go first.
    Neither bot's start.py is included; /start is handled by main's start.py.
    """
    root = Router(name="main_root")

    # Unified /start and top-level main:menu / main:help callbacks
    root.include_router(start.router)

    # --- Advertiser section ---
    root.include_router(topup.router)           # FSM TopupStates.*
    root.include_router(campaign_create.router)  # FSM CampaignCreate.*
    root.include_router(campaign_list.router)    # CB_CAMPAIGNS
    root.include_router(adv_menu.router)         # menu:balance, menu:help, menu (adv sub-menu)

    # --- Publisher section ---
    root.include_router(sell_traffic.router)     # FSM BotAddStates.*
    root.include_router(bot_card.router)         # pub:b:*
    root.include_router(bot_settings.router)     # FSM BotSettingsStates.*, pub:bs:*
    root.include_router(integration.router)      # pub:bi:*, pub:tr:*, pub:trc:*
    root.include_router(balance.router)          # FSM WithdrawStates.*, pub:balance, pub:withdraw
    root.include_router(stats.router)            # pub:stats
    root.include_router(pub_menu.router)         # pub:menu (publisher sub-menu), pub:profile, pub:help

    return root
