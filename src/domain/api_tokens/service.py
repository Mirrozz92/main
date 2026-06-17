"""Service layer for API tokens (now per-PublisherBot).

Each PublisherBot has 0..1 ACTIVE token at a time.
Regenerating creates a new token + revokes the old one in the same transaction.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db.models import PublisherApiToken
from src.core.logging import get_logger
from src.domain.api_tokens.repository import ApiTokenRepository
from src.domain.exceptions import DomainError

log = get_logger("api_tokens")


TOKEN_PREFIX_LITERAL = "fsp_live_"
TOKEN_RANDOM_HEX_LEN = 40
DISPLAY_PREFIX_LEN = 12


@dataclass
class TokenCreationResult:
    plaintext: str
    token_record: PublisherApiToken


class ApiTokenService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = ApiTokenRepository(session)

    async def create_for_bot(
        self,
        *,
        publisher_id: int,
        publisher_bot_id: int,
        label: str = "Default",
    ) -> TokenCreationResult:
        """Generate a new API token bound to a specific PublisherBot."""
        clean_label = (label or "").strip()
        if not (1 <= len(clean_label) <= 128):
            raise DomainError("Имя токена должно быть от 1 до 128 символов.")

        random_part = secrets.token_hex(TOKEN_RANDOM_HEX_LEN // 2)
        plaintext = f"{TOKEN_PREFIX_LITERAL}{random_part}"
        token_hash = hash_token(plaintext)
        token_prefix = plaintext[:DISPLAY_PREFIX_LEN]

        record = await self.repo.create(
            publisher_id=publisher_id,
            publisher_bot_id=publisher_bot_id,
            token_prefix=token_prefix,
            token_hash=token_hash,
            label=clean_label,
        )
        log.info("api_token_created",
                 publisher_id=publisher_id, publisher_bot_id=publisher_bot_id,
                 token_id=record.id)
        return TokenCreationResult(plaintext=plaintext, token_record=record)

    async def regenerate_for_bot(
        self,
        *,
        publisher_id: int,
        publisher_bot_id: int,
        label: str = "Regenerated",
    ) -> TokenCreationResult:
        """Revoke all active tokens for this bot, then create a fresh one.

        Old tokens will immediately stop working (next request returns 401).
        """
        # Revoke all active tokens for this bot
        active_tokens = await self.repo.list_for_bot(publisher_bot_id, include_revoked=False)
        for tok in active_tokens:
            await self.repo.revoke(tok)
            log.info("api_token_revoked_during_regen", token_id=tok.id)

        # Create new one
        return await self.create_for_bot(
            publisher_id=publisher_id,
            publisher_bot_id=publisher_bot_id,
            label=label,
        )

    async def get_active_for_bot(self, publisher_bot_id: int) -> PublisherApiToken | None:
        tokens = await self.repo.list_for_bot(publisher_bot_id, include_revoked=False)
        return tokens[0] if tokens else None

    async def verify(self, plaintext: str) -> PublisherApiToken | None:
        if not plaintext or not plaintext.startswith(TOKEN_PREFIX_LITERAL):
            return None
        token_hash = hash_token(plaintext)
        record = await self.repo.get_by_hash(token_hash)
        if record is None or not record.is_active:
            return None
        return record

    async def revoke(self, token: PublisherApiToken) -> None:
        await self.repo.revoke(token)
        log.info("api_token_revoked", token_id=token.id)


def hash_token(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
