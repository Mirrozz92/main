"""Publisher rating (0..10 float).

Revision ID: 0007
Revises: 0006
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, Sequence[str], None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rating 0.0..10.0, default cold-start 8.0
    op.add_column(
        "publishers",
        sa.Column(
            "rating",
            sa.Numeric(3, 1),
            nullable=False,
            server_default="8.0",
        ),
    )
    op.add_column(
        "publishers",
        sa.Column(
            "rating_calculated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    # Total verified subscriptions across all time (for volume score)
    op.add_column(
        "publishers",
        sa.Column(
            "verified_subs_total",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("publishers", "verified_subs_total")
    op.drop_column("publishers", "rating_calculated_at")
    op.drop_column("publishers", "rating")
