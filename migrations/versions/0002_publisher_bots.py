"""Add publisher_bots table and link existing tokens.

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-13
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create publisher_bots table
    op.create_table(
        "publisher_bots",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "publisher_id",
            sa.BigInteger,
            sa.ForeignKey("publishers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("tg_bot_id", sa.BigInteger, nullable=True),
        sa.Column("tg_bot_username", sa.String(64), nullable=True),
        sa.Column("tg_bot_token_encrypted", sa.LargeBinary, nullable=True),
        sa.Column("sponsors_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column("list_ttl_seconds", sa.Integer, nullable=False, server_default="3600"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("total_requests", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("total_issued", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("total_verified", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("total_earned_rub", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("sponsors_count >= 1 AND sponsors_count <= 10",
                           name="ck_publisher_bots_sponsors_range"),
        sa.CheckConstraint("list_ttl_seconds >= 300 AND list_ttl_seconds <= 604800",
                           name="ck_publisher_bots_ttl_range"),
    )
    op.create_index("ix_publisher_bots_publisher_id", "publisher_bots", ["publisher_id"])
    op.create_index("ix_publisher_bots_tg_bot_id", "publisher_bots", ["tg_bot_id"])
    op.create_index("ix_publisher_bots_active", "publisher_bots", ["is_active", "publisher_id"])

    # 2. Add publisher_bot_id column to publisher_api_tokens (nullable)
    op.add_column(
        "publisher_api_tokens",
        sa.Column("publisher_bot_id", sa.BigInteger, nullable=True),
    )
    op.create_foreign_key(
        "fk_publisher_api_tokens_publisher_bot",
        "publisher_api_tokens",
        "publisher_bots",
        ["publisher_bot_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_publisher_api_tokens_bot_active",
        "publisher_api_tokens",
        ["publisher_bot_id", "is_active"],
    )

    # 3. Backfill: for each existing publisher with tokens, create a "Default" bot
    #    and link all their tokens to it.
    bind = op.get_bind()

    # Find publishers that have tokens but no bots yet
    publishers_with_tokens = bind.execute(sa.text("""
        SELECT DISTINCT publisher_id FROM publisher_api_tokens
    """)).fetchall()

    for row in publishers_with_tokens:
        pub_id = row[0]
        # Create default bot
        new_bot = bind.execute(sa.text("""
            INSERT INTO publisher_bots
                (publisher_id, name, sponsors_count, list_ttl_seconds, is_active)
            VALUES (:pid, 'Default', 1, 3600, true)
            RETURNING id
        """), {"pid": pub_id}).fetchone()
        bot_id = new_bot[0]
        # Link all this publisher's tokens to this bot
        bind.execute(sa.text("""
            UPDATE publisher_api_tokens
            SET publisher_bot_id = :bot_id
            WHERE publisher_id = :pid
        """), {"bot_id": bot_id, "pid": pub_id})


def downgrade() -> None:
    op.drop_index("ix_publisher_api_tokens_bot_active", table_name="publisher_api_tokens")
    op.drop_constraint("fk_publisher_api_tokens_publisher_bot",
                       "publisher_api_tokens", type_="foreignkey")
    op.drop_column("publisher_api_tokens", "publisher_bot_id")

    op.drop_index("ix_publisher_bots_active", table_name="publisher_bots")
    op.drop_index("ix_publisher_bots_tg_bot_id", table_name="publisher_bots")
    op.drop_index("ix_publisher_bots_publisher_id", table_name="publisher_bots")
    op.drop_table("publisher_bots")
