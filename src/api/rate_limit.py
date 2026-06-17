"""API rate limiting via Redis sliding window.

Each endpoint can have its own limit (e.g. /request-op = 60/min,
/check-resource = 300/min). The limit is keyed by token_id (not by IP)
so each publisher token gets its own bucket.

Algorithm: simple fixed-window counter with TTL = window size.
For higher accuracy we could implement sliding window via sorted sets,
but for our scale (small partner network) this is sufficient.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from redis.asyncio import Redis

from src.core.db.models import PublisherApiToken
from src.core.logging import get_logger
from src.core.redis import make_cache_client

log = get_logger("api.rate_limit")


class RateLimiter:
    """Per-token, per-endpoint rate limiter.

    Usage:
        request_op_limit = RateLimiter("request_op", rate=60, window_seconds=60)

        @router.post("/request-op")
        async def request_op(
            token: PublisherApiToken = Depends(get_current_token),
            _: None = Depends(request_op_limit),
        ):
            ...
    """

    def __init__(
        self,
        endpoint_key: str,
        *,
        rate: int,
        window_seconds: int = 60,
    ) -> None:
        self.endpoint_key = endpoint_key
        self.rate = rate
        self.window = window_seconds
        # Created lazily per-request through __call__
        self._redis: Redis | None = None

    async def __call__(self, request: Request) -> None:
        """FastAPI dependency. Reads `current_token` from request.state."""
        token: PublisherApiToken | None = getattr(request.state, "current_token", None)
        if token is None:
            # Token middleware should have set it. If absent, skip limiting.
            return

        if self._redis is None:
            self._redis = make_cache_client()

        key = f"rl:{self.endpoint_key}:{token.id}"
        try:
            count = await self._redis.incr(key)
            if count == 1:
                await self._redis.expire(key, self.window)
        except Exception as e:
            log.warning("rate_limit_redis_error", error=str(e))
            return  # fail open

        if count > self.rate:
            log.warning(
                "rate_limit_exceeded",
                endpoint=self.endpoint_key,
                token_id=token.id,
                count=count,
                rate=self.rate,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded: {self.rate} requests per {self.window}s",
                headers={
                    "Retry-After": str(self.window),
                    "X-RateLimit-Limit": str(self.rate),
                    "X-RateLimit-Window": str(self.window),
                },
            )


# Pre-defined limiters for known endpoints
request_op_limit = RateLimiter("request_op", rate=60, window_seconds=60)
check_resource_limit = RateLimiter("check_resource", rate=300, window_seconds=60)
