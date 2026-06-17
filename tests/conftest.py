"""Shared pytest fixtures."""

from __future__ import annotations

import os

# Установим тестовое окружение ДО импорта приложения
os.environ.setdefault("ENV", "test")
