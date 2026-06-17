"""Tests for dynamic hold computation (src/domain/issues/state_machine.py)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from src.core.db.models import Publisher
from src.domain.issues.state_machine import (
    COLD_START_HOLD_HOURS,
    COLD_START_MIN_VERIFIED,
    compute_hold_hours,
    compute_hold_until,
)

D = Decimal


class TestColdStart:
    def test_below_min_verified_uses_cold_start_hours(
        self, make_publisher: Callable[..., Publisher]
    ) -> None:
        # Great retention but not enough verified subs → cold-start hold.
        pub = make_publisher(
            verified_subs_in_window=COLD_START_MIN_VERIFIED - 1,
            retention_rate=D("95"),
        )
        assert compute_hold_hours(pub) == COLD_START_HOLD_HOURS


class TestRetentionTiers:
    @pytest.mark.parametrize(
        ("retention", "expected_hours"),
        [
            (D("85"), 4),
            (D("80"), 4),
            (D("79.99"), 6),
            (D("50"), 6),
            (D("49.99"), 8),
            (D("40"), 8),
            (D("39.99"), 12),
            (D("0"), 12),
        ],
    )
    def test_tiers(
        self,
        make_publisher: Callable[..., Publisher],
        retention: Decimal,
        expected_hours: int,
    ) -> None:
        pub = make_publisher(
            verified_subs_in_window=COLD_START_MIN_VERIFIED,
            retention_rate=retention,
        )
        assert compute_hold_hours(pub) == expected_hours


def test_compute_hold_until_adds_hours(
    make_publisher: Callable[..., Publisher],
) -> None:
    pub = make_publisher(
        verified_subs_in_window=COLD_START_MIN_VERIFIED, retention_rate=D("90")
    )
    at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    until = compute_hold_until(pub, subscribed_at=at)
    assert (until - at).total_seconds() == 4 * 3600
