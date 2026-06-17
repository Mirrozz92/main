"""Bot settings handlers: sponsors_count, list_ttl_seconds, show_quiz, get_links, excluded_themes."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bots.publisher import texts
from src.bots.publisher.keyboards import (
    custom_value_cancel_kb,
    excluded_themes_kb,
    settings_kb,
    sponsors_presets_kb,
    ttl_presets_kb,
)
from src.bots.publisher.states import BotSettingsStates
from src.core.db.models import Publisher
from src.core.logging import get_logger
from src.domain.exceptions import DomainError
from src.domain.publisher_bots import PublisherBotRepository, PublisherBotService

router = Router(name="publisher_bot_settings")
log = get_logger("publisher.bot_settings")


async def _verify_ownership(callback, publisher, session, bot_id):
    if publisher is None:
        await callback.answer("Сначала пришлите /start", show_alert=True)
        return None
    repo = PublisherBotRepository(session)
    bot = await repo.get_by_id(bot_id)
    if bot is None or bot.publisher_id != publisher.id:
        await callback.answer("Бот не найден", show_alert=True)
        return None
    return bot


def _settings_text(bot) -> str:
    return texts.settings_view(
        bot.sponsors_count,
        bot.list_ttl_seconds,
        bot.show_quiz,
        bot.get_links,
        bot.excluded_themes or [],
    )


def _settings_kb(bot):
    return settings_kb(bot.id, bot.show_quiz, bot.get_links)


# ---------- Settings root ----------


@router.callback_query(F.data.startswith(texts.CB_BOT_SETTINGS))
async def show_settings(
    callback: CallbackQuery,
    state: FSMContext,
    publisher: Publisher | None,
    session: AsyncSession,
) -> None:
    await state.clear()
    try:
        bot_id = int(callback.data.removeprefix(texts.CB_BOT_SETTINGS))
    except ValueError:
        await callback.answer("Неверный ID", show_alert=True)
        return

    bot = await _verify_ownership(callback, publisher, session, bot_id)
    if bot is None:
        return

    try:
        await callback.message.edit_text(_settings_text(bot), reply_markup=_settings_kb(bot))
    except TelegramBadRequest:
        pass
    await callback.answer()


# ---------- Sponsors count ----------


@router.callback_query(F.data.startswith(texts.CB_SET_SPONSORS))
async def show_sponsors_choice(
    callback: CallbackQuery,
    publisher: Publisher | None,
    session: AsyncSession,
) -> None:
    try:
        bot_id = int(callback.data.removeprefix(texts.CB_SET_SPONSORS))
    except ValueError:
        await callback.answer("Неверный ID", show_alert=True)
        return

    bot = await _verify_ownership(callback, publisher, session, bot_id)
    if bot is None:
        return

    try:
        await callback.message.edit_text(
            texts.SET_SPONSORS_PROMPT,
            reply_markup=sponsors_presets_kb(bot.id, bot.sponsors_count),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith(texts.CB_SPONSORS_VALUE))
async def set_sponsors_preset(
    callback: CallbackQuery,
    publisher: Publisher | None,
    session: AsyncSession,
) -> None:
    raw = callback.data.removeprefix(texts.CB_SPONSORS_VALUE)
    try:
        bot_id_str, value_str = raw.split(":", 1)
        bot_id = int(bot_id_str)
        value = int(value_str)
    except (ValueError, IndexError):
        await callback.answer("Неверные данные", show_alert=True)
        return

    bot = await _verify_ownership(callback, publisher, session, bot_id)
    if bot is None:
        return

    svc = PublisherBotService(session)
    try:
        await svc.update_settings(bot, sponsors_count=value)
    except DomainError as e:
        await callback.answer(e.user_message, show_alert=True)
        return

    await callback.answer(f"Установлено: {value}")
    try:
        await callback.message.edit_text(_settings_text(bot), reply_markup=_settings_kb(bot))
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.startswith(texts.CB_SPONSORS_CUSTOM))
async def sponsors_custom_prompt(
    callback: CallbackQuery,
    state: FSMContext,
    publisher: Publisher | None,
    session: AsyncSession,
) -> None:
    try:
        bot_id = int(callback.data.removeprefix(texts.CB_SPONSORS_CUSTOM))
    except ValueError:
        await callback.answer("Неверный ID", show_alert=True)
        return

    bot = await _verify_ownership(callback, publisher, session, bot_id)
    if bot is None:
        return

    await state.set_state(BotSettingsStates.entering_sponsors_count)
    await state.update_data(bot_id=bot.id)
    try:
        await callback.message.edit_text(
            texts.SPONSORS_CUSTOM_PROMPT,
            reply_markup=custom_value_cancel_kb(bot.id, texts.CB_SET_SPONSORS),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.message(BotSettingsStates.entering_sponsors_count, F.text)
async def sponsors_custom_input(
    message: Message,
    state: FSMContext,
    publisher: Publisher | None,
    session: AsyncSession,
) -> None:
    if publisher is None:
        await state.clear()
        return
    data = await state.get_data()
    bot_id = data.get("bot_id")
    if bot_id is None:
        await state.clear()
        return

    raw = (message.text or "").strip()
    try:
        value = int(raw)
    except ValueError:
        await message.answer(
            "Введите целое число от 1 до 10.",
            reply_markup=custom_value_cancel_kb(bot_id, texts.CB_SET_SPONSORS),
        )
        return

    repo = PublisherBotRepository(session)
    bot = await repo.get_by_id(bot_id)
    if bot is None or bot.publisher_id != publisher.id:
        await state.clear()
        return

    svc = PublisherBotService(session)
    try:
        await svc.update_settings(bot, sponsors_count=value)
    except DomainError as e:
        await message.answer(
            f"{e.user_message}",
            reply_markup=custom_value_cancel_kb(bot.id, texts.CB_SET_SPONSORS),
        )
        return

    await state.clear()
    await message.answer(_settings_text(bot), reply_markup=_settings_kb(bot))


# ---------- TTL ----------


@router.callback_query(F.data.startswith(texts.CB_SET_TTL))
async def show_ttl_choice(
    callback: CallbackQuery,
    publisher: Publisher | None,
    session: AsyncSession,
) -> None:
    try:
        bot_id = int(callback.data.removeprefix(texts.CB_SET_TTL))
    except ValueError:
        await callback.answer("Неверный ID", show_alert=True)
        return

    bot = await _verify_ownership(callback, publisher, session, bot_id)
    if bot is None:
        return

    try:
        await callback.message.edit_text(
            texts.SET_TTL_PROMPT,
            reply_markup=ttl_presets_kb(bot.id, bot.list_ttl_seconds),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith(texts.CB_TTL_VALUE))
async def set_ttl_preset(
    callback: CallbackQuery,
    publisher: Publisher | None,
    session: AsyncSession,
) -> None:
    raw = callback.data.removeprefix(texts.CB_TTL_VALUE)
    try:
        bot_id_str, seconds_str = raw.split(":", 1)
        bot_id = int(bot_id_str)
        seconds = int(seconds_str)
    except (ValueError, IndexError):
        await callback.answer("Неверные данные", show_alert=True)
        return

    bot = await _verify_ownership(callback, publisher, session, bot_id)
    if bot is None:
        return

    svc = PublisherBotService(session)
    try:
        await svc.update_settings(bot, list_ttl_seconds=seconds)
    except DomainError as e:
        await callback.answer(e.user_message, show_alert=True)
        return

    await callback.answer("Установлено")
    try:
        await callback.message.edit_text(_settings_text(bot), reply_markup=_settings_kb(bot))
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.startswith(texts.CB_TTL_CUSTOM))
async def ttl_custom_prompt(
    callback: CallbackQuery,
    state: FSMContext,
    publisher: Publisher | None,
    session: AsyncSession,
) -> None:
    try:
        bot_id = int(callback.data.removeprefix(texts.CB_TTL_CUSTOM))
    except ValueError:
        await callback.answer("Неверный ID", show_alert=True)
        return

    bot = await _verify_ownership(callback, publisher, session, bot_id)
    if bot is None:
        return

    await state.set_state(BotSettingsStates.entering_ttl_minutes)
    await state.update_data(bot_id=bot.id)
    try:
        await callback.message.edit_text(
            texts.TTL_CUSTOM_PROMPT,
            reply_markup=custom_value_cancel_kb(bot.id, texts.CB_SET_TTL),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.message(BotSettingsStates.entering_ttl_minutes, F.text)
async def ttl_custom_input(
    message: Message,
    state: FSMContext,
    publisher: Publisher | None,
    session: AsyncSession,
) -> None:
    if publisher is None:
        await state.clear()
        return
    data = await state.get_data()
    bot_id = data.get("bot_id")
    if bot_id is None:
        await state.clear()
        return

    raw = (message.text or "").strip()
    try:
        minutes = int(raw)
    except ValueError:
        await message.answer(
            "Введите целое число минут от 5 до 10080.",
            reply_markup=custom_value_cancel_kb(bot_id, texts.CB_SET_TTL),
        )
        return

    seconds = minutes * 60

    repo = PublisherBotRepository(session)
    bot = await repo.get_by_id(bot_id)
    if bot is None or bot.publisher_id != publisher.id:
        await state.clear()
        return

    svc = PublisherBotService(session)
    try:
        await svc.update_settings(bot, list_ttl_seconds=seconds)
    except DomainError as e:
        await message.answer(
            f"{e.user_message}",
            reply_markup=custom_value_cancel_kb(bot.id, texts.CB_SET_TTL),
        )
        return

    await state.clear()
    await message.answer(_settings_text(bot), reply_markup=_settings_kb(bot))


# ---------- Toggle show_quiz ----------


@router.callback_query(F.data.startswith(texts.CB_TOGGLE_QUIZ))
async def toggle_show_quiz(
    callback: CallbackQuery,
    publisher: Publisher | None,
    session: AsyncSession,
) -> None:
    try:
        bot_id = int(callback.data.removeprefix(texts.CB_TOGGLE_QUIZ))
    except ValueError:
        await callback.answer("Неверный ID", show_alert=True)
        return

    bot = await _verify_ownership(callback, publisher, session, bot_id)
    if bot is None:
        return

    svc = PublisherBotService(session)
    await svc.update_extra_settings(bot, show_quiz=not bot.show_quiz)
    await session.flush()

    await callback.answer("Анкета " + ("включена" if bot.show_quiz else "выключена"))
    try:
        await callback.message.edit_text(_settings_text(bot), reply_markup=_settings_kb(bot))
    except TelegramBadRequest:
        pass


# ---------- Toggle get_links ----------


@router.callback_query(F.data.startswith(texts.CB_TOGGLE_LINKS))
async def toggle_get_links(
    callback: CallbackQuery,
    publisher: Publisher | None,
    session: AsyncSession,
) -> None:
    try:
        bot_id = int(callback.data.removeprefix(texts.CB_TOGGLE_LINKS))
    except ValueError:
        await callback.answer("Неверный ID", show_alert=True)
        return

    bot = await _verify_ownership(callback, publisher, session, bot_id)
    if bot is None:
        return

    svc = PublisherBotService(session)
    await svc.update_extra_settings(bot, get_links=not bot.get_links)
    await session.flush()

    await callback.answer("Режим ссылок " + ("включён" if bot.get_links else "выключен"))
    try:
        await callback.message.edit_text(_settings_text(bot), reply_markup=_settings_kb(bot))
    except TelegramBadRequest:
        pass


# ---------- Excluded themes multiselect ----------


@router.callback_query(F.data.startswith(texts.CB_THEMES_MENU))
async def show_themes_menu(
    callback: CallbackQuery,
    state: FSMContext,
    publisher: Publisher | None,
    session: AsyncSession,
) -> None:
    try:
        bot_id = int(callback.data.removeprefix(texts.CB_THEMES_MENU))
    except ValueError:
        await callback.answer("Неверный ID", show_alert=True)
        return

    bot = await _verify_ownership(callback, publisher, session, bot_id)
    if bot is None:
        return

    temp_excluded = list(bot.excluded_themes or [])
    await state.set_state(BotSettingsStates.selecting_themes)
    await state.update_data(bot_id=bot.id, temp_excluded=temp_excluded)

    try:
        await callback.message.edit_text(
            texts.THEMES_MENU_PROMPT,
            reply_markup=excluded_themes_kb(bot.id, temp_excluded),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.callback_query(BotSettingsStates.selecting_themes, F.data.startswith(texts.CB_THEME_TOGGLE))
async def theme_toggle(
    callback: CallbackQuery,
    state: FSMContext,
    publisher: Publisher | None,
) -> None:
    if publisher is None:
        await callback.answer("Сначала пришлите /start", show_alert=True)
        return

    raw = callback.data.removeprefix(texts.CB_THEME_TOGGLE)
    try:
        bot_id_str, theme = raw.split(":", 1)
        bot_id = int(bot_id_str)
    except (ValueError, IndexError):
        await callback.answer("Неверные данные", show_alert=True)
        return

    if theme not in texts.ALL_THEMES:
        await callback.answer("Неизвестная тематика", show_alert=True)
        return

    data = await state.get_data()
    if data.get("bot_id") != bot_id:
        await callback.answer("Неверный бот", show_alert=True)
        return

    temp_excluded: list[str] = list(data.get("temp_excluded") or [])
    if theme in temp_excluded:
        temp_excluded.remove(theme)
        label = texts.THEME_LABELS[theme]
        await callback.answer(f"{label} — включена")
    else:
        temp_excluded.append(theme)
        label = texts.THEME_LABELS[theme]
        await callback.answer(f"{label} — исключена")

    await state.update_data(temp_excluded=temp_excluded)

    try:
        await callback.message.edit_reply_markup(
            reply_markup=excluded_themes_kb(bot_id, temp_excluded),
        )
    except TelegramBadRequest:
        pass


@router.callback_query(BotSettingsStates.selecting_themes, F.data.startswith(texts.CB_THEMES_SAVE))
async def themes_save(
    callback: CallbackQuery,
    state: FSMContext,
    publisher: Publisher | None,
    session: AsyncSession,
) -> None:
    try:
        bot_id = int(callback.data.removeprefix(texts.CB_THEMES_SAVE))
    except ValueError:
        await callback.answer("Неверный ID", show_alert=True)
        return

    bot = await _verify_ownership(callback, publisher, session, bot_id)
    if bot is None:
        await state.clear()
        return

    data = await state.get_data()
    temp_excluded: list[str] = list(data.get("temp_excluded") or [])

    svc = PublisherBotService(session)
    try:
        await svc.update_extra_settings(bot, excluded_themes=temp_excluded)
    except DomainError as e:
        await callback.answer(e.user_message, show_alert=True)
        return

    await session.flush()
    await state.clear()

    await callback.answer("Тематики сохранены")
    try:
        await callback.message.edit_text(_settings_text(bot), reply_markup=_settings_kb(bot))
    except TelegramBadRequest:
        pass
