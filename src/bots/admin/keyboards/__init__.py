"""Keyboards for admin bot."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


# Callback namespaces — campaigns moderation
CB_MAIN_MENU        = "adm:menu"
CB_PENDING_LIST     = "adm:pending"
CB_PENDING_PAGE     = "adm:pending_page:"
CB_VIEW_CAMPAIGN    = "adm:view:"
CB_APPROVE          = "adm:approve:"
CB_REJECT_PROMPT    = "adm:reject:"
CB_REJECT_CANCEL    = "adm:reject_cancel"

# Callback namespaces — bot moderation
CB_BOT_MOD_LIST        = "adm:bots"
CB_BOT_MOD_PAGE        = "adm:bots_page:"
CB_BOT_MOD_VIEW        = "adm:bot_view:"
CB_BOT_MOD_APPROVE     = "adm:bot_approve:"
CB_BOT_MOD_NOTE_PROMPT = "adm:bot_note:"
CB_BOT_MOD_NOTE_SKIP   = "adm:bot_note_skip:"
CB_BOT_SET_NICHE_MENU  = "adm:bot_niche:"
CB_BOT_NICHE_SET       = "adm:bot_niche_set:"
CB_BOT_SET_AGE_MENU    = "adm:bot_age:"
CB_BOT_AGE_SET         = "adm:bot_age_set:"
CB_BOT_SET_GENDER_MENU = "adm:bot_gender:"
CB_BOT_GENDER_SET      = "adm:bot_gender_set:"

# Callback namespaces — withdrawals
CB_WITHDRAW_LIST         = "adm:wd"
CB_WITHDRAW_PAGE         = "adm:wd_page:"
CB_WITHDRAW_VIEW         = "adm:wd_view:"
CB_WITHDRAW_APPROVE      = "adm:wd_approve:"
CB_WITHDRAW_APPROVE_AUTO = "adm:wd_auto:"
CB_WITHDRAW_REJECT_PROMPT = "adm:wd_reject:"
CB_WITHDRAW_REJECT_CANCEL = "adm:wd_reject_cancel"


def main_menu_kb(
    pending_count: int,
    withdraw_count: int = 0,
    bots_count: int = 0,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    mod_label = f"На модерации ({pending_count})" if pending_count else "На модерации"
    rows.append([InlineKeyboardButton(text=mod_label, callback_data=CB_PENDING_LIST)])

    bots_label = f"Боты на проверке ({bots_count})" if bots_count else "Боты на проверке"
    rows.append([InlineKeyboardButton(text=bots_label, callback_data=CB_BOT_MOD_LIST)])

    wd_label = f"Заявки на вывод ({withdraw_count})" if withdraw_count else "Заявки на вывод"
    rows.append([InlineKeyboardButton(text=wd_label, callback_data=CB_WITHDRAW_LIST)])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def pending_list_kb(
    items: list[tuple[int, str, str]],
    *,
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for cid, label, _budget in items:
        rows.append([
            InlineKeyboardButton(
                text=f"#{cid} • {label}",
                callback_data=f"{CB_VIEW_CAMPAIGN}{cid}",
            )
        ])

    if total_pages > 1:
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(InlineKeyboardButton(
                text="« Назад", callback_data=f"{CB_PENDING_PAGE}{page - 1}",
            ))
        nav.append(InlineKeyboardButton(
            text=f"{page + 1}/{total_pages}", callback_data="noop",
        ))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(
                text="Вперёд »", callback_data=f"{CB_PENDING_PAGE}{page + 1}",
            ))
        rows.append(nav)

    rows.append([
        InlineKeyboardButton(text="Обновить", callback_data=CB_PENDING_LIST),
        InlineKeyboardButton(text="« В меню", callback_data=CB_MAIN_MENU),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def campaign_actions_kb(campaign_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Одобрить", callback_data=f"{CB_APPROVE}{campaign_id}"),
            InlineKeyboardButton(text="Отклонить", callback_data=f"{CB_REJECT_PROMPT}{campaign_id}"),
        ],
        [InlineKeyboardButton(text="« К списку", callback_data=CB_PENDING_LIST)],
    ])


def reject_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Отмена", callback_data=CB_REJECT_CANCEL)],
    ])


# ----------------------------------------------------------------
# Bot moderation keyboards
# ----------------------------------------------------------------

def bot_mod_empty_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Обновить", callback_data=CB_BOT_MOD_LIST)],
        [InlineKeyboardButton(text="« В меню", callback_data=CB_MAIN_MENU)],
    ])


def bot_mod_list_kb(
    items: list[tuple[int, str]],
    *,
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for bot_id, label in items:
        rows.append([
            InlineKeyboardButton(
                text=f"#{bot_id} • {label}",
                callback_data=f"{CB_BOT_MOD_VIEW}{bot_id}",
            )
        ])

    if total_pages > 1:
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(InlineKeyboardButton(
                text="« Назад", callback_data=f"{CB_BOT_MOD_PAGE}{page - 1}",
            ))
        nav.append(InlineKeyboardButton(
            text=f"{page + 1}/{total_pages}", callback_data="noop",
        ))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(
                text="Вперёд »", callback_data=f"{CB_BOT_MOD_PAGE}{page + 1}",
            ))
        rows.append(nav)

    rows.append([
        InlineKeyboardButton(text="Обновить", callback_data=CB_BOT_MOD_LIST),
        InlineKeyboardButton(text="« В меню", callback_data=CB_MAIN_MENU),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def bot_mod_card_kb(bot_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🏷 Тематика", callback_data=f"{CB_BOT_SET_NICHE_MENU}{bot_id}"),
            InlineKeyboardButton(text="👥 Возраст", callback_data=f"{CB_BOT_SET_AGE_MENU}{bot_id}"),
            InlineKeyboardButton(text="⚧ Гендер", callback_data=f"{CB_BOT_SET_GENDER_MENU}{bot_id}"),
        ],
        [
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"{CB_BOT_MOD_APPROVE}{bot_id}"),
            InlineKeyboardButton(text="📝 Заметка + одобрить", callback_data=f"{CB_BOT_MOD_NOTE_PROMPT}{bot_id}"),
        ],
        [InlineKeyboardButton(text="« К списку", callback_data=CB_BOT_MOD_LIST)],
    ])


def bot_mod_note_kb(bot_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пропустить", callback_data=f"{CB_BOT_MOD_NOTE_SKIP}{bot_id}")],
        [InlineKeyboardButton(text="« К боту", callback_data=f"{CB_BOT_MOD_VIEW}{bot_id}")],
    ])


def bot_mod_after_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Следующий бот", callback_data=CB_BOT_MOD_LIST)],
        [InlineKeyboardButton(text="« В меню", callback_data=CB_MAIN_MENU)],
    ])


def niche_select_kb(bot_id: int, *, current: str | None) -> InlineKeyboardMarkup:
    from src.bots.admin.handlers.bot_moderation import NICHE_LABELS
    rows: list[list[InlineKeyboardButton]] = []
    for key, label in NICHE_LABELS.items():
        mark = "✓ " if key == current else ""
        rows.append([InlineKeyboardButton(
            text=f"{mark}{label}",
            callback_data=f"{CB_BOT_NICHE_SET}{bot_id}:{key}",
        )])
    rows.append([InlineKeyboardButton(text="« Назад", callback_data=f"{CB_BOT_MOD_VIEW}{bot_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def age_select_kb(bot_id: int, *, current: str | None) -> InlineKeyboardMarkup:
    from src.bots.admin.handlers.bot_moderation import AGE_LABELS
    rows: list[list[InlineKeyboardButton]] = []
    for key, label in AGE_LABELS.items():
        mark = "✓ " if key == current else ""
        rows.append([InlineKeyboardButton(
            text=f"{mark}{label}",
            callback_data=f"{CB_BOT_AGE_SET}{bot_id}:{key}",
        )])
    rows.append([InlineKeyboardButton(text="« Назад", callback_data=f"{CB_BOT_MOD_VIEW}{bot_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def gender_select_kb(bot_id: int, *, current: str | None) -> InlineKeyboardMarkup:
    from src.bots.admin.handlers.bot_moderation import GENDER_LABELS
    rows: list[list[InlineKeyboardButton]] = []
    for key, label in GENDER_LABELS.items():
        mark = "✓ " if key == current else ""
        rows.append([InlineKeyboardButton(
            text=f"{mark}{label}",
            callback_data=f"{CB_BOT_GENDER_SET}{bot_id}:{key}",
        )])
    rows.append([InlineKeyboardButton(text="« Назад", callback_data=f"{CB_BOT_MOD_VIEW}{bot_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ----------------------------------------------------------------
# Withdrawal keyboards
# ----------------------------------------------------------------

def withdraw_list_kb(
    items: list[tuple[int, str, str]],
    *,
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for tx_id, label, amount in items:
        rows.append([
            InlineKeyboardButton(
                text=f"#{tx_id} • {label} • {amount}₽",
                callback_data=f"{CB_WITHDRAW_VIEW}{tx_id}",
            )
        ])

    if total_pages > 1:
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(InlineKeyboardButton(
                text="« Назад", callback_data=f"{CB_WITHDRAW_PAGE}{page - 1}",
            ))
        nav.append(InlineKeyboardButton(
            text=f"{page + 1}/{total_pages}", callback_data="noop",
        ))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(
                text="Вперёд »", callback_data=f"{CB_WITHDRAW_PAGE}{page + 1}",
            ))
        rows.append(nav)

    rows.append([
        InlineKeyboardButton(text="Обновить", callback_data=CB_WITHDRAW_LIST),
        InlineKeyboardButton(text="« В меню", callback_data=CB_MAIN_MENU),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def withdraw_card_kb(tx_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="Выплатить автоматически",
                callback_data=f"{CB_WITHDRAW_APPROVE_AUTO}{tx_id}",
            ),
        ],
        [
            InlineKeyboardButton(
                text="Я отправил вручную",
                callback_data=f"{CB_WITHDRAW_APPROVE}{tx_id}",
            ),
            InlineKeyboardButton(
                text="Отклонить",
                callback_data=f"{CB_WITHDRAW_REJECT_PROMPT}{tx_id}",
            ),
        ],
        [InlineKeyboardButton(text="« К списку", callback_data=CB_WITHDRAW_LIST)],
    ])


def withdraw_reject_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Отмена", callback_data=CB_WITHDRAW_REJECT_CANCEL)],
    ])
