"""Payments service: create CryptoBot invoices and handle paid notifications.

Strategy (chosen for simplicity & UX):
- Invoice is created in RUB (fiat mode), with accepted_assets="USDT,TON".
- CryptoBot shows the user the equivalent in their chosen crypto, at the
  current CryptoBot rate. We never store crypto amounts in balances.
- On invoice_paid webhook → we credit the fiat amount in RUB to advertiser.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.db.models import Advertiser, Transaction
from src.core.db.models.enums import TransactionStatus, TransactionType
from src.core.logging import get_logger
from src.domain.advertisers import AdvertiserRepository
from src.domain.exceptions import CryptoBotError, DomainError
from src.domain.transactions import TransactionService
from src.integrations.cryptobot import CryptoBotClient, Invoice
from src.integrations.cryptobot.schemas import CreateInvoiceRequest, WebhookUpdate
from src.shared.idgen import generate_id
from src.shared.money import to_money

log = get_logger("payments")


class PaymentsService:
    """Business ops for top-ups and (later) payouts."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.adv_repo = AdvertiserRepository(session)
        self.tx_service = TransactionService(session)
        self.tx_repo = self.tx_service.repo

    # ---------- Top-up creation ----------

    async def create_topup_invoice(
        self,
        *,
        advertiser: Advertiser,
        amount_rub: Decimal,
        bot_username: str | None = None,
    ) -> tuple[Invoice, Transaction]:
        """Create a RUB invoice in CryptoBot (paid by USDT or TON).

        Also creates a PENDING transaction in our ledger so we can correlate the
        webhook callback. The transaction will be marked COMPLETED in
        handle_invoice_paid().

        Args:
            advertiser: who's topping up
            amount_rub: how much to credit (in RUB)
            bot_username: the bot's username (for paid_btn_url back to the bot)

        Returns:
            (invoice, pending_transaction)
        """
        settings = get_settings()

        if amount_rub < settings.min_campaign_topup_rub:
            raise DomainError(
                f"Минимальная сумма пополнения: {settings.min_campaign_topup_rub:.0f} ₽"
            )

        amount = to_money(amount_rub)

        # Internal payload: link this invoice back to advertiser & idempotency key
        idem_key = generate_id("idm")
        payload = json.dumps({
            "advertiser_id": advertiser.id,
            "idempotency_key": idem_key,
            "tg_user_id": advertiser.tg_user_id,
        })

        req = CreateInvoiceRequest(
            amount=str(amount),
            currency_type="fiat",
            fiat="RUB",
            accepted_assets="USDT,TON",
            description=f"Пополнение FastSub на {amount:.2f} ₽",
            payload=payload,
            allow_anonymous=False,
            allow_comments=False,
            expires_in=3 * 60 * 60,  # 3 hours
        )

        if bot_username:
            req.paid_btn_name = "openBot"
            req.paid_btn_url = f"https://t.me/{bot_username.lstrip('@')}"

        # Call CryptoBot
        try:
            async with CryptoBotClient() as cb:
                invoice = await cb.create_invoice(req)
        except CryptoBotError:
            raise
        except Exception as e:
            log.error("topup_invoice_create_failed", error=str(e))
            raise CryptoBotError("Не удалось создать счёт. Попробуйте позже.") from e

        # Pre-create a PENDING transaction so /balance shows "ожидает оплаты"
        # external_id = invoice_id (str), idempotency_key — наш сгенерированный
        tx = await self.tx_repo.create(
            type=TransactionType.ADVERTISER_TOPUP,
            amount_rub=amount,
            advertiser_id=advertiser.id,
            external_id=str(invoice.invoice_id),
            description=f"Ожидает оплаты счёта #{invoice.invoice_id}",
            meta={
                "invoice_hash": invoice.hash,
                "currency_type": invoice.currency_type,
                "fiat": invoice.fiat,
                "accepted_assets": "USDT,TON",
                "bot_invoice_url": invoice.bot_invoice_url,
            },
            idempotency_key=idem_key,
            status=TransactionStatus.PENDING,
        )
        log.info(
            "topup_invoice_created",
            advertiser_id=advertiser.id,
            amount=str(amount),
            invoice_id=invoice.invoice_id,
            tx_id=tx.id,
        )
        return invoice, tx

    # ---------- Webhook: invoice_paid ----------

    async def handle_invoice_paid(self, update: WebhookUpdate) -> dict[str, Any]:
        """Handle invoice_paid webhook from CryptoBot.

        Steps:
        1. Find the pending Transaction by external_id (invoice_id).
        2. Validate amount/advertiser from invoice.payload.
        3. Credit the balance and mark transaction COMPLETED.
        4. Return info dict to be used for notification.

        Returns a dict with `advertiser_tg_id` and `amount_rub` for notify caller.
        Returns empty dict if already processed.
        """
        invoice = update.payload

        if invoice.status != "paid":
            log.warning("webhook_invoice_not_paid", invoice_id=invoice.invoice_id, status=invoice.status)
            return {}

        # Parse our payload (which we set during createInvoice)
        meta_payload: dict[str, Any] = {}
        if invoice.payload:
            try:
                meta_payload = json.loads(invoice.payload)
            except Exception as e:
                log.error(
                    "webhook_invalid_payload",
                    invoice_id=invoice.invoice_id,
                    payload=invoice.payload[:200] if invoice.payload else None,
                    error=str(e),
                )
                return {}

        advertiser_id = meta_payload.get("advertiser_id")
        idempotency_key = meta_payload.get("idempotency_key")
        tg_user_id = meta_payload.get("tg_user_id")

        if not advertiser_id or not idempotency_key:
            log.error(
                "webhook_missing_advertiser_or_key",
                invoice_id=invoice.invoice_id,
                payload_keys=list(meta_payload.keys()),
            )
            return {}

        advertiser = await self.adv_repo.get_by_id(int(advertiser_id))
        if advertiser is None:
            log.error("webhook_advertiser_not_found", invoice_id=invoice.invoice_id, advertiser_id=advertiser_id)
            return {}

        # Find the pending tx and update it. We don't use credit_advertiser_topup's
        # idempotency check directly because we want to update the EXISTING row.
        existing_tx = await self.tx_repo.get_by_idempotency_key(idempotency_key)

        # Amount in RUB — берём из invoice.amount (т.к. инвойс был выставлен в RUB)
        # Если по каким-то причинам currency_type не "fiat" — это аномалия, логируем
        if invoice.currency_type != "fiat":
            log.warning(
                "webhook_non_fiat_invoice",
                invoice_id=invoice.invoice_id,
                currency_type=invoice.currency_type,
            )
        amount_rub = to_money(invoice.amount)

        if existing_tx is None:
            # Не нашли pending — создаём как новую (на случай если webhook пришёл раньше нашей записи)
            log.warning(
                "webhook_no_pending_tx_creating_new",
                invoice_id=invoice.invoice_id,
                idempotency_key=idempotency_key,
            )
            advertiser.balance_rub = advertiser.balance_rub + amount_rub
            await self.tx_repo.create(
                type=TransactionType.ADVERTISER_TOPUP,
                amount_rub=amount_rub,
                advertiser_id=advertiser.id,
                external_id=str(invoice.invoice_id),
                description=f"Пополнение через CryptoBot, счёт #{invoice.invoice_id}",
                meta={
                    "invoice_hash": invoice.hash,
                    "paid_asset": invoice.paid_asset,
                    "paid_amount": invoice.paid_amount,
                    "paid_fiat_rate": invoice.paid_fiat_rate,
                },
                idempotency_key=idempotency_key,
                status=TransactionStatus.COMPLETED,
            )
        elif existing_tx.status == TransactionStatus.COMPLETED:
            log.info(
                "webhook_duplicate_paid",
                invoice_id=invoice.invoice_id,
                tx_id=existing_tx.id,
            )
            return {}  # idempotent: ничего не делаем
        else:
            # PENDING → COMPLETED. Credit balance.
            advertiser.balance_rub = advertiser.balance_rub + amount_rub
            existing_tx.status = TransactionStatus.COMPLETED
            existing_tx.description = f"Пополнение через CryptoBot, счёт #{invoice.invoice_id}"
            existing_tx.meta = {
                **(existing_tx.meta or {}),
                "paid_asset": invoice.paid_asset,
                "paid_amount": invoice.paid_amount,
                "paid_fiat_rate": invoice.paid_fiat_rate,
            }

        log.info(
            "topup_completed",
            advertiser_id=advertiser.id,
            amount=str(amount_rub),
            invoice_id=invoice.invoice_id,
            paid_asset=invoice.paid_asset,
            paid_amount=invoice.paid_amount,
        )

        return {
            "advertiser_tg_id": int(tg_user_id) if tg_user_id else advertiser.tg_user_id,
            "amount_rub": amount_rub,
            "invoice_id": invoice.invoice_id,
            "paid_asset": invoice.paid_asset or "",
            "paid_amount": invoice.paid_amount or "",
        }
