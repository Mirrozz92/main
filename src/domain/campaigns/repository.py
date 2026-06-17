"""Repository for Campaign + CampaignResource."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.db.models import Campaign, CampaignResource
from src.core.db.models.enums import (
    CampaignStatus,
    ResourceStatus,
    ResourceType,
    VerificationMethod,
)


# Active statuses for "cannot add same chat twice" check
_ACTIVE_CAMPAIGN_STATUSES = (
    CampaignStatus.PENDING_MODERATION,
    CampaignStatus.ACTIVE,
    CampaignStatus.PAUSED,
)


class CampaignRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---------- Campaigns ----------

    async def get_by_id(self, campaign_id: int, *, with_resources: bool = False) -> Campaign | None:
        stmt = select(Campaign).where(Campaign.id == campaign_id)
        if with_resources:
            stmt = stmt.options(selectinload(Campaign.resources))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_advertiser(
        self,
        advertiser_id: int,
        *,
        limit: int = 10,
        offset: int = 0,
        statuses: tuple[CampaignStatus, ...] | None = None,
    ) -> list[Campaign]:
        stmt = (
            select(Campaign)
            .where(Campaign.advertiser_id == advertiser_id)
            .options(selectinload(Campaign.resources))
            .order_by(desc(Campaign.created_at))
            .limit(limit)
            .offset(offset)
        )
        if statuses:
            stmt = stmt.where(Campaign.status.in_(statuses))
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all())

    async def count_for_advertiser(
        self,
        advertiser_id: int,
        *,
        statuses: tuple[CampaignStatus, ...] | None = None,
    ) -> int:
        stmt = select(func.count(Campaign.id)).where(Campaign.advertiser_id == advertiser_id)
        if statuses:
            stmt = stmt.where(Campaign.status.in_(statuses))
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def create(
        self,
        *,
        advertiser_id: int,
        title: str,
        budget_total_rub: Decimal,
        targeting: dict[str, Any] | None = None,
    ) -> Campaign:
        campaign = Campaign(
            advertiser_id=advertiser_id,
            title=title,
            status=CampaignStatus.DRAFT,
            budget_total_rub=budget_total_rub,
            targeting=targeting or {},
        )
        self.session.add(campaign)
        await self.session.flush()
        return campaign

    # ---------- Resources ----------

    async def add_resource(
        self,
        *,
        campaign_id: int,
        checker_bot_id: int | None,
        resource_type: ResourceType,
        tg_chat_id: int | None,
        title: str,
        username: str | None,
        is_private: bool,
        verify_method: VerificationMethod,
        reward_rub: Decimal,
        target_subscribers: int,
    ) -> CampaignResource:
        resource = CampaignResource(
            campaign_id=campaign_id,
            checker_bot_id=checker_bot_id,
            type=resource_type,
            tg_chat_id=tg_chat_id,
            title=title,
            username=username,
            is_private=is_private,
            verify_method=verify_method,
            reward_rub=reward_rub,
            target_subscribers=target_subscribers,
            status=ResourceStatus.PENDING,
        )
        self.session.add(resource)
        await self.session.flush()
        return resource

    async def is_chat_in_active_campaign(self, tg_chat_id: int) -> bool:
        """Check if this chat is already part of any active/pending campaign.

        Used to prevent the same chat being booked twice simultaneously.
        """
        stmt = (
            select(func.count(CampaignResource.id))
            .join(Campaign, CampaignResource.campaign_id == Campaign.id)
            .where(
                and_(
                    CampaignResource.tg_chat_id == tg_chat_id,
                    Campaign.status.in_(_ACTIVE_CAMPAIGN_STATUSES),
                    CampaignResource.status.in_((
                        ResourceStatus.PENDING,
                        ResourceStatus.ACTIVE,
                        ResourceStatus.PAUSED,
                    )),
                )
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one() > 0

    async def is_chat_in_draft_campaign(self, *, campaign_id: int, tg_chat_id: int) -> bool:
        """Check duplicate inside the same draft campaign being assembled."""
        stmt = select(func.count(CampaignResource.id)).where(
            and_(
                CampaignResource.campaign_id == campaign_id,
                CampaignResource.tg_chat_id == tg_chat_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one() > 0

    async def list_resources(self, campaign_id: int) -> list[CampaignResource]:
        result = await self.session.execute(
            select(CampaignResource)
            .where(CampaignResource.campaign_id == campaign_id)
            .order_by(CampaignResource.id)
        )
        return list(result.scalars().all())
