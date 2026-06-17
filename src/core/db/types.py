"""SQLAlchemy custom types and helpers."""

from __future__ import annotations

import enum
from typing import Any

from sqlalchemy import Enum as SQLEnum


def pg_enum(enum_class: type[enum.Enum], name: str) -> SQLEnum:
    """Create a PostgreSQL Enum that uses VALUES (not Python names).

    Without values_callable, SQLAlchemy serializes 'CampaignStatus.DRAFT' as
    'DRAFT' (the member NAME), but our DB stores 'draft' (the member VALUE).
    This helper makes them match.
    """
    return SQLEnum(
        enum_class,
        name=name,
        values_callable=lambda e: [m.value for m in e],
        native_enum=True,
        create_type=False,  # types created by migration
    )
