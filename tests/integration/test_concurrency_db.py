"""Concurrency integration test: the worker row-claim queries use
SELECT ... FOR UPDATE SKIP LOCKED so two workers never grab the same row.

This needs committed data visible across independent connections, so it manages
its own sessions (not the rolled-back db_session fixture) and truncates after.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.db.models import ResourceIssue
from src.domain.issues import ResourceIssueRepository


async def test_skip_locked_claims_are_disjoint(
    raw_engine: AsyncEngine,
    graph_builder: Callable[[AsyncSession], Awaitable[SimpleNamespace]],
    make_db_issue: Callable[..., ResourceIssue],
) -> None:
    # 1. Commit a graph + 4 expired-pending issues (default issued/expires are in
    #    the past, status PENDING → eligible for list_expired_pending).
    link_ids: set[str] = set()
    async with AsyncSession(raw_engine, expire_on_commit=False) as setup:
        g = await graph_builder(setup)
        for _ in range(4):
            issue = make_db_issue(
                publisher_id=g.publisher.id,
                publisher_token_id=g.token.id,
                publisher_bot_id=g.bot.id,
                campaign_resource_id=g.resource.id,
            )
            setup.add(issue)
            link_ids.add(issue.link_id)
        await setup.commit()

    try:
        # 2. Worker A and worker B claim batches in separate open transactions.
        conn_a = await raw_engine.connect()
        conn_b = await raw_engine.connect()
        conn_c = await raw_engine.connect()
        try:
            await conn_a.begin()
            await conn_b.begin()
            await conn_c.begin()
            repo_a = ResourceIssueRepository(AsyncSession(bind=conn_a))
            repo_b = ResourceIssueRepository(AsyncSession(bind=conn_b))
            repo_c = ResourceIssueRepository(AsyncSession(bind=conn_c))

            claimed_a = {i.link_id for i in await repo_a.list_expired_pending(limit=2)}
            # B runs while A still holds its locks → must skip A's rows.
            claimed_b = {i.link_id for i in await repo_b.list_expired_pending(limit=2)}
            # All four are now locked → C gets nothing.
            claimed_c = await repo_c.list_expired_pending(limit=10)

            assert len(claimed_a) == 2
            assert len(claimed_b) == 2
            assert claimed_a.isdisjoint(claimed_b)      # no double-claim
            assert claimed_a | claimed_b == link_ids    # together cover all, once
            assert claimed_c == []                       # everything already locked
        finally:
            await conn_a.rollback()
            await conn_b.rollback()
            await conn_c.rollback()
            await conn_a.close()
            await conn_b.close()
            await conn_c.close()
    finally:
        # Clean up the committed rows so other tests start from an empty schema.
        async with raw_engine.begin() as conn:
            await conn.exec_driver_sql(
                "TRUNCATE advertisers, publishers RESTART IDENTITY CASCADE"
            )
