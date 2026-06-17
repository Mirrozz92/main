"""Enums shared across models."""

from __future__ import annotations

import enum


class CampaignStatus(str, enum.Enum):
    DRAFT = "draft"               # Создана, не оплачена
    PENDING_MODERATION = "pending_moderation"
    ACTIVE = "active"             # Крутится
    PAUSED = "paused"             # Приостановлена рекламодателем
    COMPLETED = "completed"       # Все ресурсы набрали нужное число подписок
    REJECTED = "rejected"         # Отклонена модератором
    CANCELED = "canceled"         # Отменена рекламодателем


class ResourceType(str, enum.Enum):
    CHANNEL = "channel"           # Telegram канал
    GROUP = "group"               # Группа/чат
    BOT_START = "bot_start"       # Запуск бота (CPA)


class ResourceStatus(str, enum.Enum):
    PENDING = "pending"           # Ожидает создания invite-link
    ACTIVE = "active"             # Активен, выдаётся юзерам
    PAUSED = "paused"
    COMPLETED = "completed"       # Набрано достаточно подписчиков
    FAILED = "failed"             # Ошибка (бот не админ, канал удалён и т.д.)


class IssueStatus(str, enum.Enum):
    PENDING = "pending"           # Выдан юзеру, ждём подписки
    SUBSCRIBED = "subscribed"     # Юзер подписался, в hold
    VERIFIED = "verified"         # Прошёл hold, деньги начислены паблишеру
    PAID = "paid"                 # Выплачено (legacy/удобство)
    EXPIRED = "expired"           # TTL истёк, юзер не подписался
    UNSUBSCRIBED = "unsubscribed"  # Отписался во время hold
    REVERTED = "reverted"         # Возвращён баланс после отписки
    INVALID = "invalid"            # Ошибка верификации


class TransactionType(str, enum.Enum):
    # Рекламодатели
    ADVERTISER_TOPUP = "advertiser_topup"            # Пополнение через CryptoBot
    CAMPAIGN_RESERVE = "campaign_reserve"            # Бронь под кампанию
    CAMPAIGN_SPEND = "campaign_spend"                # Списание за подтверждённую подписку
    CAMPAIGN_REFUND = "campaign_refund"              # Возврат при отписке/истечении
    # Паблишеры
    PUBLISHER_EARN = "publisher_earn"                # Начисление в hold
    PUBLISHER_HOLD_RELEASE = "publisher_hold_release"  # Hold → доступный баланс
    PUBLISHER_HOLD_REVERT = "publisher_hold_revert"    # Списание при отписке
    PUBLISHER_PAYOUT = "publisher_payout"            # Выплата на CryptoBot
    PUBLISHER_BONUS = "publisher_bonus"              # Бонус за retention
    # Платформа
    PLATFORM_COMMISSION = "platform_commission"      # Комиссия платформы
    ADJUSTMENT = "adjustment"                         # Ручная корректировка админом


class TransactionStatus(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class VerificationMethod(str, enum.Enum):
    GET_CHAT_MEMBER = "get_chat_member"      # Публичные каналы/группы
    JOIN_REQUEST = "join_request"            # Приватные с заявками
    START_PARAM = "start_param"              # Запуск бота с реф-параметром


class WebhookEventType(str, enum.Enum):
    RESOURCE_ISSUED = "resource.issued"
    RESOURCE_SUBSCRIBED = "resource.subscribed"
    RESOURCE_VERIFIED = "resource.verified"
    RESOURCE_PAID = "resource.paid"
    RESOURCE_UNSUBSCRIBED = "resource.unsubscribed"
    RESOURCE_EXPIRED = "resource.expired"
    RESOURCE_REVERTED = "resource.reverted"


class WebhookDeliveryStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    DEAD = "dead"  # Превышены retries


# --- asyncpg enum string handling ---
# asyncpg sends Enum members by their .name (uppercase) by default, but
# PostgreSQL enum types store lowercase values. Override __str__ so that
# str(WebhookDeliveryStatus.PENDING) == "pending" instead of "PENDING".
def _enum_str(self) -> str:
    return self.value


for _cls in (
    IssueStatus,
    CampaignStatus,
    ResourceStatus,
    ResourceType,
    TransactionType,
    TransactionStatus,
    WebhookEventType,
    WebhookDeliveryStatus,
):
    _cls.__str__ = _enum_str
