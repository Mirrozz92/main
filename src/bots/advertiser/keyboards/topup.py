"""Keyboards for top-up flow."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.bots.advertiser import texts


# Callback data namespace
CB_TOPUP_PRESET ="topup:preset:"# + amount
CB_TOPUP_CUSTOM ="topup:custom"
CB_TOPUP_CANCEL ="topup:cancel"
CB_TOPUP_INVOICE_OPENED ="topup:invoice_opened"# noop, just acknowledges click


PRESETS_RUB: tuple[int, ...] = (500, 1000, 2500, 5000, 10000)


def topup_presets_kb() -> InlineKeyboardMarkup:
    """Preset amounts + custom + cancel."""
    rows: list[list[InlineKeyboardButton]] = []

    # Two presets per row
    chunk: list[InlineKeyboardButton] = []
    for amount in PRESETS_RUB:
        chunk.append(
            InlineKeyboardButton(
                text=f"{amount} ₽",
                callback_data=f"{CB_TOPUP_PRESET}{amount}",
            )
        )
        if len(chunk) == 2:
            rows.append(chunk)
            chunk = []
    if chunk:
        rows.append(chunk)

    rows.append([
        InlineKeyboardButton(text="Своя сумма", callback_data=CB_TOPUP_CUSTOM),
    ])
    rows.append([
        InlineKeyboardButton(text=texts.btn_back(), callback_data=texts.CB_MENU),
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def topup_cancel_kb() -> InlineKeyboardMarkup:
    """Single cancel button (during custom-amount input)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Отмена", callback_data=CB_TOPUP_CANCEL)],
    ])


def topup_invoice_kb(invoice_url: str) -> InlineKeyboardMarkup:
    """Shown after invoice is created: link to pay + back to menu."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Оплатить", url=invoice_url)],
        [InlineKeyboardButton(text=texts.btn_back(), callback_data=texts.CB_MENU)],
    ])
