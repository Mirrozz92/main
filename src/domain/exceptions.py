"""Domain-level exceptions, raised from service layer."""

from __future__ import annotations

from decimal import Decimal


class DomainError(Exception):
    """Base for domain errors. UI-friendly messages."""

    user_message: str = "Произошла ошибка. Попробуйте позже."

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.user_message)
        if message:
            self.user_message = message


class AdvertiserBannedError(DomainError):
    user_message = "Ваш аккаунт заблокирован. Свяжитесь с поддержкой."


class InsufficientFundsError(DomainError):
    def __init__(self, required: Decimal, available: Decimal) -> None:
        self.required = required
        self.available = available
        super().__init__(
            f"Недостаточно средств. Нужно: {required:.2f} ₽, доступно: {available:.2f} ₽. "
            f"Пополните баланс на {required - available:.2f} ₽."
        )


class CampaignValidationError(DomainError):
    pass


class ResourceValidationError(DomainError):
    pass


class CheckerNotAdminError(DomainError):
    user_message = (
        "Я не админ в этом канале/группе.\n\n"
        "Добавьте @fastsub_check1_bot администратором с правом "
        "«Приглашать пользователей по ссылке» и попробуйте снова."
    )


class ChatNotFoundError(DomainError):
    user_message = "Канал/группа не найден. Проверьте юзернейм."


class CryptoBotError(DomainError):
    user_message = "Ошибка платёжного сервиса. Попробуйте позже."


class ExchangeRateUnavailableError(DomainError):
    user_message = "Не удалось получить курс валют. Попробуйте через минуту."


class DuplicateResourceError(DomainError):
    user_message = "Этот канал уже добавлен в текущую кампанию."
