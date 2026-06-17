"""Guard: the API WebhookEventLiteral must stay in sync with the DB enum."""

from __future__ import annotations

from typing import get_args

from src.api.v1.schemas.webhooks import WebhookEventLiteral
from src.core.db.models.enums import WebhookEventType


def test_literal_matches_enum() -> None:
    literal_values = set(get_args(WebhookEventLiteral))
    enum_values = {e.value for e in WebhookEventType}
    assert literal_values == enum_values
