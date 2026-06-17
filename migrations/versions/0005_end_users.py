"""Add end_users table for partner bot users onboarding.

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-15
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "end_users",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("user_tg_id", sa.BigInteger, nullable=False),
        sa.Column("gender", sa.String(20), nullable=True),
        sa.Column("age_range", sa.String(10), nullable=True),
        sa.Column("country_code", sa.String(8), nullable=True),
        sa.Column("country_other", sa.String(64), nullable=True),
        sa.Column("consent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "onboarded_via_bot_id", sa.BigInteger,
            sa.ForeignKey("publisher_bots.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_tg_id", name="uq_end_users_user_tg_id"),
        sa.CheckConstraint(
            "gender IS NULL OR gender IN ('male', 'female', 'undisclosed')",
            name="ck_end_users_gender",
        ),
        sa.CheckConstraint(
            "age_range IS NULL OR age_range IN ('under_14', '14_16', '16_18', '18_plus')",
            name="ck_end_users_age_range",
        ),
    )
    op.create_index("ix_end_users_user_tg_id", "end_users", ["user_tg_id"])
    op.create_index("ix_end_users_gender", "end_users", ["gender"])
    op.create_index("ix_end_users_age_range", "end_users", ["age_range"])
    op.create_index("ix_end_users_country", "end_users", ["country_code"])
    op.create_index("ix_end_users_onboarded_via_bot_id", "end_users", ["onboarded_via_bot_id"])


def downgrade() -> None:
    op.drop_index("ix_end_users_onboarded_via_bot_id", table_name="end_users")
    op.drop_index("ix_end_users_country", table_name="end_users")
    op.drop_index("ix_end_users_age_range", table_name="end_users")
    op.drop_index("ix_end_users_gender", table_name="end_users")
    op.drop_index("ix_end_users_user_tg_id", table_name="end_users")
    op.drop_table("end_users")
