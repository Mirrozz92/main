"""Pydantic schemas for task-related endpoints."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class RequestOpRequest(BaseModel):
    """Input for POST /api/v1/request-op."""

    user_id: int = Field(
        ...,
        description="Telegram user ID of the end-user in the partner's bot",
        examples=[123456789],
    )
    count: int | None = Field(
        default=None,
        ge=1,
        le=10,
        description=(
            "Optional. How many tasks to issue. If omitted — uses the bot's "
            "configured sponsors_count. If higher than configured — capped."
        ),
        examples=[3],
    )

    # Audience signals about the end-user (optional, reported by the partner).
    # Used for advertiser audience filters. NULL/omitted = "not reported" =>
    # campaigns requiring that signal won't be shown to this user.
    has_telegram_premium: bool | None = Field(
        default=None,
        description="Whether the user has Telegram Premium",
        examples=[True],
    )
    has_profile_photo: bool | None = Field(
        default=None,
        description="Whether the user has a profile photo",
        examples=[True],
    )
    has_username: bool | None = Field(
        default=None,
        description="Whether the user has a @username",
        examples=[True],
    )
    has_bio: bool | None = Field(
        default=None,
        description="Whether the user has a bio/description set",
        examples=[False],
    )
    has_stories: bool | None = Field(
        default=None,
        description="Whether the user currently has active Telegram stories",
        examples=[False],
    )


class TaskItem(BaseModel):
    """One issued task."""

    link_id: str = Field(
        ...,
        description="Unique identifier for this issue. Use to verify subscription later.",
        examples=["lnk_a1b2c3d4e5f6a1b2c3d4e5f6"],
    )
    type: Literal["channel", "group", "bot_start"] = Field(
        ..., description="Resource type",
    )
    title: str = Field(..., description="Display title (channel name, etc)")
    username: str | None = Field(
        default=None,
        description="Telegram username without @ (if public)",
    )
    members_count: int | None = Field(
        default=None,
        description="Approximate member count at time of issuing",
    )
    invite_link: str | None = Field(
        default=None,
        description="Invite link to share with user. Filled for channel/group resources.",
        examples=["https://t.me/+AbCdEfGh12345678"],
    )
    start_link: str | None = Field(
        default=None,
        description=(
            "For bot_start resources: deep-link to start the partner bot. "
            "Share this with your user."
        ),
        examples=["https://t.me/somebot?start=fastsub_lnk_a1b2c3d4"],
    )
    reward_for_publisher: Decimal = Field(
        ...,
        description="Amount in RUB the publisher earns for confirmed subscription.",
        examples=["1.5000"],
    )


class RequestOpResponse(BaseModel):
    """Response from POST /api/v1/request-op."""

    ok: bool = Field(..., description="True if tasks issued, false on no_tasks/error.")
    reason: str | None = Field(
        default=None,
        description=(
            "Set when ok=false. Possible values: "
            "'no_tasks' — no available tasks for this user; "
            "'bot_disabled' — your publisher_bot is disabled; "
            "'onboarding_required' — the user has not completed onboarding yet "
            "(show `onboarding_url` to them)."
        ),
        examples=["no_tasks"],
    )
    task_id: str | None = Field(
        default=None,
        description="Set when ok=true. Group ID for all issued tasks in this call.",
        examples=["tsk_a1b2c3d4e5f6"],
    )
    tasks: list[TaskItem] = Field(
        default_factory=list,
        description="Array of issued tasks. Empty when ok=false.",
    )
    onboarding_url: str | None = Field(
        default=None,
        description=(
            "Set when reason='onboarding_required'. Show this URL to the user "
            "(as a button or message) so they can complete registration. "
            "After they submit the form, call /request-op again to receive tasks. "
            "URL is valid for 24h and is idempotent for the same user."
        ),
        examples=["https://fastsub.example.com/onboard/abc123def456"],
    )
