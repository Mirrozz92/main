"""Tests for the build_stats aggregation helper (pure, no DB)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from src.api.v1.schemas import build_stats
from src.api.v1.schemas.stats import ALL_ISSUE_STATUSES

_FROM = datetime(2026, 1, 1, tzinfo=UTC)
_TO = datetime(2026, 2, 1, tzinfo=UTC)


class TestBuildStats:
    def test_empty(self) -> None:
        s = build_stats([], period_from=_FROM, period_to=_TO)
        assert s.issued == 0
        assert s.earned_rub == Decimal("0.0000")
        assert s.in_hold_rub == Decimal("0.0000")
        assert s.bonus_rub == Decimal("0.0000")
        # all statuses present and zero
        assert set(s.by_status) == set(ALL_ISSUE_STATUSES)
        assert all(v == 0 for v in s.by_status.values())

    def test_aggregates(self) -> None:
        rows = [
            ("verified", 3, Decimal("4.5"), Decimal("0.5")),
            ("subscribed", 2, Decimal("3.0"), Decimal("0")),
            ("paid", 1, Decimal("1.5"), Decimal("0")),
            ("expired", 4, Decimal("0"), Decimal("0")),
        ]
        s = build_stats(rows, period_from=_FROM, period_to=_TO)
        assert s.issued == 10
        assert s.by_status["verified"] == 3
        assert s.by_status["subscribed"] == 2
        assert s.by_status["expired"] == 4
        assert s.by_status["pending"] == 0
        # earned = verified + paid payouts
        assert s.earned_rub == Decimal("6.0000")
        # bonus only from verified/paid
        assert s.bonus_rub == Decimal("0.5000")
        # in_hold = subscribed payout
        assert s.in_hold_rub == Decimal("3.0000")

    def test_period_echoed(self) -> None:
        s = build_stats([], period_from=_FROM, period_to=_TO)
        assert s.period_from == _FROM
        assert s.period_to == _TO
