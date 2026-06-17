"""TaskIQ background tasks for sending Telegram notifications.

All tasks are non-blocking: the calling HTTP handler / bot returns immediately
while the worker container actually sends the message.
"""

from __future__ import annotations

from decimal import Decimal

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from src.core.config import get_settings
from src.core.logging import get_logger
from src.workers.broker import broker

log = get_logger("worker.notifications")


def _advertiser_bot() -> Bot:
    settings = get_settings()
    return Bot(
        token=settings.advertiser_bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def _admin_bot() -> Bot:
    settings = get_settings()
    return Bot(
        token=settings.admin_bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def _publisher_bot() -> Bot | None:
    settings = get_settings()
    if settings.publisher_bot_token is None:
        return None
    return Bot(
        token=settings.publisher_bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


async def _send_to_publisher_tg(publisher_id: int, text: str) -> None:
    """Send text to publisher via their TG id, looking it up in DB."""
    from src.core.db import async_session_factory
    from sqlalchemy import select
    from src.core.db.models import Publisher

    bot = _publisher_bot()
    if bot is None:
        log.warning("publisher_bot_not_configured")
        return

    try:
        async with async_session_factory() as session:
            result = await session.execute(
                select(Publisher).where(Publisher.id == publisher_id)
            )
            publisher = result.scalar_one_or_none()
            if publisher is None:
                log.warning("publisher_not_found_for_notify", publisher_id=publisher_id)
                return
            tg_user_id = publisher.tg_user_id

        try:
            await bot.send_message(chat_id=tg_user_id, text=text)
            log.info("publisher_notification_sent", publisher_id=publisher_id)
        except Exception as e:
            log.warning("publisher_notify_failed", publisher_id=publisher_id, error=str(e))
    finally:
        await bot.session.close()


# ---------- Top-up ----------


@broker.task
async def notify_topup_success(
    tg_user_id: int,
    amount_rub: str,
    invoice_id: int,
    paid_asset: str = "",
    paid_amount: str = "",
) -> None:
    """Tell advertiser their balance was topped up."""
    amount = Decimal(amount_rub)
    paid_part = ""
    if paid_asset and paid_amount:
        paid_part = f"\nОплачено: <b>{paid_amount} {paid_asset}</b>"

    text = (
        f"✅ <b>Баланс пополнен</b>\n\n"
        f"Зачислено: <b>{amount:.2f} ₽</b>{paid_part}\n"
        f"Счёт: <code>#{invoice_id}</code>\n\n"
        f"Спасибо! Теперь вы можете создать кампанию."
    )
    bot = _advertiser_bot()
    try:
        await bot.send_message(chat_id=tg_user_id, text=text)
        log.info("topup_notification_sent", tg_user_id=tg_user_id, amount=str(amount))
    except Exception as e:
        log.error("topup_notification_failed", tg_user_id=tg_user_id, error=str(e))
        raise
    finally:
        await bot.session.close()


# ---------- Admin notifications ----------


@broker.task
async def notify_admin_new_campaign(
    campaign_id: int,
    advertiser_label: str,
    title: str,
    budget_rub: str,
    resources_count: int,
) -> None:
    """Notify all admins that a new campaign awaits moderation."""
    settings = get_settings()
    text = (
        f"🔔 <b>Новая кампания на модерацию</b>\n\n"
        f"<b>#{campaign_id}</b> «{title}»\n"
        f"Рекламодатель: {advertiser_label}\n"
        f"Бюджет: <b>{Decimal(budget_rub):.2f} ₽</b>\n"
        f"Ресурсов: {resources_count}\n\n"
        f"Откройте админ-бот для проверки."
    )

    admin_ids = list(settings.admin_user_ids_list)
    if not admin_ids:
        log.warning("no_admin_ids_configured_for_notify")
        return

    bot = _admin_bot()
    try:
        for admin_id in admin_ids:
            try:
                await bot.send_message(chat_id=admin_id, text=text)
            except Exception as e:
                log.warning("admin_notify_failed", admin_id=admin_id, error=str(e))
        log.info("admin_campaign_notification_sent", campaign_id=campaign_id, recipients=len(admin_ids))
    finally:
        await bot.session.close()


# ---------- Advertiser: approval / rejection ----------


@broker.task
async def notify_campaign_approved(
    tg_user_id: int,
    campaign_id: int,
    campaign_title: str,
    budget_rub: str,
) -> None:
    text = (
        f"✅ <b>Кампания одобрена!</b>\n\n"
        f"#{campaign_id} «{campaign_title}»\n"
        f"Бюджет: <b>{Decimal(budget_rub):.2f} ₽</b>\n\n"
        f"Я уже подбираю пользователей через сеть ботов-партнёров. "
        f"Следите за статистикой в «📢 Мои кампании»."
    )
    bot = _advertiser_bot()
    try:
        await bot.send_message(chat_id=tg_user_id, text=text)
        log.info("approval_notification_sent", tg_user_id=tg_user_id, campaign_id=campaign_id)
    except Exception as e:
        log.error("approval_notification_failed", tg_user_id=tg_user_id, error=str(e))
    finally:
        await bot.session.close()


@broker.task
async def notify_campaign_rejected(
    tg_user_id: int,
    campaign_id: int,
    campaign_title: str,
    refund_rub: str,
    reason: str,
) -> None:
    text = (
        f"❌ <b>Кампания отклонена</b>\n\n"
        f"#{campaign_id} «{campaign_title}»\n\n"
        f"<b>Причина:</b>\n<i>{reason}</i>\n\n"
        f"💰 Возвращено на баланс: <b>{Decimal(refund_rub):.2f} ₽</b>\n\n"
        f"Вы можете создать новую кампанию с учётом замечаний."
    )
    bot = _advertiser_bot()
    try:
        await bot.send_message(chat_id=tg_user_id, text=text)
        log.info("rejection_notification_sent", tg_user_id=tg_user_id, campaign_id=campaign_id)
    except Exception as e:
        log.error("rejection_notification_failed", tg_user_id=tg_user_id, error=str(e))
    finally:
        await bot.session.close()


@broker.task
async def notify_admin_new_withdrawal(
    publisher_id: int,
    publisher_label: str,
    amount_rub: str,
) -> None:
    """Notify admins that a publisher requested payout."""
    settings = get_settings()
    text = (
        f"📤 <b>Заявка на вывод</b>\n\n"
        f"<b>Партнёр:</b> {publisher_label} (id: {publisher_id})\n"
        f"<b>Сумма:</b> <b>{Decimal(amount_rub):.2f} ₽</b>\n\n"
        f"Обработайте заявку и перечислите средства партнёру."
    )

    admin_ids = list(settings.admin_user_ids_list)
    if not admin_ids:
        log.warning("no_admin_ids_configured_for_notify")
        return

    bot = _admin_bot()
    try:
        for admin_id in admin_ids:
            try:
                await bot.send_message(chat_id=admin_id, text=text)
            except Exception as e:
                log.warning("admin_withdrawal_notify_failed", admin_id=admin_id, error=str(e))
        log.info("withdrawal_notification_sent", publisher_id=publisher_id, recipients=len(admin_ids))
    finally:
        await bot.session.close()


@broker.task
async def notify_publisher_withdrawal_approved(
    publisher_id: int,
    tx_id: int,
    amount_rub: str,
) -> None:
    """Notify publisher that their withdrawal was approved & sent."""
    text = (
        f"✅ <b>Заявка #{tx_id} выплачена</b>\n\n"
        f"<b>Сумма:</b> {Decimal(amount_rub):.2f} ₽\n\n"
        f"Средства отправлены через CryptoBot. Проверьте свой аккаунт."
    )
    await _send_to_publisher_tg(publisher_id, text)


@broker.task
async def notify_publisher_withdrawal_rejected(
    publisher_id: int,
    tx_id: int,
    amount_rub: str,
    reason: str,
) -> None:
    """Notify publisher that their withdrawal was rejected & funds returned."""
    text = (
        f"❌ <b>Заявка #{tx_id} отклонена</b>\n\n"
        f"<b>Сумма:</b> {Decimal(amount_rub):.2f} ₽ возвращена на баланс.\n\n"
        f"<b>Причина:</b> {reason[:300]}\n\n"
        f"Вы можете создать новую заявку с корректными данными."
    )
    await _send_to_publisher_tg(publisher_id, text)
