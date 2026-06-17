"""Generate Telegram invite links via checker-bot.

Used after campaign approval: for each campaign_resource that has a tg_chat_id,
we create a per-resource invite link with a unique name. Later we use this link
to track which subscribers came from FastSub.
"""

from __future__ import annotations

from dataclasses import dataclass

from aiogram.exceptions import TelegramAPIError

from src.core.db.models import CampaignResource
from src.core.logging import get_logger
from src.integrations.telegram import get_checker_pool

log = get_logger("invite_links")


@dataclass
class InviteLinkResult:
    resource_id: int
    invite_link: str | None  # None on failure
    error: str | None = None


async def create_invite_link_for_resource(
    resource: CampaignResource,
    *,
    checker_bot_token_index: int,
    campaign_id: int,
) -> InviteLinkResult:
    """Create a uniquely-named invite link for the given resource.

    Returns InviteLinkResult — invite_link is None on failure.
    """
    if resource.tg_chat_id is None:
        return InviteLinkResult(
            resource_id=resource.id,
            invite_link=None,
            error="Resource has no tg_chat_id (bot resource?)",
        )

    pool = get_checker_pool()
    bot = pool.get_by_index(checker_bot_token_index)
    if bot is None:
        return InviteLinkResult(
            resource_id=resource.id,
            invite_link=None,
            error=f"No checker bot at index {checker_bot_token_index}",
        )

    # Unique name (Telegram requires ≤32 chars)
    link_name = f"FastSub-{campaign_id}-{resource.id}"[:32]

    try:
        link = await bot.create_chat_invite_link(
            chat_id=resource.tg_chat_id,
            name=link_name,
            creates_join_request=False,
        )
    except TelegramAPIError as e:
        log.warning(
            "invite_link_create_failed",
            resource_id=resource.id,
            chat_id=resource.tg_chat_id,
            error=str(e),
        )
        return InviteLinkResult(resource_id=resource.id, invite_link=None, error=str(e))

    log.info(
        "invite_link_created",
        resource_id=resource.id,
        chat_id=resource.tg_chat_id,
        invite_link=link.invite_link,
    )
    return InviteLinkResult(resource_id=resource.id, invite_link=link.invite_link)


async def create_links_for_campaign_resources(
    resources: list[CampaignResource],
    *,
    campaign_id: int,
) -> dict[int, str]:
    """Create invite links for all channel/group resources of a campaign.

    Bot-resources (BOT_START) are skipped — they're handled by start_param later.
    Returns map of resource_id → invite_link for successful generations.
    """
    from src.core.db.models.enums import ResourceType

    links: dict[int, str] = {}
    for r in resources:
        if r.type == ResourceType.BOT_START:
            continue  # bots don't need invite links
        if r.checker_bot_id is None or r.tg_chat_id is None:
            continue

        # We need the checker_bot.token_index. The caller must look this up
        # and pass via a separate map. Simpler: do it inline by fetching.
        from src.domain.checker_bots import CheckerBotRepository
        from src.core.db.session import get_session_dependency  # type: ignore

        # Simpler: get token_index from the resource's checker_bot relationship
        # But we don't have session here. Workflow: caller looks up token_index.
        # For now: assume resource.checker_bot is preloaded (selectinload).
        if not hasattr(r, "checker_bot") or r.checker_bot is None:
            log.warning("invite_link_skipped_no_checker_relationship", resource_id=r.id)
            continue

        result = await create_invite_link_for_resource(
            r,
            checker_bot_token_index=r.checker_bot.token_index,
            campaign_id=campaign_id,
        )
        if result.invite_link:
            links[r.id] = result.invite_link

    return links
