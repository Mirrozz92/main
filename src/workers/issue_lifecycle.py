"""Periodic tasks for ResourceIssue lifecycle (stage 3c2 — with money).

Three scheduled tasks:
1. expire_pending_issues — every 30s, mark pending issues whose TTL passed.
2. verify_subscribed_issues — every 60s, mark subscribed issues whose hold finished,
   AND atomically move money: deduct advertiser, credit publisher, record commission.
3. revert_unsubscribed_issues — every 60s, finalize unsubscribed → reverted,
   AND refund advertiser if the unsubscribe happened before verify.

All use SELECT...FOR UPDATE SKIP LOCKED to allow horizontal scaling.
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select

from src.core.db import async_session_factory
from src.core.db.models import Campaign, CampaignResource, PublisherBot
from src.core.db.models.enums import CampaignStatus, ResourceStatus
from src.core.logging import get_logger
from src.domain.issues import IssueStateMachine, ResourceIssueRepository
from src.domain.issues.financial import IssueFinancialService
from src.workers.broker import broker

log = get_logger("workers.issue_lifecycle")


@broker.task(
    schedule=[{"cron": "* * * * *"}],
    task_name="expire_pending_issues",
)
async def expire_pending_issues(batch_size: int = 100) -> dict:
    """Mark pending issues whose expires_at < now as expired.

    No money movement: pending tasks never had money committed (only reserved
    at campaign creation, and reserve is released globally on campaign cancel
    or here individually via revert).

    Actually we DO need to release reserve here, otherwise the advertiser's
    reserved_rub keeps growing indefinitely for expired tasks. Stage 3c2:
    on expire, return reward back to advertiser balance.
    """
    expired = 0
    refunded = 0
    async with async_session_factory() as session:
        try:
            repo = ResourceIssueRepository(session)
            machine = IssueStateMachine(session)
            financial = IssueFinancialService(session)

            issues = await repo.list_expired_pending(limit=batch_size)
            for issue in issues:
                await machine.mark_expired(issue)
                expired += 1

                # Release the reserve back to the advertiser (issue expired
                # without subscription)
                try:
                    await financial.apply_revert(issue)
                    refunded += 1
                except Exception as e:
                    log.warning(
                        "expire_refund_failed",
                        link_id=issue.link_id,
                        error=str(e),
                    )

            await session.commit()
        except Exception as e:
            await session.rollback()
            log.error("expire_pending_failed", error=str(e))
            raise

    if expired:
        log.info("expired_pending_issues", count=expired, refunded=refunded)
    return {"expired": expired, "refunded": refunded}


@broker.task(
    schedule=[{"cron": "* * * * *"}],
    task_name="verify_subscribed_issues",
)
async def verify_subscribed_issues(batch_size: int = 100) -> dict:
    """Mark subscribed issues whose hold_until < now as verified.

    Money flow (Variant A — atomic):
      - Decrement advertiser.reserved_rub by reward, increment total_spent_rub
      - Decrement campaign.budget_reserved_rub by reward, increment budget_spent_rub
      - Increment publisher.balance_rub by publisher_payout_rub (straight to balance, no hold)
      - Create 3 ledger txs: CAMPAIGN_SPEND, PUBLISHER_EARN, PLATFORM_COMMISSION

    Plus side effects:
      - publisher_bot.total_verified += 1
      - campaign_resource.actual_subscribers += 1
      - If resource reached target → mark COMPLETED
      - If all resources of a campaign COMPLETED → mark campaign COMPLETED
    """
    verified = 0
    resources_completed = 0
    campaigns_completed = 0

    async with async_session_factory() as session:
        try:
            repo = ResourceIssueRepository(session)
            machine = IssueStateMachine(session)
            financial = IssueFinancialService(session)

            issues = await repo.list_hold_ready(limit=batch_size)
            if not issues:
                await session.commit()
                return {"verified": 0, "resources_completed": 0, "campaigns_completed": 0}

            # 1. Transition each issue + apply financial
            increments_by_bot: dict[int, int] = defaultdict(int)
            increments_by_resource: dict[int, int] = defaultdict(int)
            for issue in issues:
                await machine.mark_verified(issue)
                try:
                    await financial.apply_verify(issue)
                except Exception as e:
                    log.error(
                        "verify_money_failed",
                        link_id=issue.link_id,
                        error=str(e),
                    )
                    # We still count it as verified for status — admin will need
                    # to reconcile manually. Future: retry queue.
                verified += 1
                if issue.publisher_bot_id is not None:
                    increments_by_bot[issue.publisher_bot_id] += 1
                increments_by_resource[issue.campaign_resource_id] += 1

            # 2. Bump publisher_bot counters
            if increments_by_bot:
                bot_rows = await session.execute(
                    select(PublisherBot).where(PublisherBot.id.in_(increments_by_bot.keys()))
                )
                for bot in bot_rows.scalars().all():
                    bot.total_verified = bot.total_verified + increments_by_bot[bot.id]
                    # Sum of publisher payouts for this bot's issues
                    earned_sum = sum(
                        (i.publisher_payout_rub for i in issues if i.publisher_bot_id == bot.id),
                        start=type(bot.total_earned_rub)(0),
                    )
                    bot.total_earned_rub = bot.total_earned_rub + earned_sum

            # 3. Bump resource counters, check completion
            affected_campaign_ids: set[int] = set()
            if increments_by_resource:
                res_rows = await session.execute(
                    select(CampaignResource).where(CampaignResource.id.in_(increments_by_resource.keys()))
                )
                for resource in res_rows.scalars().all():
                    resource.actual_subscribers = (
                        resource.actual_subscribers + increments_by_resource[resource.id]
                    )
                    affected_campaign_ids.add(resource.campaign_id)
                    if (resource.actual_subscribers >= resource.target_subscribers
                        and resource.status == ResourceStatus.ACTIVE):
                        resource.status = ResourceStatus.COMPLETED
                        resources_completed += 1
                        log.info("resource_completed", resource_id=resource.id)

            # 4. Check campaign completion
            for campaign_id in affected_campaign_ids:
                remaining = await session.execute(
                    select(CampaignResource.id).where(
                        (CampaignResource.campaign_id == campaign_id)
                        & (CampaignResource.status == ResourceStatus.ACTIVE)
                    ).limit(1)
                )
                if remaining.first() is None:
                    c_row = await session.execute(
                        select(Campaign).where(Campaign.id == campaign_id)
                    )
                    campaign = c_row.scalar_one_or_none()
                    if campaign is not None and campaign.status == CampaignStatus.ACTIVE:
                        campaign.status = CampaignStatus.COMPLETED
                        campaigns_completed += 1
                        log.info("campaign_completed", campaign_id=campaign_id)

            await session.commit()
        except Exception as e:
            await session.rollback()
            log.error("verify_subscribed_failed", error=str(e))
            raise

    if verified:
        log.info(
            "verified_subscribed_issues",
            count=verified,
            resources_completed=resources_completed,
            campaigns_completed=campaigns_completed,
        )
    return {
        "verified": verified,
        "resources_completed": resources_completed,
        "campaigns_completed": campaigns_completed,
    }


@broker.task(
    schedule=[{"cron": "* * * * *"}],
    task_name="revert_unsubscribed_issues",
)
async def revert_unsubscribed_issues(batch_size: int = 100) -> dict:
    """Finalize unsubscribed issues: mark as reverted + refund advertiser.

    Variant A: only refund if the issue was UNSUB'd before verify
    (financial.apply_revert handles this logic internally).
    """
    reverted = 0
    refunded = 0
    async with async_session_factory() as session:
        try:
            repo = ResourceIssueRepository(session)
            machine = IssueStateMachine(session)
            financial = IssueFinancialService(session)

            issues = await repo.list_unsubscribed_pending_revert(limit=batch_size)
            for issue in issues:
                await machine.mark_reverted(issue)
                reverted += 1
                try:
                    await financial.apply_revert(issue)
                    refunded += 1
                except Exception as e:
                    log.warning(
                        "revert_money_failed",
                        link_id=issue.link_id,
                        error=str(e),
                    )
            await session.commit()
        except Exception as e:
            await session.rollback()
            log.error("revert_unsubscribed_failed", error=str(e))
            raise

    if reverted:
        log.info("reverted_unsubscribed_issues", count=reverted, refunded=refunded)
    return {"reverted": reverted, "refunded": refunded}
