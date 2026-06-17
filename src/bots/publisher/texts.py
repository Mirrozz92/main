"""All user-facing texts and callback constants for publisher bot."""

from __future__ import annotations

from decimal import Decimal


# ====================== Welcome / Menu ======================

WELCOME = (
    "<b>FastSub Партнёры</b>\n\n"
    "Зарабатывайте, выдавая своим пользователям задания на подписки.\n\n"
    "Чтобы начать — добавьте свой Telegram-бот в разделе"
    "<b>« Продать трафик»</b> и подключите наш API."
)

MENU_PROMPT ="<b>Главное меню</b>"


# ====================== Sell Traffic / Bots ======================

def sell_traffic_header(bots_count: int) -> str:
    if bots_count == 0:
        return (
            "<b>Продать трафик</b>\n\n"
            "У вас пока нет подключённых ботов.\n\n"
            "Нажмите <b>« Добавить бота»</b>, чтобы начать."
        )
    return (
        f"<b>Продать трафик</b>\n\n"
        f"У вас <b>{bots_count}</b> подключённых ботов."
        f"Выберите бот для управления:"
    )


def bot_card_view(
    *,
    name: str,
    username: str | None,
    is_active: bool,
    is_moderated: bool,
) -> str:
    import html as _html
    title = f"<b>{_html.escape(name)}</b>"
    if username:
        title += f" (@{_html.escape(username)})"

    status = "✅ Допущено" if is_moderated else "⏳ На модерации"
    active_line = "\n⚠️ Бот остановлен" if not is_active else ""

    return f"{title}\nСтатус: {status}{active_line}"


def _format_ttl(seconds: int) -> str:
    if seconds < 3600:
        return f"{seconds // 60} мин"
    if seconds < 86400:
        hours = seconds // 3600
        return f"{hours} ч"
    days = seconds // 86400
    return f"{days} д"


# ====================== Add Bot Flow ======================

ADD_BOT_INTRO = (
    "<b>Добавление бота</b>\n\n"
    "Есть два варианта:\n\n"
    "1⃣ <b>С токеном</b> (рекомендуется) — пришлите API-токен вашего"
    "Telegram-бота. Получить его можно в @BotFather (команда"
    "<code>/mybots</code> выбрать бота <b>API Token</b>).\n\n"
    "Мы используем токен только для проверки личности бота. Он хранится"
    "в зашифрованном виде.\n\n"
    "2⃣ <b>Без токена</b> — просто укажите название. Подойдёт, если"
    "вы не хотите делиться токеном. Но статистика и автоматика будут"
    "ограничены.\n\n"
    "Выберите способ:"
)

ADD_BOT_PROMPT_TOKEN = (
    "<b>Введите токен бота</b>\n\n"
    "Пришлите токен в формате:\n"
    "<code>123456789:AAH...xyz</code>\n\n"
    "<i>Токен будет зашифрован в нашей базе. Plaintext"
    "не сохраняется в логах.</i>"
)

ADD_BOT_PROMPT_NAME = (
    "<b>Введите название бота</b>\n\n"
    "Это имя нужно только вам, чтобы различать ботов в списке.\n\n"
    "<i>От 2 до 128 символов.</i>"
)


def add_bot_success(name: str, username: str | None) -> str:
    username_part = f"\n<b>Username:</b> @{username}"if username else""
    return (
        f"<b>Бот добавлен!</b>\n\n"
        f"<b>Имя:</b> {name}{username_part}\n\n"
        f"Перейдите в раздел <b> Интеграция</b>, чтобы получить API-ключ."
    )


# ====================== Bot Settings ======================

ALL_THEMES: tuple[str, ...] = (
    "crypto", "gaming", "sport", "news", "finance", "entertainment", "education", "other",
)

THEME_LABELS: dict[str, str] = {
    "crypto": "Крипто",
    "gaming": "Игры",
    "sport": "Спорт",
    "news": "Новости",
    "finance": "Финансы",
    "entertainment": "Развлечения",
    "education": "Образование",
    "other": "Другое",
}


def settings_view(
    sponsors_count: int,
    list_ttl_seconds: int,
    show_quiz: bool,
    get_links: bool,
    excluded_themes: list[str],
) -> str:
    quiz_line = "Да" if show_quiz else "Нет"
    links_line = "Да" if get_links else "Нет"
    if excluded_themes:
        themes_line = ", ".join(THEME_LABELS.get(t, t) for t in excluded_themes)
    else:
        themes_line = "не выбраны (показываем все)"
    return (
        "<b>Настройки бота</b>\n\n"
        f"<b>Спонсоров за запрос:</b> {sponsors_count}\n"
        f"<i>Сколько каналов мы выдаём одному юзеру за раз (1–10).</i>\n\n"
        f"<b>Время сброса списка:</b> {_format_ttl(list_ttl_seconds)}\n"
        f"<i>Через сколько обновляется список спонсоров (5 мин – 7 дней).</i>\n\n"
        f"<b>Показывать анкету:</b> {quiz_line}\n"
        f"<i>Опрос для таргетинга интересов пользователя.</i>\n\n"
        f"<b>Отдавать ссылки в API:</b> {links_line}\n"
        f"<i>False — сами отправляем блок ОП; True — возвращаем ссылки.</i>\n\n"
        f"<b>Исключённые тематики:</b> {themes_line}"
    )


