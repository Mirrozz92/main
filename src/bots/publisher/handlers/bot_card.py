"""Bot card handlers: view, toggle active, stats."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from src.bots.publisher import texts
from src.bots.publisher.keyboards import bot_card_kb
from src.core.db.models import Publisher
from src.core.logging import get_logger
from src.domain.publisher_bots import PublisherBotRepository, PublisherBotService

router = Router(name="publisher_bot_card")
log = get_logger("publisher.bot_card")


async def _verify_ownership(
    callback: CallbackQuery,
    publisher: Publisher | None,
    session: AsyncSession,
    bot_id: int,
):
    """Return (bot, repo) if user owns this bot, else None and answer error."""
    if publisher is None:
        await callback.answer("Сначала пришлите /start", show_alert=True)
        return None, None
    repo = PublisherBotRepository(session)
    bot = await repo.get_by_id(bot_id)
    if bot is None or bot.publisher_id != publisher.id:
        await callback.answer("Бот не найден", show_alert=True)
        return None, None
    return bot, repo


# ---------- View bot card ----------


@router.callback_query(F.data.startswith(texts.CB_BOT_VIEW))
async def view_bot(
    callback: CallbackQuery,
    publisher: Publisher | None,
    session: AsyncSession,
) -> None:
    try:
        bot_id = int(callback.data.removeprefix(texts.CB_BOT_VIEW))
    except ValueError:
        await callback.answer("Неверный ID", show_alert=True)
        return

    bot, _ = await _verify_ownership(callback, publisher, session, bot_id)
    if bot is None:
        return

    text = texts.bot_card_view(
        name=bot.name,
        username=bot.tg_bot_username,
        is_active=bot.is_active,
        is_moderated=bot.is_moderated,
    )
    try:
        await callback.message.edit_text(text, reply_markup=bot_card_kb(bot.id, bot.is_active))
    except TelegramBadRequest:
        pass
    await callback.answer()


# ---------- Toggle ----------


@router.callback_query(F.data.startswith(texts.CB_BOT_TOGGLE))
async def toggle_bot(
    callback: CallbackQuery,
    publisher: Publisher | None,
    session: AsyncSession,
) -> None:
    try:
        bot_id = int(callback.data.removeprefix(texts.CB_BOT_TOGGLE))
    except ValueError:
        await callback.answer("Неверный ID", show_alert=True)
        return

    bot, _ = await _verify_ownership(callback, publisher, session, bot_id)
    if bot is None:
        return

    svc = PublisherBotService(session)
    new_state = await svc.toggle_active(bot)
    await callback.answer("Активирован"if new_state else"Отключён")

    # Re-render bot card
    text = texts.bot_card_view(
        name=bot.name,
        username=bot.tg_bot_username,
        is_active=bot.is_active,
        is_moderated=bot.is_moderated,
    )
    try:
        await callback.message.edit_text(text, reply_markup=bot_card_kb(bot.id, bot.is_active))
    except TelegramBadRequest:
        pass


# ---------- Stats ----------


@router.callback_query(F.data.startswith(texts.CB_BOT_STATS))
async def view_bot_stats(
    callback: CallbackQuery,
    publisher: Publisher | None,
    session: AsyncSession,
) -> None:
    try:
        bot_id = int(callback.data.removeprefix(texts.CB_BOT_STATS))
    except ValueError:
        await callback.answer("Неверный ID", show_alert=True)
        return

    bot, _ = await _verify_ownership(callback, publisher, session, bot_id)
    if bot is None:
        return

    text = texts.bot_stats_view(
        name=bot.name,
        total_requests=bot.total_requests,
        total_issued=bot.total_issued,
        total_verified=bot.total_verified,
        total_earned_rub=bot.total_earned_rub,
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="« К боту", callback_data=f"{texts.CB_BOT_VIEW}{bot.id}")],
    ])
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:
        pass
    await callback.answer()
