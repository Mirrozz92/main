"""Add publisher_bot_id to resource_issues.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-14
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "resource_issues",
        sa.Column("publisher_bot_id", sa.BigInteger, nullable=True),
    )
    op.create_foreign_key(
        "fk_resource_issues_publisher_bot",
        "resource_issues",
        "publisher_bots",
        ["publisher_bot_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_resource_issues_publisher_bot",
        "resource_issues",
        ["publisher_bot_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_resource_issues_publisher_bot", table_name="resource_issues")
    op.drop_constraint("fk_resource_issues_publisher_bot",
                       "resource_issues", type_="foreignkey")
    op.drop_column("resource_issues", "publisher_bot_id")
