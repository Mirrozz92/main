"""EndUser audience flags (premium, photo, username, bio, stories).

Revision ID: 0008
Revises: 0007
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, Sequence[str], None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Nullable booleans: NULL = "publisher didn't report this signal"
_FLAGS = [
    "has_telegram_premium",
    "has_profile_photo",
    "has_username",
    "has_bio",
    "has_stories",
]


def upgrade() -> None:
    for flag in _FLAGS:
        op.add_column(
            "end_users",
            sa.Column(flag, sa.Boolean(), nullable=True),
        )
    # When the audience signals were last reported by a publisher
    op.add_column(
        "end_users",
        sa.Column("audience_reported_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("end_users", "audience_reported_at")
    for flag in reversed(_FLAGS):
        op.drop_column("end_users", flag)
