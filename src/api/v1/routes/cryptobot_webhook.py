"""CryptoBot webhook endpoint.

Receives invoice_paid updates from CryptoBot, verifies HMAC signature,
credits the advertiser's balance, and enqueues a notification.
"""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request

from src.core.db import async_session_factory
from src.core.logging import get_logger
from src.domain.payments import PaymentsService
from src.integrations.cryptobot import verify_webhook_signature
from src.integrations.cryptobot.schemas import WebhookUpdate
from src.workers.notifications import notify_topup_success

router = APIRouter(prefix="/cryptobot", tags=["cryptobot"])
log = get_logger("api.cryptobot_webhook")


@router.post("/webhook")
async def cryptobot_webhook(
    request: Request,
    crypto_pay_api_signature: str | None = Header(default=None, alias="crypto-pay-api-signature"),
) -> dict[str, str]:
    """Handle CryptoBot webhook (invoice_paid).

    Per CryptoBot docs: HMAC-SHA256 of raw body, signed with SHA256(app_token)
    as the secret. We return 200 quickly on success, retry otherwise.
    """
    body = await request.body()

    if not crypto_pay_api_signature:
        log.warning("cryptobot_webhook_no_signature")
        raise HTTPException(status_code=401, detail="missing signature")

    if not verify_webhook_signature(body, crypto_pay_api_signature):
        log.warning("cryptobot_webhook_bad_signature", body_len=len(body))
        raise HTTPException(status_code=401, detail="bad signature")

    try:
        update = WebhookUpdate.model_validate_json(body)
    except Exception as e:
        log.error("cryptobot_webhook_parse_error", error=str(e))
        raise HTTPException(status_code=400, detail="invalid payload") from e

    log.info(
        "cryptobot_webhook_received",
        update_type=update.update_type,
        invoice_id=update.payload.invoice_id,
        status=update.payload.status,
        amount=update.payload.amount,
    )

    # Process the paid invoice → credit advertiser balance
    async with async_session_factory() as session:
        try:
            svc = PaymentsService(session)
            result = await svc.handle_invoice_paid(update)
            await session.commit()
        except Exception as e:
            await session.rollback()
            log.error("topup_processing_failed", invoice_id=update.payload.invoice_id, error=str(e))
            # Return 500 → CryptoBot will retry. This is safe because of idempotency.
            raise HTTPException(status_code=500, detail="processing failed") from e

    # Если ничего не обработали (дубль или ошибка валидации) — просто отвечаем ok
    if not result:
        return {"status": "ok"}

    # Enqueue notification to TaskIQ (non-blocking)
    try:
        await notify_topup_success.kiq(
            tg_user_id=result["advertiser_tg_id"],
            amount_rub=str(result["amount_rub"]),
            invoice_id=result["invoice_id"],
            paid_asset=result.get("paid_asset", ""),
            paid_amount=result.get("paid_amount", ""),
        )
    except Exception as e:
        # Уведомление не критично — баланс уже зачислен
        log.warning("notification_enqueue_failed", error=str(e))

    return {"status": "ok"}
