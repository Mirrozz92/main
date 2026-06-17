"""Smoke test for src/core/config.py."""

from __future__ import annotations

import os

import pytest

from src.core.config import Settings


def _base_env() -> dict[str, str]:
    """Минимальный набор переменных для валидного Settings."""
    return {
        "POSTGRES_HOST": "localhost",
        "POSTGRES_DB": "test",
        "POSTGRES_USER": "test",
        "POSTGRES_PASSWORD": "test",
        "REDIS_PASSWORD": "test",
        "ADVERTISER_BOT_TOKEN": "fake:token",
        "ADMIN_BOT_TOKEN": "fake:token",
        "CHECKER_BOT_TOKENS": '["fake:token"]',
        "CRYPTOBOT_TOKEN": "fake",
        "CRYPTOBOT_WEBHOOK_SECRET": "fake",
        "SECRET_KEY": "x" * 64,
        "ADMIN_USERNAMES": "nklabs,otheradmin",
    }


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    e = _base_env()
    for k, v in e.items():
        monkeypatch.setenv(k, v)
    return e


class TestSettings:
    def test_loads(self, env: dict[str, str]) -> None:
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.postgres_db == "test"
        assert s.admin_usernames == ["nklabs", "otheradmin"]
        assert len(s.checker_bot_tokens) == 1

    def test_dsn_format(self, env: dict[str, str]) -> None:
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.postgres_dsn.startswith("postgresql+asyncpg://")
        assert "/test" in s.postgres_dsn

    def test_admin_username_strips_at(self, env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ADMIN_USERNAMES", "@nklabs,@another")
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.admin_usernames == ["nklabs", "another"]
