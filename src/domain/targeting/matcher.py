"""Matching EndUser against a Campaign.targeting JSON.

Targeting structure (JSONB column on campaigns):

    {
        "min_age": "any" | "min_14_plus" | "min_16_plus" | "min_18_plus",
        "genders": ["male", "female", "undisclosed"],    # empty = any
        "countries": ["RU", "UA", ...],                  # empty = any
    }

Empty/missing targeting → default DEFAULT_TARGETING → matches everyone.

Strict semantics (decision #3):
    If user's field is NULL and campaign has an active filter for it → NO match.
    User must have filled out the demography to receive targeted ads.
"""

from __future__ import annotations

from typing import Any

from src.core.db.models import EndUser
from src.domain.targeting.constants import (
    AGE_LADDER,
    AUDIENCE_REQUIREMENTS,
    COUNTRY_VALUES,
    DEFAULT_TARGETING,
    GENDER_VALUES,
    MIN_AGE_VALUES,
)


def parse_targeting(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Validate & normalize targeting dict from DB. Unknown values are dropped."""
    if not raw:
        return dict(DEFAULT_TARGETING)

    min_age = raw.get("min_age", "any")
    if min_age not in MIN_AGE_VALUES:
        min_age = "any"

    genders_raw = raw.get("genders", []) or []
    if not isinstance(genders_raw, list):
        genders_raw = []
    genders = [g for g in genders_raw if isinstance(g, str) and g in GENDER_VALUES]

    countries_raw = raw.get("countries", []) or []
    if not isinstance(countries_raw, list):
        countries_raw = []
    countries = [c for c in countries_raw if isinstance(c, str) and c in COUNTRY_VALUES]

    audience = {}
    for key in AUDIENCE_REQUIREMENTS:
        audience[key] = bool(raw.get(key, False))

    rating_raw = raw.get("min_publisher_rating", 0)
    try:
        from decimal import Decimal
        min_rating = Decimal(str(rating_raw))
        if min_rating < 0:
            min_rating = Decimal("0")
        if min_rating > 10:
            min_rating = Decimal("10")
    except Exception:
        min_rating = Decimal("0")

    return {
        "min_age": min_age,
        "genders": genders,
        "countries": countries,
        "min_publisher_rating": min_rating,
        **audience,
    }


def end_user_matches_campaign(
    end_user: EndUser | None,
    targeting_raw: dict[str, Any] | None,
) -> bool:
    """Return True if `end_user` satisfies the campaign's targeting filters.

    Decision #3 — strict:
        Empty user field + non-empty campaign filter → False.

    No filter (default) → always True.
    """
    targeting = parse_targeting(targeting_raw)

    has_age_filter = targeting["min_age"] != "any"
    has_gender_filter = bool(targeting["genders"])
    has_country_filter = bool(targeting["countries"])
    has_audience_filter = any(
        targeting.get(k) for k in AUDIENCE_REQUIREMENTS
    )

    # Fast path: no demographic/audience filters → match everyone.
    # (Publisher-rating filter is checked separately, before matchmaking.)
    if not (has_age_filter or has_gender_filter or has_country_filter
            or has_audience_filter):
        return True

    if end_user is None:
        # Campaign has filters but no EndUser to test against
        return False

    # Age filter
    if has_age_filter:
        if end_user.age_range is None:
            return False
        required_level = MIN_AGE_VALUES[targeting["min_age"]]
        user_level = AGE_LADDER.get(end_user.age_range, -1)
        if user_level < required_level:
            return False

    # Gender filter
    if has_gender_filter:
        if end_user.gender is None:
            return False
        if end_user.gender not in targeting["genders"]:
            return False

    # Country filter
    if has_country_filter:
        if end_user.country_code is None:
            return False
        if end_user.country_code not in targeting["countries"]:
            return False

    # Audience requirement filters (positive-only, strict).
    # require_X=True => EndUser.has_X must be True. NULL/False => no match.
    for req_key, user_field in AUDIENCE_REQUIREMENTS.items():
        if targeting.get(req_key):
            user_value = getattr(end_user, user_field, None)
            if user_value is not True:
                return False

    return True
