"""Tests for src/shared/idgen.py."""

from __future__ import annotations

import re

import pytest

from src.shared.idgen import generate_id, hash_api_token, token_prefix


class TestGenerateId:
    @pytest.mark.parametrize(
        "prefix,expected_total_len",
        [
            ("lnk", 4 + 24),   # "lnk_" + 24 hex
            ("tsk", 4 + 24),
            ("inv", 4 + 16),
            ("ref", 4 + 12),
            ("fs", 3 + 48),
            ("whs", 4 + 32),
            ("idm", 4 + 32),
        ],
    )
    def test_length(self, prefix: str, expected_total_len: int) -> None:
        ident = generate_id(prefix)
        assert len(ident) == expected_total_len
        assert ident.startswith(f"{prefix}_")

    def test_unique(self) -> None:
        ids = {generate_id("lnk") for _ in range(1000)}
        assert len(ids) == 1000

    def test_hex_only(self) -> None:
        ident = generate_id("lnk")
        body = ident.split("_", 1)[1]
        assert re.fullmatch(r"[0-9a-f]+", body) is not None

    def test_unknown_prefix(self) -> None:
        with pytest.raises(ValueError):
            generate_id("unknown")


class TestHashApiToken:
    def test_deterministic(self) -> None:
        token = "fs_abc123"
        assert hash_api_token(token) == hash_api_token(token)

    def test_different_tokens_different_hashes(self) -> None:
        assert hash_api_token("a") != hash_api_token("b")

    def test_hash_length(self) -> None:
        # SHA-256 = 64 hex chars
        assert len(hash_api_token("anything")) == 64


class TestTokenPrefix:
    def test_default(self) -> None:
        assert token_prefix("fs_abcdef1234567890") == "fs_abcdef123"

    def test_custom_len(self) -> None:
        assert token_prefix("fs_abcdef", chars=5) == "fs_ab"
