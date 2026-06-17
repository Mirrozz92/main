"""Handle chat_member updates to track subscriptions.

When a user joins a channel/group where one of our checker-bots is admin,
Telegram sends a `chat_member` update. We:
  1. Find the matching ResourceIssue by (chat_id, user_tg_id).
  2. If issue is PENDING — transition to SUBSCRIBED, set hold_until.
  3. If issue is SUBSCRIBED/VERIFIED and user LEFT — transition to UNSUBSCRIBED.
  4. If no matching issue — IGNORE (direct join, not from FastSub).
"""

from __future__ import annotations

from aiogram import Router
from aiogram.types import ChatMemberUpdated
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db.models.enums import IssueStatus
from src.core.logging import get_logger
from src.domain.issues import IssueStateMachine, ResourceIssueRepository
from src.domain.publishers import PublisherRepository

router = Router(name="checker_chat_member")
log = get_logger("checker.chat_member")


# Statuses that mean"user is now a member"
JOINED_STATUSES = {"member","administrator","creator"}
# Statuses that mean"user is no longer a member"
LEFT_STATUSES = {"left","kicked","restricted"}


@router.chat_member()
async def on_chat_member_update(
    event: ChatMemberUpdated,
    session: AsyncSession,
) -> None:
    """Process chat_member status change for one user in one chat."""
    old_status = event.old_chat_member.status
    new_status = event.new_chat_member.status
    user_tg_id = event.new_chat_member.user.id
    chat_id = event.chat.id

    # Skip bots and our checker-bot itself
    if event.new_chat_member.user.is_bot:
        return

    log.debug(
        "chat_member_event",
        chat_id=chat_id, user_tg_id=user_tg_id,
        old=old_status, new=new_status,
    )

    # Determine transition direction
    joined = old_status in LEFT_STATUSES and new_status in JOINED_STATUSES
    left = old_status in JOINED_STATUSES and new_status in LEFT_STATUSES

    if not joined and not left:
        return # status changed but not in our interest (e.g. promotion to admin)

    # Find matching issue
    issue_repo = ResourceIssueRepository(session)
    issue = await issue_repo.find_active_issue_for_user_and_chat(
        chat_id=chat_id, user_tg_id=user_tg_id,
    )
    if issue is None:
        log.info(
            "chat_member_no_matching_issue",
            chat_id=chat_id, user_tg_id=user_tg_id,
            event="join"if joined else"leave",
        )
        return

    # Process transition
    machine = IssueStateMachine(session)

    if joined:
        if issue.status != IssueStatus.PENDING:
            # Already subscribed (re-join after some bug? duplicate event?) — ignore
            log.info(
                "join_event_for_non_pending",
                link_id=issue.link_id, status=issue.status.value,
            )
            return

        # Need publisher for hold computation
        pub_repo = PublisherRepository(session)
        publisher = await pub_repo.get_by_id(issue.publisher_id)
        if publisher is None:
            log.error("publisher_not_found", publisher_id=issue.publisher_id)
            return

        await machine.mark_subscribed(issue, publisher)

    elif left:
        if issue.status not in (IssueStatus.SUBSCRIBED, IssueStatus.VERIFIED):
            return
        await machine.mark_unsubscribed(issue)
