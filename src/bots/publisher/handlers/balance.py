"""Balance handlers: view, transactions history, withdrawal request."""

from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bots.publisher import texts
from src.bots.publisher.keyboards import (
    balance_kb,
    history_kb,
    main_menu_kb,
    withdraw_cancel_kb,
)
from src.bots.publisher.states import WithdrawStates
from src.core.db.models import Publisher
from src.core.db.models.enums import TransactionStatus, TransactionType
from src.core.logging import get_logger
from src.domain.exceptions import DomainError
from src.domain.transactions import TransactionRepository
from src.shared.money import to_money

router = Router(name="publisher_balance")
log = get_logger("publisher.balance")


PAGE_SIZE = 10
MIN_WITHDRAW_RUB = Decimal("100")


# ---------- Balance view ----------


@router.callback_query(F.data == texts.CB_BALANCE)
async def show_balance(
    callback: CallbackQuery,
    state: FSMContext,
    publisher: Publisher | None,
) -> None:
    await state.clear()
    if publisher is None:
        await callback.answer("Сначала пришлите /start", show_alert=True)
        return

    text = texts.balance_view(
        balance=publisher.balance_rub,
        hold=publisher.hold_rub,
        total_earned=publisher.total_earned_rub,
    )
    try:
        await callback.message.edit_text(text, reply_markup=balance_kb())
    except TelegramBadRequest:
        pass
    await callback.answer()


# ---------- History ----------


_TX_TYPE_LABELS: dict[str, str] = {
    "publisher_earn":"Заработок",
    "publisher_hold_release":"Холд баланс",
    "publisher_hold_revert":"Возврат холда",
    "publisher_payout":"Выплата",
    "publisher_bonus":"Бонус retention",
}


def _format_transaction(tx) -> str:
    type_label = _TX_TYPE_LABELS.get(tx.type.value, f"{tx.type.value}")
    amount = tx.amount_rub
    sign ="+"if amount >= 0 else""
    date_str = tx.created_at.strftime("%d.%m %H:%M") if tx.created_at else"—"
    return (
        f"<b>{type_label}</b>\n"
        f"<i>{date_str}</i> •"
        f"<b>{sign}{amount:.2f} ₽</b>"
    )


@router.callback_query(F.data == texts.CB_HISTORY)
async def show_history(
    callback: CallbackQuery,
    publisher: Publisher | None,
    session: AsyncSession,
) -> None:
    await _render_history(callback, publisher, session, page=0)


@router.callback_query(F.data.startswith(texts.CB_HISTORY_PAGE))
async def history_page(
    callback: CallbackQuery,
    publisher: Publisher | None,
    session: AsyncSession,
) -> None:
    try:
        page = int(callback.data.removeprefix(texts.CB_HISTORY_PAGE))
    except ValueError:
        await callback.answer("Неверная страница", show_alert=True)
        return
    await _render_history(callback, publisher, session, page=page)


async def _render_history(
    callback: CallbackQuery,
    publisher: Publisher | None,
    session: AsyncSession,
    *,
    page: int,
) -> None:
    if publisher is None:
        await callback.answer("Сначала пришлите /start", show_alert=True)
        return

    repo = TransactionRepository(session)
    total = await repo.count_for_publisher(publisher.id)

    if total == 0:
        try:
            await callback.message.edit_text(
                "<b>История транзакций</b>\n\n"
                "Здесь пока пусто. Транзакции появятся, когда ваши боты"
                "начнут приносить заработок.",
                reply_markup=history_kb(0, 1),
            )
        except TelegramBadRequest:
            pass
        await callback.answer()
        return

    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = max(0, min(page, total_pages - 1))

    txs = await repo.list_for_publisher(
        publisher.id, limit=PAGE_SIZE, offset=page * PAGE_SIZE,
    )

    lines = [texts.transactions_list_header(total, page, total_pages),""]
    for tx in txs:
        lines.append(_format_transaction(tx))
        lines.append("")
    text ="\n".join(lines).strip()

    try:
        await callback.message.edit_text(text, reply_markup=history_kb(page, total_pages))
    except TelegramBadRequest:
        pass
    await callback.answer()


# ---------- Withdraw FSM ----------


@router.callback_query(F.data == texts.CB_WITHDRAW)
async def withdraw_prompt(
    callback: CallbackQuery,
    state: FSMContext,
    publisher: Publisher | None,
) -> None:
    if publisher is None:
        await callback.answer("Сначала пришлите /start", show_alert=True)
        return

    if publisher.balance_rub < MIN_WITHDRAW_RUB:
        await callback.answer(
            f"Минимум для вывода: {MIN_WITHDRAW_RUB:.0f} ₽."
            f"Сейчас на балансе: {publisher.balance_rub:.2f} ₽.",
            show_alert=True,
        )
        return

    await state.set_state(WithdrawStates.entering_amount)
    try:
        await callback.message.edit_text(
            f"{texts.WITHDRAW_PROMPT}\n\n"
            f"Доступно: <b>{publisher.balance_rub:.2f} ₽</b>",
            reply_markup=withdraw_cancel_kb(),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.message(WithdrawStates.entering_amount, F.text)
async def withdraw_amount(
    message: Message,
    state: FSMContext,
    publisher: Publisher | None,
    session: AsyncSession,
) -> None:
    if publisher is None:
        await state.clear()
        return

    raw = (message.text or"").strip().replace(",",".")
    try:
        amount = to_money(Decimal(raw))
    except (InvalidOperation, ValueError):
        await message.answer(
            "Введите сумму числом. Например: <code>500</code> или <code>123.45</code>.",
            reply_markup=withdraw_cancel_kb(),
        )
        return

    if amount < MIN_WITHDRAW_RUB:
        await message.answer(
            f"Минимум для вывода: {MIN_WITHDRAW_RUB:.0f} ₽.",
            reply_markup=withdraw_cancel_kb(),
        )
        return

    if amount > publisher.balance_rub:
        await message.answer(
            f"Недостаточно средств. Доступно: {publisher.balance_rub:.2f} ₽.",
            reply_markup=withdraw_cancel_kb(),
        )
        return

    # Reserve: balance pending payout transaction
    # We don't decrement balance_rub here — that happens when admin approves payout.
    # We create a PENDING transaction to mark the request.
    tx_repo = TransactionRepository(session)
    await tx_repo.create(
        type=TransactionType.PUBLISHER_PAYOUT,
        amount_rub=-amount, # negative: leaving balance (when approved)
        publisher_id=publisher.id,
        description=f"Заявка на вывод {amount:.2f} ₽ (ожидает обработки)",
        status=TransactionStatus.PENDING,
    )

    await state.clear()
    await message.answer(texts.WITHDRAW_SUCCESS, reply_markup=main_menu_kb())

    # Notify admin
    try:
        from src.workers.notifications import notify_admin_new_withdrawal
        adv_label = (
            f"@{publisher.tg_username}"if publisher.tg_username
            else (publisher.full_name or f"id:{publisher.id}")
        )
        await notify_admin_new_withdrawal.kiq(
            publisher_id=publisher.id,
            publisher_label=adv_label,
            amount_rub=str(amount),
        )
    except Exception as e:
        log.warning("admin_withdrawal_notify_failed", error=str(e))
