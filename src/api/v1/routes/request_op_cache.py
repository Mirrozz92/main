"""Idempotency cache for /request-op responses.

Within `list_ttl_seconds` of a publisher_bot, repeated calls for the same
(publisher_bot_id, user_tg_id) return the SAME task list — preventing the
user from seeing a different list of sponsors each time they reload.

Implementation: store JSON-serialized response in Redis with TTL.
"""

from __future__ import annotations

import json
from typing import Any

from redis.asyncio import Redis

from src.core.logging import get_logger
from src.core.redis import make_cache_client

log = get_logger("api.requestop.cache")


_redis: Redis | None = None


def _get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = make_cache_client()
    return _redis


def _key(publisher_bot_id: int, user_tg_id: int) -> str:
    return f"reqop:{publisher_bot_id}:{user_tg_id}"


async def get_cached(publisher_bot_id: int, user_tg_id: int) -> dict[str, Any] | None:
    """Return cached response dict, or None if not cached."""
    try:
        raw = await _get_redis().get(_key(publisher_bot_id, user_tg_id))
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as e:
        log.warning("requestop_cache_get_failed", error=str(e))
        return None


async def set_cached(
    publisher_bot_id: int,
    user_tg_id: int,
    payload: dict[str, Any],
    ttl_seconds: int,
) -> None:
    """Store response with TTL = bot.list_ttl_seconds."""
    try:
        await _get_redis().setex(
            _key(publisher_bot_id, user_tg_id),
            ttl_seconds,
            json.dumps(payload, default=str),
        )
    except Exception as e:
        log.warning("requestop_cache_set_failed", error=str(e))


async def invalidate(publisher_bot_id: int, user_tg_id: int) -> None:
    """Drop the cache entry (e.g. on settings change). Optional."""
    try:
        await _get_redis().delete(_key(publisher_bot_id, user_tg_id))
    except Exception:
        pass
