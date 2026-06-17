"""SubGram features — таргетинг, тематики, коэффициенты, настройки паблишера.

Что добавляем:

1. campaigns
   - daily_limit        → лимит подписчиков в день
   - track_unsubs       → учитывать отписки да/нет
   - places             → свои/чужие/оба боты
   - is_free            → бесплатный показ в своих ботах
   - excluded_themes    → исключённые тематики (JSONB массив)
   - language_codes     → таргетинг по языкам
   - price_coefficient  → итоговый коэффициент цены

2. campaign_resources
   - base_reward_rub    → базовая цена до коэффициентов
   - coefficient        → итоговый коэффициент

3. publisher_bots
   - niche              → тематика бота (уже в 0009, здесь остальное)
   - get_links          → режим API: ссылки/SubGram сам шлёт
   - show_quiz          → показывать анкету да/нет
   - excluded_themes    → исключённые тематики
   - show_bots          → показывать рекламу ботов
   - show_resources     → показывать рекламу ресурсов

4. end_users
   - language_code      → язык Telegram юзера
   - first_name         → имя (для анализа)

5. exclusions           → новая таблица чёрных списков
   паблишер исключает спонсора / рекламодатель исключает бота

Revision ID: 0010
Revises: 0009
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, Sequence[str], None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:

    # -------------------------------------------------------------------------
    # 1. campaigns — новые поля
    # -------------------------------------------------------------------------

    # Дневной лимит подписчиков (NULL = без лимита)
    op.add_column(
        "campaigns",
        sa.Column(
            "daily_limit",
            sa.BigInteger(),
            nullable=True,
            comment="Макс. подписчиков в день. NULL = без лимита",
        ),
    )

    # Счётчик подписчиков за сегодня (сбрасывается воркером каждую ночь)
    op.add_column(
        "campaigns",
        sa.Column(
            "daily_count",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
            comment="Подписчиков сегодня. Сбрасывается каждую ночь",
        ),
    )

    # Учитывать отписки при расчёте
    op.add_column(
        "campaigns",
        sa.Column(
            "track_unsubs",
            sa.Boolean(),
            nullable=False,
            server_default="true",
            comment="Учитывать отписки да/нет",
        ),
    )

    # Места показов: 0=свои боты, 1=чужие боты, 2=оба
    op.add_column(
        "campaigns",
        sa.Column(
            "places",
            sa.SmallInteger(),
            nullable=False,
            server_default="2",
            comment="0=свои боты, 1=чужие, 2=оба",
        ),
    )

    # Бесплатный показ в своих ботах (без комиссии)
    op.add_column(
        "campaigns",
        sa.Column(
            "is_free",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="Бесплатный показ в своих ботах",
        ),
    )

    # Исключённые тематики ботов ["crypto", "18+", ...]
    op.add_column(
        "campaigns",
        sa.Column(
            "excluded_themes",
            sa.JSON(),
            nullable=False,
            server_default="[]",
            comment="Тематики ботов которые исключены из показа",
        ),
    )

    # Языки таргетинга ["ru", "uk", "be", "kz", "uz"]
    # NULL = все языки
    op.add_column(
        "campaigns",
        sa.Column(
            "language_codes",
            sa.JSON(),
            nullable=True,
            comment="Языки таргетинга. NULL = все языки",
        ),
    )

    # Итоговый коэффициент цены (вычисляется при создании/обновлении заказа)
    op.add_column(
        "campaigns",
        sa.Column(
            "price_coefficient",
            sa.Numeric(6, 4),
            nullable=False,
            server_default="1.0000",
            comment="Итоговый коэффициент цены от таргетинга",
        ),
    )

    # -------------------------------------------------------------------------
    # 2. campaign_resources — базовая цена и коэффициент
    # -------------------------------------------------------------------------

    # Базовая цена до применения коэффициентов
    op.add_column(
        "campaign_resources",
        sa.Column(
            "base_reward_rub",
            sa.Numeric(18, 4),
            nullable=True,
            comment="Базовая цена до коэффициентов. NULL = старые записи",
        ),
    )

    # Коэффициент этого конкретного ресурса
    op.add_column(
        "campaign_resources",
        sa.Column(
            "coefficient",
            sa.Numeric(6, 4),
            nullable=False,
            server_default="1.0000",
            comment="Итоговый коэффициент цены",
        ),
    )

    # -------------------------------------------------------------------------
    # 3. publisher_bots — настройки паблишера
    # -------------------------------------------------------------------------

    # Режим API: False = SubGram сам шлёт блок, True = отдаём ссылки
    op.add_column(
        "publisher_bots",
        sa.Column(
            "get_links",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="True = отдавать ссылки в API. False = сами шлём блок ОП",
        ),
    )

    # Показывать анкету юзерам
    op.add_column(
        "publisher_bots",
        sa.Column(
            "show_quiz",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="Показывать анкету юзерам для точного таргетинга",
        ),
    )

    # Исключённые тематики в этом боте
    op.add_column(
        "publisher_bots",
        sa.Column(
            "excluded_themes",
            sa.JSON(),
            nullable=False,
            server_default="[]",
            comment="Тематики рекламы которые не показываем в этом боте",
        ),
    )

    # Показывать рекламу ботов
    op.add_column(
        "publisher_bots",
        sa.Column(
            "show_bots",
            sa.Boolean(),
            nullable=False,
            server_default="true",
            comment="Показывать рекламу ботов",
        ),
    )

    # Показывать рекламу ресурсов (каналы/группы)
    op.add_column(
        "publisher_bots",
        sa.Column(
            "show_resources",
            sa.Boolean(),
            nullable=False,
            server_default="true",
            comment="Показывать рекламу каналов и групп",
        ),
    )

    # Кастомный текст блока ОП
    op.add_column(
        "publisher_bots",
        sa.Column(
            "custom_op_text",
            sa.Text(),
            nullable=True,
            comment="Кастомный текст блока обязательной подписки",
        ),
    )

    # URL кастомной картинки блока ОП
    op.add_column(
        "publisher_bots",
        sa.Column(
            "custom_op_image_url",
            sa.String(512),
            nullable=True,
            comment="URL картинки для блока ОП",
        ),
    )

    # -------------------------------------------------------------------------
    # 4. end_users — добавляем language_code и first_name
    # -------------------------------------------------------------------------

    # Язык Telegram юзера (передаётся паблишером в /request-op)
    op.add_column(
        "end_users",
        sa.Column(
            "language_code",
            sa.String(8),
            nullable=True,
            comment="Код языка Telegram: ru, en, uk, be, kz...",
        ),
    )

    # Имя юзера (для анализа, не для показа)
    op.add_column(
        "end_users",
        sa.Column(
            "first_name",
            sa.String(128),
            nullable=True,
            comment="Имя юзера в Telegram",
        ),
    )

    # Индекс по языку для быстрой фильтрации в matchmaking
    op.create_index(
        "ix_end_users_language_code",
        "end_users",
        ["language_code"],
    )

    # -------------------------------------------------------------------------
    # 5. exclusions — новая таблица чёрных списков
    # -------------------------------------------------------------------------
    op.create_table(
        "exclusions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),

        # Контекст: advertiser (рекл исключает бота) / publisher (паблишер исключает спонсора)
        sa.Column(
            "context",
            sa.String(16),
            nullable=False,
            comment="advertiser или publisher",
        ),

        # Рекламодатель исключает бота из своего заказа
        sa.Column(
            "campaign_id",
            sa.BigInteger(),
            sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
            nullable=True,
            comment="ID заказа рекламодателя (для context=advertiser)",
        ),
        sa.Column(
            "excluded_bot_id",
            sa.BigInteger(),
            sa.ForeignKey("publisher_bots.id", ondelete="CASCADE"),
            nullable=True,
            comment="ID бота паблишера который исключён из заказа",
        ),

        # Паблишер исключает спонсора из своего бота
        sa.Column(
            "publisher_bot_id",
            sa.BigInteger(),
            sa.ForeignKey("publisher_bots.id", ondelete="CASCADE"),
            nullable=True,
            comment="ID бота паблишера (NULL = глобально для всех ботов)",
        ),
        sa.Column(
            "excluded_campaign_id",
            sa.BigInteger(),
            sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
            nullable=True,
            comment="ID исключённого заказа спонсора",
        ),

        # Кто создал исключение
        sa.Column(
            "created_by_tg_id",
            sa.BigInteger(),
            nullable=False,
            comment="TG ID юзера который создал исключение",
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    # Индексы для быстрого поиска исключений в matchmaking
    op.create_index(
        "ix_exclusions_campaign_bot",
        "exclusions",
        ["campaign_id", "excluded_bot_id"],
    )
    op.create_index(
        "ix_exclusions_publisher_campaign",
        "exclusions",
        ["publisher_bot_id", "excluded_campaign_id"],
    )


def downgrade() -> None:
    # exclusions
    op.drop_index("ix_exclusions_publisher_campaign", table_name="exclusions")
    op.drop_index("ix_exclusions_campaign_bot", table_name="exclusions")
    op.drop_table("exclusions")

    # end_users
    op.drop_index("ix_end_users_language_code", table_name="end_users")
    op.drop_column("end_users", "first_name")
    op.drop_column("end_users", "language_code")

    # publisher_bots
    op.drop_column("publisher_bots", "custom_op_image_url")
    op.drop_column("publisher_bots", "custom_op_text")
    op.drop_column("publisher_bots", "show_resources")
    op.drop_column("publisher_bots", "show_bots")
    op.drop_column("publisher_bots", "excluded_themes")
    op.drop_column("publisher_bots", "show_quiz")
    op.drop_column("publisher_bots", "get_links")

    # campaign_resources
    op.drop_column("campaign_resources", "coefficient")
    op.drop_column("campaign_resources", "base_reward_rub")

    # campaigns
    op.drop_column("campaigns", "price_coefficient")
    op.drop_column("campaigns", "language_codes")
    op.drop_column("campaigns", "excluded_themes")
    op.drop_column("campaigns", "is_free")
    op.drop_column("campaigns", "places")
    op.drop_column("campaigns", "track_unsubs")
    op.drop_column("campaigns", "daily_count")
    op.drop_column("campaigns", "daily_limit")
