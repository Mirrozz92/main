"""Matchmaking — find appropriate campaign resources to issue to a user.

Algorithm (stage 3b — basic, no targeting):

1. Get all eligible ACTIVE campaign resources:
   - Campaign status = ACTIVE
   - CampaignResource status = ACTIVE
   - actual_subscribers < target_subscribers (not overflowed)

2. Filter out resources already issued to this user (any status — once shown, never again).

3. Sort by a balancing key that prefers under-served resources (with lower fill_rate)
   while keeping older campaigns competitive (FIFO weighting).

4. Take top N where N = min(requested_count, bot.sponsors_count).

5. For each picked resource: compute reward + commission split.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from src.domain.publishers.commission import commission_for
from src.domain.targeting.matcher import end_user_matches_campaign, parse_targeting
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.db.models import (
    Campaign,
    CampaignResource,
    PublisherBot,
)
from src.core.db.models.enums import (
    CampaignStatus,
    ResourceStatus,
)
from src.core.logging import get_logger
from src.domain.issues.repository import ResourceIssueRepository

log = get_logger("matchmaking")


# Platform commission is computed from publisher retention via the scale
# in src.domain.publishers.commission.


@dataclass
class MatchedTask:
    """One picked task ready for issuing."""

    campaign_resource_id: int
    campaign_id: int
    resource_type: str          # "channel" | "group" | "bot_start"
    title: str
    username: str | None
    members_count: int | None
    invite_link: str | None     # for channels/groups
    bot_username: str | None    # for bot_start resources (their @username)
    reward_rub: Decimal
    publisher_payout_rub: Decimal
    platform_commission_rub: Decimal


class MatchmakingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_tasks_for_user(
        self,
        *,
        publisher_id: int,
        publisher_bot: PublisherBot,
        user_tg_id: int,
        requested_count: int | None = None,
        is_vip: bool = False,
        end_user=None,
    ) -> list[MatchedTask]:
        """Pick up to `requested_count` (capped at publisher_bot.sponsors_count) tasks.

        Returns empty list if nothing suitable found.
        Does NOT create ResourceIssues — caller does that after locking budgets.
        """
        # Cap count
        max_count = publisher_bot.sponsors_count
        if requested_count is None:
            target_count = max_count
        else:
            target_count = min(max_count, max(1, requested_count))

        # 1. Find already-issued resources for this user → exclude them
        issue_repo = ResourceIssueRepository(self.session)
        already_seen = await issue_repo.already_issued_resource_ids_for_user(
            user_tg_id=user_tg_id, publisher_id=publisher_id,
        )

        # Load publisher early (needed for rating filter + commission)
        from src.core.db.models import Publisher
        pub_row = await self.session.execute(
            select(Publisher).where(Publisher.id == publisher_id)
        )
        publisher = pub_row.scalar_one_or_none()
        publisher_rating = publisher.rating if publisher is not None else Decimal("0")

        # 2. Find candidate resources
        stmt = (
            select(CampaignResource, Campaign)
            .join(Campaign, CampaignResource.campaign_id == Campaign.id)
            .where(
                and_(
                    Campaign.status == CampaignStatus.ACTIVE,
                    CampaignResource.status == ResourceStatus.ACTIVE,
                    CampaignResource.actual_subscribers < CampaignResource.target_subscribers,
                )
            )
        )
        if already_seen:
            stmt = stmt.where(CampaignResource.id.notin_(already_seen))

        result = await self.session.execute(stmt)
        rows = result.all()

        if not rows:
            log.info(
                "matchmaking_no_candidates",
                publisher_id=publisher_id,
                user_tg_id=user_tg_id,
                already_seen=len(already_seen),
            )
            return []

        # 2b. Apply targeting filters: demography/audience (per end_user) +
        # publisher rating threshold (per campaign).
        filtered: list = []
        dropped_targeting = 0
        dropped_rating = 0
        for resource, campaign in rows:
            targeting = parse_targeting(campaign.targeting)
            # Publisher rating gate
            min_rating = targeting.get("min_publisher_rating", Decimal("0"))
            if publisher_rating < min_rating:
                dropped_rating += 1
                continue
            # Demography + audience gate
            if not end_user_matches_campaign(end_user, campaign.targeting):
                dropped_targeting += 1
                continue
            filtered.append((resource, campaign))

        if not filtered:
            log.info(
                "matchmaking_all_filtered",
                publisher_id=publisher_id,
                user_tg_id=user_tg_id,
                dropped_targeting=dropped_targeting,
                dropped_rating=dropped_rating,
            )
            return []

        rows = filtered

        # 3. Rank candidates: prefer resources with LOWER fill rate (newer/under-served first)
        # Tie-breaker: earlier created_at (FIFO fairness)
        def rank_key(row: tuple[CampaignResource, Campaign]) -> tuple[float, float]:
            r, c = row
            target = max(1, r.target_subscribers)
            fill_rate = float(r.actual_subscribers) / float(target)
            # Older campaigns get a tiny boost (negative timestamp puts them first)
            created_ts = c.created_at.timestamp() if c.created_at else 0
            return (fill_rate, created_ts)

        rows_sorted = sorted(rows, key=rank_key)
        picked = rows_sorted[:target_count]

        # 4. Build MatchedTask for each.
        # Commission is determined by the publisher's retention via the scale
        # (cold start <100 verified subs -> base 25%). VIP keeps a flat 20%.
        if is_vip:
            commission_rate = Decimal("0.20")
        elif publisher is not None:
            commission_rate = commission_for(
                publisher.retention_rate,
                publisher.verified_subs_in_window,
            )
        else:
            commission_rate = Decimal("0.25")
        publisher_rate = Decimal("1") - commission_rate

        tasks: list[MatchedTask] = []
        for resource, _campaign in picked:
            reward = resource.reward_rub
            publisher_payout = (reward * publisher_rate).quantize(Decimal("0.0001"))
            platform_commission = reward - publisher_payout

            tasks.append(MatchedTask(
                campaign_resource_id=resource.id,
                campaign_id=resource.campaign_id,
                resource_type=resource.type.value,
                title=resource.title,
                username=resource.username,
                members_count=None,  # we don't track member_count snapshot in CampaignResource
                invite_link=resource.invite_link,
                bot_username=resource.username if resource.type.value == "bot_start" else None,
                reward_rub=reward,
                publisher_payout_rub=publisher_payout,
                platform_commission_rub=platform_commission,
            ))

        log.info(
            "matchmaking_picked",
            publisher_id=publisher_id,
            user_tg_id=user_tg_id,
            requested=requested_count,
            target_count=target_count,
            picked=len(tasks),
            candidates_total=len(rows),
        )
        return tasks
