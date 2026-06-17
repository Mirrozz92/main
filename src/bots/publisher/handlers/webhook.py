"""Webhook settings for a publisher bot."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bots.publisher.keyboards import (
    webhook_card_kb,
    webhook_url_cancel_kb,
    settings_kb,
)
from src.bots.publisher.states import WebhookStates
from src.core.db.models import Publisher
from src.core.logging import get_logger
from src.domain.publisher_bots import PublisherBotRepository
from src.domain.webhooks import (
    WebhookError,
    WebhookService,
    WebhookValidationError,
)

router = Router(name="publisher_webhook")
log = get_logger("publisher.webhook")


# All issue-related event types (used as default when user enables webhook)
ALL_EVENTS = [
    "resource.subscribed",
    "resource.verified",
    "resource.unsubscribed",
    "resource.expired",
    "resource.reverted",
]


# ---------- View webhook card ----------


@router.callback_query(F.data.startswith("pub:webhook:"))
async def show_webhook(
    callback: CallbackQuery,
    state: FSMContext,
    publisher: Publisher | None,
    session: AsyncSession,
) -> None:
    await state.clear()
    if publisher is None:
        await callback.answer()
        return

    try:
        bot_id = int(callback.data.split(":")[-1])
    except (ValueError, AttributeError):
        await callback.answer("Некорректный бот", show_alert=True)
        return

    # Verify ownership
    bot_repo = PublisherBotRepository(session)
    bot = await bot_repo.get_by_id(bot_id)
    if bot is None or bot.publisher_id != publisher.id:
        await callback.answer("Бот не найден", show_alert=True)
        return

    svc = WebhookService(session)
    endpoint = await svc.get_endpoint(bot.id)

    text = _format_webhook_card(bot, endpoint)
    try:
        await callback.message.edit_text(
            text,
            reply_markup=webhook_card_kb(
                bot.id,
                has_endpoint=endpoint is not None,
                is_active=bool(endpoint and endpoint.is_active),
            ),
            disable_web_page_preview=True,
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


# ---------- Enter URL ----------


@router.callback_query(F.data.startswith("pub:webhook_url:"))
async def prompt_url(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    try:
        bot_id = int(callback.data.split(":")[-1])
    except (ValueError, AttributeError):
        await callback.answer()
        return

    await state.set_state(WebhookStates.entering_url)
    await state.update_data(bot_id=bot_id)
    try:
        await callback.message.edit_text(
            "🔔 <b>Подключение webhook</b>\n\n"
            "Введите URL вашего сервера, на который FastSub будет отправлять"
            " события (подписки, отписки и т.д.).\n\n"
            "Требования:\n"
            "• HTTPS обязателен (HTTP допустим только для localhost)\n"
            "• Сервер должен отвечать 2xx за 10 секунд\n"
            "• Поддержка POST с JSON в теле\n\n"
            "Пример: <code>https://your-server.com/fastsub/webhook</code>",
            reply_markup=webhook_url_cancel_kb(bot_id),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.message(WebhookStates.entering_url, F.text)
async def receive_url(
    message: Message,
    state: FSMContext,
    publisher: Publisher | None,
    session: AsyncSession,
) -> None:
    if publisher is None:
        await state.clear()
        return

    data = await state.get_data()
    bot_id = data.get("bot_id")
    if not bot_id:
        await state.clear()
        return

    bot_repo = PublisherBotRepository(session)
    bot = await bot_repo.get_by_id(bot_id)
    if bot is None or bot.publisher_id != publisher.id:
        await state.clear()
        await message.answer("Бот не найден")
        return

    url = (message.text or "").strip()

    svc = WebhookService(session)
    try:
        endpoint, plaintext_secret = await svc.setup_endpoint(
            publisher_bot_id=bot.id,
            url=url,
            enabled_events=ALL_EVENTS,
        )
    except WebhookValidationError as e:
        await message.answer(
            f"⚠️ {e.user_message}\n\nПопробуйте ещё раз:",
            reply_markup=webhook_url_cancel_kb(bot_id),
        )
        return

    await state.clear()

    secret_block = ""
    if plaintext_secret:
        secret_block = (
            f"\n\n🔑 <b>Секрет (HMAC-ключ):</b>\n"
            f"<code>{plaintext_secret}</code>\n\n"
            f"<i>Сохраните его — больше показан не будет!</i>"
        )

    await message.answer(
        f"✅ Webhook подключён!\n\n"
        f"<b>URL:</b> <code>{endpoint.url}</code>"
        f"{secret_block}\n\n"
        f"Все события доставляются автоматически. "
        f"Нажмите 🧪 Тест чтобы проверить.",
        reply_markup=webhook_card_kb(
            bot.id, has_endpoint=True, is_active=True,
        ),
        disable_web_page_preview=True,
    )


# ---------- Test event ----------


@router.callback_query(F.data.startswith("pub:webhook_test:"))
async def send_test(
    callback: CallbackQuery,
    publisher: Publisher | None,
    session: AsyncSession,
) -> None:
    if publisher is None:
        await callback.answer()
        return
    try:
        bot_id = int(callback.data.split(":")[-1])
    except (ValueError, AttributeError):
        await callback.answer()
        return

    bot_repo = PublisherBotRepository(session)
    bot = await bot_repo.get_by_id(bot_id)
    if bot is None or bot.publisher_id != publisher.id:
        await callback.answer()
        return

    svc = WebhookService(session)
    endpoint = await svc.get_endpoint(bot.id)
    if endpoint is None:
        await callback.answer("Сначала настройте URL", show_alert=True)
        return

    await svc.emit_test_event(endpoint)
    await callback.answer(
        "Тестовое событие отправлено! Через ~1 минуту проверьте логи сервера.",
        show_alert=True,
    )


# ---------- Rotate secret ----------


@router.callback_query(F.data.startswith("pub:webhook_rotate:"))
async def rotate_secret(
    callback: CallbackQuery,
    publisher: Publisher | None,
    session: AsyncSession,
) -> None:
    if publisher is None:
        await callback.answer()
        return
    try:
        bot_id = int(callback.data.split(":")[-1])
    except (ValueError, AttributeError):
        await callback.answer()
        return

    bot_repo = PublisherBotRepository(session)
    bot = await bot_repo.get_by_id(bot_id)
    if bot is None or bot.publisher_id != publisher.id:
        await callback.answer()
        return

    svc = WebhookService(session)
    endpoint = await svc.get_endpoint(bot.id)
    if endpoint is None:
        await callback.answer("Webhook не настроен", show_alert=True)
        return

    new_endpoint, new_secret = await svc.setup_endpoint(
        publisher_bot_id=bot.id,
        url=endpoint.url,
        enabled_events=endpoint.enabled_events or ALL_EVENTS,
        rotate_secret=True,
    )

    try:
        await callback.message.edit_text(
            f"🔑 <b>Новый секрет</b>\n\n"
            f"<code>{new_secret}</code>\n\n"
            f"<i>Сохраните его — больше показан не будет!</i>\n\n"
            f"Старый секрет немедленно перестал работать.",
            reply_markup=webhook_card_kb(
                bot.id, has_endpoint=True, is_active=True,
            ),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


# ---------- Disable ----------


@router.callback_query(F.data.startswith("pub:webhook_disable:"))
async def disable(
    callback: CallbackQuery,
    publisher: Publisher | None,
    session: AsyncSession,
) -> None:
    if publisher is None:
        await callback.answer()
        return
    try:
        bot_id = int(callback.data.split(":")[-1])
    except (ValueError, AttributeError):
        await callback.answer()
        return

    bot_repo = PublisherBotRepository(session)
    bot = await bot_repo.get_by_id(bot_id)
    if bot is None or bot.publisher_id != publisher.id:
        await callback.answer()
        return

    svc = WebhookService(session)
    await svc.disable(bot.id)

    endpoint = await svc.get_endpoint(bot.id)
    try:
        await callback.message.edit_text(
            _format_webhook_card(bot, endpoint),
            reply_markup=webhook_card_kb(
                bot.id, has_endpoint=True, is_active=False,
            ),
            disable_web_page_preview=True,
        )
    except TelegramBadRequest:
        pass
    await callback.answer("Webhook отключён")


# ---------- Helpers ----------


def _format_webhook_card(bot, endpoint) -> str:
    text = f"🔔 <b>Webhook для бота «{bot.name}»</b>\n\n"

    if endpoint is None:
        text += (
            "Webhook не подключён.\n\n"
            "Подключите URL, чтобы получать события (подписки, отписки) "
            "на ваш сервер автоматически — без polling.\n\n"
            "📚 <b>Что вы получите:</b>\n"
            "• <code>resource.subscribed</code> — юзер подписался\n"
            "• <code>resource.verified</code> — подписка подтверждена (вам начислили)\n"
            "• <code>resource.unsubscribed</code> — юзер отписался\n"
            "• <code>resource.expired</code> — TTL вышел без подписки\n"
            "• <code>resource.reverted</code> — финальное состояние после отписки\n\n"
            "🔒 Каждый запрос подписан HMAC-SHA256 в заголовке "
            "<code>X-FastSub-Signature</code>."
        )
        return text

    status_emoji = "🟢" if endpoint.is_active else "🔴"
    status_text = "активен" if endpoint.is_active else "отключён"
    text += f"<b>Статус:</b> {status_emoji} {status_text}\n"
    text += f"<b>URL:</b> <code>{endpoint.url}</code>\n\n"

    if endpoint.last_success_at:
        text += f"✅ Последний успех: {endpoint.last_success_at.strftime('%Y-%m-%d %H:%M UTC')}\n"
    if endpoint.last_failure_at:
        text += f"⚠️ Последняя ошибка: {endpoint.last_failure_at.strftime('%Y-%m-%d %H:%M UTC')}\n"
    if endpoint.consecutive_failures > 0:
        text += f"❌ Подряд неудачных: {endpoint.consecutive_failures}\n"

    return text
