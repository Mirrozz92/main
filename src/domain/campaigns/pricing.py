"""Коэффициенты цены за таргетинг.

Чем точнее таргетинг → тем дороже подписчик.
Коэффициенты перемножаются.

Пример:
  Базовая цена: 1.0 ₽
  Язык RU:      x1.2
  Страна RU:    x1.5
  Возраст 18+:  x2.0
  Итого:        1.0 × 1.2 × 1.5 × 2.0 = 3.6 ₽
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any


# Коэффициенты по языку
# Конкретный язык дороже чем "все языки"
LANGUAGE_COEFFICIENT = Decimal("1.2")

# Коэффициенты по стране
COUNTRY_COEFFICIENT = Decimal("1.5")

# Коэффициенты по возрасту
AGE_COEFFICIENTS: dict[str, Decimal] = {
    "under_14": Decimal("1.2"),
    "14_16":    Decimal("1.2"),
    "16_18":    Decimal("1.5"),
    "18_plus":  Decimal("2.0"),
}

# Коэффициенты по полу (небольшой за конкретный пол)
GENDER_COEFFICIENT = Decimal("1.1")

# Коэффициенты по аудитории профиля
AUDIENCE_COEFFICIENTS: dict[str, Decimal] = {
    "has_telegram_premium": Decimal("1.3"),
    "has_profile_photo":    Decimal("1.1"),
    "has_username":         Decimal("1.1"),
    "has_bio":              Decimal("1.1"),
}

# Минимальный и максимальный коэффициент
MIN_COEFFICIENT = Decimal("1.0")
MAX_COEFFICIENT = Decimal("5.0")


def compute_coefficient(targeting: dict[str, Any]) -> Decimal:
    """Вычислить итоговый коэффициент цены из параметров таргетинга.

    Args:
        targeting: словарь из campaign.targeting (JSONB)

    Returns:
        Decimal коэффициент, минимум 1.0
    """
    coefficient = Decimal("1.0")

    # Язык — если выбраны конкретные языки (не все)
    languages = targeting.get("languages")
    if languages:
        coefficient *= LANGUAGE_COEFFICIENT

    # Страна — если выбраны конкретные страны
    countries = targeting.get("countries")
    if countries:
        coefficient *= COUNTRY_COEFFICIENT

    # Возраст — берём максимальный коэффициент из выбранных категорий
    ages = targeting.get("ages")
    if ages:
        age_coefs = [AGE_COEFFICIENTS.get(age, Decimal("1.0")) for age in ages]
        coefficient *= max(age_coefs)

    # Пол — если выбран конкретный
    gender = targeting.get("gender")
    if gender and gender != "all":
        coefficient *= GENDER_COEFFICIENT

    # Аудитория профиля
    for field, coef in AUDIENCE_COEFFICIENTS.items():
        if targeting.get(field):
            coefficient *= coef

    # Ограничиваем максимумом
    coefficient = min(coefficient, MAX_COEFFICIENT)

    return coefficient.quantize(Decimal("0.0001"))


def apply_coefficient(base_price: Decimal, coefficient: Decimal) -> Decimal:
    """Применить коэффициент к базовой цене."""
    return (base_price * coefficient).quantize(Decimal("0.0001"))


def describe_coefficient(targeting: dict[str, Any]) -> str:
    """Человекочитаемое описание коэффициентов (для бота)."""
    lines = []
    coefficient = Decimal("1.0")

    languages = targeting.get("languages")
    if languages:
        c = LANGUAGE_COEFFICIENT
        lines.append(f"Язык: ×{c}")
        coefficient *= c

    countries = targeting.get("countries")
    if countries:
        c = COUNTRY_COEFFICIENT
        lines.append(f"Страна: ×{c}")
        coefficient *= c

    ages = targeting.get("ages")
    if ages:
        age_coefs = [AGE_COEFFICIENTS.get(age, Decimal("1.0")) for age in ages]
        c = max(age_coefs)
        lines.append(f"Возраст: ×{c}")
        coefficient *= c

    gender = targeting.get("gender")
    if gender and gender != "all":
        c = GENDER_COEFFICIENT
        lines.append(f"Пол: ×{c}")
        coefficient *= c

    for field, coef in AUDIENCE_COEFFICIENTS.items():
        if targeting.get(field):
            label = {
                "has_telegram_premium": "Premium",
                "has_profile_photo":    "Фото",
                "has_username":         "Ник",
                "has_bio":              "Био",
            }.get(field, field)
            lines.append(f"{label}: ×{coef}")
            coefficient *= coef

    if not lines:
        return "Без таргетинга — базовая цена"

    coefficient = min(coefficient, MAX_COEFFICIENT)
    result = "\n".join(lines)
    result += f"\n\nИтоговый коэффициент: ×{coefficient:.2f}"
    return result


# Список тематик ботов (как у SubGram)
BOT_NICHES = [
    "скачивалки",
    "музыка",
    "приложения",
    "нейросети",
    "общение",
    "старсы_нфт",
    "инструменты",
    "стикеры_темы",
    "развлечения",
    "18плюс",
    "кино",
    "полезное",
    "заработок",
    "другое",
]
