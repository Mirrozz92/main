"""Withdrawal service — atomic money movement for publisher payout flow.

Stage 3d (Variant с заморозкой в hold_rub):

submit():
    publisher.balance_rub -= amount
    publisher.hold_rub += amount
    Tx { type=PUBLISHER_PAYOUT, amount=-amount, status=pending,
         publisher_id=..., meta={method, recipient} }

approve(admin_id):
    publisher.hold_rub -= amount             # деньги ушли админу из FastSub
    tx.status = completed
    tx.meta.processed_by_admin_id = admin_id
    tx.meta.processed_at = now

reject(admin_id, reason):
    publisher.hold_rub -= amount             # возврат
    publisher.balance_rub += amount          # на основной баланс
    tx.status = cancelled
    tx.meta.processed_by_admin_id = admin_id
    tx.meta.reject_reason = reason

All operations are session-scoped. Caller commits.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db.models import Publisher, Transaction
from src.core.db.models.enums import TransactionStatus, TransactionType
from src.core.logging import get_logger
from src.domain.exceptions import DomainError
from src.domain.transactions.repository import TransactionRepository

log = get_logger("withdrawals.service")


class WithdrawalError(DomainError):
    """Base for withdrawal-related domain errors."""


class InsufficientBalanceError(WithdrawalError):
    user_message = "Недостаточно средств на балансе."


class WithdrawalNotFoundError(WithdrawalError):
    user_message = "Заявка не найдена."


class WithdrawalAlreadyProcessedError(WithdrawalError):
    user_message = "Эта заявка уже обработана."


class AutoPayoutError(WithdrawalError):
    """CryptoBot transfer failed — заявка остаётся pending."""
    user_message = "Не удалось выполнить автоматическую выплату."


class WithdrawalService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.tx_repo = TransactionRepository(session)

    async def submit(
        self,
        *,
        publisher: Publisher,
        amount: Decimal,
        method: str,
        recipient: str,
    ) -> Transaction:
        """Create a pending withdrawal request and freeze the amount.

        Atomically:
          publisher.balance_rub -= amount
          publisher.hold_rub += amount
          Create PUBLISHER_PAYOUT Tx with status=pending.
        """
        if amount <= 0:
            raise WithdrawalError("Сумма должна быть положительной.")
        if publisher.balance_rub < amount:
            raise InsufficientBalanceError()

        publisher.balance_rub = publisher.balance_rub - amount
        publisher.hold_rub = publisher.hold_rub + amount

        tx = await self.tx_repo.create(
            type=TransactionType.PUBLISHER_PAYOUT,
            amount_rub=-amount,
            publisher_id=publisher.id,
            description=(
                f"Заявка на вывод {amount:.2f} ₽ ({method}: {recipient})"
            ),
            status=TransactionStatus.PENDING,
            meta={
                "method": method,
                "recipient": recipient,
                "requested_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        log.info(
            "withdrawal_submitted",
            tx_id=tx.id, publisher_id=publisher.id,
            amount=str(amount), method=method,
        )
        return tx

    async def approve(
        self,
        *,
        tx_id: int,
        admin_tg_id: int,
        admin_username: str | None = None,
    ) -> Transaction:
        """Mark withdrawal as paid out. Removes amount from hold_rub permanently."""
        tx = await self._load_pending_withdrawal(tx_id)
        publisher = await self._load_publisher(tx.publisher_id)
        amount = -tx.amount_rub  # tx amount is negative

        if publisher.hold_rub < amount:
            # Shouldn't happen, but defensive
            log.warning(
                "publisher_hold_underflow_on_approve",
                publisher_id=publisher.id,
                hold=str(publisher.hold_rub), amount=str(amount),
            )
            publisher.hold_rub = Decimal("0")
        else:
            publisher.hold_rub = publisher.hold_rub - amount

        publisher.total_paid_out_rub = publisher.total_paid_out_rub + amount

        # Update tx
        tx.status = TransactionStatus.COMPLETED
        meta = dict(tx.meta or {})
        meta["processed_by_admin_tg_id"] = admin_tg_id
        if admin_username:
            meta["processed_by_admin_username"] = admin_username
        meta["processed_at"] = datetime.now(timezone.utc).isoformat()
        tx.meta = meta

        log.info(
            "withdrawal_approved",
            tx_id=tx.id, publisher_id=publisher.id,
            amount=str(amount), admin_tg_id=admin_tg_id,
        )
        return tx

    async def approve_auto(
        self,
        *,
        tx_id: int,
        admin_tg_id: int,
        admin_username: str | None = None,
        asset: str = "USDT",
    ) -> Transaction:
        """Auto-payout via CryptoBot Transfer API.

        Flow:
          1. Load pending withdrawal + publisher (locked)
          2. Convert RUB → asset via CryptoBot rates
          3. Call transfer (idempotent spend_id = fastsub_payout_<tx_id>)
          4. On success → same financial effect as approve()
          5. On failure → raise AutoPayoutError, tx STAYS pending (no money moved)

        IMPORTANT: We do NOT mutate balances until the transfer succeeds.
        """
        from src.integrations.cryptobot import CryptoBotClient
        from src.integrations.cryptobot.schemas import TransferRequest
        from src.domain.exceptions import CryptoBotError

        tx = await self._load_pending_withdrawal(tx_id)
        publisher = await self._load_publisher(tx.publisher_id)
        amount_rub = -tx.amount_rub

        # Recipient: use publisher's telegram user id (CryptoBot transfers by user_id)
        recipient_tg_id = publisher.tg_user_id
        if not recipient_tg_id:
            raise AutoPayoutError("У паблишера не указан Telegram ID.")

        # Convert + transfer
        client = CryptoBotClient()
        try:
            asset_amount = await client.rub_to_asset(amount_rub, asset)
            if asset_amount is None or asset_amount <= 0:
                raise AutoPayoutError(f"Не удалось получить курс {asset}/RUB.")

            spend_id = f"fastsub_payout_{tx.id}"
            transfer = await client.transfer(TransferRequest(
                user_id=recipient_tg_id,
                asset=asset,
                amount=str(asset_amount),
                spend_id=spend_id,
            ))
        except CryptoBotError as e:
            log.warning(
                "auto_payout_cryptobot_error",
                tx_id=tx.id, error=str(e),
            )
            raise AutoPayoutError(f"CryptoBot: {e}")
        except AutoPayoutError:
            raise
        except Exception as e:
            log.error("auto_payout_unexpected_error", tx_id=tx.id, error=str(e))
            raise AutoPayoutError(f"Ошибка перевода: {e}")
        finally:
            await client.close()

        # Transfer succeeded → apply financial effect (same as manual approve)
        if publisher.hold_rub < amount_rub:
            log.warning(
                "publisher_hold_underflow_on_auto_approve",
                publisher_id=publisher.id,
                hold=str(publisher.hold_rub), amount=str(amount_rub),
            )
            publisher.hold_rub = Decimal("0")
        else:
            publisher.hold_rub = publisher.hold_rub - amount_rub

        publisher.total_paid_out_rub = publisher.total_paid_out_rub + amount_rub

        tx.status = TransactionStatus.COMPLETED
        meta = dict(tx.meta or {})
        meta["processed_by_admin_tg_id"] = admin_tg_id
        if admin_username:
            meta["processed_by_admin_username"] = admin_username
        meta["processed_at"] = datetime.now(timezone.utc).isoformat()
        meta["auto_payout"] = True
        meta["cryptobot_transfer_id"] = transfer.transfer_id
        meta["asset"] = asset
        meta["asset_amount"] = str(asset_amount)
        tx.meta = meta

        log.info(
            "withdrawal_auto_approved",
            tx_id=tx.id, publisher_id=publisher.id,
            amount_rub=str(amount_rub), asset=asset, asset_amount=str(asset_amount),
            transfer_id=transfer.transfer_id, admin_tg_id=admin_tg_id,
        )
        return tx

    async def reject(
        self,
        *,
        tx_id: int,
        admin_tg_id: int,
        admin_username: str | None,
        reason: str,
    ) -> Transaction:
        """Reject the withdrawal: return amount from hold to balance."""
        tx = await self._load_pending_withdrawal(tx_id)
        publisher = await self._load_publisher(tx.publisher_id)
        amount = -tx.amount_rub

        if publisher.hold_rub < amount:
            log.warning(
                "publisher_hold_underflow_on_reject",
                publisher_id=publisher.id,
                hold=str(publisher.hold_rub), amount=str(amount),
            )
            publisher.hold_rub = Decimal("0")
        else:
            publisher.hold_rub = publisher.hold_rub - amount

        publisher.balance_rub = publisher.balance_rub + amount

        tx.status = TransactionStatus.CANCELLED
        meta = dict(tx.meta or {})
        meta["processed_by_admin_tg_id"] = admin_tg_id
        if admin_username:
            meta["processed_by_admin_username"] = admin_username
        meta["processed_at"] = datetime.now(timezone.utc).isoformat()
        meta["reject_reason"] = reason[:500]
        tx.meta = meta

        log.info(
            "withdrawal_rejected",
            tx_id=tx.id, publisher_id=publisher.id,
            amount=str(amount), admin_tg_id=admin_tg_id,
            reason=reason[:80],
        )
        return tx

    # --- Internal ---

    async def _load_pending_withdrawal(self, tx_id: int) -> Transaction:
        result = await self.session.execute(
            select(Transaction).where(Transaction.id == tx_id).with_for_update()
        )
        tx = result.scalar_one_or_none()
        if tx is None:
            raise WithdrawalNotFoundError()
        if tx.type != TransactionType.PUBLISHER_PAYOUT:
            raise WithdrawalNotFoundError()
        if tx.status != TransactionStatus.PENDING:
            raise WithdrawalAlreadyProcessedError()
        return tx

    async def _load_publisher(self, publisher_id: int | None) -> Publisher:
        if publisher_id is None:
            raise WithdrawalError("Заявка повреждена: нет publisher_id.")
        result = await self.session.execute(
            select(Publisher).where(Publisher.id == publisher_id).with_for_update()
        )
        publisher = result.scalar_one_or_none()
        if publisher is None:
            raise WithdrawalError(f"Паблишер {publisher_id} не найден.")
        return publisher
