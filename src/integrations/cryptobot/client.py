"""Async HTTP client for CryptoBot Crypto Pay API.

Docs: https://help.crypt.bot/crypto-pay-api
"""

from __future__ import annotations

import hashlib
import hmac
from decimal import Decimal
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.core.config import get_settings
from src.core.logging import get_logger
from src.domain.exceptions import CryptoBotError
from src.integrations.cryptobot.schemas import (
    AppInfo,
    Balance,
    CreateInvoiceRequest,
    ExchangeRate,
    Invoice,
    Transfer,
    TransferRequest,
)

log = get_logger("cryptobot")


class CryptoBotClient:
    """Async client for Crypto Pay API.

    Use as context manager or call .close() to release the HTTP session.
    """

    def __init__(
        self,
        token: str | None = None,
        api_url: str | None = None,
        timeout: float = 15.0,
    ) -> None:
        settings = get_settings()
        self._token = token or settings.cryptobot_token.get_secret_value()
        self._api_url = (api_url or settings.cryptobot_api_url).rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._api_url,
            timeout=timeout,
            headers={"Crypto-Pay-API-Token": self._token},
        )

    async def __aenter__(self) -> "CryptoBotClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        reraise=True,
    )
    async def _request(self, method: str, payload: dict | None = None) -> Any:
        """Low-level POST request.

        On success returns the `result` field. On failure raises CryptoBotError.
        """
        try:
            resp = await self._client.post(f"/{method}", json=payload or {})
        except httpx.TransportError as e:
            log.error("cryptobot_transport_error", method=method, error=str(e))
            raise

        # Try to parse JSON regardless of HTTP status (CryptoBot returns 200 with ok=false)
        try:
            data = resp.json()
        except Exception as e:
            log.error("cryptobot_non_json_response", method=method, status=resp.status_code, body=resp.text[:500])
            raise CryptoBotError(f"Invalid response from CryptoBot ({resp.status_code})") from e

        if not data.get("ok"):
            err = data.get("error", {})
            log.warning("cryptobot_api_error", method=method, error=err)
            raise CryptoBotError(f"CryptoBot: {err.get('name', 'unknown')} - {err.get('code', '')}")

        return data.get("result")

    # ---------- Public methods ----------

    async def get_me(self) -> AppInfo:
        """Test authentication and return app info."""
        result = await self._request("getMe")
        return AppInfo.model_validate(result)

    async def create_invoice(self, req: CreateInvoiceRequest) -> Invoice:
        """Create new invoice."""
        result = await self._request(
            "createInvoice",
            req.model_dump(exclude_none=True),
        )
        return Invoice.model_validate(result)

    async def get_invoices(
        self,
        *,
        invoice_ids: list[int] | None = None,
        status: str | None = None,
        offset: int = 0,
        count: int = 100,
    ) -> list[Invoice]:
        """Get invoices created by this app."""
        payload: dict[str, Any] = {"offset": offset, "count": count}
        if invoice_ids:
            payload["invoice_ids"] = ",".join(str(i) for i in invoice_ids)
        if status:
            payload["status"] = status

        result = await self._request("getInvoices", payload)
        items = result.get("items", []) if isinstance(result, dict) else []
        return [Invoice.model_validate(item) for item in items]

    async def delete_invoice(self, invoice_id: int) -> bool:
        """Delete invoice. Returns True on success."""
        result = await self._request("deleteInvoice", {"invoice_id": invoice_id})
        return bool(result)

    async def get_exchange_rates(self) -> list[ExchangeRate]:
        """Get current exchange rates table."""
        result = await self._request("getExchangeRates")
        if not isinstance(result, list):
            return []
        return [ExchangeRate.model_validate(item) for item in result]

    async def get_balance(self) -> list[Balance]:
        """Get app's balance across all assets."""
        result = await self._request("getBalance")
        if not isinstance(result, list):
            return []
        return [Balance.model_validate(item) for item in result]

    async def transfer(self, req: TransferRequest) -> Transfer:
        """Send coins from app's balance to a user.

        Requires the app to have transfer enabled and sufficient balance.
        spend_id makes this idempotent — repeating the same spend_id returns
        the same transfer instead of sending twice.
        """
        result = await self._request(
            "transfer",
            req.model_dump(exclude_none=True),
        )
        return Transfer.model_validate(result)

    async def get_rate(self, source: str, target: str) -> Decimal | None:
        """Get exchange rate source→target (e.g. USDT→RUB).

        Returns Decimal rate or None if pair not found / invalid.
        """
        rates = await self.get_exchange_rates()
        for r in rates:
            if r.source == source and r.target == target and r.is_valid:
                return r.rate_decimal
        return None

    async def rub_to_asset(self, rub_amount: Decimal, asset: str = "USDT") -> Decimal | None:
        """Convert RUB amount to asset amount using CryptoBot rates.

        rate is asset→RUB (e.g. 1 USDT = 95 RUB), so asset_amount = rub / rate.
        Returns asset amount rounded to 6 dp, or None if rate unavailable.
        """
        rate = await self.get_rate(asset, "RUB")
        if rate is None or rate <= 0:
            return None
        from decimal import ROUND_DOWN
        asset_amount = (rub_amount / rate).quantize(Decimal("0.000001"), rounding=ROUND_DOWN)
        return asset_amount


# ---------- Webhook signature verification ----------


def verify_webhook_signature(
    body: bytes,
    signature_header: str,
    *,
    app_token: str | None = None,
) -> bool:
    """Verify HMAC-SHA256 signature of CryptoBot webhook.

    Per docs: "the hexadecimal representation of HMAC-SHA-256 signature used
    to sign the entire request body (unparsed JSON string) with a secret key
    that is SHA256 hash of your app's token."

    Args:
        body: raw request body bytes
        signature_header: value of "crypto-pay-api-signature" header
        app_token: app token. Defaults to settings.cryptobot_token.

    Returns:
        True if signature is valid.
    """
    if not signature_header:
        return False

    token = app_token or get_settings().cryptobot_token.get_secret_value()
    secret = hashlib.sha256(token.encode()).digest()
    expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected.lower(), signature_header.lower())
