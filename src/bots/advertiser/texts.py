"""All user-facing texts of the advertiser bot."""

from __future__ import annotations
from decimal import Decimal

# Map: name Telegram custom_emoji_id. Fill in when you collect IDs.
CUSTOM_EMOJI: dict[str, str] = {}


def emoji(name: str, fallback: str) -> str:
    """Return custom-emoji HTML tag if configured, else fallback unicode."""
    eid = CUSTOM_EMOJI.get(name)
    if eid:
        return f'<tg-emoji emoji-id="{eid}">{fallback}</tg-emoji>'
    return fallback


def welcome_new() -> str:
    return (
        f"{emoji('wave', '')} <b>Добро пожаловать в FastSub!</b>\n\n"
        "Это платформа для покупки целевых подписчиков в Telegram-каналы,"
        "группы и боты. Мы доставим вам живых пользователей через сеть"
        "ботов-партнёров.\n\n"
        "<b>Как это работает:</b>\n"
        "1⃣ Пополните баланс\n"
        "2⃣ Создайте кампанию: укажите ресурсы и цену\n"
        "3⃣ Дождитесь модерации\n"
        "4⃣ Получайте подписчиков\n\n"
        "Выберите действие в меню ниже."
    )


def welcome_back(name: str) -> str:
    return (
        f"{emoji('wave', '')} <b>С возвращением, {name}!</b>\n\n"
        "Выберите действие в меню ниже."
    )


MENU_PROMPT ="<b>Главное меню</b>\n\nВыберите действие:"


def balance_view(*, balance: Decimal, reserved: Decimal, total_spent: Decimal) -> str:
    return (
        f"{emoji('money', '')} <b>Ваш баланс</b>\n\n"
        f"<b>Доступно:</b> {balance:.2f} ₽\n"
        f"<b>В резерве:</b> {reserved:.2f} ₽\n"
        f"<b>Всего потрачено:</b> {total_spent:.2f} ₽\n\n"
        "<i>«В резерве» — средства, забронированные под активные кампании"
        "и ожидающие подтверждения подписок.</i>"
    )


TOPUP_STUB = (
    "<b>Пополнение баланса</b>\n\n"
    "В следующем обновлении вы сможете пополнить баланс через CryptoBot"
    "(USDT / TON). А пока — раздел в разработке."
)

CAMPAIGNS_EMPTY = (
    "<b>Кампании</b>\n\n"
    "У вас пока нет ни одной кампании.\n\n"
    "В следующем обновлении вы сможете создать первую кампанию."
)

HELP_TEXT = (
    "<b>Справка</b>\n\n"
    "<b>FastSub</b> — платформа для покупки трафика в Telegram.\n\n"
    "<b>Тарифы:</b>\n"
    "• Цена за подписчика: от 0.50 ₽ до 25 ₽ (устанавливаете сами)\n"
    "• Минимальный бюджет кампании: 300 ₽\n"
    "• Минимальное пополнение: 500 ₽\n\n"
    "<b>Что такое hold:</b>\n"
    "После подписки нового юзера деньги «замораживаются» на несколько часов"
    "(зависит от качества трафика паблишера). Если за это время юзер не"
    "отписался — мы засчитываем подписку и платим паблишеру.\n\n"
    "<b>Что мы проверяем:</b>\n"
    "Перед добавлением ресурса в кампанию вы должны добавить нашего бота"
    "@fastsub_check1_bot админом в свой канал/группу с правом «Приглашать"
    "по ссылке». Без этого мы не сможем отслеживать подписки.\n\n"
    "По вопросам пишите админу: @nklabs"
)

ERROR_GENERIC ="Произошла ошибка. Попробуйте ещё раз через минуту."
ERROR_BANNED ="Ваш аккаунт заблокирован."


def btn_balance() -> str: return f"{emoji('money', '')} Баланс"
def btn_campaigns() -> str: return f"{emoji('speaker', '')} Мои кампании"
def btn_topup() -> str: return f"{emoji('card', '')} Пополнить"
def btn_help() -> str: return f"{emoji('question', '')} Помощь"
def btn_back() -> str: return f"{emoji('back', '«')} Назад"


CB_MENU ="menu"
CB_BALANCE ="menu:balance"
CB_CAMPAIGNS ="menu:campaigns"
CB_TOPUP ="menu:topup"
CB_HELP ="menu:help"
