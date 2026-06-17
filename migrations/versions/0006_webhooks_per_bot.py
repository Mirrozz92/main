"""Webhooks: bind endpoint to PublisherBot, add resource.reverted event.

Revision ID: 0006
Revises: 0005
"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op

revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Drop old FK + unique (real names from DB)
    op.drop_constraint(
        "fk_webhook_endpoints_publisher_id_publishers",
        "webhook_endpoints",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_webhook_endpoints_publisher_id",
        "webhook_endpoints",
        type_="unique",
    )

    # 2. Rename column
    op.alter_column(
        "webhook_endpoints",
        "publisher_id",
        new_column_name="publisher_bot_id",
    )

    # 3. Recreate FK + unique + index, pointing to publisher_bots
    op.create_foreign_key(
        "fk_webhook_endpoints_publisher_bot_id_publisher_bots",
        "webhook_endpoints",
        "publisher_bots",
        ["publisher_bot_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_webhook_endpoints_publisher_bot_id",
        "webhook_endpoints",
        ["publisher_bot_id"],
    )
    op.create_index(
        "ix_webhook_endpoints_publisher_bot_id",
        "webhook_endpoints",
        ["publisher_bot_id"],
    )

    # 4. Enum value
    op.execute("ALTER TYPE webhook_event_type ADD VALUE IF NOT EXISTS 'resource.reverted'")


def downgrade() -> None:
    op.drop_index("ix_webhook_endpoints_publisher_bot_id", table_name="webhook_endpoints")
    op.drop_constraint(
        "uq_webhook_endpoints_publisher_bot_id",
        "webhook_endpoints",
        type_="unique",
    )
    op.drop_constraint(
        "fk_webhook_endpoints_publisher_bot_id_publisher_bots",
        "webhook_endpoints",
        type_="foreignkey",
    )
    op.alter_column(
        "webhook_endpoints",
        "publisher_bot_id",
        new_column_name="publisher_id",
    )
    op.create_foreign_key(
        "fk_webhook_endpoints_publisher_id_publishers",
        "webhook_endpoints",
        "publishers",
        ["publisher_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_webhook_endpoints_publisher_id",
        "webhook_endpoints",
        ["publisher_id"],
    )
