"""/start and main-menu handlers for admin bot."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bots.admin import keyboards as kb
from src.core.logging import get_logger
from src.domain.campaigns import CampaignService
from src.domain.transactions import TransactionRepository

router = Router(name="admin_start")
log = get_logger("admin.start")


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    admin_tg_id: int,
    admin_username: str | None,
    session: AsyncSession,
) -> None:
    log.info("admin_start", admin_tg_id=admin_tg_id, username=admin_username)
    svc = CampaignService(session)
    tx_repo = TransactionRepository(session)
    pending = await svc.count_pending()
    withdrawals = await tx_repo.count_pending_withdrawals()
    await message.answer(
        f"Привет, админ!\n\n"
        f"<b>На модерации:</b> {pending}\n"
        f"<b>Заявок на вывод:</b> {withdrawals}",
        reply_markup=kb.main_menu_kb(pending, withdrawals),
    )


@router.callback_query(F.data == kb.CB_MAIN_MENU)
async def main_menu(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await state.clear()
    svc = CampaignService(session)
    tx_repo = TransactionRepository(session)
    pending = await svc.count_pending()
    withdrawals = await tx_repo.count_pending_withdrawals()
    try:
        await callback.message.edit_text(
            f"<b>Админ-меню</b>\n\n"
            f"<b>На модерации:</b> {pending}\n"
            f"<b>Заявок на вывод:</b> {withdrawals}",
            reply_markup=kb.main_menu_kb(pending, withdrawals),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.callback_query(F.data =="noop")
async def noop(callback: CallbackQuery) -> None:
    await callback.answer()
