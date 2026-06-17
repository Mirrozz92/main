"""Webhook delivery worker.

Runs every minute. Picks pending deliveries whose next_attempt_at <= now,
POSTs to endpoint URL with signed body, updates status:
  - HTTP 2xx → status=success, delivered_at=now, reset endpoint.consecutive_failures
  - else → schedule next attempt by exp backoff:
        attempt 1 → +1 min,  2 → +5 min,  3 → +30 min,
        attempt 4 → +2 h,    5 → +6 h,   ≥6 → status=dead

  After MAX_CONSECUTIVE_FAILURES on the endpoint, it auto-disables.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select

from src.core.db import async_session_factory
from src.core.db.models import WebhookEndpoint
from src.core.db.models.enums import WebhookDeliveryStatus
from src.core.logging import get_logger
from src.domain.webhooks.repository import WebhookRepository
from src.domain.webhooks.service import MAX_CONSECUTIVE_FAILURES
from src.domain.webhooks.signing import canonical_payload, compute_signature
from src.workers.broker import broker

log = get_logger("workers.webhook_delivery")

# Backoff schedule (minutes). attempts is 0-indexed after we increment it.
BACKOFF_MINUTES = [1, 5, 30, 120, 360]  # 1m, 5m, 30m, 2h, 6h
MAX_ATTEMPTS = len(BACKOFF_MINUTES) + 1  # 6 attempts total then dead

REQUEST_TIMEOUT_SEC = 10


@broker.task(
    schedule=[{"cron": "* * * * *"}],
    task_name="deliver_pending_webhooks",
)
async def deliver_pending_webhooks(batch_size: int = 50) -> dict:
    """Pick due deliveries and POST them. Updates statuses in place."""
    delivered = 0
    failed = 0
    dead = 0

    async with async_session_factory() as session:
        try:
            repo = WebhookRepository(session)
            due = await repo.list_due_deliveries(limit=batch_size)
            if not due:
                await session.commit()
                return {"delivered": 0, "failed": 0, "dead": 0}

            # Group by endpoint to load endpoints once
            endpoint_ids = {d.endpoint_id for d in due}
            ep_rows = await session.execute(
                select(WebhookEndpoint).where(WebhookEndpoint.id.in_(endpoint_ids))
            )
            endpoints: dict[int, WebhookEndpoint] = {
                ep.id: ep for ep in ep_rows.scalars().all()
            }

            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SEC) as http:
                for delivery in due:
                    endpoint = endpoints.get(delivery.endpoint_id)
                    if endpoint is None or not endpoint.is_active:
                        # Skip silently — mark dead
                        delivery.status = WebhookDeliveryStatus.DEAD
                        delivery.last_response_body = "endpoint missing or disabled"
                        dead += 1
                        continue

                    delivery.attempts += 1
                    body = canonical_payload(delivery.payload)
                    signature = compute_signature(endpoint.secret, body)
                    headers = {
                        "Content-Type": "application/json",
                        "X-FastSub-Signature": signature,
                        "X-FastSub-Event": delivery.event_type.value,
                        "X-FastSub-Delivery-Id": str(delivery.id),
                        "User-Agent": "FastSub-Webhook/1.0",
                    }
                    now = datetime.now(timezone.utc)

                    try:
                        resp = await http.post(
                            endpoint.url, content=body, headers=headers,
                        )
                        delivery.last_response_status = resp.status_code
                        # Truncate body to avoid bloat
                        delivery.last_response_body = (resp.text or "")[:2000]

                        if 200 <= resp.status_code < 300:
                            delivery.status = WebhookDeliveryStatus.SUCCESS
                            delivery.delivered_at = now
                            endpoint.last_success_at = now
                            endpoint.consecutive_failures = 0
                            delivered += 1
                        else:
                            # Non-2xx → retry or dead
                            await _schedule_retry_or_dead(delivery, endpoint, now)
                            if delivery.status == WebhookDeliveryStatus.DEAD:
                                dead += 1
                            else:
                                failed += 1
                    except Exception as e:
                        delivery.last_response_status = None
                        delivery.last_response_body = f"network: {type(e).__name__}: {str(e)[:200]}"
                        await _schedule_retry_or_dead(delivery, endpoint, now)
                        if delivery.status == WebhookDeliveryStatus.DEAD:
                            dead += 1
                        else:
                            failed += 1

            await session.commit()
        except Exception as e:
            await session.rollback()
            log.error("delivery_batch_failed", error=str(e))
            raise

    if delivered or failed or dead:
        log.info(
            "webhook_batch_done",
            delivered=delivered, failed=failed, dead=dead,
        )
    return {"delivered": delivered, "failed": failed, "dead": dead}


async def _schedule_retry_or_dead(
    delivery,
    endpoint: WebhookEndpoint,
    now: datetime,
) -> None:
    """If attempts >= MAX_ATTEMPTS → DEAD, else PENDING with next_attempt_at."""
    endpoint.last_failure_at = now
    endpoint.consecutive_failures = endpoint.consecutive_failures + 1

    if endpoint.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
        endpoint.is_active = False
        log.warning(
            "endpoint_auto_disabled",
            endpoint_id=endpoint.id,
            failures=endpoint.consecutive_failures,
        )

    if delivery.attempts >= MAX_ATTEMPTS:
        delivery.status = WebhookDeliveryStatus.DEAD
        delivery.next_attempt_at = None
        return

    # Schedule next attempt
    minutes_idx = min(delivery.attempts - 1, len(BACKOFF_MINUTES) - 1)
    delay = BACKOFF_MINUTES[minutes_idx]
    delivery.status = WebhookDeliveryStatus.PENDING
    delivery.next_attempt_at = now + timedelta(minutes=delay)
