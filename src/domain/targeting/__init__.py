"""Targeting layer — campaign demographic filters and EndUser matching."""

from src.domain.targeting.constants import (
    AGE_LADDER,
    AGE_LADDER_ORDER,
    COUNTRY_VALUES,
    DEFAULT_TARGETING,
    GENDER_VALUES,
    MIN_AGE_VALUES,
)
from src.domain.targeting.matcher import (
    end_user_matches_campaign,
    parse_targeting,
)

__all__ = [
    "AGE_LADDER",
    "AGE_LADDER_ORDER",
    "COUNTRY_VALUES",
    "DEFAULT_TARGETING",
    "GENDER_VALUES",
    "MIN_AGE_VALUES",
    "end_user_matches_campaign",
    "parse_targeting",
]
