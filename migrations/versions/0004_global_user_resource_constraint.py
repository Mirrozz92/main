"""Replace per-publisher uniqueness with global uniqueness on resource_issues.

A user can claim a given resource only once globally — across all publishers.
The first publisher who issues that resource to that user "owns" them.

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-14
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop old per-publisher constraint
    op.drop_constraint(
        "uq_user_resource_per_publisher",
        "resource_issues",
        type_="unique",
    )
    # Add new global constraint
    op.create_unique_constraint(
        "uq_user_resource_global",
        "resource_issues",
        ["user_tg_id", "campaign_resource_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_user_resource_global",
        "resource_issues",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_user_resource_per_publisher",
        "resource_issues",
        ["user_tg_id", "campaign_resource_id", "publisher_id"],
    )
