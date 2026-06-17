"""Admin: process publisher withdrawal requests.

Flow:
  /start → 💸 Заявки на вывод → список pending → карточка
    → ✅ Я отправил   → approve()
    → ❌ Отклонить    → enter reason → reject()
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.bots.admin import keyboards as kb
from src.bots.admin.states import WithdrawalStates
from src.core.db.models import Publisher, Transaction
from src.core.logging import get_logger
from src.domain.transactions import (
    AutoPayoutError,
    TransactionRepository,
    WithdrawalError,
    WithdrawalService,
)

router = Router(name="admin_withdrawals")
log = get_logger("admin.withdrawals")

PAGE_SIZE = 10


# ---------- List ----------


@router.callback_query(F.data == kb.CB_WITHDRAW_LIST)
async def show_list(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    await state.clear()
    await _render_list(callback, session, page=0)


@router.callback_query(F.data.startswith(kb.CB_WITHDRAW_PAGE))
async def page_nav(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    try:
        page = int(callback.data.split(":")[-1])
    except (ValueError, AttributeError):
        page = 0
    await _render_list(callback, session, page=page)


async def _render_list(
    callback: CallbackQuery,
    session: AsyncSession,
    *,
    page: int,
) -> None:
    repo = TransactionRepository(session)
    total = await repo.count_pending_withdrawals()
    if total == 0:
        try:
            await callback.message.edit_text(
                "💸 <b>Заявки на вывод</b>\n\nСейчас нет заявок в очереди.",
                reply_markup=kb.withdraw_list_kb([], page=0, total_pages=1),
            )
        except TelegramBadRequest:
            pass
        await callback.answer()
        return

    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = max(0, min(page, total_pages - 1))

    txs = await repo.list_pending_withdrawals(
        limit=PAGE_SIZE, offset=page * PAGE_SIZE,
    )

    # Fetch publisher labels in one query
    pub_ids = list({tx.publisher_id for tx in txs if tx.publisher_id})
    publishers: dict[int, Publisher] = {}
    if pub_ids:
        result = await session.execute(
            select(Publisher).where(Publisher.id.in_(pub_ids))
        )
        publishers = {p.id: p for p in result.scalars().all()}

    items: list[tuple[int, str, str]] = []
    for tx in txs:
        pub = publishers.get(tx.publisher_id or 0)
        label = _publisher_short_label(pub)
        amount = f"{-tx.amount_rub:.0f}"
        items.append((tx.id, label, amount))

    text = (
        f"💸 <b>Заявки на вывод</b>\n\n"
        f"Всего ожидают обработки: <b>{total}</b>"
    )
    try:
        await callback.message.edit_text(
            text,
            reply_markup=kb.withdraw_list_kb(items, page=page, total_pages=total_pages),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


# ---------- View card ----------


@router.callback_query(F.data.startswith(kb.CB_WITHDRAW_VIEW))
async def show_card(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    await state.clear()
    try:
        tx_id = int(callback.data.split(":")[-1])
    except (ValueError, AttributeError):
        await callback.answer("Некорректная заявка", show_alert=True)
        return

    repo = TransactionRepository(session)
    tx = await repo.get_by_id(tx_id)
    if tx is None:
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    pub = None
    if tx.publisher_id:
        result = await session.execute(
            select(Publisher).where(Publisher.id == tx.publisher_id)
        )
        pub = result.scalar_one_or_none()

    text = _format_card(tx, pub)
    try:
        await callback.message.edit_text(
            text,
            reply_markup=kb.withdraw_card_kb(tx.id),
            disable_web_page_preview=True,
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


# ---------- Approve ----------


@router.callback_query(F.data.startswith(kb.CB_WITHDRAW_APPROVE))
async def approve(
    callback: CallbackQuery,
    session: AsyncSession,
    admin_tg_id: int,
    admin_username: str | None,
) -> None:
    try:
        tx_id = int(callback.data.split(":")[-1])
    except (ValueError, AttributeError):
        await callback.answer("Некорректная заявка", show_alert=True)
        return

    svc = WithdrawalService(session)
    try:
        tx = await svc.approve(
            tx_id=tx_id, admin_tg_id=admin_tg_id, admin_username=admin_username,
        )
    except WithdrawalError as e:
        await callback.answer(e.user_message, show_alert=True)
        return

    amount = -tx.amount_rub
    log.info("admin_approved_withdrawal", tx_id=tx.id, admin_tg_id=admin_tg_id)

    # Notify publisher
    try:
        from src.workers.notifications import notify_publisher_withdrawal_approved
        await notify_publisher_withdrawal_approved.kiq(
            publisher_id=tx.publisher_id,
            tx_id=tx.id,
            amount_rub=str(amount),
        )
    except Exception as e:
        log.warning("publisher_approve_notify_failed", error=str(e))

    try:
        await callback.message.edit_text(
            f"✅ <b>Заявка #{tx.id} выплачена</b>\n\n"
            f"<b>Сумма:</b> {amount:.2f} ₽\n"
            f"Паблишер уведомлён.",
            reply_markup=kb.withdraw_list_kb([], page=0, total_pages=1),
        )
    except TelegramBadRequest:
        pass
    await callback.answer("Выплата подтверждена")


# ---------- Approve AUTO (CryptoBot transfer) ----------


@router.callback_query(F.data.startswith(kb.CB_WITHDRAW_APPROVE_AUTO))
async def approve_auto(
    callback: CallbackQuery,
    session: AsyncSession,
    admin_tg_id: int,
    admin_username: str | None,
) -> None:
    try:
        tx_id = int(callback.data.split(":")[-1])
    except (ValueError, AttributeError):
        await callback.answer("Некорректная заявка", show_alert=True)
        return

    await callback.answer("⏳ Выполняю перевод через CryptoBot...", show_alert=False)

    svc = WithdrawalService(session)
    try:
        tx = await svc.approve_auto(
            tx_id=tx_id, admin_tg_id=admin_tg_id, admin_username=admin_username,
        )
    except AutoPayoutError as e:
        # Transfer failed — tx stays pending, нет движения денег
        await callback.message.answer(
            f"⚠️ <b>Автовыплата не удалась</b>\n\n"
            f"{e.user_message}\n\n"
            f"Заявка осталась в очереди. Можно повторить или выплатить вручную.",
        )
        return
    except WithdrawalError as e:
        await callback.answer(e.user_message, show_alert=True)
        return

    amount = -tx.amount_rub
    meta = tx.meta or {}
    asset = meta.get("asset", "USDT")
    asset_amount = meta.get("asset_amount", "?")
    transfer_id = meta.get("cryptobot_transfer_id", "?")

    log.info("admin_auto_approved_withdrawal", tx_id=tx.id, admin_tg_id=admin_tg_id)

    # Notify publisher
    try:
        from src.workers.notifications import notify_publisher_withdrawal_approved
        await notify_publisher_withdrawal_approved.kiq(
            publisher_id=tx.publisher_id,
            tx_id=tx.id,
            amount_rub=str(amount),
        )
    except Exception as e:
        log.warning("publisher_approve_notify_failed", error=str(e))

    try:
        await callback.message.edit_text(
            f"⚡ <b>Заявка #{tx.id} выплачена автоматически</b>\n\n"
            f"<b>Сумма:</b> {amount:.2f} ₽ → {asset_amount} {asset}\n"
            f"<b>CryptoBot transfer:</b> #{transfer_id}\n\n"
            f"Паблишер уведомлён.",
            reply_markup=kb.withdraw_list_kb([], page=0, total_pages=1),
        )
    except TelegramBadRequest:
        pass


# ---------- Reject ----------


@router.callback_query(F.data.startswith(kb.CB_WITHDRAW_REJECT_PROMPT))
async def reject_prompt(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    try:
        tx_id = int(callback.data.split(":")[-1])
    except (ValueError, AttributeError):
        await callback.answer("Некорректная заявка", show_alert=True)
        return

    await state.set_state(WithdrawalStates.entering_reject_reason)
    await state.update_data(tx_id=tx_id)
    try:
        await callback.message.edit_text(
            f"❌ <b>Отклонить заявку #{tx_id}</b>\n\n"
            f"Укажите причину отклонения (она будет показана паблишеру). "
            f"Сумма вернётся на его баланс.",
            reply_markup=kb.withdraw_reject_cancel_kb(),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.callback_query(F.data == kb.CB_WITHDRAW_REJECT_CANCEL)
async def reject_cancel(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    data = await state.get_data()
    tx_id = data.get("tx_id")
    await state.clear()
    if tx_id is None:
        await callback.answer()
        return
    # Re-render the card
    callback.data = f"{kb.CB_WITHDRAW_VIEW}{tx_id}"
    await show_card(callback, session, state)


@router.message(WithdrawalStates.entering_reject_reason, F.text)
async def reject_with_reason(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    admin_tg_id: int,
    admin_username: str | None,
) -> None:
    data = await state.get_data()
    tx_id = data.get("tx_id")
    if tx_id is None:
        await state.clear()
        await message.answer("Сессия сброшена.")
        return

    reason = (message.text or "").strip()
    if len(reason) < 3:
        await message.answer(
            "⚠️ Причина слишком короткая. Опишите её подробнее (минимум 3 символа).",
            reply_markup=kb.withdraw_reject_cancel_kb(),
        )
        return
    if len(reason) > 500:
        reason = reason[:500]

    svc = WithdrawalService(session)
    try:
        tx = await svc.reject(
            tx_id=tx_id,
            admin_tg_id=admin_tg_id,
            admin_username=admin_username,
            reason=reason,
        )
    except WithdrawalError as e:
        await state.clear()
        await message.answer(f"⚠️ {e.user_message}")
        return

    await state.clear()
    amount = -tx.amount_rub
    log.info("admin_rejected_withdrawal", tx_id=tx.id, admin_tg_id=admin_tg_id)

    # Notify publisher
    try:
        from src.workers.notifications import notify_publisher_withdrawal_rejected
        await notify_publisher_withdrawal_rejected.kiq(
            publisher_id=tx.publisher_id,
            tx_id=tx.id,
            amount_rub=str(amount),
            reason=reason,
        )
    except Exception as e:
        log.warning("publisher_reject_notify_failed", error=str(e))

    await message.answer(
        f"❌ <b>Заявка #{tx.id} отклонена</b>\n\n"
        f"<b>Сумма:</b> {amount:.2f} ₽ возвращена на баланс паблишера.\n"
        f"<b>Причина:</b> {reason[:100]}\n\n"
        f"Паблишер уведомлён.",
        reply_markup=kb.withdraw_list_kb([], page=0, total_pages=1),
    )


# ---------- Formatting helpers ----------


def _publisher_short_label(pub: Publisher | None) -> str:
    if pub is None:
        return "—"
    if pub.tg_username:
        return f"@{pub.tg_username}"
    return pub.full_name or f"id:{pub.id}"


def _format_card(tx: Transaction, pub: Publisher | None) -> str:
    amount = -tx.amount_rub
    meta = tx.meta or {}
    method = meta.get("method", "—")
    recipient = meta.get("recipient", "—")

    created = tx.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    elapsed = datetime.now(timezone.utc) - created
    h = int(elapsed.total_seconds() // 3600)
    m = int((elapsed.total_seconds() % 3600) // 60)
    age = f"{h} ч {m} мин назад" if h else f"{m} мин назад"

    pub_label = _publisher_short_label(pub)
    pub_extra = ""
    if pub is not None:
        pub_extra = (
            f"\n<b>Баланс паблишера:</b> {pub.balance_rub:.2f} ₽"
            f" (заморожено: {pub.hold_rub:.2f} ₽)"
            f"\n<b>Всего заработано:</b> {pub.total_earned_rub:.2f} ₽"
            f"\n<b>Retention:</b> {pub.retention_rate}%"
            f" ({pub.verified_subs_in_window} подписок за 30 дней)"
        )

    return (
        f"💸 <b>Заявка #{tx.id}</b>\n\n"
        f"<b>Паблишер:</b> {pub_label}{pub_extra}\n\n"
        f"<b>Сумма к выплате:</b> {amount:.2f} ₽\n"
        f"<b>Способ:</b> {method}\n"
        f"<b>Получатель:</b> <code>{recipient}</code>\n"
        f"<b>Создана:</b> {created.strftime('%Y-%m-%d %H:%M UTC')} ({age})\n\n"
        f"Сделайте перевод вручную через CryptoBot, затем нажмите «✅ Я отправил»."
    )
