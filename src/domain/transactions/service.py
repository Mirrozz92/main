"""Service layer for transactions (double-entry ledger).

All money movements in the system go through here. Each call:
- Updates the balance(s) atomically
- Creates a Transaction row for audit

The session passed in MUST be inside an active transaction; commit/rollback
is the caller's responsibility.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db.models import Advertiser, Transaction
from src.core.db.models.enums import TransactionStatus, TransactionType
from src.core.logging import get_logger
from src.domain.transactions.repository import TransactionRepository

log = get_logger("transactions")


class TransactionService:
    """Business operations on the ledger."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = TransactionRepository(session)

    # ---------- Advertiser side ----------

    async def credit_advertiser_topup(
        self,
        *,
        advertiser: Advertiser,
        amount_rub: Decimal,
        external_id: str,
        idempotency_key: str,
        description: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> Transaction | None:
        """Crediting advertiser balance from a CryptoBot top-up.

        Idempotent: if a transaction with the same idempotency_key already exists
        in COMPLETED status, returns None (caller should treat as already-applied).

        Returns the new Transaction on success.
        """
        if amount_rub <= 0:
            raise ValueError("amount_rub must be positive")

        # Idempotency check
        existing = await self.repo.get_by_idempotency_key(idempotency_key)
        if existing is not None:
            if existing.status == TransactionStatus.COMPLETED:
                log.info(
                    "topup_already_applied",
                    advertiser_id=advertiser.id,
                    idempotency_key=idempotency_key,
                    tx_id=existing.id,
                )
                return None
            # If it's PENDING / FAILED — we'll overwrite via update below
            # but easier path is to mark it completed and move on:
            log.warning(
                "topup_existing_non_completed",
                tx_id=existing.id,
                status=existing.status,
            )

        # Credit balance
        advertiser.balance_rub = advertiser.balance_rub + amount_rub

        # Create completed transaction
        tx = await self.repo.create(
            type=TransactionType.ADVERTISER_TOPUP,
            amount_rub=amount_rub,
            advertiser_id=advertiser.id,
            external_id=external_id,
            description=description,
            meta=meta,
            idempotency_key=idempotency_key,
            status=TransactionStatus.COMPLETED,
        )
        log.info(
            "topup_applied",
            advertiser_id=advertiser.id,
            amount=str(amount_rub),
            tx_id=tx.id,
            external_id=external_id,
        )
        return tx
