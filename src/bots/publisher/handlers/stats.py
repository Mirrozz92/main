"""Publisher-level stats handler: 1d / 7d / 30d windows, retention, hold, commission."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.bots.publisher import texts
from src.bots.publisher.keyboards import back_to_menu_kb
from src.core.db.models import Publisher, ResourceIssue
from src.core.db.models.enums import IssueStatus
from src.core.logging import get_logger
from src.domain.issues.state_machine import compute_hold_hours
from src.domain.publishers.commission import (
    MIN_VERIFIED_FOR_SCALE,
    commission_for,
    is_cold_start,
)
from src.domain.transactions.repository import TransactionRepository

router = Router(name="publisher_stats")
log = get_logger("publisher.stats")


async def _issue_window_stats(
    session: AsyncSession,
    publisher_id: int,
    cutoff_1d: datetime,
    cutoff_7d: datetime,
    cutoff_30d: datetime,
) -> dict:
    """Two queries: issued counts (by issued_at) and verified counts (by verified_at)."""

    issued_row = (await session.execute(
        select(
            func.coalesce(
                func.sum(case((ResourceIssue.issued_at >= cutoff_1d, 1))), 0
            ).label("d1"),
            func.coalesce(
                func.sum(case((ResourceIssue.issued_at >= cutoff_7d, 1))), 0
            ).label("d7"),
            func.coalesce(func.count(ResourceIssue.link_id), 0).label("d30"),
        ).where(
            and_(
                ResourceIssue.publisher_id == publisher_id,
                ResourceIssue.issued_at >= cutoff_30d,
            )
        )
    )).one()

    verified_row = (await session.execute(
        select(
            func.coalesce(
                func.sum(case((ResourceIssue.verified_at >= cutoff_1d, 1))), 0
            ).label("d1"),
            func.coalesce(
                func.sum(case((ResourceIssue.verified_at >= cutoff_7d, 1))), 0
            ).label("d7"),
            func.coalesce(func.count(ResourceIssue.link_id), 0).label("d30"),
        ).where(
            and_(
                ResourceIssue.publisher_id == publisher_id,
                ResourceIssue.verified_at >= cutoff_30d,
                ResourceIssue.status.in_([IssueStatus.VERIFIED, IssueStatus.PAID]),
            )
        )
    )).one()

    return {
        "issued_1d": int(issued_row.d1),
        "issued_7d": int(issued_row.d7),
        "issued_30d": int(issued_row.d30),
        "verified_1d": int(verified_row.d1),
        "verified_7d": int(verified_row.d7),
        "verified_30d": int(verified_row.d30),
    }


@router.callback_query(F.data == texts.CB_STATS)
async def show_publisher_stats(
    callback: CallbackQuery,
    publisher: Publisher | None,
    session: AsyncSession,
) -> None:
    if publisher is None:
        await callback.answer("Сначала пришлите /start", show_alert=True)
        return

    now = datetime.now(timezone.utc)
    cutoff_1d = now - timedelta(days=1)
    cutoff_7d = now - timedelta(days=7)
    cutoff_30d = now - timedelta(days=30)

    issues = await _issue_window_stats(
        session, publisher.id, cutoff_1d, cutoff_7d, cutoff_30d,
    )

    tx_repo = TransactionRepository(session)
    earned_1d, earned_7d, earned_30d = await tx_repo.sum_earned_for_publisher_windows(
        publisher.id,
        cutoff_1d=cutoff_1d,
        cutoff_7d=cutoff_7d,
        cutoff_30d=cutoff_30d,
    )

    hold_hours = compute_hold_hours(publisher)
    commission = commission_for(publisher.retention_rate, publisher.verified_subs_in_window)
    cold = is_cold_start(publisher.verified_subs_in_window)

    text = texts.publisher_stats_view(
        issued_1d=issues["issued_1d"],
        issued_7d=issues["issued_7d"],
        issued_30d=issues["issued_30d"],
        verified_1d=issues["verified_1d"],
        verified_7d=issues["verified_7d"],
        verified_30d=issues["verified_30d"],
        earned_1d=earned_1d,
        earned_7d=earned_7d,
        earned_30d=earned_30d,
        retention_rate=publisher.retention_rate,
        verified_subs_in_window=publisher.verified_subs_in_window,
        hold_hours=hold_hours,
        commission=commission,
        cold_start=cold,
    )

    try:
        await callback.message.edit_text(text, reply_markup=back_to_menu_kb())
    except TelegramBadRequest:
        pass
    await callback.answer()
