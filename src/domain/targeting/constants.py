"""Allowed values for targeting filters + age ladder."""

from __future__ import annotations

# Возрастная лестница: чем выше индекс — тем старше.
# Используется чтобы сравнивать "юзер удовлетворяет min_X+".
AGE_LADDER = {
    "under_14": 0,
    "14_16": 1,
    "16_18": 2,
    "18_plus": 3,
}
AGE_LADDER_ORDER = ["under_14", "14_16", "16_18", "18_plus"]

# Допустимые значения targeting.min_age
MIN_AGE_VALUES = {
    "any":         -1,  # showcase to anyone (no age filter)
    "min_14_plus":  1,  # require >= 14_16
    "min_16_plus":  2,  # require >= 16_18
    "min_18_plus":  3,  # require == 18_plus
}

# Допустимые значения targeting.genders (пустой список = «любой»)
GENDER_VALUES = {"male", "female", "undisclosed"}

# Допустимые значения targeting.countries (пустой список = «любая»)
COUNTRY_VALUES = {"RU", "UA", "BY", "KZ", "OTHER"}

# Audience requirement flags (positive-only). Each maps to an EndUser field.
# require_X=True => show only if EndUser.has_X is True (NULL/False => skip).
AUDIENCE_REQUIREMENTS = {
    "require_premium":  "has_telegram_premium",
    "require_photo":    "has_profile_photo",
    "require_username": "has_username",
    "require_bio":      "has_bio",
    "require_stories":  "has_stories",
}

# Default — кампания без targeting показывается всем
DEFAULT_TARGETING: dict = {
    "min_age": "any",
    "genders": [],
    "countries": [],
    "require_premium": False,
    "require_photo": False,
    "require_username": False,
    "require_bio": False,
    "require_stories": False,
    "min_publisher_rating": 0,
}
