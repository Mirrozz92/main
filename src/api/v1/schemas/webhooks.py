"""Schemas for webhook configuration endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# Keep in sync with core.db.models.enums.WebhookEventType
# (guarded by tests/unit/test_webhook_events_sync).
WebhookEventLiteral = Literal[
    "resource.issued",
    "resource.subscribed",
    "resource.verified",
    "resource.paid",
    "resource.unsubscribed",
    "resource.expired",
    "resource.reverted",
]

SIGNATURE_HEADER = "X-FastSub-Signature"


class WebhookConfigureRequest(BaseModel):
    """Input for POST /api/v1/webhook/configure."""

    url: str = Field(
        ..., max_length=500,
        description="HTTPS endpoint to receive events (http allowed only for localhost).",
        examples=["https://example.com/fastsub/webhook"],
    )
    events: list[WebhookEventLiteral] | None = Field(
        default=None,
        description="Event types to receive. Omit or empty = all events.",
        examples=[["resource.subscribed", "resource.verified"]],
    )
    rotate_secret: bool = Field(
        default=False,
        description="If true, generate a new signing secret (returned once in `secret`).",
    )


class WebhookConfigureResponse(BaseModel):
    """Response from POST /api/v1/webhook/configure."""

    ok: bool = True
    url: str
    enabled_events: list[str] = Field(description="Empty list = all events enabled.")
    secret: str | None = Field(
        default=None,
        description=(
            "The signing secret — returned ONLY when freshly generated (first setup "
            "or rotate_secret=true). Store it now; it is not retrievable later. "
            f"Each delivery is signed as HMAC-SHA256(secret, body) in the "
            f"`{SIGNATURE_HEADER}` header."
        ),
    )
    signature_header: str = SIGNATURE_HEADER


class WebhookInfoResponse(BaseModel):
    """Response from GET /api/v1/webhook — current config (no secret)."""

    ok: bool = True
    configured: bool
    url: str | None = None
    enabled_events: list[str] = Field(default_factory=list)
    is_active: bool | None = None
    consecutive_failures: int | None = None
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
