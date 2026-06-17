"""Pydantic models for CryptoBot Crypto Pay API.

API reference: https://help.crypt.bot/crypto-pay-api
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# --- Common ---

CryptoAsset = Literal["USDT", "TON", "BTC", "ETH", "LTC", "BNB", "TRX", "USDC"]
FiatCurrency = Literal["RUB", "USD", "EUR", "BYN", "UAH", "GBP", "CNY", "KZT", "UZS", "GEL", "TRY", "AMD", "THB", "INR", "BRL", "IDR", "AZN", "AED", "PLN", "ILS"]
InvoiceStatus = Literal["active", "paid", "expired"]
CurrencyType = Literal["crypto", "fiat"]
PaidBtnName = Literal["viewItem", "openChannel", "openBot", "callback"]


class CryptoBotResponse(BaseModel):
    """Generic API response wrapper."""

    model_config = ConfigDict(extra="allow")

    ok: bool
    result: dict | list | None = None
    error: dict | None = None


# --- getMe ---


class AppInfo(BaseModel):
    """Result of getMe."""

    model_config = ConfigDict(extra="allow")

    app_id: int
    name: str
    payment_processing_bot_username: str


# --- createInvoice ---


class CreateInvoiceRequest(BaseModel):
    """Parameters for createInvoice.

    Two modes:
    1. crypto: asset + amount (in crypto)
    2. fiat: currency_type='fiat' + fiat + amount (in RUB) + accepted_assets
    """

    model_config = ConfigDict(extra="allow")

    # Common
    amount: str  # always string per API
    description: str | None = None
    hidden_message: str | None = None
    paid_btn_name: PaidBtnName | None = None
    paid_btn_url: str | None = None
    payload: str | None = None  # up to 4096 chars, JSON string
    allow_comments: bool = True
    allow_anonymous: bool = True
    expires_in: int | None = None  # seconds (60..2_678_400)

    # Mode 1: crypto
    asset: CryptoAsset | None = None

    # Mode 2: fiat
    currency_type: CurrencyType | None = None
    fiat: FiatCurrency | None = None
    accepted_assets: str | None = None  # comma-separated, e.g. "USDT,TON"


class Invoice(BaseModel):
    """Invoice object returned by createInvoice / getInvoices."""

    model_config = ConfigDict(extra="allow")

    invoice_id: int
    hash: str
    currency_type: CurrencyType = "crypto"
    asset: str | None = None
    fiat: str | None = None
    amount: str  # Decimal-as-str

    # Payment links
    bot_invoice_url: str | None = None
    mini_app_invoice_url: str | None = None
    web_app_invoice_url: str | None = None
    pay_url: str | None = None  # legacy

    status: InvoiceStatus
    created_at: datetime
    paid_at: datetime | None = None
    expiration_date: datetime | None = None

    # Set after payment
    paid_asset: str | None = None
    paid_amount: str | None = None  # in crypto
    paid_fiat_rate: str | None = None
    paid_usd_rate: str | None = None

    description: str | None = None
    hidden_message: str | None = None
    payload: str | None = None
    paid_btn_name: str | None = None
    paid_btn_url: str | None = None

    @property
    def amount_decimal(self) -> Decimal:
        return Decimal(self.amount)

    @property
    def paid_amount_decimal(self) -> Decimal | None:
        return Decimal(self.paid_amount) if self.paid_amount else None


# --- Webhook ---


class WebhookUpdate(BaseModel):
    """Webhook update body from CryptoBot."""

    model_config = ConfigDict(extra="allow")

    update_id: int
    update_type: Literal["invoice_paid"]
    request_date: datetime
    payload: Invoice = Field(..., description="The Invoice object")


# --- getExchangeRates ---


class ExchangeRate(BaseModel):
    """One row of getExchangeRates."""

    model_config = ConfigDict(extra="allow")

    is_valid: bool
    source: str        # e.g. "USDT"
    target: str        # e.g. "RUB"
    rate: str          # decimal as string

    @property
    def rate_decimal(self) -> Decimal:
        return Decimal(self.rate)


# --- getBalance ---


class Balance(BaseModel):
    model_config = ConfigDict(extra="allow")

    currency_code: str
    available: str
    onhold: str


# --- transfer ---


class TransferRequest(BaseModel):
    """Params for POST /transfer."""

    user_id: int
    asset: str               # "USDT", "TON", etc.
    amount: str              # decimal as string
    spend_id: str            # idempotency key, <=64 chars
    comment: str | None = None
    disable_send_notification: bool | None = None


class Transfer(BaseModel):
    """Result of POST /transfer."""

    model_config = ConfigDict(extra="allow")

    transfer_id: int
    user_id: int
    asset: str
    amount: str
    status: str              # "completed"
    completed_at: str | None = None
    comment: str | None = None
    spend_id: str | None = None

    @property
    def amount_decimal(self) -> Decimal:
        return Decimal(self.amount)
