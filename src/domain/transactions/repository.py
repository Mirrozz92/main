"""Repository for Transaction (the ledger entry)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db.models import Transaction
from src.core.db.models.enums import TransactionStatus, TransactionType


class TransactionRepository:
    """Data-access for transactions ledger. Pure CRUD."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, tx_id: int) -> Transaction | None:
        result = await self.session.execute(
            select(Transaction).where(Transaction.id == tx_id)
        )
        return result.scalar_one_or_none()

    async def get_by_idempotency_key(self, key: str) -> Transaction | None:
        result = await self.session.execute(
            select(Transaction).where(Transaction.idempotency_key == key)
        )
        return result.scalar_one_or_none()

    async def get_by_external_id(
        self,
        external_id: str,
        *,
        tx_type: TransactionType | None = None,
    ) -> Transaction | None:
        stmt = select(Transaction).where(Transaction.external_id == external_id)
        if tx_type is not None:
            stmt = stmt.where(Transaction.type == tx_type)
        result = await self.session.execute(stmt.limit(1))
        return result.scalar_one_or_none()

    async def list_for_advertiser(
        self,
        advertiser_id: int,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Transaction]:
        stmt = (
            select(Transaction)
            .where(Transaction.advertiser_id == advertiser_id)
            .order_by(desc(Transaction.created_at))
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_publisher(
        self,
        publisher_id: int,
        *,
        limit: int = 10,
        offset: int = 0,
    ) -> list[Transaction]:
        result = await self.session.execute(
            select(Transaction)
            .where(Transaction.publisher_id == publisher_id)
            .order_by(desc(Transaction.created_at))
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def count_for_publisher(self, publisher_id: int) -> int:
        from sqlalchemy import func
        result = await self.session.execute(
            select(func.count(Transaction.id)).where(
                Transaction.publisher_id == publisher_id
            )
        )
        return result.scalar_one()

    async def count_for_advertiser(self, advertiser_id: int) -> int:
        stmt = (
            select(func.count(Transaction.id))
            .where(Transaction.advertiser_id == advertiser_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def create(
        self,
        *,
        type: TransactionType,
        amount_rub: Decimal,
        advertiser_id: int | None = None,
        publisher_id: int | None = None,
        campaign_id: int | None = None,
        resource_issue_link_id: str | None = None,
        external_id: str | None = None,
        description: str | None = None,
        meta: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        status: TransactionStatus = TransactionStatus.COMPLETED,
    ) -> Transaction:
        tx = Transaction(
            type=type,
            status=status,
            amount_rub=amount_rub,
            advertiser_id=advertiser_id,
            publisher_id=publisher_id,
            campaign_id=campaign_id,
            resource_issue_link_id=resource_issue_link_id,
            external_id=external_id,
            description=description,
            meta=meta or {},
            idempotency_key=idempotency_key,
        )
        self.session.add(tx)
        await self.session.flush()
        return tx

    async def mark_completed(self, tx: Transaction, *, at: datetime | None = None) -> None:
        tx.status = TransactionStatus.COMPLETED
        if at is not None:
            tx.updated_at = at

    async def mark_failed(self, tx: Transaction, *, reason: str | None = None) -> None:
        tx.status = TransactionStatus.FAILED
        if reason:
            tx.meta = {**(tx.meta or {}), "failure_reason": reason}

    async def list_pending_withdrawals(
        self,
        *,
        limit: int = 10,
        offset: int = 0,
    ) -> list[Transaction]:
        """Pending PUBLISHER_PAYOUT requests, FIFO (oldest first)."""
        from sqlalchemy import asc
        stmt = (
            select(Transaction)
            .where(
                (Transaction.type == TransactionType.PUBLISHER_PAYOUT)
                & (Transaction.status == TransactionStatus.PENDING)
            )
            .order_by(asc(Transaction.created_at))
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def sum_earned_for_publisher_windows(
        self,
        publisher_id: int,
        *,
        cutoff_1d: datetime,
        cutoff_7d: datetime,
        cutoff_30d: datetime,
    ) -> tuple[Decimal, Decimal, Decimal]:
        """Sum PUBLISHER_EARN amounts in three rolling windows.

        Returns (earned_1d, earned_7d, earned_30d).
        """
        row = (await self.session.execute(
            select(
                func.coalesce(
                    func.sum(case((Transaction.created_at >= cutoff_1d, Transaction.amount_rub))),
                    0,
                ).label("d1"),
                func.coalesce(
                    func.sum(case((Transaction.created_at >= cutoff_7d, Transaction.amount_rub))),
                    0,
                ).label("d7"),
                func.coalesce(func.sum(Transaction.amount_rub), 0).label("d30"),
            ).where(
                and_(
                    Transaction.publisher_id == publisher_id,
                    Transaction.type == TransactionType.PUBLISHER_EARN,
                    Transaction.status == TransactionStatus.COMPLETED,
                    Transaction.created_at >= cutoff_30d,
                )
            )
        )).one()
        return (
            Decimal(str(row.d1)),
            Decimal(str(row.d7)),
            Decimal(str(row.d30)),
        )

    async def count_pending_withdrawals(self) -> int:
        stmt = (
            select(func.count(Transaction.id))
            .where(
                (Transaction.type == TransactionType.PUBLISHER_PAYOUT)
                & (Transaction.status == TransactionStatus.PENDING)
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()
