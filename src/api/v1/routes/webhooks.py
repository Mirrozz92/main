"""Webhook configuration API.

POST /api/v1/webhook/configure — set the delivery URL / events for the token's bot.
GET  /api/v1/webhook          — read the current configuration (without the secret).

Webhooks are bound to the publisher_bot the API token belongs to.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import (
    get_current_publisher,
    get_current_publisher_bot,
    get_session,
)
from src.api.rate_limit import webhook_config_limit
from src.api.v1.schemas import (
    WebhookConfigureRequest,
    WebhookConfigureResponse,
    WebhookInfoResponse,
)
from src.core.db.models import Publisher, PublisherBot
from src.core.logging import get_logger
from src.domain.webhooks import WebhookService, WebhookValidationError

router = APIRouter(prefix="/api/v1", tags=["webhooks"])
log = get_logger("api.webhooks")


@router.post(
    "/webhook/configure",
    response_model=WebhookConfigureResponse,
    summary="Configure the webhook endpoint for your bot",
    description=(
        "Sets (or updates) the HTTPS URL that receives event callbacks for the "
        "bot this token belongs to.\n\n"
        "On first setup a signing **secret** is generated and returned **once** — "
        "store it. Set `rotate_secret=true` to generate a new one. Each delivery is "
        "signed `HMAC-SHA256(secret, body)` in the `X-FastSub-Signature` header.\n\n"
        "Pass `events` to receive only specific event types; omit for all events.\n\n"
        "**Rate limit**: 20 requests per minute per token."
    ),
)
async def configure_webhook(
    body: WebhookConfigureRequest,
    publisher: Publisher = Depends(get_current_publisher),
    publisher_bot: PublisherBot = Depends(get_current_publisher_bot),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(webhook_config_limit),
) -> WebhookConfigureResponse:
    svc = WebhookService(session)
    events = [str(e) for e in body.events] if body.events else None
    try:
        endpoint, secret = await svc.setup_endpoint(
            publisher_bot_id=publisher_bot.id,
            url=body.url,
            enabled_events=events,
            rotate_secret=body.rotate_secret,
        )
    except WebhookValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    log.info(
        "webhook_configured_via_api",
        publisher_bot_id=publisher_bot.id,
        url=endpoint.url,
        events=endpoint.enabled_events,
        rotated=body.rotate_secret,
        secret_issued=secret is not None,
    )

    return WebhookConfigureResponse(
        ok=True,
        url=endpoint.url,
        enabled_events=endpoint.enabled_events,
        secret=secret,
    )


@router.get(
    "/webhook",
    response_model=WebhookInfoResponse,
    summary="Get current webhook configuration",
    description=(
        "Returns the webhook configuration for the bot this token belongs to "
        "(without the secret). `configured=false` if none is set yet.\n\n"
        "**Rate limit**: 20 requests per minute per token."
    ),
)
async def get_webhook(
    publisher: Publisher = Depends(get_current_publisher),
    publisher_bot: PublisherBot = Depends(get_current_publisher_bot),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(webhook_config_limit),
) -> WebhookInfoResponse:
    svc = WebhookService(session)
    endpoint = await svc.get_endpoint(publisher_bot.id)
    if endpoint is None:
        return WebhookInfoResponse(ok=True, configured=False)

    return WebhookInfoResponse(
        ok=True,
        configured=True,
        url=endpoint.url,
        enabled_events=endpoint.enabled_events,
        is_active=endpoint.is_active,
        consecutive_failures=endpoint.consecutive_failures,
        last_success_at=endpoint.last_success_at,
        last_failure_at=endpoint.last_failure_at,
    )
