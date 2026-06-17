"""POST /api/v1/check-task — check status of all resources in a task.

Batch counterpart of /check-resource: given a `task_id` from /request-op,
returns the current status of every issued link in that task in one call.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import (
    get_current_publisher,
    get_current_publisher_bot,
    get_session,
)
from src.api.rate_limit import check_task_limit
from src.api.v1.schemas import CheckTaskRequest, CheckTaskResponse, IssueStatusItem
from src.core.db.models import Publisher, PublisherBot
from src.core.logging import get_logger
from src.domain.issues import ResourceIssueRepository

router = APIRouter(prefix="/api/v1", tags=["tasks"])
log = get_logger("api.check_task")


@router.post(
    "/check-task",
    response_model=CheckTaskResponse,
    summary="Check status of all resources in a task",
    description=(
        "Returns the current status of every `link_id` issued under one "
        "`task_id` (from a `/request-op` response) in a single call. Use this "
        "instead of calling `/check-resource` once per link.\n\n"
        "See `/check-resource` for the list of possible statuses.\n\n"
        "**Rate limit**: 300 requests per minute per token."
    ),
)
async def check_task(
    body: CheckTaskRequest,
    publisher: Publisher = Depends(get_current_publisher),
    publisher_bot: PublisherBot = Depends(get_current_publisher_bot),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(check_task_limit),
) -> CheckTaskResponse:
    issue_repo = ResourceIssueRepository(session)
    rows = await issue_repo.list_by_task_id_with_resource(body.task_id)

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"task_id not found: {body.task_id}",
        )

    # Ownership check: every issue in the task must belong to this publisher.
    if any(issue.publisher_id != publisher.id for issue, _ in rows):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="this task_id belongs to a different publisher",
        )

    items = [IssueStatusItem.from_issue(issue, resource) for issue, resource in rows]

    log.info(
        "check_task_called",
        task_id=body.task_id,
        publisher_id=publisher.id,
        items=len(items),
    )

    return CheckTaskResponse(ok=True, task_id=body.task_id, items=items)
