"""Async SQLAlchemy engine and session factory.

Connects through pgbouncer in transaction pooling mode, so:
- We must disable prepared statements (server_settings).
- We must NOT use connection-level features like LISTEN/NOTIFY here.
- Use `async with get_session() as session:` for transactional units of work.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.config import get_settings

_settings = get_settings()

# Engine connects via pgbouncer in production, direct in dev
_dsn = _settings.pgbouncer_dsn if _settings.is_production else _settings.postgres_dsn

engine = create_async_engine(
    _dsn,
    echo=_settings.debug,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    pool_recycle=1800,
    # pgbouncer transaction mode requires statement_cache_size=0
    connect_args={
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
        "server_settings": {
            "application_name": "fastsub",
        },
    },
)

async_session_factory = async_sessionmaker(
    engine,
    expire_on_commit=False,
    autoflush=False,
    class_=AsyncSession,
)


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield a new AsyncSession.

    Commits on success, rolls back on exception, always closes.
    """
    session = async_session_factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
