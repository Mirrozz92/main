"""Main menu callback handlers (inline buttons).

NOTE:
- CB_TOPUP is handled in topup.py (starts FSM)
- CB_CAMPAIGNS is handled in campaign_list.py (real listing)
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from src.bots.advertiser import texts
from src.bots.advertiser.keyboards.main_menu import back_to_menu_kb, main_menu_inline_kb
from src.core.db.models import Advertiser
from src.core.logging import get_logger

router = Router(name="menu")
log = get_logger("handler.menu")


async def _edit(callback: CallbackQuery, text: str, *, back: bool = False) -> None:
    keyboard = back_to_menu_kb() if back else main_menu_inline_kb()
    try:
        await callback.message.edit_text(text=text, reply_markup=keyboard)
    except TelegramBadRequest as e:
        if"not modified"not in str(e).lower():
            log.warning("edit_failed", error=str(e))
    finally:
        await callback.answer()


@router.callback_query(F.data == texts.CB_MENU)
async def show_menu(callback: CallbackQuery, state: FSMContext, advertiser: Advertiser) -> None:
    # Reset any active FSM-flow when returning to menu
    await state.clear()
    await _edit(callback, texts.MENU_PROMPT)


@router.callback_query(F.data == texts.CB_BALANCE)
async def show_balance(callback: CallbackQuery, advertiser: Advertiser) -> None:
    await _edit(
        callback,
        texts.balance_view(
            balance=advertiser.balance_rub,
            reserved=advertiser.reserved_rub,
            total_spent=advertiser.total_spent_rub,
        ),
        back=True,
    )


@router.callback_query(F.data == texts.CB_HELP)
async def show_help(callback: CallbackQuery, advertiser: Advertiser) -> None:
    await _edit(callback, texts.HELP_TEXT, back=True)


@router.callback_query(F.data =="noop")
async def noop(callback: CallbackQuery) -> None:
    """Pagination counter button — just acknowledges."""
    await callback.answer()
