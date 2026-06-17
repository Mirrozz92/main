"""Periodic retention rate recalculation for all publishers.

Runs once per hour. For each publisher whose `retention_calculated_at` is
older than 1 hour (or null), recompute over a rolling 30-day window.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select

from src.core.db import async_session_factory
from src.core.db.models import Publisher
from src.core.logging import get_logger
from src.domain.publishers.retention import recompute_for_publisher
from src.workers.broker import broker

log = get_logger("workers.retention")


@broker.task(
    schedule=[{"cron": "0 * * * *"}],  # every hour at :00
    task_name="recompute_publisher_retention",
)
async def recompute_publisher_retention(batch_size: int = 100) -> dict:
    """Recompute retention_rate for publishers stale or never computed."""
    stale_cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    processed = 0

    async with async_session_factory() as session:
        try:
            result = await session.execute(
                select(Publisher).where(
                    or_(
                        Publisher.retention_calculated_at.is_(None),
                        Publisher.retention_calculated_at < stale_cutoff,
                    )
                ).limit(batch_size)
            )
            publishers = list(result.scalars().all())

            for pub in publishers:
                await recompute_for_publisher(session, pub)
                processed += 1

            await session.commit()
        except Exception as e:
            await session.rollback()
            log.error("retention_recompute_failed", error=str(e))
            raise

    if processed:
        log.info("retention_recomputed_batch", count=processed)
    return {"processed": processed}
