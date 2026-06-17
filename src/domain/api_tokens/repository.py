"""Repository for PublisherApiToken."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db.models import PublisherApiToken


class ApiTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_hash(self, token_hash: str) -> PublisherApiToken | None:
        result = await self.session.execute(
            select(PublisherApiToken).where(PublisherApiToken.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, token_id: int) -> PublisherApiToken | None:
        result = await self.session.execute(
            select(PublisherApiToken).where(PublisherApiToken.id == token_id)
        )
        return result.scalar_one_or_none()

    async def list_for_publisher(
        self,
        publisher_id: int,
        *,
        include_revoked: bool = False,
    ) -> list[PublisherApiToken]:
        stmt = select(PublisherApiToken).where(
            PublisherApiToken.publisher_id == publisher_id,
        )
        if not include_revoked:
            stmt = stmt.where(PublisherApiToken.is_active.is_(True))
        stmt = stmt.order_by(desc(PublisherApiToken.created_at))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_bot(
        self,
        publisher_bot_id: int,
        *,
        include_revoked: bool = False,
    ) -> list[PublisherApiToken]:
        stmt = select(PublisherApiToken).where(
            PublisherApiToken.publisher_bot_id == publisher_bot_id,
        )
        if not include_revoked:
            stmt = stmt.where(PublisherApiToken.is_active.is_(True))
        stmt = stmt.order_by(desc(PublisherApiToken.created_at))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(
        self,
        *,
        publisher_id: int,
        publisher_bot_id: int | None,
        token_prefix: str,
        token_hash: str,
        label: str,
    ) -> PublisherApiToken:
        token = PublisherApiToken(
            publisher_id=publisher_id,
            publisher_bot_id=publisher_bot_id,
            token_prefix=token_prefix,
            token_hash=token_hash,
            label=label,
            is_active=True,
        )
        self.session.add(token)
        await self.session.flush()
        return token

    async def revoke(self, token: PublisherApiToken) -> None:
        token.is_active = False
        token.revoked_at = datetime.now(timezone.utc)

    async def touch(self, token: PublisherApiToken) -> None:
        token.last_used_at = datetime.now(timezone.utc)
        token.requests_count = token.requests_count + 1
