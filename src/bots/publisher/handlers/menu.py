"""Main menu handlers: menu, profile, help."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from src.bots.publisher import texts
from src.bots.publisher.keyboards import back_to_menu_kb, main_menu_kb
from src.core.db.models import Publisher
from src.core.logging import get_logger
from src.domain.publisher_bots import PublisherBotRepository

router = Router(name="publisher_menu")
log = get_logger("publisher.menu")


async def _edit(callback: CallbackQuery, text: str, kb) -> None:
    try:
        await callback.message.edit_text(text=text, reply_markup=kb)
    except TelegramBadRequest as e:
        if"not modified"not in str(e).lower():
            log.warning("edit_failed", error=str(e))
    finally:
        await callback.answer()


@router.callback_query(F.data == texts.CB_MENU)
async def show_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _edit(callback, texts.MENU_PROMPT, main_menu_kb())


@router.callback_query(F.data == texts.CB_PROFILE)
async def show_profile(
    callback: CallbackQuery,
    publisher: Publisher | None,
    session: AsyncSession,
) -> None:
    if publisher is None:
        await callback.answer("Сначала пришлите /start", show_alert=True)
        return

    bot_repo = PublisherBotRepository(session)
    bots = await bot_repo.list_for_publisher(publisher.id)
    active_count = sum(1 for b in bots if b.is_active)

    full_name = publisher.full_name or (
        f"@{publisher.tg_username}"if publisher.tg_username else"—"
    )

    text = texts.profile_view(
        full_name=full_name,
        tg_username=publisher.tg_username,
        registered_at=publisher.created_at.strftime("%Y-%m-%d") if publisher.created_at else"—",
        total_bots=len(bots),
        active_bots=active_count,
        total_subscriptions=publisher.total_subscriptions,
        total_unsubscriptions=publisher.total_unsubscriptions,
        retention_rate=publisher.retention_rate,
        verified_subs_in_window=publisher.verified_subs_in_window,
        rating=publisher.rating,
        verified_subs_total=publisher.verified_subs_total,
        total_earned=publisher.total_earned_rub,
    )
    await _edit(callback, text, back_to_menu_kb())


@router.callback_query(F.data == texts.CB_HELP)
async def show_help(callback: CallbackQuery) -> None:
    await _edit(callback, texts.HELP_TEXT, back_to_menu_kb())


@router.callback_query(F.data == texts.CB_NOOP)
async def noop(callback: CallbackQuery) -> None:
    """Pagination counter — just acknowledge."""
    await callback.answer()
