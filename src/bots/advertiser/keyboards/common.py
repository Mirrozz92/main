"""Common buttons (back, cancel, refresh)."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.bots.advertiser import texts


def back_inline_kb(callback_data: str ="menu") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=texts.BTN_BACK, callback_data=callback_data)],
        ]
    )


def refresh_inline_kb(callback_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=texts.BTN_REFRESH, callback_data=callback_data),
            ],
        ]
    )
