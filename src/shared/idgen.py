"""ID generation helpers.

Все наши публичные идентификаторы — короткие, urlsafe, человекочитаемые префиксами.
"""

from __future__ import annotations

import hashlib
import secrets

# Prefix → длина случайной части (hex chars)
PREFIXES: dict[str, int] = {
    "lnk": 24,    # resource_issues.link_id    → "lnk_<24hex>"     (32 chars)
    "tsk": 24,    # task_id                    → "tsk_<24hex>"     (32 chars)
    "inv": 16,    # invite link name suffix    → "inv_<16hex>"     (20 chars)
    "ref": 12,    # start_param for bot ads    → "ref_<12hex>"     (16 chars)
    "fs":  48,    # publisher API token        → "fs_<48hex>"      (51 chars)
    "whs": 32,    # webhook secret             → "whs_<32hex>"     (36 chars)
    "idm": 32,    # idempotency key            → "idm_<32hex>"     (36 chars)
}


def generate_id(prefix: str) -> str:
    """Generate a new ID with the given prefix.

    >>> generate_id("lnk")  # doctest: +SKIP
    'lnk_a1b2c3d4...'
    """
    if prefix not in PREFIXES:
        raise ValueError(f"Unknown ID prefix: {prefix!r}")
    length = PREFIXES[prefix]
    # secrets.token_hex(n) -> 2n hex chars; делим на 2 чтобы получить нужную длину
    body = secrets.token_hex(length // 2)
    return f"{prefix}_{body}"


def hash_api_token(token: str) -> str:
    """Return SHA-256 hex digest of an API token, for storage in DB."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_prefix(token: str, chars: int = 12) -> str:
    """Return a short prefix of a token, for display purposes only."""
    return token[:chars]
