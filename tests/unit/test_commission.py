"""Tests for the platform commission scale (src/domain/publishers/commission.py)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.domain.publishers.commission import (
    BASE_COMMISSION,
    MIN_VERIFIED_FOR_SCALE,
    commission_for,
    is_cold_start,
)

D = Decimal


class TestColdStart:
    def test_below_threshold_uses_base_rate(self) -> None:
        # Even with great retention, too few verified subs → base 25%.
        assert commission_for(D("90"), MIN_VERIFIED_FOR_SCALE - 1) == BASE_COMMISSION

    def test_is_cold_start_boundary(self) -> None:
        assert is_cold_start(MIN_VERIFIED_FOR_SCALE - 1) is True
        assert is_cold_start(MIN_VERIFIED_FOR_SCALE) is False


class TestScale:
    @pytest.mark.parametrize(
        ("retention", "expected"),
        [
            (D("100"), D("0.200")),
            (D("85"), D("0.200")),   # inclusive lower edge of top tier
            (D("84.99"), D("0.225")),
            (D("70"), D("0.225")),
            (D("69.99"), D("0.250")),
            (D("50"), D("0.250")),
            (D("49.99"), D("0.300")),
            (D("20"), D("0.300")),
            (D("19.99"), D("0.350")),
            (D("0"), D("0.350")),
        ],
    )
    def test_tiers(self, retention: Decimal, expected: Decimal) -> None:
        # Past cold start, the retention scale applies.
        assert commission_for(retention, MIN_VERIFIED_FOR_SCALE) == expected
