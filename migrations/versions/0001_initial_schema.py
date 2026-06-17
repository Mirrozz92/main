"""Initial schema.

Revision ID: 0001
Revises:
Create Date: 2026-05-12
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Enums (create_type=False — создаём их явно один раз в upgrade,
# чтобы create_table их не дублировал)
CAMPAIGN_STATUS = postgresql.ENUM(
    "draft", "pending_moderation", "active", "paused",
    "completed", "rejected", "canceled",
    name="campaign_status", create_type=False,
)
RESOURCE_TYPE = postgresql.ENUM(
    "channel", "group", "bot_start",
    name="resource_type", create_type=False,
)
RESOURCE_STATUS = postgresql.ENUM(
    "pending", "active", "paused", "completed", "failed",
    name="resource_status", create_type=False,
)
ISSUE_STATUS = postgresql.ENUM(
    "pending", "subscribed", "verified", "paid",
    "expired", "unsubscribed", "reverted", "invalid",
    name="issue_status", create_type=False,
)
TRANSACTION_TYPE = postgresql.ENUM(
    "advertiser_topup", "campaign_reserve", "campaign_spend", "campaign_refund",
    "publisher_earn", "publisher_hold_release", "publisher_hold_revert",
    "publisher_payout", "publisher_bonus",
    "platform_commission", "adjustment",
    name="transaction_type", create_type=False,
)
TRANSACTION_STATUS = postgresql.ENUM(
    "pending", "completed", "failed", "canceled",
    name="transaction_status", create_type=False,
)
VERIFICATION_METHOD = postgresql.ENUM(
    "get_chat_member", "join_request", "start_param",
    name="verification_method", create_type=False,
)
WEBHOOK_EVENT_TYPE = postgresql.ENUM(
    "resource.issued", "resource.subscribed", "resource.verified",
    "resource.paid", "resource.unsubscribed", "resource.expired",
    name="webhook_event_type", create_type=False,
)
WEBHOOK_DELIVERY_STATUS = postgresql.ENUM(
    "pending", "success", "failed", "dead",
    name="webhook_delivery_status", create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()

    # Создаём enum'ы один раз
    for enum_t in (
        CAMPAIGN_STATUS, RESOURCE_TYPE, RESOURCE_STATUS, ISSUE_STATUS,
        TRANSACTION_TYPE, TRANSACTION_STATUS, VERIFICATION_METHOD,
        WEBHOOK_EVENT_TYPE, WEBHOOK_DELIVERY_STATUS,
    ):
        enum_t.create(bind, checkfirst=True)

    # === advertisers ===
    op.create_table(
        "advertisers",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("tg_user_id", sa.BigInteger, nullable=False, unique=True),
        sa.Column("tg_username", sa.String(64), nullable=True),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("balance_rub", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("reserved_rub", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("total_spent_rub", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("is_banned", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("ban_reason", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # === publishers ===
    op.create_table(
        "publishers",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("tg_user_id", sa.BigInteger, nullable=False, unique=True),
        sa.Column("tg_username", sa.String(64), nullable=True),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("project_name", sa.String(128), nullable=False),
        sa.Column("balance_rub", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("hold_rub", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("total_earned_rub", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("total_paid_out_rub", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("retention_rate", sa.Numeric(5, 2), nullable=False, server_default="100"),
        sa.Column("verified_subs_in_window", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("retention_calculated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_vip", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_banned", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("ban_reason", sa.Text, nullable=True),
        sa.Column("total_subscriptions", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("total_unsubscriptions", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # === publisher_api_tokens ===
    op.create_table(
        "publisher_api_tokens",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("publisher_id", sa.BigInteger,
                  sa.ForeignKey("publishers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_prefix", sa.String(16), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("label", sa.String(128), nullable=False, server_default="Default"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requests_count", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_publisher_api_tokens_publisher_id", "publisher_api_tokens", ["publisher_id"])
    op.create_index("ix_publisher_api_tokens_active", "publisher_api_tokens", ["is_active", "publisher_id"])

    # === checker_bots ===
    op.create_table(
        "checker_bots",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("tg_bot_id", sa.BigInteger, nullable=False, unique=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True),
        sa.Column("token_index", sa.Integer, nullable=False),
        sa.Column("active_resources_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_resources", sa.Integer, nullable=False, server_default="400"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("last_health_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # === campaigns ===
    op.create_table(
        "campaigns",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("advertiser_id", sa.BigInteger,
                  sa.ForeignKey("advertisers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("status", CAMPAIGN_STATUS, nullable=False, server_default="draft"),
        sa.Column("budget_total_rub", sa.Numeric(18, 4), nullable=False),
        sa.Column("budget_spent_rub", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("budget_reserved_rub", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("targeting", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("rejection_reason", sa.Text, nullable=True),
        sa.Column("moderated_by_admin_id", sa.BigInteger, nullable=True),
        sa.Column("moderated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("budget_total_rub > 0", name="ck_campaigns_budget_total_positive"),
        sa.CheckConstraint("budget_spent_rub >= 0", name="ck_campaigns_budget_spent_non_negative"),
        sa.CheckConstraint("budget_reserved_rub >= 0", name="ck_campaigns_budget_reserved_non_negative"),
        sa.CheckConstraint(
            "budget_spent_rub + budget_reserved_rub <= budget_total_rub",
            name="ck_campaigns_budget_not_overdrawn",
        ),
    )
    op.create_index("ix_campaigns_advertiser_id", "campaigns", ["advertiser_id"])
    op.create_index("ix_campaigns_status", "campaigns", ["status"])
    op.create_index("ix_campaigns_advertiser_status", "campaigns", ["advertiser_id", "status"])

    # === campaign_resources ===
    op.create_table(
        "campaign_resources",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("campaign_id", sa.BigInteger,
                  sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("checker_bot_id", sa.BigInteger,
                  sa.ForeignKey("checker_bots.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("type", RESOURCE_TYPE, nullable=False),
        sa.Column("tg_chat_id", sa.BigInteger, nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("username", sa.String(64), nullable=True),
        sa.Column("is_private", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("invite_link", sa.String(255), nullable=True, unique=True),
        sa.Column("invite_link_name", sa.String(64), nullable=True),
        sa.Column("start_param", sa.String(64), nullable=True),
        sa.Column("verify_method", VERIFICATION_METHOD, nullable=False),
        sa.Column("reward_rub", sa.Numeric(18, 4), nullable=False),
        sa.Column("target_subscribers", sa.BigInteger, nullable=False),
        sa.Column("actual_subscribers", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("status", RESOURCE_STATUS, nullable=False, server_default="pending"),
        sa.Column("targeting_override", postgresql.JSONB, nullable=True),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("reward_rub > 0", name="ck_campaign_resources_reward_positive"),
        sa.CheckConstraint("target_subscribers > 0", name="ck_campaign_resources_target_positive"),
        sa.CheckConstraint("actual_subscribers >= 0", name="ck_campaign_resources_actual_non_negative"),
    )
    op.create_index("ix_campaign_resources_campaign_id", "campaign_resources", ["campaign_id"])
    op.create_index("ix_campaign_resources_checker_bot_id", "campaign_resources", ["checker_bot_id"])
    op.create_index("ix_campaign_resources_tg_chat_id", "campaign_resources", ["tg_chat_id"])
    op.create_index("ix_campaign_resources_status", "campaign_resources", ["status"])
    op.create_index("ix_campaign_resources_active", "campaign_resources", ["status", "checker_bot_id"])
    op.execute("""
        CREATE INDEX ix_campaign_resources_rotation
        ON campaign_resources (status, reward_rub)
        WHERE status = 'active'
    """)

    # === resource_issues ===
    op.create_table(
        "resource_issues",
        sa.Column("link_id", sa.String(32), primary_key=True),
        sa.Column("task_id", sa.String(32), nullable=False),
        sa.Column("publisher_id", sa.BigInteger,
                  sa.ForeignKey("publishers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("publisher_token_id", sa.BigInteger,
                  sa.ForeignKey("publisher_api_tokens.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("user_tg_id", sa.BigInteger, nullable=False),
        sa.Column("campaign_resource_id", sa.BigInteger,
                  sa.ForeignKey("campaign_resources.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("reward_rub", sa.Numeric(18, 4), nullable=False),
        sa.Column("publisher_payout_rub", sa.Numeric(18, 4), nullable=False),
        sa.Column("platform_commission_rub", sa.Numeric(18, 4), nullable=False),
        sa.Column("retention_bonus_rub", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("status", ISSUE_STATUS, nullable=False, server_default="pending"),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("subscribed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hold_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unsubscribed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_context", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("check_calls_count", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "user_tg_id", "campaign_resource_id", "publisher_id",
            name="uq_user_resource_per_publisher",
        ),
        sa.CheckConstraint("expires_at > issued_at", name="ck_resource_issues_expires_after_issued"),
        sa.CheckConstraint("reward_rub >= 0", name="ck_resource_issues_reward_non_negative"),
        sa.CheckConstraint("publisher_payout_rub >= 0", name="ck_resource_issues_payout_non_negative"),
        sa.CheckConstraint("platform_commission_rub >= 0", name="ck_resource_issues_commission_non_negative"),
    )
    op.create_index("ix_resource_issues_task_id", "resource_issues", ["task_id"])
    op.create_index("ix_resource_issues_status", "resource_issues", ["status"])
    op.create_index("ix_resource_issues_issued_at", "resource_issues", ["issued_at"])
    op.create_index("ix_resource_issues_user_history", "resource_issues",
                    ["user_tg_id", "publisher_id", "issued_at"])
    op.create_index("ix_resource_issues_publisher_status", "resource_issues",
                    ["publisher_id", "status", "issued_at"])
    op.execute("""
        CREATE INDEX ix_resource_issues_hold_pending
        ON resource_issues (hold_until)
        WHERE status = 'subscribed'
    """)
    op.execute("""
        CREATE INDEX ix_resource_issues_expiring
        ON resource_issues (expires_at)
        WHERE status = 'pending'
    """)

    # === transactions ===
    op.create_table(
        "transactions",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("type", TRANSACTION_TYPE, nullable=False),
        sa.Column("status", TRANSACTION_STATUS, nullable=False, server_default="completed"),
        sa.Column("amount_rub", sa.Numeric(18, 4), nullable=False),
        sa.Column("advertiser_id", sa.BigInteger,
                  sa.ForeignKey("advertisers.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("publisher_id", sa.BigInteger,
                  sa.ForeignKey("publishers.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("campaign_id", sa.BigInteger,
                  sa.ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True),
        sa.Column("resource_issue_link_id", sa.String(32),
                  sa.ForeignKey("resource_issues.link_id", ondelete="SET NULL"), nullable=True),
        sa.Column("external_id", sa.String(128), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("meta", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("idempotency_key", sa.String(128), nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "(advertiser_id IS NOT NULL) OR (publisher_id IS NOT NULL)",
            name="ck_transactions_subject_required",
        ),
        sa.CheckConstraint(
            "NOT (advertiser_id IS NOT NULL AND publisher_id IS NOT NULL)",
            name="ck_transactions_single_subject",
        ),
    )
    op.create_index("ix_transactions_type", "transactions", ["type"])
    op.create_index("ix_transactions_advertiser_id", "transactions", ["advertiser_id"])
    op.create_index("ix_transactions_publisher_id", "transactions", ["publisher_id"])
    op.create_index("ix_transactions_campaign_id", "transactions", ["campaign_id"])
    op.create_index("ix_transactions_resource_issue_link_id", "transactions", ["resource_issue_link_id"])
    op.create_index("ix_transactions_external_id", "transactions", ["external_id"])
    op.create_index("ix_transactions_idempotency_key", "transactions", ["idempotency_key"])
    op.create_index("ix_transactions_advertiser_time", "transactions", ["advertiser_id", "created_at"])
    op.create_index("ix_transactions_publisher_time", "transactions", ["publisher_id", "created_at"])

    # === verification_logs (PARTITIONED) ===
    op.execute("""
        CREATE TABLE verification_logs (
            id BIGSERIAL NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            resource_issue_link_id VARCHAR(32),
            campaign_resource_id BIGINT,
            user_tg_id BIGINT NOT NULL,
            checker_bot_id BIGINT REFERENCES checker_bots(id) ON DELETE SET NULL,
            is_subscribed BOOLEAN NOT NULL,
            member_status VARCHAR(32),
            error_code VARCHAR(64),
            error_message VARCHAR(500),
            duration_ms BIGINT,
            raw_response JSONB,
            PRIMARY KEY (id, created_at)
        ) PARTITION BY RANGE (created_at);
    """)
    op.execute("CREATE TABLE verification_logs_2026_05 PARTITION OF verification_logs FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');")
    op.execute("CREATE TABLE verification_logs_2026_06 PARTITION OF verification_logs FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');")
    op.execute("CREATE TABLE verification_logs_2026_07 PARTITION OF verification_logs FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');")
    op.execute("CREATE INDEX ix_verification_logs_link_id ON verification_logs (resource_issue_link_id) WHERE resource_issue_link_id IS NOT NULL;")
    op.execute("CREATE INDEX ix_verification_logs_resource_user ON verification_logs (campaign_resource_id, user_tg_id);")

    # === webhook_endpoints ===
    op.create_table(
        "webhook_endpoints",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("publisher_id", sa.BigInteger,
                  sa.ForeignKey("publishers.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("secret", sa.String(128), nullable=False),
        sa.Column("enabled_events", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consecutive_failures", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # === webhook_deliveries ===
    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("endpoint_id", sa.BigInteger,
                  sa.ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", WEBHOOK_EVENT_TYPE, nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("status", WEBHOOK_DELIVERY_STATUS, nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_response_status", sa.Integer, nullable=True),
        sa.Column("last_response_body", sa.Text, nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_webhook_deliveries_endpoint_id", "webhook_deliveries", ["endpoint_id"])
    op.create_index("ix_webhook_deliveries_status", "webhook_deliveries", ["status"])
    op.create_index("ix_webhook_deliveries_pending", "webhook_deliveries", ["status", "next_attempt_at"])


def downgrade() -> None:
    op.drop_table("webhook_deliveries")
    op.drop_table("webhook_endpoints")
    op.execute("DROP TABLE IF EXISTS verification_logs CASCADE")
    op.drop_table("transactions")
    op.drop_table("resource_issues")
    op.drop_table("campaign_resources")
    op.drop_table("campaigns")
    op.drop_table("checker_bots")
    op.drop_table("publisher_api_tokens")
    op.drop_table("publishers")
    op.drop_table("advertisers")

    bind = op.get_bind()
    for enum_t in (
        WEBHOOK_DELIVERY_STATUS, WEBHOOK_EVENT_TYPE, VERIFICATION_METHOD,
        TRANSACTION_STATUS, TRANSACTION_TYPE, ISSUE_STATUS,
        RESOURCE_STATUS, RESOURCE_TYPE, CAMPAIGN_STATUS,
    ):
        enum_t.drop(bind, checkfirst=True)
