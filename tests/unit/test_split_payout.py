"""Tests for split_payout — the core commission split (src/shared/money.py)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.shared.money import split_payout, to_money

D = Decimal


class TestSplitPayout:
    def test_basic_split(self) -> None:
        payout, commission, bonus = split_payout(D("2.00"), D("25"))
        assert commission == D("0.5000")
        assert payout == D("1.5000")
        assert bonus == D("0.0000")

    def test_conservation_invariant(self) -> None:
        # The defining property: publisher payout + platform commission == reward.
        for reward in ("1.00", "2.00", "1.01", "3.33", "9.99", "0.05"):
            for pct in ("20", "22.5", "25", "30", "35"):
                payout, commission, _ = split_payout(D(reward), D(pct))
                assert payout + commission == to_money(D(reward)), (reward, pct)

    def test_bonus_is_extra_on_top_of_base(self) -> None:
        # Bonus is computed from publisher base and paid by the platform —
        # it does NOT come out of reward, so payout+commission still == reward.
        payout, commission, bonus = split_payout(D("2.00"), D("25"), D("5"))
        assert payout == D("1.5000")
        assert commission == D("0.5000")
        assert bonus == D("0.0750")  # 5% of 1.50
        assert payout + commission == D("2.0000")

    def test_rounding_half_up(self) -> None:
        # 1.01 * 25% = 0.2525 → payout 0.7575; sum still exact.
        payout, commission, _ = split_payout(D("1.01"), D("25"))
        assert commission == D("0.2525")
        assert payout == D("0.7575")
        assert payout + commission == D("1.0100")

    @pytest.mark.parametrize("pct", ["0", "100"])
    def test_extreme_percentages(self, pct: str) -> None:
        payout, commission, _ = split_payout(D("2.00"), D(pct))
        assert payout + commission == D("2.0000")
