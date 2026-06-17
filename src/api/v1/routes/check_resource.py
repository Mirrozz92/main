"""POST /api/v1/check-resource — check subscription status by link_id.

**Stage 3b: stub implementation.**

Returns the current `status` field from `resource_issues`. Real subscription
verification (via chat_member events through checker-bot) will come in 3c —
this endpoint will then return updated statuses after the worker has processed
chat_member updates.

For now: this returns `pending` for newly-issued tasks. Partner bots can poll
this to know when a subscription is confirmed.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import (
    get_current_publisher,
    get_current_publisher_bot,
    get_session,
)
from src.api.rate_limit import check_resource_limit
from src.core.db.models import Publisher, PublisherBot
from src.core.logging import get_logger
from src.domain.issues import ResourceIssueRepository

router = APIRouter(prefix="/api/v1", tags=["tasks"])
log = get_logger("api.check_resource")


class CheckResourceRequest(BaseModel):
    link_id: str = Field(
        ..., min_length=10, max_length=32,
        description="link_id from /request-op response",
        examples=["lnk_a1b2c3d4e5f6a1b2c3d4e5f6"],
    )


class CheckResourceResponse(BaseModel):
    ok: bool
    link_id: str
    status: Literal[
        "pending", "subscribed", "verified", "expired",
        "unsubscribed", "reverted", "invalid", "paid",
    ] | None = None
    reason: str | None = None


@router.post(
    "/check-resource",
    response_model=CheckResourceResponse,
    summary="Check status of one issued task",
    description=(
        "Returns the current verification status for a `link_id` issued earlier "
        "via `/request-op`.\n\n"
        "**Possible statuses**:\n"
        "- `pending` — issued, user has not subscribed yet\n"
        "- `subscribed` — user is subscribed, awaiting hold period\n"
        "- `verified` — confirmed, payment processing\n"
        "- `paid` — paid out to publisher\n"
        "- `expired` — link expired without subscription\n"
        "- `unsubscribed` — user subscribed then left within hold\n"
        "- `reverted` — payment reverted due to unsubscription\n"
        "- `invalid` — task became invalid (campaign canceled, etc)\n\n"
        "**Rate limit**: 300 requests per minute per token.\n\n"
        "**Note (stage 3b)**: Real-time verification through Telegram is not yet "
        "implemented. Statuses will be updated in stage 3c when chat_member "
        "tracking is enabled."
    ),
)
async def check_resource(
    body: CheckResourceRequest,
    publisher: Publisher = Depends(get_current_publisher),
    publisher_bot: PublisherBot = Depends(get_current_publisher_bot),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(check_resource_limit),
) -> CheckResourceResponse:
    issue_repo = ResourceIssueRepository(session)
    issue = await issue_repo.get_by_link_id(body.link_id)

    if issue is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"link_id not found: {body.link_id}",
        )

    # Ownership check: only the publisher who issued can query
    if issue.publisher_id != publisher.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="this link_id belongs to a different publisher",
        )

    # Update check_calls_count
    issue.check_calls_count = issue.check_calls_count + 1

    log.info(
        "check_resource_called",
        link_id=issue.link_id,
        publisher_id=publisher.id,
        status=issue.status.value,
        check_calls=issue.check_calls_count,
    )

    return CheckResourceResponse(
        ok=True,
        link_id=issue.link_id,
        status=issue.status.value,  # type: ignore[arg-type]
    )
