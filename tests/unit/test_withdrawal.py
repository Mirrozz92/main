"""Tests for WithdrawalService (src/domain/transactions/withdrawal_service.py).

Loaders and the tx repository are stubbed; these verify the balance/hold money
movement for submit / approve / reject against in-memory rows.

Note: test_reject_* would have caught the TransactionStatus.CANCELLED typo
(the enum member is CANCELED) that previously crashed payout rejection.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.core.db.models import Publisher, Transaction
from src.core.db.models.enums import TransactionStatus, TransactionType
from src.domain.transactions.withdrawal_service import (
    InsufficientBalanceError,
    WithdrawalError,
    WithdrawalService,
)

D = Decimal


def _service_for_processing(tx: Transaction, publisher: Publisher) -> WithdrawalService:
    """Service with _load_pending_withdrawal / _load_publisher stubbed."""
    svc = WithdrawalService(AsyncMock())
    svc._load_pending_withdrawal = AsyncMock(return_value=tx)  # type: ignore[method-assign]
    svc._load_publisher = AsyncMock(return_value=publisher)  # type: ignore[method-assign]
    return svc


class TestSubmit:
    async def test_submit_freezes_amount_and_creates_pending_tx(
        self,
        make_publisher: Callable[..., Publisher],
        fake_tx_repo: Any,
    ) -> None:
        publisher = make_publisher(balance_rub=D("100.0000"), hold_rub=D("0.0000"))
        svc = WithdrawalService(AsyncMock())
        svc.tx_repo = fake_tx_repo

        tx = await svc.submit(
            publisher=publisher, amount=D("30.0000"), method="card", recipient="123",
        )

        assert publisher.balance_rub == D("70.0000")
        assert publisher.hold_rub == D("30.0000")
        assert len(fake_tx_repo.created) == 1
        created = fake_tx_repo.created[0]
        assert created["type"] == TransactionType.PUBLISHER_PAYOUT
        assert created["amount_rub"] == D("-30.0000")  # stored negative
        assert created["status"] == TransactionStatus.PENDING
        assert tx.amount_rub == D("-30.0000")

    async def test_submit_insufficient_balance_raises(
        self, make_publisher: Callable[..., Publisher], fake_tx_repo: Any
    ) -> None:
        publisher = make_publisher(balance_rub=D("10.0000"))
        svc = WithdrawalService(AsyncMock())
        svc.tx_repo = fake_tx_repo
        with pytest.raises(InsufficientBalanceError):
            await svc.submit(publisher=publisher, amount=D("30.0000"), method="card", recipient="1")
        assert fake_tx_repo.created == []

    @pytest.mark.parametrize("amount", [D("0"), D("-5.0000")])
    async def test_submit_non_positive_raises(
        self, make_publisher: Callable[..., Publisher], fake_tx_repo: Any, amount: Decimal
    ) -> None:
        publisher = make_publisher(balance_rub=D("100.0000"))
        svc = WithdrawalService(AsyncMock())
        svc.tx_repo = fake_tx_repo
        with pytest.raises(WithdrawalError):
            await svc.submit(publisher=publisher, amount=amount, method="card", recipient="1")


class TestApprove:
    async def test_approve_removes_hold_and_completes(
        self,
        make_publisher: Callable[..., Publisher],
        make_payout_tx: Callable[..., Transaction],
    ) -> None:
        publisher = make_publisher(hold_rub=D("100.0000"), total_paid_out_rub=D("0.0000"))
        tx = make_payout_tx(amount_rub=D("-100.0000"))
        svc = _service_for_processing(tx, publisher)

        result = await svc.approve(tx_id=1, admin_tg_id=42)

        assert publisher.hold_rub == D("0.0000")
        assert publisher.total_paid_out_rub == D("100.0000")
        assert result.status == TransactionStatus.COMPLETED
        assert result.meta["processed_by_admin_tg_id"] == 42


class TestReject:
    async def test_reject_returns_hold_to_balance_and_cancels(
        self,
        make_publisher: Callable[..., Publisher],
        make_payout_tx: Callable[..., Transaction],
    ) -> None:
        publisher = make_publisher(hold_rub=D("100.0000"), balance_rub=D("0.0000"))
        tx = make_payout_tx(amount_rub=D("-100.0000"))
        svc = _service_for_processing(tx, publisher)

        result = await svc.reject(
            tx_id=1, admin_tg_id=42, admin_username="adm", reason="suspicious",
        )

        # Money returned from hold to spendable balance.
        assert publisher.hold_rub == D("0.0000")
        assert publisher.balance_rub == D("100.0000")
        # Status uses the real enum member CANCELED (not CANCELLED).
        assert result.status == TransactionStatus.CANCELED
        assert result.meta["reject_reason"] == "suspicious"
