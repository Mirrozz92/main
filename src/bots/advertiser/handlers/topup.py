"""Top-up flow handlers (FSM).

Flow:
1. User clicks"Пополнить"show presets
2. User clicks preset OR"Своя сумма"either go straight to invoice creation
   or ask to type amount.
3. After amount is determined create CryptoBot invoice show"Pay"button.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bots.advertiser import texts
from src.bots.advertiser.keyboards import topup as topup_kb
from src.bots.advertiser.keyboards.main_menu import main_menu_inline_kb
from src.bots.advertiser.states.topup import TopupStates
from src.core.config import get_settings
from src.core.db.models import Advertiser
from src.core.logging import get_logger
from src.domain.exceptions import CryptoBotError, DomainError
from src.domain.payments import PaymentsService
from src.shared.money import to_money

router = Router(name="topup")
log = get_logger("handler.topup")


# ---------- Texts (local to topup) ----------

TOPUP_PROMPT = (
    "<b>Пополнение баланса</b>\n\n"
    "Выберите сумму пополнения. Оплата принимается в"
    "<b>USDT</b> или <b>TON</b> через CryptoBot.\n\n"
    "<i>Минимум: {min_amount:.0f} ₽</i>"
)


CUSTOM_PROMPT = (
    "<b>Введите сумму пополнения в рублях</b>\n\n"
    "Например: <code>700</code> или <code>1500</code>\n\n"
    "<i>Минимум: {min_amount:.0f} ₽, максимум: 1 000 000 ₽</i>"
)


def custom_invalid(reason: str) -> str:
    return f"{reason}\n\nВведите сумму ещё раз или нажмите «Отмена»."


def invoice_ready(amount_rub: Decimal, invoice_id: int) -> str:
    return (
        f"<b>Счёт создан</b>\n\n"
        f"Сумма: <b>{amount_rub:.2f} ₽</b>\n"
        f"Счёт: <code>#{invoice_id}</code>\n\n"
        f"Нажмите «Оплатить» — откроется CryptoBot.\n"
        f"После оплаты баланс пополнится автоматически"
        f"(обычно в течение минуты).\n\n"
        f"<i>Счёт действителен 3 часа.</i>"
    )


# ---------- Entry: replace TOPUP_STUB handler ----------


@router.callback_query(F.data == texts.CB_TOPUP)
async def show_topup_presets(callback: CallbackQuery, state: FSMContext) -> None:
    """User clicked ' Пополнить' from main menu."""
    settings = get_settings()
    await state.set_state(TopupStates.choosing_amount)
    try:
        await callback.message.edit_text(
            TOPUP_PROMPT.format(min_amount=settings.min_campaign_topup_rub),
            reply_markup=topup_kb.topup_presets_kb(),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


# ---------- Preset chosen ----------


@router.callback_query(F.data.startswith(topup_kb.CB_TOPUP_PRESET))
async def preset_chosen(
    callback: CallbackQuery,
    state: FSMContext,
    advertiser: Advertiser,
    session: AsyncSession,
    bot: Bot,
) -> None:
    """User clicked a preset amount button."""
    try:
        amount_str = callback.data.removeprefix(topup_kb.CB_TOPUP_PRESET)
        amount_rub = to_money(Decimal(amount_str))
    except (InvalidOperation, ValueError):
        await callback.answer("Неверная сумма", show_alert=True)
        return

    await _create_invoice_and_show(
        callback=callback,
        state=state,
        advertiser=advertiser,
        session=session,
        bot=bot,
        amount_rub=amount_rub,
    )


# ---------- Custom amount ----------


@router.callback_query(F.data == topup_kb.CB_TOPUP_CUSTOM)
async def custom_amount_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    settings = get_settings()
    await state.set_state(TopupStates.entering_custom)
    try:
        await callback.message.edit_text(
            CUSTOM_PROMPT.format(min_amount=settings.min_campaign_topup_rub),
            reply_markup=topup_kb.topup_cancel_kb(),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.message(TopupStates.entering_custom, F.text)
async def custom_amount_input(
    message: Message,
    state: FSMContext,
    advertiser: Advertiser,
    session: AsyncSession,
    bot: Bot,
) -> None:
    settings = get_settings()
    raw = (message.text or"").strip().replace(",",".").replace("","")

    try:
        amount = to_money(Decimal(raw))
    except (InvalidOperation, ValueError):
        await message.answer(custom_invalid("Это не число."), reply_markup=topup_kb.topup_cancel_kb())
        return

    if amount < settings.min_campaign_topup_rub:
        await message.answer(
            custom_invalid(
                f"Слишком маленькая сумма. Минимум — {settings.min_campaign_topup_rub:.0f} ₽."
            ),
            reply_markup=topup_kb.topup_cancel_kb(),
        )
        return

    if amount > Decimal("1000000"):
        await message.answer(
            custom_invalid("Слишком большая сумма. Максимум — 1 000 000 ₽."),
            reply_markup=topup_kb.topup_cancel_kb(),
        )
        return

    # Создаём счёт — но не редактируем сообщение (его нет в этом сценарии),
    # а отправляем новое
    await _create_invoice_from_message(
        message=message,
        state=state,
        advertiser=advertiser,
        session=session,
        bot=bot,
        amount_rub=amount,
    )


# ---------- Cancel ----------


@router.callback_query(F.data == topup_kb.CB_TOPUP_CANCEL)
async def cancel_topup(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    try:
        await callback.message.edit_text(
            texts.MENU_PROMPT,
            reply_markup=main_menu_inline_kb(),
        )
    except TelegramBadRequest:
        pass
    await callback.answer("Отменено")


# ---------- Shared invoice-creation helpers ----------


async def _create_invoice_and_show(
    *,
    callback: CallbackQuery,
    state: FSMContext,
    advertiser: Advertiser,
    session: AsyncSession,
    bot: Bot,
    amount_rub: Decimal,
) -> None:
    """Create CryptoBot invoice and edit the current message with the pay link."""
    await callback.answer("Создаю счёт…")

    me = await bot.get_me()
    svc = PaymentsService(session)
    try:
        invoice, _tx = await svc.create_topup_invoice(
            advertiser=advertiser,
            amount_rub=amount_rub,
            bot_username=me.username,
        )
    except DomainError as e:
        try:
            await callback.message.edit_text(
                f"{e.user_message}",
                reply_markup=topup_kb.topup_presets_kb(),
            )
        except TelegramBadRequest:
            pass
        return
    except CryptoBotError as e:
        log.error("topup_cryptobot_error", error=str(e), advertiser_id=advertiser.id)
        try:
            await callback.message.edit_text(
                "Не удалось создать счёт. Попробуйте позже.",
                reply_markup=main_menu_inline_kb(),
            )
        except TelegramBadRequest:
            pass
        return

    pay_url = invoice.bot_invoice_url or invoice.mini_app_invoice_url or invoice.pay_url or""
    await state.clear()
    try:
        await callback.message.edit_text(
            invoice_ready(amount_rub, invoice.invoice_id),
            reply_markup=topup_kb.topup_invoice_kb(pay_url) if pay_url else main_menu_inline_kb(),
        )
    except TelegramBadRequest:
        pass


async def _create_invoice_from_message(
    *,
    message: Message,
    state: FSMContext,
    advertiser: Advertiser,
    session: AsyncSession,
    bot: Bot,
    amount_rub: Decimal,
) -> None:
    """Same as above but for typed-input flow (sends a new message)."""
    me = await bot.get_me()
    svc = PaymentsService(session)
    try:
        invoice, _tx = await svc.create_topup_invoice(
            advertiser=advertiser,
            amount_rub=amount_rub,
            bot_username=me.username,
        )
    except DomainError as e:
        await message.answer(f"{e.user_message}", reply_markup=topup_kb.topup_presets_kb())
        return
    except CryptoBotError as e:
        log.error("topup_cryptobot_error", error=str(e), advertiser_id=advertiser.id)
        await message.answer(
            "Не удалось создать счёт. Попробуйте позже.",
            reply_markup=main_menu_inline_kb(),
        )
        return

    pay_url = invoice.bot_invoice_url or invoice.mini_app_invoice_url or invoice.pay_url or""
    await state.clear()
    await message.answer(
        invoice_ready(amount_rub, invoice.invoice_id),
        reply_markup=topup_kb.topup_invoice_kb(pay_url) if pay_url else main_menu_inline_kb(),
    )
