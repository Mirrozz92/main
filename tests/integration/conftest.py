"""Integration-test harness backed by a real PostgreSQL database.

The schema is built by running the project's Alembic migrations against a
throwaway database (so the migrations themselves are exercised too). Each test
runs inside a transaction that is rolled back, giving full isolation without
recreating the schema per test.

Point TEST_DATABASE_URL at a disposable database. If it is unreachable the
integration tests are skipped, so the unit suite still runs without a DB.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://fastsub_test:fastsub_test@127.0.0.1:5432/fastsub_test",
)

# Populate the env so Settings (used by Alembic's env.py) builds the same DSN
# and constructs without missing required fields.
_url = make_url(TEST_DATABASE_URL)
os.environ.setdefault("ENV", "test")
os.environ["POSTGRES_HOST"] = _url.host or "127.0.0.1"
os.environ["POSTGRES_PORT"] = str(_url.port or 5432)
os.environ["POSTGRES_DB"] = _url.database or "fastsub_test"
os.environ["POSTGRES_USER"] = _url.username or "fastsub_test"
os.environ["POSTGRES_PASSWORD"] = _url.password or ""
for _k, _v in {
    "REDIS_PASSWORD": "test",
    "ADVERTISER_BOT_TOKEN": "0:test",
    "ADMIN_BOT_TOKEN": "0:test",
    "CRYPTOBOT_TOKEN": "test",
    "CRYPTOBOT_WEBHOOK_SECRET": "test",
    "SECRET_KEY": "x" * 64,
}.items():
    os.environ.setdefault(_k, _v)

# Importing the models package eagerly evaluates src.core.db.session, which calls
# get_settings() at import time — it may have been cached from .env (with the
# Docker hostname "postgres") before we set the env above. Drop that cache so
# Alembic's env.py rebuilds the DSN against the test database.
from src.core.config import get_settings as _get_settings

_get_settings.cache_clear()

_NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


async def _reset_schema() -> None:
    import asyncpg

    conn = await asyncpg.connect(
        host=_url.host or "127.0.0.1",
        port=_url.port or 5432,
        user=_url.username,
        password=_url.password,
        database=_url.database,
    )
    try:
        await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    finally:
        await conn.close()


@pytest.fixture(scope="session")
def _migrated_db() -> Iterator[None]:
    """Reset the schema and run migrations once per session (sync — no running loop)."""
    from alembic import command
    from alembic.config import Config

    try:
        asyncio.run(_reset_schema())
    except Exception as e:
        pytest.skip(f"Postgres test DB not available: {e}")

    command.upgrade(Config("alembic.ini"), "head")
    yield


@pytest.fixture
async def raw_engine(_migrated_db: None) -> AsyncIterator[object]:
    """A fresh engine for tests that manage their own connections/commits
    (e.g. concurrency tests that need committed data visible across sessions)."""
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def db_session(_migrated_db: None) -> AsyncIterator[AsyncSession]:
    """A session bound to a transaction that is rolled back after the test."""
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    conn = await engine.connect()
    trans = await conn.begin()
    session = AsyncSession(bind=conn, expire_on_commit=False, autoflush=False)
    try:
        yield session
    finally:
        await session.close()
        # A failed flush (e.g. an IntegrityError test) already rolled the
        # transaction back internally, leaving `trans` inactive.
        if trans.is_active:
            await trans.rollback()
        await conn.close()
        await engine.dispose()


@pytest.fixture
def make_db_issue() -> Callable[..., object]:
    """Factory for a valid ResourceIssue row (caller sets ids/amounts)."""
    from src.core.db.models import ResourceIssue
    from src.core.db.models.enums import IssueStatus

    counter = {"n": 0}

    def _make(**overrides: object) -> ResourceIssue:
        counter["n"] += 1
        n = counter["n"]
        defaults: dict[str, object] = {
            "link_id": f"lnk_int{n:020d}",
            "task_id": f"tsk_int{n:020d}",
            "status": IssueStatus.PENDING,
            "user_tg_id": 5000 + n,
            "reward_rub": Decimal("2.0000"),
            "publisher_payout_rub": Decimal("1.5000"),
            "platform_commission_rub": Decimal("0.5000"),
            "retention_bonus_rub": Decimal("0.0000"),
            "issued_at": _NOW,
            "expires_at": _NOW + timedelta(hours=1),
        }
        defaults.update(overrides)
        return ResourceIssue(**defaults)

    return _make


async def _build_graph(db_session: AsyncSession) -> SimpleNamespace:
    """Persist a minimal valid advertiser→campaign→resource + publisher→bot→token graph."""
    from src.core.db.models import (
        Advertiser,
        Campaign,
        CampaignResource,
        Publisher,
        PublisherApiToken,
        PublisherBot,
    )
    from src.core.db.models.enums import (
        CampaignStatus,
        ResourceStatus,
        ResourceType,
        VerificationMethod,
    )

    adv = Advertiser(
        tg_user_id=1001,
        balance_rub=Decimal("0.0000"),
        reserved_rub=Decimal("100.0000"),
        total_spent_rub=Decimal("0.0000"),
    )
    db_session.add(adv)
    await db_session.flush()

    camp = Campaign(
        advertiser_id=adv.id,
        title="Test campaign",
        status=CampaignStatus.ACTIVE,
        budget_total_rub=Decimal("100.0000"),
        budget_spent_rub=Decimal("0.0000"),
        budget_reserved_rub=Decimal("100.0000"),
        targeting={},
    )
    db_session.add(camp)
    await db_session.flush()

    res = CampaignResource(
        campaign_id=camp.id,
        type=ResourceType.CHANNEL,
        title="Test channel",
        reward_rub=Decimal("2.0000"),
        target_subscribers=1000,
        actual_subscribers=0,
        status=ResourceStatus.ACTIVE,
        verify_method=VerificationMethod.GET_CHAT_MEMBER,
    )
    db_session.add(res)
    await db_session.flush()

    pub = Publisher(
        tg_user_id=2002,
        project_name="Test publisher",
        balance_rub=Decimal("0.0000"),
        hold_rub=Decimal("0.0000"),
        total_earned_rub=Decimal("0.0000"),
        total_paid_out_rub=Decimal("0.0000"),
        verified_subs_in_window=0,
        total_subscriptions=0,
        total_unsubscriptions=0,
    )
    db_session.add(pub)
    await db_session.flush()

    bot = PublisherBot(publisher_id=pub.id, name="Test bot")
    db_session.add(bot)
    await db_session.flush()

    token = PublisherApiToken(
        publisher_id=pub.id,
        publisher_bot_id=bot.id,
        token_prefix="fsp_live_",
        token_hash="hash_" + "0" * 59,
        label="test",
    )
    db_session.add(token)
    await db_session.flush()

    return SimpleNamespace(
        advertiser=adv, campaign=camp, resource=res,
        publisher=pub, bot=bot, token=token,
    )


@pytest.fixture
def graph_builder() -> Callable[[AsyncSession], Awaitable[SimpleNamespace]]:
    """Expose the graph builder for tests that manage their own session."""
    return _build_graph


@pytest.fixture
async def seed(db_session: AsyncSession) -> SimpleNamespace:
    return await _build_graph(db_session)
