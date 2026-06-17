"""Retention rate calculation for publishers.

Retention is computed over a rolling 30-day window:
    retention_rate = verified / (verified + unsubscribed)
where both counts are taken from resource_issues within the last 30 days.

Counters:
    - verified_subs_in_window: count of issues with status in (verified) in window
    - unsubscriptions_in_window (computed inline): status in (unsubscribed, reverted)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db.models import Publisher, ResourceIssue
from src.core.db.models.enums import IssueStatus
from src.core.logging import get_logger

log = get_logger("publishers.retention")


RETENTION_WINDOW_DAYS = 30


async def recompute_for_publisher(
    session: AsyncSession,
    publisher: Publisher,
) -> None:
    """Recompute retention_rate and verified_subs_in_window for one publisher.

    Counts over the last 30 days of issued_at.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_WINDOW_DAYS)

    # Count verified and unsubscribed/reverted issues in window
    stmt = (
        select(ResourceIssue.status, func.count(ResourceIssue.link_id))
        .where(
            and_(
                ResourceIssue.publisher_id == publisher.id,
                ResourceIssue.issued_at >= cutoff,
                ResourceIssue.status.in_([
                    IssueStatus.VERIFIED,
                    IssueStatus.UNSUBSCRIBED,
                    IssueStatus.REVERTED,
                ]),
            )
        )
        .group_by(ResourceIssue.status)
    )
    result = await session.execute(stmt)
    counts: dict[IssueStatus, int] = {row[0]: row[1] for row in result.all()}

    verified = counts.get(IssueStatus.VERIFIED, 0)
    unsubbed = counts.get(IssueStatus.UNSUBSCRIBED, 0) + counts.get(IssueStatus.REVERTED, 0)

    total = verified + unsubbed
    if total == 0:
        rate = Decimal("100")  # No data → assume perfect
    else:
        rate = (Decimal(verified) / Decimal(total) * Decimal("100")).quantize(Decimal("0.01"))

    publisher.verified_subs_in_window = verified
    publisher.retention_rate = rate
    publisher.retention_calculated_at = datetime.now(timezone.utc)

    # All-time verified count (for rating volume score)
    total_verified_stmt = select(func.count(ResourceIssue.link_id)).where(
        and_(
            ResourceIssue.publisher_id == publisher.id,
            ResourceIssue.status == IssueStatus.VERIFIED,
        )
    )
    total_verified = (await session.execute(total_verified_stmt)).scalar_one() or 0
    publisher.verified_subs_total = total_verified

    # Recompute reputation rating
    from src.domain.publishers.rating import compute_rating
    publisher.rating = compute_rating(rate, total_verified)
    publisher.rating_calculated_at = datetime.now(timezone.utc)

    log.info(
        "retention_recomputed",
        publisher_id=publisher.id,
        verified=verified,
        unsubscribed=unsubbed,
        rate=str(rate),
        verified_total=total_verified,
        rating=str(publisher.rating),
    )
