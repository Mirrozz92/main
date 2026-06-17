"""Schemas for GET /api/v1/stats."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import get_args

from pydantic import BaseModel, Field

from src.api.v1.schemas.tasks import IssueStatusLiteral
from src.shared.money import to_money

# Canonical status list (kept in sync with IssueStatusLiteral) for zero-filling.
ALL_ISSUE_STATUSES: tuple[str, ...] = get_args(IssueStatusLiteral)

_EARNED_STATUSES = frozenset({"verified", "paid"})


class StatsResponse(BaseModel):
    """Aggregated counters for the authenticated publisher over a time window."""

    ok: bool = True
    period_from: datetime = Field(description="Start of the window (issued_at >= this)")
    period_to: datetime = Field(description="End of the window (issued_at <= this)")
    issued: int = Field(description="Total tasks issued in the window")
    by_status: dict[str, int] = Field(
        description="Count of issued tasks per lifecycle status (all statuses, incl. zeros)."
    )
    earned_rub: Decimal = Field(description="Payout earned (verified + paid) in the window.")
    bonus_rub: Decimal = Field(description="Retention bonus earned (verified + paid).")
    in_hold_rub: Decimal = Field(
        description="Payout currently in hold (subscribed, awaiting verification)."
    )


def build_stats(
    rows: list[tuple[str, int, Decimal, Decimal]],
    *,
    period_from: datetime,
    period_to: datetime,
) -> StatsResponse:
    """Assemble StatsResponse from per-status (status, count, payout_sum, bonus_sum) rows."""
    counts: dict[str, int] = {s: 0 for s in ALL_ISSUE_STATUSES}
    earned = Decimal("0")
    bonus = Decimal("0")
    in_hold = Decimal("0")

    for status_value, count, payout_sum, bonus_sum in rows:
        counts[status_value] = count
        if status_value in _EARNED_STATUSES:
            earned += payout_sum
            bonus += bonus_sum
        elif status_value == "subscribed":
            in_hold += payout_sum

    return StatsResponse(
        period_from=period_from,
        period_to=period_to,
        issued=sum(counts.values()),
        by_status=counts,
        earned_rub=to_money(earned),
        bonus_rub=to_money(bonus),
        in_hold_rub=to_money(in_hold),
    )
