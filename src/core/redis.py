"""Redis client factories.

We keep separate clients for different DB indices:
- cache (DB 0): hot data (offers, sessions)
- taskiq (DB 1): broker for background tasks (managed by taskiq itself)
- ratelimit (DB 2): rate limit counters
"""

from __future__ import annotations

from redis.asyncio import Redis

from src.core.config import get_settings


def make_cache_client() -> Redis:
    """Create Redis client for general caching."""
    return Redis.from_url(
        get_settings().redis_url_cache,
        decode_responses=True,
        socket_timeout=5,
        socket_connect_timeout=5,
        retry_on_timeout=True,
        health_check_interval=30,
    )


def make_ratelimit_client() -> Redis:
    """Create Redis client for rate limiting."""
    return Redis.from_url(
        get_settings().redis_url_ratelimit,
        decode_responses=True,
        socket_timeout=2,
        socket_connect_timeout=2,
    )
