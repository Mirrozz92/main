"""Symmetric encryption for sensitive data stored in DB.

Used for: PublisherBot.tg_bot_token_encrypted (TG Bot API tokens given to us
by publishers for deep integration).

Key management:
- Key is generated once and stored in .env as FERNET_KEY (base64-encoded 32 bytes).
- If FERNET_KEY is missing, the module will raise on first use.
- Rotation: generate new key, re-encrypt all rows offline, swap key.
"""

from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from src.core.config import get_settings


class CryptoError(Exception):
    """Raised when encryption/decryption fails."""


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    settings = get_settings()
    if not settings.fernet_key:
        raise CryptoError(
            "FERNET_KEY is not set in environment. "
            "Generate one with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
        )
    key = settings.fernet_key.get_secret_value()
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception as e:
        raise CryptoError(f"Invalid FERNET_KEY (must be 32 url-safe base64-encoded bytes): {e}") from e


def encrypt(plaintext: str) -> bytes:
    """Encrypt a string, return ciphertext bytes (suitable for BYTEA column)."""
    if not plaintext:
        raise CryptoError("Cannot encrypt empty string")
    return _fernet().encrypt(plaintext.encode("utf-8"))


def decrypt(ciphertext: bytes) -> str:
    """Decrypt ciphertext bytes back to original string."""
    if not ciphertext:
        raise CryptoError("Cannot decrypt empty value")
    try:
        return _fernet().decrypt(ciphertext).decode("utf-8")
    except InvalidToken as e:
        raise CryptoError("Decryption failed: token invalid (wrong key or tampered data)") from e


def generate_key() -> str:
    """Helper: generate a new Fernet key (call once, store in .env)."""
    return Fernet.generate_key().decode("ascii")
