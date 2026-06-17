"""Publisher reputation rating (0.0 .. 10.0).

The rating reflects traffic quality and is used to let advertisers filter
which publishers may show their sponsor (higher rating = better-quality
traffic, but fewer publishers => slower subscriber growth).

Formula (after cold-start threshold):

    rating = retention_score * W_RETENTION + volume_score * W_VOLUME

    retention_score = retention_rate / 10            # 100% -> 10.0
    volume_score    = min(verified_total / X, 1)*10  # saturates at X verified

Cold start:
    Until MIN_VERIFIED_FOR_RATING verified subscriptions, the publisher keeps
    the COLD_START_RATING (8.0). This gives newcomers a fair chance to be shown
    despite having no track record — important for marketplace liquidity.

Rounded to 1 decimal place.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

# Weights
W_RETENTION = Decimal("0.7")
W_VOLUME = Decimal("0.3")

# Volume saturation: this many verified subs (all-time) => full volume score
VOLUME_SATURATION = 500

# Cold start
MIN_VERIFIED_FOR_RATING = 100
COLD_START_RATING = Decimal("8.0")

MAX_RATING = Decimal("10.0")
MIN_RATING = Decimal("0.0")


def compute_rating(
    retention_rate: Decimal,
    verified_subs_total: int,
) -> Decimal:
    """Return rating 0.0..10.0 (1 dp).

    Args:
        retention_rate: percent 0..100 (verified / (verified+unsub))
        verified_subs_total: all-time verified subscriptions count
    """
    if verified_subs_total < MIN_VERIFIED_FOR_RATING:
        return COLD_START_RATING

    retention_score = (retention_rate / Decimal("10"))
    if retention_score > Decimal("10"):
        retention_score = Decimal("10")

    volume_ratio = Decimal(verified_subs_total) / Decimal(VOLUME_SATURATION)
    if volume_ratio > Decimal("1"):
        volume_ratio = Decimal("1")
    volume_score = volume_ratio * Decimal("10")

    rating = retention_score * W_RETENTION + volume_score * W_VOLUME
    rating = rating.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

    if rating > MAX_RATING:
        rating = MAX_RATING
    if rating < MIN_RATING:
        rating = MIN_RATING
    return rating


def is_rating_cold_start(verified_subs_total: int) -> bool:
    return verified_subs_total < MIN_VERIFIED_FOR_RATING


def describe_rating() -> str:
    """Human-readable description (Russian, no emoji)."""
    return (
        "Рейтинг (0.0–10.0) отражает качество вашего трафика и влияет на то, "
        "у скольких рекламодателей будет показываться ваш бот.\n\n"
        "Рейтинг складывается из:\n"
        "- Удержание (вес 70%) — процент подписок, оставшихся активными\n"
        "- Объём (вес 30%) — общее число подтверждённых подписок "
        f"(максимум при {VOLUME_SATURATION})\n\n"
        f"Пока у вас меньше {MIN_VERIFIED_FOR_RATING} подтверждённых подписок, "
        f"действует стартовый рейтинг {COLD_START_RATING}, чтобы дать "
        "возможность показать качество трафика.\n\n"
        "Чем выше рейтинг — тем более качественным считается ваш трафик."
    )
