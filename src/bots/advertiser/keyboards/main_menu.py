"""Main menu inline keyboard."""

from __future__ import annotations
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from src.bots.advertiser import texts


def main_menu_inline_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=texts.btn_balance(), callback_data=texts.CB_BALANCE),
            InlineKeyboardButton(text=texts.btn_campaigns(), callback_data=texts.CB_CAMPAIGNS),
        ],
        [
            InlineKeyboardButton(text=texts.btn_topup(), callback_data=texts.CB_TOPUP),
            InlineKeyboardButton(text=texts.btn_help(), callback_data=texts.CB_HELP),
        ],
    ])


def back_to_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=texts.btn_back(), callback_data=texts.CB_MENU)],
    ])
