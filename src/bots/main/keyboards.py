"""Keyboards for the combined main bot top-level menu."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.bots.advertiser import texts as adv_texts
from src.bots.main import texts
from src.bots.publisher import texts as pub_texts


def main_menu_kb() -> InlineKeyboardMarkup:
    """Combined top-level menu: advertiser section + publisher section."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=texts.BTN_CAMPAIGNS, callback_data=adv_texts.CB_CAMPAIGNS),
                InlineKeyboardButton(text=texts.BTN_TOPUP, callback_data=adv_texts.CB_TOPUP),
            ],
            [
                InlineKeyboardButton(text=texts.BTN_SELL_TRAFFIC, callback_data=pub_texts.CB_SELL_TRAFFIC),
                InlineKeyboardButton(text=texts.BTN_EARNINGS, callback_data=pub_texts.CB_BALANCE),
            ],
            [
                InlineKeyboardButton(text=texts.BTN_PROFILE, callback_data=pub_texts.CB_PROFILE),
                InlineKeyboardButton(text=texts.BTN_HELP, callback_data=texts.CB_MAIN_HELP),
            ],
        ]
    )


def back_to_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=texts.BTN_BACK_MAIN, callback_data=texts.CB_MAIN_MENU)],
        ]
    )