THEMES_MENU_PROMPT = (
    "<b>Исключить тематики рекламы</b>\n\n"
    "Отметьте тематики, которые <b>не</b> нужно показывать в вашем боте.\n"
    "Нажмите «Сохранить» когда закончите."
)


SET_SPONSORS_PROMPT = (
    "<b>Количество спонсоров</b>\n\n"
    "Выберите, сколько спонсоров выдавать одному пользователю за один запрос."
    "Слишком много — отпугнёт юзера, слишком мало — снизит заработок."
)

SET_TTL_PROMPT = (
    "<b>Время сброса списка</b>\n\n"
    "Через какое время список спонсоров обновляется."
)

TTL_CUSTOM_PROMPT = (
    "<b>Своё значение</b>\n\n"
    "Введите время в минутах (от 5 до 10080):\n"
    "Например: <code>30</code> (30 минут), <code>120</code> (2 часа),"
    "<code>1440</code> (1 день)."
)

SPONSORS_CUSTOM_PROMPT = (
    "<b>Своё значение</b>\n\n"
    "Введите число от 1 до 10:"
)


# ====================== Integration ======================

def integration_view(
    *,
    bot_name: str,
    token_prefix: str | None,
    requests_count: int,
    last_used_at: str | None,
) -> str:
    if token_prefix:
        token_line = (
            f"<b>Текущий API-ключ:</b> <code>{token_prefix}...</code>\n"
            f"<b>Запросов:</b> {requests_count}\n"
        )
        if last_used_at:
            token_line += f"<b>Последнее использование:</b> {last_used_at}\n"
    else:
        token_line ="<b>API-ключ:</b> <i>не создан</i> — нажмите «Перевыпустить» чтобы получить.\n"

    return (
        f"<b>Интеграция</b> — {bot_name}\n\n"
        f"{token_line}\n"
        "<b>База API:</b>\n"
        "<code>https://fastsub.95-85-251-42.sslip.io/api/v1</code>\n\n"
        "<b>Аутентификация:</b>\n"
        "<code>Authorization: Bearer fsp_live_...</code>\n\n"
        "<b>Документация:</b>\n"
        "<code>https://fastsub.95-85-251-42.sslip.io/docs</code>"
    )


def token_revealed(plaintext: str) -> str:
    return (
        "<b>Ваш новый API-ключ</b>\n\n"
        f"<code>{plaintext}</code>\n\n"
        "<b>Сохраните ключ сейчас!</b> Plaintext-значение показывается"
        "только один раз. После закрытия этого сообщения вы увидите"
        "только префикс.\n\n"
        f"<b>Использование:</b>\n"
        f"<code>Authorization: Bearer {plaintext}</code>"
    )


REGENERATE_CONFIRM = (
    "<b>Подтверждение регенерации</b>\n\n"
    "Старый API-ключ <b>немедленно</b> перестанет работать. Все запросы"
    "с ним вернут <code>401 Unauthorized</code>.\n\n"
    "Это действие <b>необратимо</b>. Продолжить?"
)


# ====================== Publisher Stats ======================

def publisher_stats_view(
    *,
    issued_1d: int,
    issued_7d: int,
    issued_30d: int,
    verified_1d: int,
    verified_7d: int,
    verified_30d: int,
    earned_1d: Decimal,
    earned_7d: Decimal,
    earned_30d: Decimal,
    retention_rate: Decimal,
    verified_subs_in_window: int,
    hold_hours: int,
    commission: Decimal,
    cold_start: bool,
) -> str:
    commission_pct = (commission * 100).quantize(Decimal("0.1"))

    def _row(issued: int, verified: int, earned: Decimal) -> str:
        return (
            f"  Выдано: <b>{issued}</b>  "
            f"Подтверждено: <b>{verified}</b>  "
            f"Заработано: <b>{earned:.2f} ₽</b>"
        )

    if cold_start:
        retention_block = (
            f"<b>Удержание:</b> идёт накопление"
            f" ({verified_subs_in_window} / 100 верификаций)\n"
            f"<b>Комиссия платформы:</b> {commission_pct}% (базовая)"
        )
    else:
        retention_block = (
            f"<b>Удержание:</b> {retention_rate:.1f}% (30 дн.)\n"
            f"<b>Комиссия платформы:</b> {commission_pct}%"
        )

    return (
        "<b>Статистика</b>\n\n"
        f"<b>За 1 день:</b>\n{_row(issued_1d, verified_1d, earned_1d)}\n\n"
        f"<b>За 7 дней:</b>\n{_row(issued_7d, verified_7d, earned_7d)}\n\n"
        f"<b>За 30 дней:</b>\n{_row(issued_30d, verified_30d, earned_30d)}\n\n"
        f"<b>Hold-период:</b> {hold_hours} ч\n"
        f"{retention_block}"
    )


