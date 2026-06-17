"""Platform commission scale based on publisher retention rate.

Commission scale (retention = % of successful/verified subscriptions):

    retention >= 85%       -> 20.0%
    70% <= retention < 85% -> 22.5%
    50% <= retention < 70% -> 25.0%
    20% <= retention < 50% -> 30.0%
    retention < 20%        -> 35.0%

Cold start protection:
    Until the publisher has accumulated at least MIN_VERIFIED_FOR_SCALE
    verified subscriptions, we apply the BASE rate (25%) regardless of the
    computed retention. This avoids punishing/rewarding new publishers based
    on a tiny, noisy sample.

Boundaries are inclusive toward the BETTER (lower) commission tier.
"""

from __future__ import annotations

from decimal import Decimal

# Minimum verified subscriptions before the retention scale applies.
MIN_VERIFIED_FOR_SCALE = 100

# Base / cold-start commission
BASE_COMMISSION = Decimal("0.25")  # 25%

# (retention_threshold_percent, commission_rate) — checked high → low
COMMISSION_SCALE: list[tuple[Decimal, Decimal]] = [
    (Decimal("85"), Decimal("0.200")),   # >= 85%  -> 20%
    (Decimal("70"), Decimal("0.225")),   # >= 70%  -> 22.5%
    (Decimal("50"), Decimal("0.250")),   # >= 50%  -> 25%
    (Decimal("20"), Decimal("0.300")),   # >= 20%  -> 30%
    (Decimal("0"),  Decimal("0.350")),   # < 20%   -> 35%
]


def commission_for(
    retention_rate: Decimal,
    verified_subs_in_window: int,
) -> Decimal:
    """Return platform commission rate (e.g. Decimal('0.225')) for a publisher.

    Args:
        retention_rate: percent 0..100
        verified_subs_in_window: count of verified subs in the 30-day window

    Cold start: below MIN_VERIFIED_FOR_SCALE verified subs -> BASE_COMMISSION.
    """
    if verified_subs_in_window < MIN_VERIFIED_FOR_SCALE:
        return BASE_COMMISSION

    for threshold, rate in COMMISSION_SCALE:
        if retention_rate >= threshold:
            return rate

    return BASE_COMMISSION  # unreachable, last tier has threshold 0


def is_cold_start(verified_subs_in_window: int) -> bool:
    """True if the publisher hasn't accumulated enough data for the scale."""
    return verified_subs_in_window < MIN_VERIFIED_FOR_SCALE


def describe_scale() -> str:
    """Human-readable description of the commission scale (Russian, no emoji)."""
    return (
        "Комиссия платформы зависит от вашего удержания — процента подписок, "
        "которые остались активными (не отписались до подтверждения).\n\n"
        "Шкала комиссии:\n"
        "- Удержание 85% и выше — комиссия 20%\n"
        "- Удержание 70–85% — комиссия 22.5%\n"
        "- Удержание 50–70% — комиссия 25%\n"
        "- Удержание 20–50% — комиссия 30%\n"
        "- Удержание ниже 20% — комиссия 35%\n\n"
        f"Шкала начинает действовать после {MIN_VERIFIED_FOR_SCALE} подтверждённых "
        "подписок. До этого действует базовая комиссия 25%.\n\n"
        "Чем выше удержание — тем больше ваш доход с каждой подписки. "
        "Приводите заинтересованную аудиторию, которая не отписывается сразу."
    )
