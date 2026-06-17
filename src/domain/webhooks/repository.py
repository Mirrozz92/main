"""Repository for WebhookEndpoint + WebhookDelivery."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db.models import WebhookDelivery, WebhookEndpoint
from src.core.db.models.enums import WebhookDeliveryStatus, WebhookEventType


class WebhookRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # --- Endpoints ---

    async def get_endpoint_by_bot(self, publisher_bot_id: int) -> WebhookEndpoint | None:
        result = await self.session.execute(
            select(WebhookEndpoint).where(
                WebhookEndpoint.publisher_bot_id == publisher_bot_id
            )
        )
        return result.scalar_one_or_none()

    async def get_endpoint_by_id(self, endpoint_id: int) -> WebhookEndpoint | None:
        result = await self.session.execute(
            select(WebhookEndpoint).where(WebhookEndpoint.id == endpoint_id)
        )
        return result.scalar_one_or_none()

    async def upsert_endpoint(
        self,
        *,
        publisher_bot_id: int,
        url: str,
        secret: str,
        enabled_events: list[str],
    ) -> WebhookEndpoint:
        ep = await self.get_endpoint_by_bot(publisher_bot_id)
        if ep is None:
            ep = WebhookEndpoint(
                publisher_bot_id=publisher_bot_id,
                url=url,
                secret=secret,
                enabled_events=enabled_events,
                is_active=True,
                consecutive_failures=0,
            )
            self.session.add(ep)
        else:
            ep.url = url
            # Don't rotate secret on simple URL update — keep existing.
            # Caller passes secret only for fresh creation.
            if secret:
                ep.secret = secret
            ep.enabled_events = enabled_events
            ep.is_active = True
            ep.consecutive_failures = 0
        await self.session.flush()
        return ep

    async def disable_endpoint(self, publisher_bot_id: int) -> None:
        ep = await self.get_endpoint_by_bot(publisher_bot_id)
        if ep is not None:
            ep.is_active = False

    # --- Deliveries ---

    async def create_delivery(
        self,
        *,
        endpoint_id: int,
        event_type: WebhookEventType,
        payload: dict[str, Any],
    ) -> WebhookDelivery:
        delivery = WebhookDelivery(
            endpoint_id=endpoint_id,
            event_type=event_type,
            payload=payload,
            status=WebhookDeliveryStatus.PENDING,
            attempts=0,
            next_attempt_at=datetime.now(timezone.utc),
        )
        self.session.add(delivery)
        await self.session.flush()
        return delivery

    async def list_due_deliveries(self, *, limit: int = 50) -> list[WebhookDelivery]:
        """Pending deliveries whose next_attempt_at is in the past."""
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            select(WebhookDelivery)
            .where(
                and_(
                    WebhookDelivery.status == WebhookDeliveryStatus.PENDING,
                    WebhookDelivery.next_attempt_at <= now,
                )
            )
            .order_by(WebhookDelivery.next_attempt_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list(result.scalars().all())