# ====================== Bot Stats ======================

def bot_stats_view(
    *,
    name: str,
    total_requests: int,
    total_issued: int,
    total_verified: int,
    total_earned_rub: Decimal,
) -> str:
    conv = (total_verified / total_issued * 100) if total_issued > 0 else 0
    return (
        f"<b>Статистика</b> — {name}\n\n"
        f"<b>Запросов через API:</b> {total_requests}\n"
        f"<b>Заданий выдано:</b> {total_issued}\n"
        f"<b>Подписок подтверждено:</b> {total_verified}\n"
        f"<b>Конверсия:</b> {conv:.1f}%\n\n"
        f"<b>Заработано:</b> {total_earned_rub:.2f} ₽"
    )


# ====================== Profile ======================

def profile_view(
    *,
    full_name: str,
    tg_username: str | None,
    registered_at: str,
    total_bots: int,
    active_bots: int,
    total_subscriptions: int,
    total_unsubscriptions: int,
    retention_rate: Decimal,
    verified_subs_in_window: int,
    rating: Decimal,
    verified_subs_total: int,
    total_earned: Decimal,
) -> str:
    from src.domain.publishers.commission import (
        commission_for,
        is_cold_start,
        MIN_VERIFIED_FOR_SCALE,
    )
    from src.domain.publishers.rating import is_rating_cold_start

    username_line = f"\n<b>Юзернейм:</b> @{tg_username}" if tg_username else ""

    commission = commission_for(retention_rate, verified_subs_in_window)
    commission_pct = (commission * 100).quantize(Decimal("0.1"))

    if is_cold_start(verified_subs_in_window):
        remaining = MIN_VERIFIED_FOR_SCALE - verified_subs_in_window
        retention_block = (
            f"<b>Удержание:</b> идёт накопление данных\n"
            f"Подтверждённых подписок: {verified_subs_in_window} из "
            f"{MIN_VERIFIED_FOR_SCALE}\n"
            f"Ещё {remaining} до начала расчёта удержания\n"
            f"Текущая комиссия: {commission_pct}% (базовая)"
        )
    else:
        retention_block = (
            f"<b>Удержание:</b> {retention_rate:.1f}%\n"
            f"Подтверждённых подписок за 30 дней: {verified_subs_in_window}\n"
            f"Текущая комиссия: {commission_pct}%"
        )

    if is_rating_cold_start(verified_subs_total):
        rating_line = f"<b>Рейтинг:</b> {rating:.1f} / 10 (стартовый)"
    else:
        rating_line = f"<b>Рейтинг:</b> {rating:.1f} / 10"

    return (
        f"<b>Профиль</b>\n\n"
        f"<b>Имя:</b> {full_name}{username_line}\n"
        f"<b>Регистрация:</b> {registered_at}\n\n"
        f"{rating_line}\n\n"
        f"<b>Боты:</b>\n"
        f"Всего: {total_bots}\n"
        f"Активных: {active_bots}\n\n"
        f"<b>Статистика:</b>\n"
        f"Подписок выдано: {total_subscriptions}\n"
        f"Отписалось: {total_unsubscriptions}\n"
        f"{retention_block}\n\n"
        f"<b>Всего заработано:</b> {total_earned:.2f} ₽"
    )


# ====================== Balance ======================

def balance_view(
    *,
    balance: Decimal,
    hold: Decimal,
    total_earned: Decimal,
) -> str:
    return (
        f"<b>Баланс</b>\n\n"
        f"<b>Всего заработано:</b> {total_earned:.2f} ₽\n"
        f"<b>Текущий баланс:</b> {(balance + hold):.2f} ₽\n"
        f"<b>Доступно для вывода:</b> <b>{balance:.2f} ₽</b>\n"
        f"<b>На холде:</b> {hold:.2f} ₽\n\n"
        f"<i>На холде — деньги за подписки, ожидающие подтверждения"
        f"(обычно 4–12 часов). После подтверждения они переходят"
        f"в доступный баланс.</i>"
    )


WITHDRAW_PROMPT = (
    "<b>Заявка на вывод</b>\n\n"
    "Введите сумму для вывода в рублях.\n\n"
    "<i>Минимум: 100 ₽.</i>"
)

