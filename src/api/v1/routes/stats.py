"""GET /api/v1/stats — aggregated task counters for the authenticated publisher."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import (
    get_current_publisher,
    get_current_publisher_bot,
    get_session,
)
from src.api.rate_limit import stats_limit
from src.api.v1.schemas import StatsResponse, build_stats
from src.core.db.models import Publisher, PublisherBot
from src.core.logging import get_logger
from src.domain.issues import ResourceIssueRepository

router = APIRouter(prefix="/api/v1", tags=["publishers"])
log = get_logger("api.stats")

DEFAULT_WINDOW_DAYS = 30


def _as_utc(dt: datetime) -> datetime:
    """Treat tz-naive input as UTC; the DB stores tz-aware timestamps."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


@router.get(
    "/stats",
    response_model=StatsResponse,
    summary="Aggregated counters for your account",
    description=(
        "Returns issued-task counts per status plus earned/in-hold payouts for "
        "the authenticated publisher, aggregated by `issued_at` over a window.\n\n"
        "**Window**: pass `from` and/or `to` (ISO-8601). Defaults to the last "
        f"{DEFAULT_WINDOW_DAYS} days. Counts cover all of the publisher's bots.\n\n"
        "**Rate limit**: 60 requests per minute per token."
    ),
)
async def stats(
    from_: datetime | None = Query(
        default=None, alias="from", description="Window start (ISO-8601). Default: to - 30d."
    ),
    to: datetime | None = Query(
        default=None, description="Window end (ISO-8601). Default: now."
    ),
    publisher: Publisher = Depends(get_current_publisher),
    publisher_bot: PublisherBot = Depends(get_current_publisher_bot),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(stats_limit),
) -> StatsResponse:
    now = datetime.now(UTC)
    period_to = _as_utc(to) if to is not None else now
    period_from = _as_utc(from_) if from_ is not None else period_to - timedelta(days=DEFAULT_WINDOW_DAYS)

    if period_from > period_to:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="`from` must be earlier than or equal to `to`",
        )

    repo = ResourceIssueRepository(session)
    rows = await repo.aggregate_for_publisher(
        publisher_id=publisher.id,
        since=period_from,
        until=period_to,
    )
    str_rows = [(s.value, count, payout, bonus) for s, count, payout, bonus in rows]

    log.info(
        "stats_called",
        publisher_id=publisher.id,
        period_from=period_from.isoformat(),
        period_to=period_to.isoformat(),
    )

    return build_stats(str_rows, period_from=period_from, period_to=period_to)
