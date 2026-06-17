"""Smoke test that the integration harness (migrations + seed graph) works."""

from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db.models import Publisher


async def test_seed_graph_persists(seed: SimpleNamespace, db_session: AsyncSession) -> None:
    # Flushing the graph assigned primary keys across the FK chain.
    assert seed.advertiser.id is not None
    assert seed.campaign.advertiser_id == seed.advertiser.id
    assert seed.resource.campaign_id == seed.campaign.id
    assert seed.token.publisher_bot_id == seed.bot.id

    # And the rows are queryable within the test transaction.
    pub = (
        await db_session.execute(
            select(Publisher).where(Publisher.id == seed.publisher.id)
        )
    ).scalar_one()
    assert pub.project_name == "Test publisher"
