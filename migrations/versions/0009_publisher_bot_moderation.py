"""Publisher bot moderation fields — niche, audience labels, moderation status.

Revision ID: 0009
Revises: 0008
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, Sequence[str], None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Допустимые значения для niche
# Хранятся как строки — не enum, чтобы легко добавлять новые категории
# без новой миграции
NICHE_VALUES = (
    "crypto",        # Крипто / Web3
    "gaming",        # Игры
    "sport",         # Спорт
    "news",          # Новости
    "finance",       # Финансы / инвестиции
    "entertainment", # Развлечения / юмор
    "education",     # Образование
    "other",         # Другое
)

# Возрастная аудитория бота
AGE_AUDIENCE_VALUES = (
    "14_plus",  # Аудитория 14+
    "16_plus",  # Аудитория 16+
    "18_plus",  # Аудитория 18+
    "mixed",    # Смешанная
)

# Гендерная аудитория бота
GENDER_AUDIENCE_VALUES = (
    "male",    # Преимущественно мужская
    "female",  # Преимущественно женская
    "mixed",   # Смешанная
)


def upgrade() -> None:
    # Тематика бота (одна категория)
    op.add_column(
        "publisher_bots",
        sa.Column(
            "niche",
            sa.String(32),
            nullable=True,
            comment="Тематика бота: crypto|gaming|sport|news|finance|entertainment|education|other",
        ),
    )

    # Возрастная аудитория
    op.add_column(
        "publisher_bots",
        sa.Column(
            "age_audience",
            sa.String(16),
            nullable=True,
            comment="Возрастная аудитория: 14_plus|16_plus|18_plus|mixed",
        ),
    )

    # Гендерная аудитория
    op.add_column(
        "publisher_bots",
        sa.Column(
            "gender_audience",
            sa.String(16),
            nullable=True,
            comment="Гендерная аудитория: male|female|mixed",
        ),
    )

    # Страны аудитории (массив строк, хранится как JSONB)
    # Пример: ["RU", "UA", "BY"]
    op.add_column(
        "publisher_bots",
        sa.Column(
            "country_audience",
            sa.JSON(),
            nullable=True,
            server_default=None,
            comment="Страны аудитории: список кодов ['RU', 'UA', 'BY', ...]",
        ),
    )

    # Флаг — прошёл ли бот модерацию
    op.add_column(
        "publisher_bots",
        sa.Column(
            "is_moderated",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="True если модер одобрил бота и выставил ярлыки",
        ),
    )

    # Когда прошёл модерацию
    op.add_column(
        "publisher_bots",
        sa.Column(
            "moderated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Когда модер одобрил бота",
        ),
    )

    # Кто провёл модерацию (tg_user_id модера)
    op.add_column(
        "publisher_bots",
        sa.Column(
            "moderated_by_tg_id",
            sa.BigInteger(),
            nullable=True,
            comment="Telegram ID модератора который одобрил бота",
        ),
    )

    # Заметка модератора (опционально)
    op.add_column(
        "publisher_bots",
        sa.Column(
            "moderation_note",
            sa.Text(),
            nullable=True,
            comment="Заметка модератора при одобрении/отклонении",
        ),
    )

    # Индекс для быстрого поиска по тематике (matchmaking будет фильтровать)
    op.create_index(
        "ix_publisher_bots_niche",
        "publisher_bots",
        ["niche"],
    )

    # Индекс для поиска немодерированных ботов (очередь модерации)
    op.create_index(
        "ix_publisher_bots_moderated",
        "publisher_bots",
        ["is_moderated"],
    )


def downgrade() -> None:
    op.drop_index("ix_publisher_bots_moderated", table_name="publisher_bots")
    op.drop_index("ix_publisher_bots_niche", table_name="publisher_bots")
    op.drop_column("publisher_bots", "moderation_note")
    op.drop_column("publisher_bots", "moderated_by_tg_id")
    op.drop_column("publisher_bots", "moderated_at")
    op.drop_column("publisher_bots", "is_moderated")
    op.drop_column("publisher_bots", "country_audience")
    op.drop_column("publisher_bots", "gender_audience")
    op.drop_column("publisher_bots", "age_audience")
    op.drop_column("publisher_bots", "niche")
