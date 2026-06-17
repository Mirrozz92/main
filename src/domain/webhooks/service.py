"""Service layer for webhook management."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db.models import ResourceIssue, WebhookEndpoint
from src.core.db.models.enums import WebhookEventType
from src.core.logging import get_logger
from src.domain.exceptions import DomainError
from src.domain.webhooks.repository import WebhookRepository
from src.domain.webhooks.signing import generate_webhook_secret

log = get_logger("webhooks.service")


# Max consecutive failures before endpoint auto-disabled
MAX_CONSECUTIVE_FAILURES = 50


class WebhookError(DomainError):
    """Base for webhook-related domain errors."""


class WebhookValidationError(WebhookError):
    """URL format invalid."""


def validate_webhook_url(url: str) -> str:
    """Basic URL validation. Returns normalized URL or raises."""
    url = url.strip()
    if not url:
        raise WebhookValidationError("URL не может быть пустым")
    if len(url) > 500:
        raise WebhookValidationError("URL слишком длинный (макс 500 символов)")
    try:
        parsed = urlparse(url)
    except Exception:
        raise WebhookValidationError("Не удалось распарсить URL")
    if parsed.scheme not in ("http", "https"):
        raise WebhookValidationError("URL должен начинаться с https:// или http://")
    if not parsed.netloc:
        raise WebhookValidationError("URL должен содержать домен")
    if parsed.scheme == "http" and parsed.netloc not in ("localhost", "127.0.0.1"):
        # Allow http only for local testing
        raise WebhookValidationError("Используйте https:// (http разрешён только для localhost)")
    return url


class WebhookService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = WebhookRepository(session)

    # --- Endpoint management ---

    async def setup_endpoint(
        self,
        *,
        publisher_bot_id: int,
        url: str,
        enabled_events: list[str] | None = None,
        rotate_secret: bool = False,
    ) -> tuple[WebhookEndpoint, str | None]:
        """Create or update webhook endpoint for a publisher bot.

        Returns (endpoint, secret_to_show_user).
        secret_to_show_user is the plain-text secret if just generated, else None.
        """
        url = validate_webhook_url(url)
        events = enabled_events or []

        existing = await self.repo.get_endpoint_by_bot(publisher_bot_id)
        secret_to_show: str | None = None

        if existing is None or rotate_secret:
            secret = generate_webhook_secret()
            secret_to_show = secret
        else:
            secret = ""  # signal: keep existing

        ep = await self.repo.upsert_endpoint(
            publisher_bot_id=publisher_bot_id,
            url=url,
            secret=secret,
            enabled_events=events,
        )
        log.info(
            "webhook_endpoint_set",
            endpoint_id=ep.id,
            publisher_bot_id=publisher_bot_id,
            url=url,
            events=events,
            rotated=rotate_secret,
        )
        return ep, secret_to_show

    async def get_endpoint(self, publisher_bot_id: int) -> WebhookEndpoint | None:
        return await self.repo.get_endpoint_by_bot(publisher_bot_id)

    async def disable(self, publisher_bot_id: int) -> None:
        await self.repo.disable_endpoint(publisher_bot_id)

    # --- Event emission ---

    async def emit_issue_event(
        self,
        *,
        issue: ResourceIssue,
        event_type: WebhookEventType,
    ) -> None:
        """Build payload and queue a delivery for issue's publisher_bot endpoint.

        No-op if endpoint missing, inactive, or event not enabled.
        """
        if issue.publisher_bot_id is None:
            return  # legacy issues without bot — skip
        endpoint = await self.repo.get_endpoint_by_bot(issue.publisher_bot_id)
        if endpoint is None or not endpoint.is_active:
            return
        if endpoint.enabled_events and event_type.value not in endpoint.enabled_events:
            return  # filtered out

        payload = self._build_issue_payload(issue, event_type)
        await self.repo.create_delivery(
            endpoint_id=endpoint.id,
            event_type=event_type,
            payload=payload,
        )

    async def emit_test_event(
        self,
        endpoint: WebhookEndpoint,
    ) -> None:
        """Send a fake `resource.subscribed` event for testing."""
        payload = {
            "event": WebhookEventType.RESOURCE_SUBSCRIBED.value,
            "test": True,
            "link_id": "lnk_test_demo",
            "task_id": "tsk_test_demo",
            "user_id": 0,
            "status": "subscribed",
            "reward_rub": "0.00",
            "publisher_payout_rub": "0.00",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await self.repo.create_delivery(
            endpoint_id=endpoint.id,
            event_type=WebhookEventType.RESOURCE_SUBSCRIBED,
            payload=payload,
        )

    # --- Helpers ---

    def _build_issue_payload(
        self,
        issue: ResourceIssue,
        event_type: WebhookEventType,
    ) -> dict[str, Any]:
        return {
            "event": event_type.value,
            "link_id": issue.link_id,
            "task_id": issue.task_id,
            "user_id": issue.user_tg_id,
            "campaign_resource_id": issue.campaign_resource_id,
            "status": issue.status.value if hasattr(issue.status, "value") else str(issue.status),
            "reward_rub": _money(issue.reward_rub),
            "publisher_payout_rub": _money(issue.publisher_payout_rub),
            "platform_commission_rub": _money(issue.platform_commission_rub),
            "issued_at": _iso(issue.issued_at),
            "subscribed_at": _iso(issue.subscribed_at),
            "verified_at": _iso(issue.verified_at),
            "unsubscribed_at": _iso(issue.unsubscribed_at),
            "expires_at": _iso(issue.expires_at),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


def _money(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return f"{value:.4f}"


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()