WITHDRAW_SUCCESS = (
    "<b>Заявка создана</b>\n\n"
    "Мы обработаем её вручную. Уведомим, как только деньги"
    "будут отправлены (обычно в течение 24 часов).\n\n"
    "По вопросам выплат: @nklabs"
)


def transactions_list_header(count: int, page: int, total_pages: int) -> str:
    return (
        f"<b>История транзакций</b> (всего: {count})\n\n"
        f"Страница {page + 1} из {total_pages}"
    )


# ====================== Help ======================

HELP_TEXT = (
    "<b>Справка</b>\n\n"
    "<b>FastSub для партнёров</b> — платформа для монетизации трафика.\n\n"
    "<b>Документация API:</b>\n"
    "<code>https://fastsub.95-85-251-42.sslip.io/docs</code>\n\n"
    "<b>Базовый URL:</b>\n"
    "<code>https://fastsub.95-85-251-42.sslip.io/api/v1</code>\n\n"
    "<b>Аутентификация:</b>\n"
    "<code>Authorization: Bearer fsp_live_...</code>\n\n"
    "<b>Комиссия зависит от удержания:</b>\n"
    "Удержание 85%+ — комиссия 20%\n"
    "Удержание 70–85% — 22.5%\n"
    "Удержание 50–70% — 25%\n"
    "Удержание 20–50% — 30%\n"
    "Удержание ниже 20% — 35%\n"
    "Шкала действует после 100 подтверждённых подписок,"
    "до этого базовая комиссия 25%.\n\n"
    "<b>Минимальный вывод:</b> 100 ₽.\n\n"
    "<b>Поддержка:</b> @nklabs"
)


# ====================== Buttons ======================

BTN_SELL_TRAFFIC ="Продать трафик"
BTN_PROFILE ="Профиль"
BTN_BALANCE ="Баланс"
BTN_STATS ="Статистика"
BTN_HELP ="Помощь"
BTN_BACK ="« Назад"

BTN_ADD_BOT ="Добавить бота"
BTN_BOT_WITH_TOKEN ="С токеном"
BTN_BOT_WITHOUT_TOKEN ="Без токена"

BTN_SETTINGS ="Настройки"
BTN_INTEGRATION ="Интеграция"
BTN_BOT_STATS ="Статистика"

BTN_REGENERATE ="Перевыпустить ключ"

BTN_WITHDRAW ="Вывести"
BTN_HISTORY ="История"

BTN_CONFIRM ="Да, продолжить"
BTN_CANCEL ="Отмена"


# ====================== Callback constants ======================

CB_MENU ="pub:menu"
CB_SELL_TRAFFIC ="pub:sell"
CB_PROFILE ="pub:profile"
CB_BALANCE ="pub:balance"
CB_STATS ="pub:stats"
CB_HELP ="pub:help"

CB_ADD_BOT ="pub:add_bot"
CB_ADD_WITH_TOKEN ="pub:add_with_token"
CB_ADD_WITHOUT_TOKEN ="pub:add_without_token"

CB_BOT_VIEW ="pub:b:"
CB_BOT_SETTINGS ="pub:bs:"
CB_BOT_INTEGRATION ="pub:bi:"
CB_BOT_STATS ="pub:bx:"
CB_BOT_TOGGLE ="pub:bt:"

CB_SET_SPONSORS ="pub:sponsors:"
CB_SET_TTL ="pub:ttl:"
CB_SPONSORS_VALUE ="pub:sv:"
CB_TTL_VALUE ="pub:tv:"
CB_SPONSORS_CUSTOM ="pub:scu:"
CB_TTL_CUSTOM ="pub:tcu:"

CB_TOGGLE_QUIZ ="pub:tq:"
CB_TOGGLE_LINKS ="pub:tl:"
CB_THEMES_MENU ="pub:thm:"
CB_THEME_TOGGLE ="pub:tht:"
CB_THEMES_SAVE ="pub:ths:"

CB_TOKEN_REGEN_PROMPT ="pub:tr:"
CB_TOKEN_REGEN_CONFIRM ="pub:trc:"

CB_WITHDRAW ="pub:withdraw"
CB_HISTORY ="pub:history"
CB_HISTORY_PAGE ="pub:history_p:"

CB_NOOP ="noop"


SPONSORS_PRESETS: tuple[int, ...] = (1, 2, 3, 5, 10)
TTL_PRESETS_SECONDS: tuple[tuple[int, str], ...] = (
    (300,"5 мин"),
    (1800,"30 мин"),
    (3600,"1 ч"),
    (10800,"3 ч"),
    (43200,"12 ч"),
    (86400,"1 д"),
    (604800,"7 д"),
)
