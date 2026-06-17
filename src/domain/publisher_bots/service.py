"""Service layer for PublisherBot.

Encapsulates business rules:
- Settings validation (sponsors_count range, ttl range)
- Telegram bot identity resolution via getMe
- Bot token encryption
- Active toggle
"""

from __future__ import annotations

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.crypto import CryptoError, encrypt
from src.core.db.models import PublisherBot
from src.core.logging import get_logger
from src.domain.exceptions import DomainError
from src.domain.publisher_bots.repository import PublisherBotRepository

log = get_logger("publisher_bots")


VALID_THEMES: frozenset[str] = frozenset([
    "crypto", "gaming", "sport", "news", "finance", "entertainment", "education", "other",
])

MIN_SPONSORS = 1
MAX_SPONSORS = 10
MIN_TTL = 300        # 5 minutes
MAX_TTL = 7 * 86400  # 7 days


class PublisherBotService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = PublisherBotRepository(session)

    @staticmethod
    def validate_name(name: str) -> str:
        clean = (name or "").strip()
        if not (2 <= len(clean) <= 128):
            raise DomainError("Название бота должно быть от 2 до 128 символов.")
        return clean

    @staticmethod
    def validate_sponsors_count(n: int) -> int:
        if not (MIN_SPONSORS <= n <= MAX_SPONSORS):
            raise DomainError(
                f"Количество спонсоров должно быть от {MIN_SPONSORS} до {MAX_SPONSORS}."
            )
        return n

    @staticmethod
    def validate_ttl(seconds: int) -> int:
        if not (MIN_TTL <= seconds <= MAX_TTL):
            raise DomainError(
                f"Время сброса должно быть от 5 минут до 7 дней "
                f"(в секундах: {MIN_TTL}–{MAX_TTL})."
            )
        return seconds

    async def add_bot(
        self,
        *,
        publisher_id: int,
        name: str | None = None,
        tg_bot_token: str | None = None,
    ) -> PublisherBot:
        """Add a new PublisherBot.

        If tg_bot_token is provided — we call getMe to fetch identity, encrypt
        the token, and store it. Otherwise, we just create a bot with the given name.
        """
        if tg_bot_token:
            # Resolve identity via Bot API
            tmp_bot = Bot(
                token=tg_bot_token.strip(),
                default=DefaultBotProperties(parse_mode=ParseMode.HTML),
            )
            try:
                me = await tmp_bot.get_me()
            except Exception as e:
                log.warning("publisher_bot_token_invalid", error=str(e))
                raise DomainError(
                    "Не удалось проверить токен. Убедитесь, что он валиден "
                    "(вы получаете его в @BotFather)."
                ) from e
            finally:
                await tmp_bot.session.close()

            # Check for duplicates (same TG bot added twice)
            existing = await self.repo.get_by_tg_bot_id(me.id)
            if existing is not None:
                if existing.publisher_id == publisher_id:
                    raise DomainError(f"Бот @{me.username} уже добавлен в ваш аккаунт.")
                raise DomainError(
                    f"Бот @{me.username} уже подключён другим партнёром. "
                    "Свяжитесь с поддержкой если это ошибка."
                )

            try:
                encrypted = encrypt(tg_bot_token.strip())
            except CryptoError as e:
                log.error("encryption_failed", error=str(e))
                raise DomainError("Внутренняя ошибка шифрования. Свяжитесь с админом.") from e

            display_name = name or me.first_name or f"@{me.username}"
            bot = await self.repo.create(
                publisher_id=publisher_id,
                name=self.validate_name(display_name),
                tg_bot_id=me.id,
                tg_bot_username=me.username,
                tg_bot_token_encrypted=encrypted,
            )
            log.info(
                "publisher_bot_added_with_token",
                publisher_id=publisher_id,
                bot_id=bot.id,
                tg_bot_id=me.id,
            )
            return bot

        # No token — just name
        if not name:
            raise DomainError("Если нет токена, нужно указать название бота.")
        bot = await self.repo.create(
            publisher_id=publisher_id, name=self.validate_name(name),
        )
        log.info("publisher_bot_added_no_token", publisher_id=publisher_id, bot_id=bot.id)
        return bot

    async def update_settings(
        self,
        bot: PublisherBot,
        *,
        sponsors_count: int | None = None,
        list_ttl_seconds: int | None = None,
    ) -> None:
        if sponsors_count is not None:
            bot.sponsors_count = self.validate_sponsors_count(sponsors_count)
        if list_ttl_seconds is not None:
            bot.list_ttl_seconds = self.validate_ttl(list_ttl_seconds)
        log.info(
            "publisher_bot_settings_updated",
            bot_id=bot.id,
            sponsors_count=bot.sponsors_count,
            list_ttl_seconds=bot.list_ttl_seconds,
        )

    async def update_extra_settings(
        self,
        bot: PublisherBot,
        *,
        show_quiz: bool | None = None,
        get_links: bool | None = None,
        excluded_themes: list[str] | None = None,
    ) -> None:
        if show_quiz is not None:
            bot.show_quiz = show_quiz
        if get_links is not None:
            bot.get_links = get_links
        if excluded_themes is not None:
            invalid = set(excluded_themes) - VALID_THEMES
            if invalid:
                raise DomainError(f"Неизвестные тематики: {', '.join(sorted(invalid))}")
            bot.excluded_themes = list(excluded_themes)
        log.info(
            "publisher_bot_extra_settings_updated",
            bot_id=bot.id,
            show_quiz=bot.show_quiz,
            get_links=bot.get_links,
            excluded_themes=bot.excluded_themes,
        )

    async def toggle_active(self, bot: PublisherBot) -> bool:
        """Toggle is_active. Returns the new state."""
        bot.is_active = not bot.is_active
        log.info("publisher_bot_toggled", bot_id=bot.id, is_active=bot.is_active)
        return bot.is_active
