"""Tests for IssueStateMachine transitions (src/domain/issues/state_machine.py).

These exercise the in-memory state changes only. Webhook emission is a no-op
because the test issues have publisher_bot_id=None.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock

import pytest

from src.core.db.models import Publisher, ResourceIssue
from src.core.db.models.enums import IssueStatus
from src.domain.issues.state_machine import IssueStateMachine, StateTransitionError

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def sm() -> IssueStateMachine:
    return IssueStateMachine(Mock())


@pytest.fixture
def established_publisher(make_publisher: Callable[..., Publisher]) -> Publisher:
    # Past cold start, high retention → 4h hold.
    return make_publisher(verified_subs_in_window=100, retention_rate=Decimal("90"))


class TestSubscribe:
    async def test_pending_to_subscribed_sets_hold(
        self,
        sm: IssueStateMachine,
        make_issue: Callable[..., ResourceIssue],
        established_publisher: Publisher,
    ) -> None:
        issue = make_issue(status=IssueStatus.PENDING, expires_at=NOW + timedelta(hours=1))
        await sm.mark_subscribed(issue, established_publisher, at=NOW)
        assert issue.status == IssueStatus.SUBSCRIBED
        assert issue.subscribed_at == NOW
        assert issue.hold_until == NOW + timedelta(hours=4)

    async def test_expired_link_marks_expired_not_subscribed(
        self,
        sm: IssueStateMachine,
        make_issue: Callable[..., ResourceIssue],
        established_publisher: Publisher,
    ) -> None:
        issue = make_issue(status=IssueStatus.PENDING, expires_at=NOW - timedelta(minutes=1))
        await sm.mark_subscribed(issue, established_publisher, at=NOW)
        assert issue.status == IssueStatus.EXPIRED
        assert issue.subscribed_at is None

    async def test_subscribe_from_non_pending_raises(
        self,
        sm: IssueStateMachine,
        make_issue: Callable[..., ResourceIssue],
        established_publisher: Publisher,
    ) -> None:
        issue = make_issue(status=IssueStatus.SUBSCRIBED)
        with pytest.raises(StateTransitionError):
            await sm.mark_subscribed(issue, established_publisher, at=NOW)


class TestUnsubscribe:
    async def test_subscribed_to_unsubscribed(
        self, sm: IssueStateMachine, make_issue: Callable[..., ResourceIssue]
    ) -> None:
        issue = make_issue(status=IssueStatus.SUBSCRIBED)
        await sm.mark_unsubscribed(issue, at=NOW)
        assert issue.status == IssueStatus.UNSUBSCRIBED
        assert issue.unsubscribed_at == NOW

    async def test_verified_can_still_be_marked_unsubscribed(
        self, sm: IssueStateMachine, make_issue: Callable[..., ResourceIssue]
    ) -> None:
        issue = make_issue(status=IssueStatus.VERIFIED, verified_at=NOW)
        await sm.mark_unsubscribed(issue, at=NOW)
        assert issue.status == IssueStatus.UNSUBSCRIBED

    async def test_unsubscribe_ignored_from_pending(
        self, sm: IssueStateMachine, make_issue: Callable[..., ResourceIssue]
    ) -> None:
        issue = make_issue(status=IssueStatus.PENDING)
        await sm.mark_unsubscribed(issue, at=NOW)
        assert issue.status == IssueStatus.PENDING


class TestVerify:
    async def test_subscribed_to_verified_after_hold(
        self, sm: IssueStateMachine, make_issue: Callable[..., ResourceIssue]
    ) -> None:
        issue = make_issue(
            status=IssueStatus.SUBSCRIBED,
            subscribed_at=NOW - timedelta(hours=5),
            hold_until=NOW - timedelta(hours=1),
        )
        await sm.mark_verified(issue, at=NOW)
        assert issue.status == IssueStatus.VERIFIED
        assert issue.verified_at == NOW

    async def test_verify_before_hold_finished_raises(
        self, sm: IssueStateMachine, make_issue: Callable[..., ResourceIssue]
    ) -> None:
        issue = make_issue(
            status=IssueStatus.SUBSCRIBED, hold_until=NOW + timedelta(hours=1)
        )
        with pytest.raises(StateTransitionError):
            await sm.mark_verified(issue, at=NOW)

    async def test_verify_from_wrong_status_raises(
        self, sm: IssueStateMachine, make_issue: Callable[..., ResourceIssue]
    ) -> None:
        issue = make_issue(status=IssueStatus.PENDING)
        with pytest.raises(StateTransitionError):
            await sm.mark_verified(issue, at=NOW)


class TestExpireAndRevert:
    async def test_expire_only_from_pending(
        self, sm: IssueStateMachine, make_issue: Callable[..., ResourceIssue]
    ) -> None:
        issue = make_issue(status=IssueStatus.PENDING)
        await sm.mark_expired(issue, at=NOW)
        assert issue.status == IssueStatus.EXPIRED

        already = make_issue(status=IssueStatus.SUBSCRIBED)
        await sm.mark_expired(already, at=NOW)
        assert already.status == IssueStatus.SUBSCRIBED  # unchanged

    async def test_revert_only_from_unsubscribed(
        self, sm: IssueStateMachine, make_issue: Callable[..., ResourceIssue]
    ) -> None:
        issue = make_issue(status=IssueStatus.UNSUBSCRIBED)
        await sm.mark_reverted(issue, at=NOW)
        assert issue.status == IssueStatus.REVERTED

        verified = make_issue(status=IssueStatus.VERIFIED)
        await sm.mark_reverted(verified, at=NOW)
        assert verified.status == IssueStatus.VERIFIED  # unchanged
