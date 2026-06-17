"""/start and top-level menu callbacks for the combined bot."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bots.main import texts
from src.bots.main.keyboards import back_to_main_kb, main_menu_kb
from src.core.db.models import Advertiser, Publisher
from src.core.logging import get_logger
from src.domain.exceptions import DomainError
from src.domain.publishers import PublisherService

router = Router(name="main_start")
log = get_logger("main.start")


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    state: FSMContext,
    advertiser: Advertiser,
    publisher: Publisher | None,
    session: AsyncSession,
) -> None:
    """Show combined welcome menu. Auto-register as publisher on first visit."""
    await state.clear()

    if publisher is None and message.from_user is not None:
        svc = PublisherService(session)
        try:
            await svc.get_or_create(
                tg_user_id=message.from_user.id,
                tg_username=message.from_user.username,
                full_name=message.from_user.full_name,
            )
        except DomainError as e:
            log.warning("publisher_create_failed", error=str(e))

    is_new = (
        advertiser.created_at == advertiser.updated_at
        or (advertiser.updated_at - advertiser.created_at).total_seconds() < 2
    )
    text = texts.WELCOME_NEW if is_new else texts.WELCOME_BACK
    await message.answer(text=text, reply_markup=main_menu_kb())

    log.info(
        "main_start",
        advertiser_id=advertiser.id,
        tg_user_id=advertiser.tg_user_id,
        is_new=is_new,
    )


@router.callback_query(F.data == texts.CB_MAIN_MENU)
async def show_main_menu(callback: CallbackQuery, state: FSMContext) -> None:
    """Return to the top-level combined menu."""
    await state.clear()
    try:
        await callback.message.edit_text(
            text=texts.MAIN_MENU_PROMPT,
            reply_markup=main_menu_kb(),
        )
    except TelegramBadRequest as e:
        if "not modified" not in str(e).lower():
            log.warning("edit_failed", error=str(e))
    finally:
        await callback.answer()


@router.callback_query(F.data == texts.CB_MAIN_HELP)
async def show_help(callback: CallbackQuery) -> None:
    try:
        await callback.message.edit_text(
            text=texts.HELP_TEXT,
            reply_markup=back_to_main_kb(),
        )
    except TelegramBadRequest as e:
        if "not modified" not in str(e).lower():
            log.warning("edit_failed", error=str(e))
    finally:
        await callback.answer()
