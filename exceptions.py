"""Application-level exception hierarchy."""

from __future__ import annotations


class FastSubError(Exception):
    """Base exception for all application errors."""

    code: str = "internal_error"
    http_status: int = 500

    def __init__(self, message: str = "", *, details: dict | None = None) -> None:
        super().__init__(message or self.__class__.__name__)
        self.message = message or self.__class__.__name__
        self.details = details or {}


# --- Auth ---


class AuthError(FastSubError):
    code = "unauthorized"
    http_status = 401


class ForbiddenError(FastSubError):
    code = "forbidden"
    http_status = 403


# --- Validation ---


class ValidationError(FastSubError):
    code = "validation_error"
    http_status = 422


class NotFoundError(FastSubError):
    code = "not_found"
    http_status = 404


class ConflictError(FastSubError):
    code = "conflict"
    http_status = 409


# --- Business rules ---


class InsufficientFundsError(FastSubError):
    code = "insufficient_funds"
    http_status = 402


class CampaignExhaustedError(FastSubError):
    code = "campaign_exhausted"
    http_status = 410


class LinkExpiredError(FastSubError):
    code = "link_expired"
    http_status = 410


class AlreadySubscribedError(FastSubError):
    code = "already_subscribed"
    http_status = 409


class NoOffersAvailableError(FastSubError):
    code = "no_offers"
    http_status = 404


# --- Rate limiting ---


class RateLimitError(FastSubError):
    code = "rate_limit_exceeded"
    http_status = 429


# --- External services ---


class ExternalServiceError(FastSubError):
    code = "external_service_error"
    http_status = 502


class CryptoBotError(ExternalServiceError):
    code = "cryptobot_error"


class TelegramAPIError(ExternalServiceError):
    code = "telegram_error"
