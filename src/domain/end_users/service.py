"""Service layer for EndUser + onboarding tokens (Redis).

OnboardingTokenService manages one-shot tokens used to securely identify
the (user_tg_id, partner_bot_id) pair during the web-onboarding form flow.

Token lives in Redis (cache DB) with TTL 24h, idempotent — repeated calls
for the same (user, bot) within TTL return the same token.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from typing import Literal

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db.models import EndUser
from src.core.logging import get_logger
from src.core.redis import make_cache_client
from src.domain.end_users.repository import EndUserRepository
from src.domain.exceptions import DomainError

log = get_logger("end_users.service")


ONBOARDING_TOKEN_TTL_SECONDS = 24 * 3600  # 24 hours
INDEX_TTL_SECONDS = ONBOARDING_TOKEN_TTL_SECONDS

VALID_GENDERS = {"male", "female", "undisclosed"}
VALID_AGE_RANGES = {"under_14", "14_16", "16_18", "18_plus"}
VALID_COUNTRIES = {"RU", "UA", "BY", "KZ", "OTHER"}


@dataclass
class OnboardingTokenPayload:
    user_tg_id: int
    publisher_bot_id: int


class OnboardingTokenService:
    """Redis-backed one-shot tokens for the onboarding URL.

    Storage:
      Key:   "onb:t:<token>"  → JSON {user_tg_id, publisher_bot_id}
      Index: "onb:idx:<user_tg_id>:<publisher_bot_id>" → token

    The index allows idempotent issuance: if the same (user, bot) requests
    onboarding within TTL, we return the same token.
    """

    def __init__(self, redis: Redis | None = None) -> None:
        self._redis = redis or make_cache_client()

    @staticmethod
    def _token_key(token: str) -> str:
        return f"onb:t:{token}"

    @staticmethod
    def _index_key(user_tg_id: int, publisher_bot_id: int) -> str:
        return f"onb:idx:{user_tg_id}:{publisher_bot_id}"

    async def issue(
        self,
        *,
        user_tg_id: int,
        publisher_bot_id: int,
    ) -> str:
        """Generate or reuse a token for (user, bot).

        Returns the token string (without URL prefix).
        """
        index_key = self._index_key(user_tg_id, publisher_bot_id)
        existing = await self._redis.get(index_key)
        if existing is not None:
            return existing.decode() if isinstance(existing, bytes) else existing

        # New token
        token = secrets.token_urlsafe(24)
        payload = json.dumps({
            "user_tg_id": user_tg_id,
            "publisher_bot_id": publisher_bot_id,
        })
        # Store with TTL atomically
        async with self._redis.pipeline() as pipe:
            pipe.setex(self._token_key(token), ONBOARDING_TOKEN_TTL_SECONDS, payload)
            pipe.setex(index_key, INDEX_TTL_SECONDS, token)
            await pipe.execute()
        log.info(
            "onboarding_token_issued",
            user_tg_id=user_tg_id, publisher_bot_id=publisher_bot_id,
        )
        return token

    async def resolve(self, token: str) -> OnboardingTokenPayload | None:
        """Validate a token, return the bound (user, bot) or None if expired/invalid."""
        raw = await self._redis.get(self._token_key(token))
        if raw is None:
            return None
        try:
            data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
            return OnboardingTokenPayload(
                user_tg_id=int(data["user_tg_id"]),
                publisher_bot_id=int(data["publisher_bot_id"]),
            )
        except (ValueError, KeyError, TypeError) as e:
            log.warning("onboarding_token_corrupt", token=token[:8], error=str(e))
            return None

    async def consume(self, token: str) -> OnboardingTokenPayload | None:
        """Resolve and DELETE the token (one-shot use). Returns payload or None."""
        payload = await self.resolve(token)
        if payload is None:
            return None
        async with self._redis.pipeline() as pipe:
            pipe.delete(self._token_key(token))
            pipe.delete(self._index_key(payload.user_tg_id, payload.publisher_bot_id))
            await pipe.execute()
        return payload


class EndUserService:
    """High-level operations on EndUser."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = EndUserRepository(session)

    async def is_onboarded(self, user_tg_id: int) -> bool:
        return await self.repo.get_by_tg_id(user_tg_id) is not None

    async def create_from_form(
        self,
        *,
        user_tg_id: int,
        gender: str | None,
        age_range: str | None,
        country_code: str | None,
        country_other: str | None,
        publisher_bot_id: int | None,
    ) -> EndUser:
        """Persist user data from web-form submission.

        Validation:
          - gender in VALID_GENDERS (or None)
          - age_range in VALID_AGE_RANGES (or None — but typically required)
          - country_code in VALID_COUNTRIES (or None)
          - country_other only when country_code='OTHER'
        """
        # Validate
        if gender is not None and gender not in VALID_GENDERS:
            raise DomainError(f"Некорректное значение пола: {gender}")
        if age_range is not None and age_range not in VALID_AGE_RANGES:
            raise DomainError(f"Некорректный возрастной диапазон: {age_range}")
        if country_code is not None and country_code not in VALID_COUNTRIES:
            raise DomainError(f"Некорректный код страны: {country_code}")

        if country_code == "OTHER":
            if not country_other or len(country_other.strip()) < 2:
                raise DomainError("Укажите страну текстом")
            country_other = country_other.strip()[:64]
        else:
            country_other = None

        # Check for duplicate
        existing = await self.repo.get_by_tg_id(user_tg_id)
        if existing is not None:
            # Update existing — same user re-submitting (e.g. from another partner)
            await self.repo.touch(existing)
            return existing

        return await self.repo.create(
            user_tg_id=user_tg_id,
            gender=gender,
            age_range=age_range,
            country_code=country_code,
            country_other=country_other,
            onboarded_via_bot_id=publisher_bot_id,
        )
