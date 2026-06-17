"""Tests for src/shared/money.py."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.shared.money import split_payout, to_display, to_money


class TestToMoney:
    def test_int(self) -> None:
        assert to_money(100) == Decimal("100.0000")

    def test_str(self) -> None:
        assert to_money("1.5") == Decimal("1.5000")

    def test_decimal(self) -> None:
        assert to_money(Decimal("3.14159")) == Decimal("3.1416")

    def test_rounds_half_up(self) -> None:
        # 0.12345 → 0.1235 (half-up)
        assert to_money(Decimal("0.12345")) == Decimal("0.1235")

    def test_float_via_str(self) -> None:
        # Принимаем float только через str (избегаем binary repr issues)
        assert to_money(0.1) == Decimal("0.1000")


class TestToDisplay:
    def test_basic(self) -> None:
        assert to_display(Decimal("1.2345")) == Decimal("1.23")

    def test_half_up(self) -> None:
        assert to_display(Decimal("1.235")) == Decimal("1.24")


class TestSplitPayout:
    def test_25_percent_no_bonus(self) -> None:
        payout, commission, bonus = split_payout(
            reward_rub=Decimal("100"),
            commission_percent=Decimal("25"),
        )
        assert commission == Decimal("25.0000")
        assert payout == Decimal("75.0000")
        assert bonus == Decimal("0.0000")
        # Инвариант: payout + commission == reward
        assert payout + commission == Decimal("100.0000")

    def test_vip_20_percent(self) -> None:
        payout, commission, bonus = split_payout(
            reward_rub=Decimal("100"),
            commission_percent=Decimal("20"),
        )
        assert commission == Decimal("20.0000")
        assert payout == Decimal("80.0000")

    def test_with_retention_bonus(self) -> None:
        # 100 ₽, комиссия 25%, бонус 5% от payout
        # payout = 75, commission = 25, bonus = 75 * 0.05 = 3.75
        payout, commission, bonus = split_payout(
            reward_rub=Decimal("100"),
            commission_percent=Decimal("25"),
            retention_bonus_percent=Decimal("5"),
        )
        assert payout == Decimal("75.0000")
        assert commission == Decimal("25.0000")
        assert bonus == Decimal("3.7500")

    @pytest.mark.parametrize("amount", ["1", "10", "150.50", "999.99"])
    def test_invariant_payout_plus_commission_equals_reward(self, amount: str) -> None:
        reward = Decimal(amount)
        payout, commission, _bonus = split_payout(
            reward_rub=reward,
            commission_percent=Decimal("25"),
        )
        assert payout + commission == to_money(reward)
