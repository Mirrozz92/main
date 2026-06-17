"""Service layer for campaigns.

Critical: budget reservation MUST be atomic. We:
1. Lock the advertiser row (SELECT ... FOR UPDATE).
2. Verify balance >= budget.
3. Deduct from balance_rub, add to reserved_rub.
4. Update campaign budget fields.
5. Create a CAMPAIGN_RESERVE transaction.

All in one DB session/transaction.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.db.models import Advertiser, Campaign, CampaignResource
from src.core.db.models.enums import (
    CampaignStatus,
    ResourceStatus,
    ResourceType,
    TransactionStatus,
    TransactionType,
    VerificationMethod,
)
from src.core.logging import get_logger
from src.domain.campaigns.repository import CampaignRepository
from src.domain.checker_bots import CheckerBotRepository
from src.domain.exceptions import (
    CampaignValidationError,
    DuplicateResourceError,
    InsufficientFundsError,
    ResourceValidationError,
)
from src.domain.resources.chat_validator import ChatProbeResult
from src.domain.transactions import TransactionRepository

log = get_logger("campaigns")


# Resource type → verification method
_VERIFY_METHOD_MAP: dict[ResourceType, VerificationMethod] = {
    ResourceType.CHANNEL: VerificationMethod.GET_CHAT_MEMBER,
    ResourceType.GROUP: VerificationMethod.GET_CHAT_MEMBER,
    ResourceType.BOT_START: VerificationMethod.START_PARAM,
}


class CampaignService:
    """High-level business operations on campaigns."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = CampaignRepository(session)
        self.checker_repo = CheckerBotRepository(session)
        self.tx_repo = TransactionRepository(session)

    # ---------- Draft creation ----------

    async def create_draft(self, *, advertiser_id: int, title: str) -> Campaign:
        """Create a DRAFT campaign with empty budget. Resources added later.

        Budget is computed when user adds resources (sum of reward * target).
        """
        title = title.strip()
        if not (3 <= len(title) <= 255):
            raise CampaignValidationError(
                "Название должно быть от 3 до 255 символов."
            )

        # Используем budget=0.01 как placeholder т.к. CHECK budget > 0 в БД.
        # Реальный бюджет посчитаем и установим при submit (либо обновим
        # после добавления каждого ресурса). См. update_budget_from_resources().
        return await self.repo.create(
            advertiser_id=advertiser_id,
            title=title,
            budget_total_rub=Decimal("0.01"),
        )

    # ---------- Resource addition ----------

    async def add_resource_to_draft(
        self,
        *,
        campaign: Campaign,
        probe: ChatProbeResult,
        reward_rub: Decimal,
        target_subscribers: int,
    ) -> CampaignResource:
        """Add a resource (channel/group/bot) to a DRAFT campaign.

        Validates:
        - Campaign is in DRAFT
        - reward_rub in [min, max]
        - target in [100, 100000]
        - This chat isn't in another active campaign
        - This chat isn't already in this draft
        """
        settings = get_settings()

        if campaign.status != CampaignStatus.DRAFT:
            raise CampaignValidationError(
                "Можно изменять только черновики кампаний."
            )

        # Validate reward
        min_reward = Decimal("0.50")
        max_reward = Decimal("25")
        if reward_rub < min_reward or reward_rub > max_reward:
            raise ResourceValidationError(
                f"Цена за подписчика должна быть от {min_reward:.2f} ₽ до {max_reward:.0f} ₽."
            )

        # Validate target
        if target_subscribers < 100 or target_subscribers > 100_000:
            raise ResourceValidationError(
                "Количество подписчиков должно быть от 100 до 100 000."
            )

        # Dedup checks
        if probe.tg_chat_id is not None:
            if await self.repo.is_chat_in_draft_campaign(
                campaign_id=campaign.id,
                tg_chat_id=probe.tg_chat_id,
            ):
                raise DuplicateResourceError()
            if await self.repo.is_chat_in_active_campaign(probe.tg_chat_id):
                raise DuplicateResourceError(
                    "Этот канал уже участвует в другой активной кампании. "
                    "Дождитесь её завершения или используйте другой ресурс."
                )

        # Update checker_bots load counter
        cb = await self.checker_repo.get_by_id(probe.checker_bot.id)
        if cb is not None:
            cb.active_resources_count = cb.active_resources_count + 1

        resource = await self.repo.add_resource(
            campaign_id=campaign.id,
            checker_bot_id=probe.checker_bot.id,
            resource_type=probe.resource_type,
            tg_chat_id=probe.tg_chat_id,
            title=probe.title,
            username=probe.username,
            is_private=probe.is_private,
            verify_method=_VERIFY_METHOD_MAP[probe.resource_type],
            reward_rub=reward_rub,
            target_subscribers=target_subscribers,
        )

        # Recompute total budget
        await self._recompute_budget(campaign)

        log.info(
            "campaign_resource_added",
            campaign_id=campaign.id,
            resource_id=resource.id,
            type=probe.resource_type.value,
            chat_id=probe.tg_chat_id,
            reward=str(reward_rub),
            target=target_subscribers,
        )
        return resource

    async def _recompute_budget(self, campaign: Campaign) -> None:
        """Set campaign.budget_total_rub = sum(reward * target) for all resources."""
        resources = await self.repo.list_resources(campaign.id)
        total = sum(
            (r.reward_rub * Decimal(r.target_subscribers) for r in resources),
            Decimal("0"),
        )
        # Avoid zero — CHECK constraint requires > 0
        campaign.budget_total_rub = total if total > 0 else Decimal("0.01")

    # ---------- Submit for moderation ----------

    async def submit_for_moderation(
        self,
        *,
        campaign: Campaign,
        advertiser: Advertiser,
    ) -> None:
        """Move campaign DRAFT → PENDING_MODERATION, reserve budget.

        Atomicity is ensured because everything happens in one DB session.
        """
        settings = get_settings()

        if campaign.status != CampaignStatus.DRAFT:
            raise CampaignValidationError("Можно отправлять только черновики.")

        resources = await self.repo.list_resources(campaign.id)
        if not resources:
            raise CampaignValidationError(
                "В кампании нет ни одного ресурса. Добавьте хотя бы один."
            )

        # Recompute budget from resources
        budget = sum(
            (r.reward_rub * Decimal(r.target_subscribers) for r in resources),
            Decimal("0"),
        )

        if budget < settings.min_campaign_topup_rub:
            # Use min_campaign_topup_rub as our floor for now (= 500 RUB by default)
            # but business rule says 300 RUB. We'll use settings.min_payout_rub * 3 = 300
            # …simpler: introduce explicit setting? For now hardcode 300.
            pass

        if budget < Decimal("300"):
            raise CampaignValidationError(
                f"Минимальный бюджет кампании — 300 ₽. Текущий: {budget:.2f} ₽."
            )

        # Lock advertiser row (FOR UPDATE) to prevent race conditions
        # SQLAlchemy: use with_for_update on a fresh load
        result = await self.session.execute(
            select(Advertiser).where(Advertiser.id == advertiser.id).with_for_update()
        )
        adv_locked = result.scalar_one()

        if adv_locked.balance_rub < budget:
            raise InsufficientFundsError(required=budget, available=adv_locked.balance_rub)

        # Atomic budget reservation
        adv_locked.balance_rub = adv_locked.balance_rub - budget
        adv_locked.reserved_rub = adv_locked.reserved_rub + budget

        campaign.budget_total_rub = budget
        campaign.status = CampaignStatus.PENDING_MODERATION

        await self.tx_repo.create(
            type=TransactionType.CAMPAIGN_RESERVE,
            amount_rub=-budget,                      # отрицательная, т.к. это уход из balance
            advertiser_id=advertiser.id,
            campaign_id=campaign.id,
            description=f"Резервирование бюджета по кампании #{campaign.id}: «{campaign.title}»",
            status=TransactionStatus.COMPLETED,
        )

        log.info(
            "campaign_submitted",
            campaign_id=campaign.id,
            advertiser_id=advertiser.id,
            budget=str(budget),
            resources_count=len(resources),
        )

    # ---------- Cancellation ----------

    async def cancel_draft(self, *, campaign: Campaign) -> None:
        """Delete a DRAFT campaign and decrement checker_bots load."""
        if campaign.status != CampaignStatus.DRAFT:
            raise CampaignValidationError("Можно отменять только черновики.")

        resources = await self.repo.list_resources(campaign.id)
        for r in resources:
            if r.checker_bot_id is not None:
                cb = await self.checker_repo.get_by_id(r.checker_bot_id)
                if cb is not None and cb.active_resources_count > 0:
                    cb.active_resources_count = cb.active_resources_count - 1

        campaign.status = CampaignStatus.CANCELED
        log.info("campaign_cancelled_draft", campaign_id=campaign.id)


    # ---------- Moderation (admin actions) ----------

    async def approve(
        self,
        *,
        campaign: Campaign,
        admin_tg_id: int,
        invite_links: dict[int, str] | None = None,
    ) -> None:
        """Approve a campaign waiting for moderation.

        Args:
            campaign: campaign to approve
            admin_tg_id: TG ID of the admin who approved
            invite_links: map of campaign_resource_id → invite URL (pre-created
                by admin handler via checker-bot.createChatInviteLink)
        """
        from datetime import datetime, timezone

        if campaign.status != CampaignStatus.PENDING_MODERATION:
            raise CampaignValidationError(
                "Можно одобрять только кампании в статусе «на модерации»."
            )

        campaign.status = CampaignStatus.ACTIVE
        campaign.moderated_by_admin_id = admin_tg_id
        campaign.moderated_at = datetime.now(timezone.utc)
        campaign.started_at = datetime.now(timezone.utc)

        # Move budget from reserved → budget_reserved on campaign (т.е. отделяем
        # «зарезервировано на этой кампании» от баланса рекламодателя)
        # Note: до этого момента budget_reserved_rub был 0; теперь он = budget_total_rub.
        campaign.budget_reserved_rub = campaign.budget_total_rub

        # Activate each resource and save invite link
        resources = await self.repo.list_resources(campaign.id)
        for r in resources:
            r.status = ResourceStatus.ACTIVE
            if invite_links and r.id in invite_links:
                r.invite_link = invite_links[r.id]

        log.info(
            "campaign_approved",
            campaign_id=campaign.id,
            admin_tg_id=admin_tg_id,
            resources=len(resources),
        )

    async def reject(
        self,
        *,
        campaign: Campaign,
        admin_tg_id: int,
        reason: str,
    ) -> None:
        """Reject a campaign and refund the reserved budget.

        Moves money from advertiser.reserved_rub → advertiser.balance_rub,
        creates a CAMPAIGN_REFUND transaction.
        """
        from datetime import datetime, timezone

        if campaign.status != CampaignStatus.PENDING_MODERATION:
            raise CampaignValidationError(
                "Можно отклонять только кампании в статусе «на модерации»."
            )

        # Lock advertiser
        result = await self.session.execute(
            select(Advertiser).where(Advertiser.id == campaign.advertiser_id).with_for_update()
        )
        advertiser = result.scalar_one()

        refund_amount = campaign.budget_total_rub

        # Refund: reserved → balance
        if advertiser.reserved_rub < refund_amount:
            log.error(
                "reject_underflow_reserved",
                campaign_id=campaign.id,
                reserved=str(advertiser.reserved_rub),
                refund=str(refund_amount),
            )
            # Защита: не уходим в минус. Возвращаем сколько можем.
            refund_amount = advertiser.reserved_rub

        advertiser.reserved_rub = advertiser.reserved_rub - refund_amount
        advertiser.balance_rub = advertiser.balance_rub + refund_amount

        campaign.status = CampaignStatus.REJECTED
        campaign.rejection_reason = reason
        campaign.moderated_by_admin_id = admin_tg_id
        campaign.moderated_at = datetime.now(timezone.utc)

        # Refund transaction (positive: money returning to balance)
        await self.tx_repo.create(
            type=TransactionType.CAMPAIGN_REFUND,
            amount_rub=refund_amount,
            advertiser_id=advertiser.id,
            campaign_id=campaign.id,
            description=f"Возврат бюджета по отклонённой кампании #{campaign.id}",
            status=TransactionStatus.COMPLETED,
            meta={"rejection_reason": reason},
        )

        # Decrement checker_bots load for each resource (campaign is no longer active)
        for r in await self.repo.list_resources(campaign.id):
            if r.checker_bot_id is not None:
                cb = await self.checker_repo.get_by_id(r.checker_bot_id)
                if cb is not None and cb.active_resources_count > 0:
                    cb.active_resources_count = cb.active_resources_count - 1
            r.status = ResourceStatus.FAILED  # ресурс не пошёл в работу

        log.info(
            "campaign_rejected",
            campaign_id=campaign.id,
            admin_tg_id=admin_tg_id,
            refund=str(refund_amount),
            reason=reason[:100],
        )

    # ---------- Pending moderation queue ----------

    async def list_pending_for_admin(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Campaign]:
        """List campaigns waiting for moderation, oldest first (FIFO)."""
        from sqlalchemy import asc
        from sqlalchemy.orm import selectinload

        result = await self.session.execute(
            select(Campaign)
            .where(Campaign.status == CampaignStatus.PENDING_MODERATION)
            .options(selectinload(Campaign.resources))
            .order_by(asc(Campaign.created_at))
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().unique().all())

    async def count_pending(self) -> int:
        from sqlalchemy import func
        result = await self.session.execute(
            select(func.count(Campaign.id)).where(
                Campaign.status == CampaignStatus.PENDING_MODERATION
            )
        )
        return result.scalar_one()
