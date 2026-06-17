"""Financial operations for ResourceIssue state transitions.

Stage 3c2 — Variant A:
    subscribed → verified is ATOMIC.
    Money movement happens exactly once, on verify:
      - Advertiser pays reward_rub (budget_spent_rub += reward, budget_reserved_rub -= reward)
      - Publisher receives publisher_payout_rub directly to balance_rub (no hold_rub)
      - Platform records platform_commission_rub as PLATFORM_COMMISSION tx

    Verified is final. After verified — unsubscriptions are ignored.

    Revert (subscribed → unsubscribed → reverted): no money to move,
    since money only moves at verify.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db.models import (
    Advertiser,
    Campaign,
    Publisher,
    ResourceIssue,
)
from src.core.db.models.enums import (
    TransactionStatus,
    TransactionType,
)
from src.core.logging import get_logger
from src.domain.transactions import TransactionRepository

log = get_logger("issues.financial")


class FinancialError(Exception):
    """Raised when a financial operation fails (e.g. budget mismatch)."""


class IssueFinancialService:
    """Owns money movement triggered by ResourceIssue transitions."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.tx_repo = TransactionRepository(session)

    async def apply_verify(self, issue: ResourceIssue) -> None:
        """Money movement at the moment of verification.

        Steps (all within current transaction):
          1. Find advertiser of the campaign + their campaign + publisher.
          2. Decrement campaign.budget_reserved_rub by reward (it was reserved
             when campaign was created).
          3. Increment campaign.budget_spent_rub by reward.
          4. Decrement advertiser.reserved_rub by reward.
             Increment advertiser.total_spent_rub by reward.
          5. Increment publisher.balance_rub by publisher_payout_rub.
          6. Increment publisher.total_earned_rub by publisher_payout_rub.
          7. Bump publisher.verified_subs_in_window (counter for cold-start exit).
          8. Bump publisher.total_subscriptions (cumulative).
          9. Create 3 transactions: CAMPAIGN_SPEND, PUBLISHER_EARN, PLATFORM_COMMISSION.

        All amounts are taken from the issue snapshot — these were fixed at
        the moment of request-op, so we don't depend on current rates.
        """
        # Fetch related entities — we use SELECT in a single roundtrip per object
        campaign = await self._get_campaign_for_issue(issue)
        if campaign is None:
            raise FinancialError(
                f"campaign not found for issue {issue.link_id}"
            )

        advertiser = await self._get_advertiser(campaign.advertiser_id)
        if advertiser is None:
            raise FinancialError(
                f"advertiser {campaign.advertiser_id} not found"
            )

        publisher = await self._get_publisher(issue.publisher_id)
        if publisher is None:
            raise FinancialError(
                f"publisher {issue.publisher_id} not found"
            )

        # --- Budget bookkeeping ---
        reward = issue.reward_rub
        payout = issue.publisher_payout_rub
        commission = issue.platform_commission_rub

        # Safety: ensure reserved >= reward (otherwise budget pre-check failed)
        if campaign.budget_reserved_rub < reward:
            log.warning(
                "campaign_reserved_underflow",
                campaign_id=campaign.id,
                reserved=str(campaign.budget_reserved_rub),
                reward=str(reward),
            )
            # We still proceed but clamp to avoid negative reserved
            release_from_reserve = campaign.budget_reserved_rub
        else:
            release_from_reserve = reward

        campaign.budget_reserved_rub = campaign.budget_reserved_rub - release_from_reserve
        campaign.budget_spent_rub = campaign.budget_spent_rub + reward

        if advertiser.reserved_rub >= release_from_reserve:
            advertiser.reserved_rub = advertiser.reserved_rub - release_from_reserve
        else:
            log.warning(
                "advertiser_reserved_underflow",
                advertiser_id=advertiser.id,
                reserved=str(advertiser.reserved_rub),
                reward=str(reward),
            )
            advertiser.reserved_rub = Decimal("0")

        advertiser.total_spent_rub = advertiser.total_spent_rub + reward

        # --- Publisher earnings → straight to balance ---
        publisher.balance_rub = publisher.balance_rub + payout
        publisher.total_earned_rub = publisher.total_earned_rub + payout
        publisher.verified_subs_in_window = publisher.verified_subs_in_window + 1
        publisher.total_subscriptions = publisher.total_subscriptions + 1

        # --- Transactions (ledger) ---
        await self.tx_repo.create(
            type=TransactionType.CAMPAIGN_SPEND,
            amount_rub=-reward,
            advertiser_id=advertiser.id,
            campaign_id=campaign.id,
            description=f"Подтверждённая подписка (link {issue.link_id})",
            status=TransactionStatus.COMPLETED,
        )
        await self.tx_repo.create(
            type=TransactionType.PUBLISHER_EARN,
            amount_rub=payout,
            publisher_id=publisher.id,
            campaign_id=campaign.id,
            description=f"Выплата за подписку (link {issue.link_id})",
            status=TransactionStatus.COMPLETED,
        )
        await self.tx_repo.create(
            type=TransactionType.PLATFORM_COMMISSION,
            amount_rub=commission,
            advertiser_id=advertiser.id,
            campaign_id=campaign.id,
            description=f"Комиссия платформы (link {issue.link_id})",
            status=TransactionStatus.COMPLETED,
        )

        log.info(
            "verify_money_applied",
            link_id=issue.link_id,
            advertiser_id=advertiser.id,
            publisher_id=publisher.id,
            reward=str(reward),
            payout=str(payout),
            commission=str(commission),
        )

    async def apply_revert(self, issue: ResourceIssue) -> None:
        """Money movement for `unsubscribed → reverted`.

        Variant A: money only moves at verify, so:
          - If reverted from `subscribed` (before verify): nothing to do for the
            publisher (they never got paid). But we DO need to release the
            advertiser's reserve back: budget_reserved_rub -= reward,
            advertiser.reserved_rub -= reward, advertiser.balance_rub += reward.
            Create CAMPAIGN_REFUND tx.
          - If reverted from `verified` (after verify): we per business rule
            ignore late unsubscribes — do nothing here. (Caller should ensure
            we don't get here in practice; defensive check below.)

        Note: revert from `subscribed` happens when scheduler picks up the
        unsubscribed → reverted batch. At that point we don't know the prior
        status without an extra field. But we can deduce: subscribed_at is set
        and verified_at is NOT set → was subscribed when leaving.
        """
        was_verified_before_unsub = issue.verified_at is not None

        if was_verified_before_unsub:
            # User unsubscribed AFTER verify — ignore (Variant A rule).
            log.info(
                "revert_after_verify_ignored",
                link_id=issue.link_id,
                verified_at=issue.verified_at.isoformat(),
            )
            return

        # Revert during hold (before verify): refund the advertiser
        campaign = await self._get_campaign_for_issue(issue)
        if campaign is None:
            log.warning(
                "campaign_not_found_during_revert",
                link_id=issue.link_id,
            )
            return

        advertiser = await self._get_advertiser(campaign.advertiser_id)
        if advertiser is None:
            return

        reward = issue.reward_rub

        # Release reserve back to balance
        if campaign.budget_reserved_rub >= reward:
            campaign.budget_reserved_rub = campaign.budget_reserved_rub - reward
        else:
            log.warning(
                "campaign_reserved_underflow_on_revert",
                campaign_id=campaign.id,
                reserved=str(campaign.budget_reserved_rub),
            )
            campaign.budget_reserved_rub = Decimal("0")

        if advertiser.reserved_rub >= reward:
            advertiser.reserved_rub = advertiser.reserved_rub - reward
            advertiser.balance_rub = advertiser.balance_rub + reward
        else:
            log.warning(
                "advertiser_reserved_underflow_on_revert",
                advertiser_id=advertiser.id,
            )
            advertiser.reserved_rub = Decimal("0")
            advertiser.balance_rub = advertiser.balance_rub + reward

        # Increment unsubscriptions counter
        publisher = await self._get_publisher(issue.publisher_id)
        if publisher is not None:
            publisher.total_unsubscriptions = publisher.total_unsubscriptions + 1

        await self.tx_repo.create(
            type=TransactionType.CAMPAIGN_REFUND,
            amount_rub=reward,
            advertiser_id=advertiser.id,
            campaign_id=campaign.id,
            description=f"Возврат при отписке (link {issue.link_id})",
            status=TransactionStatus.COMPLETED,
        )

        log.info(
            "revert_refund_applied",
            link_id=issue.link_id,
            advertiser_id=advertiser.id,
            refund=str(reward),
        )

    # --- Helpers ---

    async def _get_campaign_for_issue(self, issue: ResourceIssue) -> Campaign | None:
        from src.core.db.models import CampaignResource

        result = await self.session.execute(
            select(Campaign)
            .join(CampaignResource, CampaignResource.campaign_id == Campaign.id)
            .where(CampaignResource.id == issue.campaign_resource_id)
        )
        return result.scalar_one_or_none()

    async def _get_advertiser(self, advertiser_id: int) -> Advertiser | None:
        result = await self.session.execute(
            select(Advertiser).where(Advertiser.id == advertiser_id)
        )
        return result.scalar_one_or_none()

    async def _get_publisher(self, publisher_id: int) -> Publisher | None:
        result = await self.session.execute(
            select(Publisher).where(Publisher.id == publisher_id)
        )
        return result.scalar_one_or_none()
