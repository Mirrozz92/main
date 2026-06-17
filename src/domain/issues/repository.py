"""Repository for ResourceIssue — issued tasks tracking."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, desc, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db.models import ResourceIssue
from src.core.db.models.enums import IssueStatus


# How long a pending issue is "fresh" — after this we consider it expired (and may re-issue)
DEFAULT_ISSUE_TTL_SECONDS = 3600  # 1 hour


def generate_link_id() -> str:
    """Generate a unique link_id in format lnk_<24hex>."""
    return f"lnk_{secrets.token_hex(12)}"


def generate_task_id() -> str:
    """Generate a unique task_id in format tsk_<24hex>."""
    return f"tsk_{secrets.token_hex(12)}"


class ResourceIssueRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_link_id(self, link_id: str) -> ResourceIssue | None:
        result = await self.session.execute(
            select(ResourceIssue).where(ResourceIssue.link_id == link_id)
        )
        return result.scalar_one_or_none()

    async def list_by_task_id(self, task_id: str) -> list[ResourceIssue]:
        result = await self.session.execute(
            select(ResourceIssue)
            .where(ResourceIssue.task_id == task_id)
            .order_by(ResourceIssue.issued_at)
        )
        return list(result.scalars().all())

    async def already_issued_resource_ids_for_user(
        self,
        *,
        user_tg_id: int,
        publisher_id: int | None = None,
    ) -> set[int]:
        """All campaign_resource_ids that this user has ever been issued.

        Under stage 3c1's GLOBAL uniqueness rule: a resource issued to a user
        by ANY publisher blocks it from being issued to the same user again
        (across all publishers). So we ignore publisher_id here — it stays in
        the signature for backwards compatibility but does nothing.
        """
        result = await self.session.execute(
            select(ResourceIssue.campaign_resource_id).where(
                ResourceIssue.user_tg_id == user_tg_id,
            )
        )
        return {row[0] for row in result.all()}

    async def create_batch(
        self,
        *,
        task_id: str,
        publisher_id: int,
        publisher_bot_id: int,
        publisher_token_id: int,
        user_tg_id: int,
        items: list[dict[str, Any]],
        ttl_seconds: int = DEFAULT_ISSUE_TTL_SECONDS,
    ) -> list[ResourceIssue]:
        """Insert a batch of ResourceIssues atomically.

        Each item dict must have keys:
            campaign_resource_id, reward_rub, publisher_payout_rub, platform_commission_rub
        """
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=ttl_seconds)

        issues: list[ResourceIssue] = []
        for item in items:
            issue = ResourceIssue(
                link_id=generate_link_id(),
                task_id=task_id,
                publisher_id=publisher_id,
                publisher_bot_id=publisher_bot_id,
                publisher_token_id=publisher_token_id,
                user_tg_id=user_tg_id,
                campaign_resource_id=item["campaign_resource_id"],
                reward_rub=item["reward_rub"],
                publisher_payout_rub=item["publisher_payout_rub"],
                platform_commission_rub=item["platform_commission_rub"],
                retention_bonus_rub=item.get("retention_bonus_rub", Decimal("0")),
                status=IssueStatus.PENDING,
                issued_at=now,
                expires_at=expires_at,
                user_context=item.get("user_context", {}),
            )
            self.session.add(issue)
            issues.append(issue)

        await self.session.flush()
        return issues

    async def find_active_issue_for_user_and_chat(
        self,
        *,
        chat_id: int,
        user_tg_id: int,
    ) -> "ResourceIssue | None":
        """Find a non-final issue for (chat_id, user_tg_id).

        Used when checker-bot receives chat_member event and we need to map
        it to a resource_issue. We look in resource_issues joined with
        campaign_resources where tg_chat_id matches.

        Returns the issue if status is PENDING or SUBSCRIBED (i.e. still
        actionable), otherwise None.
        """
        from sqlalchemy import and_, or_, select
        from src.core.db.models import CampaignResource
        from src.core.db.models.enums import IssueStatus

        result = await self.session.execute(
            select(ResourceIssue)
            .join(CampaignResource, ResourceIssue.campaign_resource_id == CampaignResource.id)
            .where(
                and_(
                    CampaignResource.tg_chat_id == chat_id,
                    ResourceIssue.user_tg_id == user_tg_id,
                    ResourceIssue.status.in_([IssueStatus.PENDING, IssueStatus.SUBSCRIBED, IssueStatus.VERIFIED]),
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_expired_pending(self, *, limit: int = 100) -> list["ResourceIssue"]:
        """For expire-worker: pending issues whose expires_at < now."""
        from datetime import datetime, timezone
        from sqlalchemy import and_, select
        from src.core.db.models.enums import IssueStatus

        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            select(ResourceIssue)
            .where(
                and_(
                    ResourceIssue.status == IssueStatus.PENDING,
                    ResourceIssue.expires_at < now,
                )
            )
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list(result.scalars().all())

    async def list_hold_ready(self, *, limit: int = 100) -> list["ResourceIssue"]:
        """For verify-worker: subscribed issues whose hold_until < now."""
        from datetime import datetime, timezone
        from sqlalchemy import and_, select
        from src.core.db.models.enums import IssueStatus

        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            select(ResourceIssue)
            .where(
                and_(
                    ResourceIssue.status == IssueStatus.SUBSCRIBED,
                    ResourceIssue.hold_until.is_not(None),
                    ResourceIssue.hold_until < now,
                )
            )
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list(result.scalars().all())

    async def list_unsubscribed_pending_revert(self, *, limit: int = 100) -> list["ResourceIssue"]:
        """For revert-worker: unsubscribed issues that need finalization."""
        from sqlalchemy import select
        from src.core.db.models.enums import IssueStatus

        result = await self.session.execute(
            select(ResourceIssue)
            .where(ResourceIssue.status == IssueStatus.UNSUBSCRIBED)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list(result.scalars().all())
