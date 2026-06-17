"""FastAPI dependencies: DB session, current publisher (auth), publisher_bot."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import async_session_factory
from src.core.db.models import Publisher, PublisherApiToken, PublisherBot
from src.core.logging import get_logger
from src.domain.api_tokens import ApiTokenService
from src.domain.publisher_bots import PublisherBotRepository
from src.domain.publishers import PublisherRepository

log = get_logger("api.deps")


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield a fresh DB session per request. Commits on success, rolls back on error."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_current_token(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
    session: AsyncSession = Depends(get_session),
) -> PublisherApiToken:
    """Extract and verify Authorization: Bearer <token>.

    On success: updates last_used_at + counter, stashes token in request.state
    so rate-limit middleware can key off it.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = authorization.split(maxsplit=1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid authorization scheme; expected Bearer",
            headers={"WWW-Authenticate": "Bearer"},
        )

    plaintext = parts[1].strip()
    svc = ApiTokenService(session)
    token = await svc.verify(plaintext)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or revoked token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    await svc.repo.touch(token)
    request.state.current_token = token
    return token


async def get_current_publisher(
    token: PublisherApiToken = Depends(get_current_token),
    session: AsyncSession = Depends(get_session),
) -> Publisher:
    """Resolve authenticated Publisher. Raises 401 if banned."""
    repo = PublisherRepository(session)
    publisher = await repo.get_by_id(token.publisher_id)
    if publisher is None or publisher.is_banned:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="account disabled",
        )
    return publisher


async def get_current_publisher_bot(
    token: PublisherApiToken = Depends(get_current_token),
    session: AsyncSession = Depends(get_session),
) -> PublisherBot:
    """Resolve the PublisherBot this token is bound to.

    For 3a v2+: every API token MUST be bound to a PublisherBot.
    If not — token is from old data; return 401 to force re-issue.
    """
    if token.publisher_bot_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token not bound to a bot — please regenerate via @fastsub_publisher_bot",
        )
    repo = PublisherBotRepository(session)
    pub_bot = await repo.get_by_id(token.publisher_bot_id)
    if pub_bot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="associated bot not found",
        )
    if not pub_bot.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="bot is currently disabled by its owner",
        )
    return pub_bot
