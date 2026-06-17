"""Money utilities.

Все суммы в системе хранятся как Decimal с 4 знаками после запятой.
Никогда не используем float для денег.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

MONEY_PLACES = Decimal("0.0001")
DISPLAY_PLACES = Decimal("0.01")


def to_money(value: Decimal | int | float | str) -> Decimal:
    """Coerce to Decimal with 4 decimal places (banker's-safe rounding)."""
    if isinstance(value, float):
        # Никогда не передавайте float напрямую — это для совместимости
        value = str(value)
    return Decimal(value).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


def to_display(value: Decimal) -> Decimal:
    """Round to 2 decimal places for displaying to users."""
    return value.quantize(DISPLAY_PLACES, rounding=ROUND_HALF_UP)


def split_payout(
    reward_rub: Decimal,
    commission_percent: Decimal,
    retention_bonus_percent: Decimal = Decimal("0"),
) -> tuple[Decimal, Decimal, Decimal]:
    """Разделить вознаграждение на payout паблишеру, комиссию и бонус.

    Args:
        reward_rub: общая сумма, которую списываем с рекламодателя
        commission_percent: % комиссии платформы (например, 25)
        retention_bonus_percent: бонус паблишеру на retention (например, 5)

    Returns:
        (publisher_payout, platform_commission, retention_bonus)

    Сумма (publisher_payout + platform_commission) всегда == reward_rub.
    retention_bonus выплачивается ДОПОЛНИТЕЛЬНО за счёт платформы.
    """
    commission = to_money(reward_rub * commission_percent / Decimal("100"))
    publisher_base = to_money(reward_rub - commission)
    bonus = to_money(publisher_base * retention_bonus_percent / Decimal("100"))
    return publisher_base, commission, bonus
