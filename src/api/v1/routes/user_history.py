"""GET /api/v1/user/{user_id}/history — paginated task history for an end-user.

Returns the issues this publisher has handed to a given Telegram user, newest
first. Lets partners show a user their subscription history and reconcile payouts.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import (
    get_current_publisher,
    get_current_publisher_bot,
    get_session,
)
from src.api.rate_limit import user_history_limit
from src.api.v1.schemas import IssueStatusItem, UserHistoryResponse
from src.core.db.models import Publisher, PublisherBot
from src.core.logging import get_logger
from src.domain.issues import ResourceIssueRepository

router = APIRouter(prefix="/api/v1", tags=["tasks"])
log = get_logger("api.user_history")


@router.get(
    "/user/{user_id}/history",
    response_model=UserHistoryResponse,
    summary="Paginated task history for one end-user",
    description=(
        "Returns issues handed to the given Telegram `user_id` by your account, "
        "newest first. Only issues owned by the authenticated publisher are "
        "returned.\n\n"
        "**Pagination**: use `limit` (max 100) and `offset`. When `has_more` is "
        "true, request the next page with `offset += limit`.\n\n"
        "**Rate limit**: 120 requests per minute per token."
    ),
)
async def user_history(
    user_id: int = Path(..., description="Telegram user ID of the end-user"),
    limit: int = Query(default=50, ge=1, le=100, description="Page size (max 100)"),
    offset: int = Query(default=0, ge=0, description="Number of items to skip"),
    publisher: Publisher = Depends(get_current_publisher),
    publisher_bot: PublisherBot = Depends(get_current_publisher_bot),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(user_history_limit),
) -> UserHistoryResponse:
    issue_repo = ResourceIssueRepository(session)
    rows, has_more = await issue_repo.list_user_history(
        user_tg_id=user_id,
        publisher_id=publisher.id,
        limit=limit,
        offset=offset,
    )

    items = [IssueStatusItem.from_issue(issue, resource) for issue, resource in rows]

    log.info(
        "user_history_called",
        user_id=user_id,
        publisher_id=publisher.id,
        returned=len(items),
        offset=offset,
    )

    return UserHistoryResponse(
        ok=True,
        user_id=user_id,
        items=items,
        limit=limit,
        offset=offset,
        has_more=has_more,
    )
