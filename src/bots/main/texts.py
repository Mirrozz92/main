"""Top-level texts for the combined advertiser+publisher bot."""

from __future__ import annotations


WELCOME_NEW = (
    "<b>Добро пожаловать в FastSub!</b>\n\n"
    "Платформа монетизации трафика в Telegram.\n\n"
    "📢 <b>Реклама</b> — размещайте рекламу в ботах партнёров\n"
    "🤖 <b>Монетизация</b> — зарабатывайте на своих пользователях\n\n"
    "Выберите раздел:"
)

WELCOME_BACK = "<b>FastSub</b>\n\nВыберите раздел:"

MAIN_MENU_PROMPT = "<b>FastSub</b>\n\nВыберите раздел:"

HELP_TEXT = (
    "<b>Справка FastSub</b>\n\n"
    "📢 <b>Реклама:</b>\n"
    "Создавайте кампании, пополняйте баланс через CryptoBot.\n"
    "Цена за подписчика — от 0.50 до 25 ₽.\n\n"
    "🤖 <b>Монетизация:</b>\n"
    "Подключите свой бот, выдавайте задания юзерам через API.\n"
    "Комиссия 20–35% (зависит от удержания).\n"
    "Минимальный вывод: 100 ₽.\n\n"
    "<b>Поддержка:</b> @nklabs"
)

# Callbacks
CB_MAIN_MENU = "main:menu"
CB_MAIN_HELP = "main:help"

# Button labels
BTN_CAMPAIGNS = "📢 Кампании"
BTN_TOPUP = "💰 Пополнить"
BTN_SELL_TRAFFIC = "🤖 Продать трафик"
BTN_EARNINGS = "💳 Заработок"
BTN_PROFILE = "👤 Профиль"
BTN_HELP = "❓ Помощь"
BTN_BACK_MAIN = "« Главное меню"
