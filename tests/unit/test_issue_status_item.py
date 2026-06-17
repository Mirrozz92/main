"""Tests for IssueStatusItem.from_issue mapper (pure, no DB)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from src.api.v1.schemas import IssueStatusItem
from src.core.db.models import CampaignResource, ResourceIssue
from src.core.db.models.enums import IssueStatus, ResourceType


def _issue(**overrides: object) -> ResourceIssue:
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    defaults: dict[str, object] = {
        "link_id": "lnk_a1b2c3d4e5f6a1b2c3d4e5f6",
        "status": IssueStatus.SUBSCRIBED,
        "publisher_payout_rub": Decimal("1.5000"),
        "retention_bonus_rub": Decimal("0.0000"),
        "issued_at": now,
        "expires_at": now,
        "subscribed_at": now,
        "hold_until": now,
        "verified_at": None,
        "unsubscribed_at": None,
    }
    defaults.update(overrides)
    return ResourceIssue(**defaults)


def _resource(**overrides: object) -> CampaignResource:
    defaults: dict[str, object] = {
        "type": ResourceType.CHANNEL,
        "title": "My Channel",
        "username": "mychannel",
    }
    defaults.update(overrides)
    return CampaignResource(**defaults)


class TestFromIssue:
    def test_maps_core_fields(self) -> None:
        item = IssueStatusItem.from_issue(_issue(), _resource())
        assert item.link_id == "lnk_a1b2c3d4e5f6a1b2c3d4e5f6"
        assert item.status == "subscribed"
        assert item.type == "channel"
        assert item.title == "My Channel"
        assert item.username == "mychannel"
        assert item.reward_for_publisher == Decimal("1.5000")
        assert item.retention_bonus_rub == Decimal("0.0000")

    def test_active_status_has_no_reason(self) -> None:
        assert IssueStatusItem.from_issue(_issue(status=IssueStatus.PENDING)).reason is None
        assert IssueStatusItem.from_issue(_issue(status=IssueStatus.VERIFIED)).reason is None

    def test_terminal_status_has_reason(self) -> None:
        for status, needle in [
            (IssueStatus.EXPIRED, "expired"),
            (IssueStatus.INVALID, "invalid"),
            (IssueStatus.UNSUBSCRIBED, "left"),
            (IssueStatus.REVERTED, "reverted"),
        ]:
            item = IssueStatusItem.from_issue(_issue(status=status))
            assert item.reason is not None
            assert needle in item.reason

    def test_without_resource_leaves_resource_fields_none(self) -> None:
        item = IssueStatusItem.from_issue(_issue(), None)
        assert item.type is None
        assert item.title is None
        assert item.username is None
