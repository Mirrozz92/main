"""HMAC-SHA256 signature for webhook payloads.

Partner verifies:
    expected = hmac.new(secret.encode(), body, "sha256").hexdigest()
    if expected != header_value: reject

We send the body as canonical JSON (sorted keys, compact separators) so the
partner can recompute it deterministically.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets


def generate_webhook_secret() -> str:
    """64-char URL-safe token used as HMAC key."""
    return secrets.token_urlsafe(48)[:64]


def canonical_payload(payload: dict) -> bytes:
    """JSON-encode with sorted keys and no spaces — stable representation."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def compute_signature(secret: str, body: bytes) -> str:
    """Hex-digest HMAC-SHA256 signature."""
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
