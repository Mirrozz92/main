"""ResourceIssue state machine.

Allowed transitions (stage 3c1 — no money movement yet):

    pending → subscribed    (chat_member: user joined)
    pending → expired       (scheduler: TTL passed without subscribe)
    subscribed → verified   (scheduler: hold_until passed)
    subscribed → unsubscribed  (chat_member: user left during hold)
    unsubscribed → reverted (scheduler: finalize after some grace, OR immediately)

Final states: verified, paid, expired, reverted, invalid.

Dynamic hold period based on publisher retention:
    retention >= 80%  → 4h
    50-80%            → 6h
    40-50%            → 8h
    < 40%             → 12h
    Cold start (< 50 verified) → 8h (overrides above)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db.models import (
    CampaignResource,
    Publisher,
    PublisherBot,
    ResourceIssue,
)
from src.core.db.models.enums import (
    CampaignStatus,
    IssueStatus,
    ResourceStatus,
    WebhookEventType,
)
from src.core.logging import get_logger
from src.domain.webhooks import WebhookService

log = get_logger("issues.state")


# ---------- Hold computation ----------

COLD_START_MIN_VERIFIED = 50
COLD_START_HOLD_HOURS = 8

HOLD_BY_RETENTION = [
    (Decimal("80"), 4),    # >= 80% → 4h
    (Decimal("50"), 6),    # 50-80% → 6h
    (Decimal("40"), 8),    # 40-50% → 8h
    (Decimal("0"),  12),   # < 40% → 12h
]


def compute_hold_hours(publisher: Publisher) -> int:
    """Pick hold duration in hours based on publisher reputation."""
    # Cold start override: based on rolling 30-day verified count
    if publisher.verified_subs_in_window < COLD_START_MIN_VERIFIED:
        return COLD_START_HOLD_HOURS

    rate = publisher.retention_rate
    for threshold, hours in HOLD_BY_RETENTION:
        if rate >= threshold:
            return hours
    return 12  # fallback


def compute_hold_until(publisher: Publisher, *, subscribed_at: datetime) -> datetime:
    hours = compute_hold_hours(publisher)
    return subscribed_at + timedelta(hours=hours)


# ---------- State transitions ----------


class StateTransitionError(Exception):
    """Raised when a state transition is invalid."""


class IssueStateMachine:
    """Manages ResourceIssue lifecycle. All transitions are session-attached;
    caller is responsible for committing.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def mark_subscribed(
        self,
        issue: ResourceIssue,
        publisher: Publisher,
        *,
        at: datetime | None = None,
    ) -> None:
        """pending → subscribed. Sets hold_until based on publisher retention."""
        if issue.status != IssueStatus.PENDING:
            raise StateTransitionError(
                f"cannot subscribe issue {issue.link_id}: status is {issue.status.value}"
            )

        now = at or datetime.now(timezone.utc)
        if issue.expires_at < now:
            # Race: scheduler already expired it. Mark expired instead.
            issue.status = IssueStatus.EXPIRED
            log.warning("issue_expired_at_subscribe", link_id=issue.link_id)
            return

        issue.status = IssueStatus.SUBSCRIBED
        issue.subscribed_at = now
        issue.hold_until = compute_hold_until(publisher, subscribed_at=now)
        log.info(
            "issue_subscribed",
            link_id=issue.link_id,
            user_tg_id=issue.user_tg_id,
            hold_until=issue.hold_until.isoformat(),
        )
        await self._emit_webhook(issue, WebhookEventType.RESOURCE_SUBSCRIBED)

    async def mark_unsubscribed(
        self,
        issue: ResourceIssue,
        *,
        at: datetime | None = None,
    ) -> None:
        """subscribed → unsubscribed (terminal-ish, will become reverted).

        Per business rules: re-subscribing after unsub does NOT restore the issue.
        """
        now = at or datetime.now(timezone.utc)

        if issue.status == IssueStatus.SUBSCRIBED:
            issue.status = IssueStatus.UNSUBSCRIBED
            issue.unsubscribed_at = now
            log.info("issue_unsubscribed", link_id=issue.link_id, user_tg_id=issue.user_tg_id)
            await self._emit_webhook(issue, WebhookEventType.RESOURCE_UNSUBSCRIBED)
        elif issue.status == IssueStatus.VERIFIED:
            # User unsubscribed AFTER hold ended → still mark unsubscribed for analytics,
            # but money is already counted. 3c2 will handle revert from balance.
            issue.status = IssueStatus.UNSUBSCRIBED
            issue.unsubscribed_at = now
            log.warning(
                "issue_unsubscribed_after_verify",
                link_id=issue.link_id, user_tg_id=issue.user_tg_id,
            )
            await self._emit_webhook(issue, WebhookEventType.RESOURCE_UNSUBSCRIBED)
        else:
            log.info(
                "issue_unsubscribe_ignored",
                link_id=issue.link_id, current_status=issue.status.value,
            )

    async def mark_verified(
        self,
        issue: ResourceIssue,
        *,
        at: datetime | None = None,
    ) -> None:
        """subscribed → verified. Called by scheduler after hold_until."""
        if issue.status != IssueStatus.SUBSCRIBED:
            raise StateTransitionError(
                f"cannot verify {issue.link_id}: status is {issue.status.value}"
            )

        now = at or datetime.now(timezone.utc)
        if issue.hold_until is None or issue.hold_until > now:
            raise StateTransitionError(
                f"cannot verify {issue.link_id}: hold not finished"
            )

        issue.status = IssueStatus.VERIFIED
        issue.verified_at = now
        log.info(
            "issue_verified",
            link_id=issue.link_id, user_tg_id=issue.user_tg_id,
        )
        await self._emit_webhook(issue, WebhookEventType.RESOURCE_VERIFIED)

    async def mark_expired(
        self,
        issue: ResourceIssue,
        *,
        at: datetime | None = None,
    ) -> None:
        """pending → expired (TTL passed without subscription)."""
        if issue.status != IssueStatus.PENDING:
            return  # nothing to do

        issue.status = IssueStatus.EXPIRED
        log.info(
            "issue_expired",
            link_id=issue.link_id, user_tg_id=issue.user_tg_id,
            expires_at=issue.expires_at.isoformat() if issue.expires_at else None,
        )
        await self._emit_webhook(issue, WebhookEventType.RESOURCE_EXPIRED)

    async def mark_reverted(
        self,
        issue: ResourceIssue,
        *,
        at: datetime | None = None,
    ) -> None:
        """unsubscribed → reverted (final). 3c2 will handle money revert."""
        if issue.status != IssueStatus.UNSUBSCRIBED:
            return

        issue.status = IssueStatus.REVERTED
        log.info("issue_reverted", link_id=issue.link_id)
        await self._emit_webhook(issue, WebhookEventType.RESOURCE_REVERTED)

    async def _emit_webhook(
        self,
        issue: ResourceIssue,
        event_type: "WebhookEventType",
    ) -> None:
        """Emit a webhook event for an issue transition. Swallows errors."""
        try:
            svc = WebhookService(self.session)
            await svc.emit_issue_event(issue=issue, event_type=event_type)
        except Exception as e:
            log.warning("webhook_emit_failed", link_id=issue.link_id, error=str(e))
