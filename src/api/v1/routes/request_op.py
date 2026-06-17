"""POST /api/v1/request-op — issue tasks (subscription requests) to a user.

This is the main endpoint of the publisher-side API. Partner bots call it
when they want to show their user new sponsor channels/bots to subscribe to.

Flow:
  1. Auth via Bearer token → get PublisherBot
  2. Check Redis idempotency cache: if same (bot, user) requested within
     list_ttl_seconds — return same response.
  3. Matchmaking: find suitable campaigns, filter already-seen ones, rank.
  4. Atomically create ResourceIssue rows (one per task).
  5. Build response: task_id + array of TaskItem with invite_link/start_link.
  6. Cache response in Redis with TTL.

Rate limit: 60 req/min per token (RFC 6585 429).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import (
    get_current_publisher,
    get_current_publisher_bot,
    get_current_token,
    get_session,
)
from src.api.rate_limit import request_op_limit
from src.api.v1.routes import request_op_cache as cache
from src.api.v1.schemas import RequestOpRequest, RequestOpResponse, TaskItem
from src.core.db.models import Publisher, PublisherApiToken, PublisherBot
from src.core.config import get_settings
from src.core.logging import get_logger
from src.domain.end_users import EndUserRepository, EndUserService, OnboardingTokenService
from src.domain.issues import MatchmakingService, ResourceIssueRepository
from src.domain.issues.repository import generate_task_id

router = APIRouter(prefix="/api/v1", tags=["tasks"])
log = get_logger("api.request_op")


@router.post(
    "/request-op",
    response_model=RequestOpResponse,
    summary="Request a batch of sponsor tasks for a user",
    description=(
        "Issues a batch of sponsor tasks (channels/groups/bots to subscribe to) "
        "for the given Telegram user. The user is expected to subscribe to each "
        "of them, then your bot calls `/check-resource` for each `link_id` to "
        "confirm subscription.\n\n"
        "**Idempotency**: within your bot's `list_ttl_seconds` window, repeated "
        "calls for the same `user_id` return the SAME task list. After TTL — "
        "a fresh list is issued.\n\n"
        "**Rate limit**: 60 requests per minute per token.\n\n"
        "**Errors**:\n"
        "- `401` — missing or invalid token\n"
        "- `403` — bot disabled by owner\n"
        "- `429` — rate limit exceeded\n"
    ),
)
async def request_op(
    body: RequestOpRequest,
    publisher: Publisher = Depends(get_current_publisher),
    publisher_bot: PublisherBot = Depends(get_current_publisher_bot),
    token: PublisherApiToken = Depends(get_current_token),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(request_op_limit),
) -> RequestOpResponse:
    user_tg_id = body.user_id

    # 1. Check idempotency cache (only for successful task issues — onboarding
    # checks are skipped from cache so user sees fresh state)
    cached = await cache.get_cached(publisher_bot.id, user_tg_id)
    if cached is not None and cached.get("reason") != "onboarding_required":
        log.info(
            "request_op_cache_hit",
            publisher_bot_id=publisher_bot.id, user_tg_id=user_tg_id,
        )
        return RequestOpResponse(**cached)

    # 2. Onboarding check — does this user have a EndUser record?
    eu_svc = EndUserService(session)
    if not await eu_svc.is_onboarded(user_tg_id):
        token_svc = OnboardingTokenService()
        try:
            onb_token = await token_svc.issue(
                user_tg_id=user_tg_id,
                publisher_bot_id=publisher_bot.id,
            )
            settings = get_settings()
            base_url = settings.public_base_url.rstrip("/")
            onboarding_url = f"{base_url}/onboard/{onb_token}"
            log.info(
                "request_op_onboarding_required",
                publisher_bot_id=publisher_bot.id, user_tg_id=user_tg_id,
            )
            return RequestOpResponse(
                ok=False,
                reason="onboarding_required",
                onboarding_url=onboarding_url,
            )
        except Exception as e:
            log.error("onboarding_token_issue_failed", error=str(e))
            # Fall through — degrade gracefully to no_tasks rather than crash

    # 3. Load EndUser for targeting filter (we already know it exists past
    # the onboarding check above, but defensively None-check).
    eu_repo = EndUserRepository(session)
    end_user = await eu_repo.get_by_tg_id(user_tg_id)

    # 3b. Update audience signals if the partner reported any (NULL = skip).
    if end_user is not None:
        from datetime import datetime, timezone
        reported = False
        for field in (
            "has_telegram_premium", "has_profile_photo",
            "has_username", "has_bio", "has_stories",
        ):
            value = getattr(body, field, None)
            if value is not None:
                setattr(end_user, field, value)
                reported = True
        if reported:
            end_user.audience_reported_at = datetime.now(timezone.utc)

    # 4. Matchmaking
    mm = MatchmakingService(session)
    tasks = await mm.find_tasks_for_user(
        publisher_id=publisher.id,
        publisher_bot=publisher_bot,
        user_tg_id=user_tg_id,
        requested_count=body.count,
        is_vip=publisher.is_vip,
        end_user=end_user,
    )

    if not tasks:
        response = RequestOpResponse(ok=False, reason="no_tasks")
        # Cache "no_tasks" for shorter period (60s) to allow re-checking soon
        await cache.set_cached(publisher_bot.id, user_tg_id, response.model_dump(), 60)
        log.info(
            "request_op_no_tasks",
            publisher_bot_id=publisher_bot.id, user_tg_id=user_tg_id,
        )
        return response

    # 3. Atomically create ResourceIssue rows
    task_id = generate_task_id()
    issue_repo = ResourceIssueRepository(session)
    items = [
        {
            "campaign_resource_id": t.campaign_resource_id,
            "reward_rub": t.reward_rub,
            "publisher_payout_rub": t.publisher_payout_rub,
            "platform_commission_rub": t.platform_commission_rub,
        }
        for t in tasks
    ]
    issues = await issue_repo.create_batch(
        task_id=task_id,
        publisher_id=publisher.id,
        publisher_bot_id=publisher_bot.id,
        publisher_token_id=token.id,
        user_tg_id=user_tg_id,
        items=items,
        ttl_seconds=publisher_bot.list_ttl_seconds,
    )

    # 4. Increment bot counters
    publisher_bot.total_requests = publisher_bot.total_requests + 1
    publisher_bot.total_issued = publisher_bot.total_issued + len(issues)

    # 5. Build response items (zip matched tasks ↔ issues for link_id)
    task_items: list[TaskItem] = []
    for matched, issue in zip(tasks, issues):
        start_link = None
        invite_link = None
        if matched.resource_type == "bot_start":
            if matched.bot_username:
                start_link = (
                    f"https://t.me/{matched.bot_username}"
                    f"?start=fastsub_{issue.link_id}"
                )
        else:
            invite_link = matched.invite_link

        task_items.append(TaskItem(
            link_id=issue.link_id,
            type=matched.resource_type,  # type: ignore[arg-type]
            title=matched.title,
            username=matched.username,
            members_count=matched.members_count,
            invite_link=invite_link,
            start_link=start_link,
            reward_for_publisher=matched.publisher_payout_rub,
        ))

    response = RequestOpResponse(
        ok=True,
        task_id=task_id,
        tasks=task_items,
    )

    # 6. Cache for bot.list_ttl_seconds
    await cache.set_cached(
        publisher_bot.id, user_tg_id,
        response.model_dump(), publisher_bot.list_ttl_seconds,
    )

    log.info(
        "request_op_issued",
        publisher_bot_id=publisher_bot.id,
        user_tg_id=user_tg_id,
        task_id=task_id,
        tasks_count=len(task_items),
    )
    return response
