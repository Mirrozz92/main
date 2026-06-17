"""Keyboards for publisher bot — new bot-centric UX."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.bots.publisher import texts


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=texts.BTN_SELL_TRAFFIC, callback_data=texts.CB_SELL_TRAFFIC)],
        [
            InlineKeyboardButton(text=texts.BTN_PROFILE, callback_data=texts.CB_PROFILE),
            InlineKeyboardButton(text=texts.BTN_BALANCE, callback_data=texts.CB_BALANCE),
        ],
        [InlineKeyboardButton(text=texts.BTN_STATS, callback_data=texts.CB_STATS)],
        [InlineKeyboardButton(text=texts.BTN_HELP, callback_data=texts.CB_HELP)],
    ])


def back_to_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=texts.BTN_BACK, callback_data=texts.CB_MENU)],
    ])


def sell_traffic_kb(bots: list[tuple[int, str, bool]]) -> InlineKeyboardMarkup:
    """bots: list of (bot_id, name, is_active)."""
    rows: list[list[InlineKeyboardButton]] = []
    for bid, name, is_active in bots:
        emoji =""if is_active else""
        display = name if len(name) <= 30 else name[:27] +"…"
        rows.append([
            InlineKeyboardButton(
                text=f"{emoji} {display}",
                callback_data=f"{texts.CB_BOT_VIEW}{bid}",
            )
        ])
    rows.append([InlineKeyboardButton(text=texts.BTN_ADD_BOT, callback_data=texts.CB_ADD_BOT)])
    rows.append([InlineKeyboardButton(text=texts.BTN_BACK, callback_data=texts.CB_MENU)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def add_bot_choice_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=texts.BTN_BOT_WITH_TOKEN, callback_data=texts.CB_ADD_WITH_TOKEN)],
        [InlineKeyboardButton(text=texts.BTN_BOT_WITHOUT_TOKEN, callback_data=texts.CB_ADD_WITHOUT_TOKEN)],
        [InlineKeyboardButton(text=texts.BTN_CANCEL, callback_data=texts.CB_SELL_TRAFFIC)],
    ])


def add_bot_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=texts.BTN_CANCEL, callback_data=texts.CB_SELL_TRAFFIC)],
    ])


def bot_card_kb(bot_id: int, is_active: bool) -> InlineKeyboardMarkup:
    toggle_text = "⏹ Остановить" if is_active else "▶️ Запустить"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⚙️ Настройки", callback_data=f"{texts.CB_BOT_SETTINGS}{bot_id}"),
            InlineKeyboardButton(text="📊 Статистика", callback_data=f"{texts.CB_BOT_STATS}{bot_id}"),
        ],
        [
            InlineKeyboardButton(text="🖥 Интеграция (API)", callback_data=f"{texts.CB_BOT_INTEGRATION}{bot_id}"),
        ],
        [InlineKeyboardButton(text=toggle_text, callback_data=f"{texts.CB_BOT_TOGGLE}{bot_id}")],
        [InlineKeyboardButton(text="« Назад", callback_data=texts.CB_SELL_TRAFFIC)],
    ])


def settings_kb(bot_id: int, show_quiz: bool, get_links: bool) -> InlineKeyboardMarkup:
    quiz_mark = "✓" if show_quiz else "✗"
    links_mark = "✓" if get_links else "✗"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Кол-во спонсоров",
            callback_data=f"{texts.CB_SET_SPONSORS}{bot_id}",
        )],
        [InlineKeyboardButton(
            text="Время сброса",
            callback_data=f"{texts.CB_SET_TTL}{bot_id}",
        )],
        [InlineKeyboardButton(
            text=f"{quiz_mark} Показывать анкету",
            callback_data=f"{texts.CB_TOGGLE_QUIZ}{bot_id}",
        )],
        [InlineKeyboardButton(
            text=f"{links_mark} Отдавать ссылки в API",
            callback_data=f"{texts.CB_TOGGLE_LINKS}{bot_id}",
        )],
        [InlineKeyboardButton(
            text="Исключить тематики",
            callback_data=f"{texts.CB_THEMES_MENU}{bot_id}",
        )],
        [InlineKeyboardButton(text="« К боту", callback_data=f"{texts.CB_BOT_VIEW}{bot_id}")],
    ])


def excluded_themes_kb(bot_id: int, excluded: list[str]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    chunk: list[InlineKeyboardButton] = []
    for theme in texts.ALL_THEMES:
        mark = "✓ " if theme in excluded else ""
        label = texts.THEME_LABELS[theme]
        chunk.append(InlineKeyboardButton(
            text=f"{mark}{label}",
            callback_data=f"{texts.CB_THEME_TOGGLE}{bot_id}:{theme}",
        ))
        if len(chunk) == 2:
            rows.append(chunk)
            chunk = []
    if chunk:
        rows.append(chunk)
    rows.append([
        InlineKeyboardButton(
            text="Сохранить",
            callback_data=f"{texts.CB_THEMES_SAVE}{bot_id}",
        ),
        InlineKeyboardButton(
            text="Отмена",
            callback_data=f"{texts.CB_BOT_SETTINGS}{bot_id}",
        ),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def sponsors_presets_kb(bot_id: int, current: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    chunk: list[InlineKeyboardButton] = []
    for n in texts.SPONSORS_PRESETS:
        mark ="" if n == current else""
        chunk.append(InlineKeyboardButton(
            text=f"{mark}{n}",
            callback_data=f"{texts.CB_SPONSORS_VALUE}{bot_id}:{n}",
        ))
        if len(chunk) == 5:
            rows.append(chunk); chunk = []
    if chunk:
        rows.append(chunk)
    rows.append([InlineKeyboardButton(
        text="Своё значение",
        callback_data=f"{texts.CB_SPONSORS_CUSTOM}{bot_id}",
    )])
    rows.append([InlineKeyboardButton(
        text="« К настройкам",
        callback_data=f"{texts.CB_BOT_SETTINGS}{bot_id}",
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def ttl_presets_kb(bot_id: int, current: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    chunk: list[InlineKeyboardButton] = []
    for seconds, label in texts.TTL_PRESETS_SECONDS:
        mark ="" if seconds == current else""
        chunk.append(InlineKeyboardButton(
            text=f"{mark}{label}",
            callback_data=f"{texts.CB_TTL_VALUE}{bot_id}:{seconds}",
        ))
        if len(chunk) == 4:
            rows.append(chunk); chunk = []
    if chunk:
        rows.append(chunk)
    rows.append([InlineKeyboardButton(
        text="Своё значение",
        callback_data=f"{texts.CB_TTL_CUSTOM}{bot_id}",
    )])
    rows.append([InlineKeyboardButton(
        text="« К настройкам",
        callback_data=f"{texts.CB_BOT_SETTINGS}{bot_id}",
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def custom_value_cancel_kb(bot_id: int, callback_back: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=texts.BTN_CANCEL, callback_data=f"{callback_back}{bot_id}")],
    ])


def integration_kb(bot_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=texts.BTN_REGENERATE,
            callback_data=f"{texts.CB_TOKEN_REGEN_PROMPT}{bot_id}",
        )],
        [InlineKeyboardButton(text="« К боту", callback_data=f"{texts.CB_BOT_VIEW}{bot_id}")],
    ])


def regenerate_confirm_kb(bot_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=texts.BTN_CONFIRM,
                callback_data=f"{texts.CB_TOKEN_REGEN_CONFIRM}{bot_id}",
            ),
            InlineKeyboardButton(
                text=texts.BTN_CANCEL,
                callback_data=f"{texts.CB_BOT_INTEGRATION}{bot_id}",
            ),
        ],
    ])


def balance_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=texts.BTN_WITHDRAW, callback_data=texts.CB_WITHDRAW),
            InlineKeyboardButton(text=texts.BTN_HISTORY, callback_data=texts.CB_HISTORY),
        ],
        [InlineKeyboardButton(text=texts.BTN_BACK, callback_data=texts.CB_MENU)],
    ])


def history_kb(page: int, total_pages: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if total_pages > 1:
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(InlineKeyboardButton(
                text="« Назад", callback_data=f"{texts.CB_HISTORY_PAGE}{page - 1}",
            ))
        nav.append(InlineKeyboardButton(
            text=f"{page + 1}/{total_pages}", callback_data=texts.CB_NOOP,
        ))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(
                text="Вперёд »", callback_data=f"{texts.CB_HISTORY_PAGE}{page + 1}",
            ))
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="« К балансу", callback_data=texts.CB_BALANCE)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def withdraw_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=texts.BTN_CANCEL, callback_data=texts.CB_BALANCE)],
    ])
