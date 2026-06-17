"""Tests for IssueFinancialService money movement (src/domain/issues/financial.py).

The DB getters and the transaction repository are stubbed, so these verify the
arithmetic of verify/revert against in-memory advertiser/campaign/publisher rows.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

from src.core.db.models import Advertiser, Campaign, Publisher, ResourceIssue
from src.core.db.models.enums import IssueStatus, TransactionType
from src.domain.issues.financial import IssueFinancialService

D = Decimal
NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _service(
    *,
    campaign: Campaign,
    advertiser: Advertiser,
    publisher: Publisher,
    tx_repo: Any,
) -> IssueFinancialService:
    svc = IssueFinancialService(AsyncMock())
    svc._get_campaign_for_issue = AsyncMock(return_value=campaign)  # type: ignore[method-assign]
    svc._get_advertiser = AsyncMock(return_value=advertiser)  # type: ignore[method-assign]
    svc._get_publisher = AsyncMock(return_value=publisher)  # type: ignore[method-assign]
    svc.tx_repo = tx_repo  # type: ignore[assignment]
    return svc


class TestApplyVerify:
    async def test_full_money_round_trip(
        self,
        make_issue: Callable[..., ResourceIssue],
        make_campaign: Callable[..., Campaign],
        make_advertiser: Callable[..., Advertiser],
        make_publisher: Callable[..., Publisher],
        fake_tx_repo: Any,
    ) -> None:
        issue = make_issue(
            status=IssueStatus.SUBSCRIBED,
            reward_rub=D("2.0000"),
            publisher_payout_rub=D("1.5000"),
            platform_commission_rub=D("0.5000"),
        )
        campaign = make_campaign(budget_reserved_rub=D("10.0000"), budget_spent_rub=D("0"))
        advertiser = make_advertiser(reserved_rub=D("10.0000"), total_spent_rub=D("0"))
        publisher = make_publisher(
            balance_rub=D("0"), total_earned_rub=D("0"),
            verified_subs_in_window=5, total_subscriptions=10,
        )
        svc = _service(
            campaign=campaign, advertiser=advertiser,
            publisher=publisher, tx_repo=fake_tx_repo,
        )

        await svc.apply_verify(issue)

        # Advertiser side: reserve released, spend recorded.
        assert campaign.budget_reserved_rub == D("8.0000")
        assert campaign.budget_spent_rub == D("2.0000")
        assert advertiser.reserved_rub == D("8.0000")
        assert advertiser.total_spent_rub == D("2.0000")

        # Publisher side: payout straight to balance, counters bumped.
        assert publisher.balance_rub == D("1.5000")
        assert publisher.total_earned_rub == D("1.5000")
        assert publisher.verified_subs_in_window == 6
        assert publisher.total_subscriptions == 11

        # Ledger: exactly three entries with conserving amounts.
        spend = fake_tx_repo.of_type(TransactionType.CAMPAIGN_SPEND)
        earn = fake_tx_repo.of_type(TransactionType.PUBLISHER_EARN)
        commission = fake_tx_repo.of_type(TransactionType.PLATFORM_COMMISSION)
        assert len(fake_tx_repo.created) == 3
        assert spend[0]["amount_rub"] == D("-2.0000")
        assert earn[0]["amount_rub"] == D("1.5000")
        assert commission[0]["amount_rub"] == D("0.5000")
        # Money conservation: what the advertiser pays == publisher + platform.
        assert -spend[0]["amount_rub"] == earn[0]["amount_rub"] + commission[0]["amount_rub"]

    async def test_reserve_underflow_clamps_to_zero(
        self,
        make_issue: Callable[..., ResourceIssue],
        make_campaign: Callable[..., Campaign],
        make_advertiser: Callable[..., Advertiser],
        make_publisher: Callable[..., Publisher],
        fake_tx_repo: Any,
    ) -> None:
        issue = make_issue(status=IssueStatus.SUBSCRIBED, reward_rub=D("2.0000"))
        # Reserve smaller than reward → must clamp, never go negative.
        campaign = make_campaign(budget_reserved_rub=D("1.0000"))
        advertiser = make_advertiser(reserved_rub=D("1.0000"))
        publisher = make_publisher()
        svc = _service(
            campaign=campaign, advertiser=advertiser,
            publisher=publisher, tx_repo=fake_tx_repo,
        )

        await svc.apply_verify(issue)

        assert campaign.budget_reserved_rub == D("0.0000")
        assert advertiser.reserved_rub == D("0.0000")
        # Spend is still recorded at full reward.
        assert campaign.budget_spent_rub == D("2.0000")


class TestApplyRevert:
    async def test_revert_before_verify_refunds_advertiser(
        self,
        make_issue: Callable[..., ResourceIssue],
        make_campaign: Callable[..., Campaign],
        make_advertiser: Callable[..., Advertiser],
        make_publisher: Callable[..., Publisher],
        fake_tx_repo: Any,
    ) -> None:
        issue = make_issue(
            status=IssueStatus.UNSUBSCRIBED, reward_rub=D("2.0000"), verified_at=None
        )
        campaign = make_campaign(budget_reserved_rub=D("10.0000"))
        advertiser = make_advertiser(reserved_rub=D("10.0000"), balance_rub=D("0"))
        publisher = make_publisher(total_unsubscriptions=0)
        svc = _service(
            campaign=campaign, advertiser=advertiser,
            publisher=publisher, tx_repo=fake_tx_repo,
        )

        await svc.apply_revert(issue)

        # Reserve released back to advertiser balance.
        assert campaign.budget_reserved_rub == D("8.0000")
        assert advertiser.reserved_rub == D("8.0000")
        assert advertiser.balance_rub == D("2.0000")
        assert publisher.total_unsubscriptions == 1
        refunds = fake_tx_repo.of_type(TransactionType.CAMPAIGN_REFUND)
        assert len(refunds) == 1
        assert refunds[0]["amount_rub"] == D("2.0000")

    async def test_revert_after_verify_is_noop(
        self,
        make_issue: Callable[..., ResourceIssue],
        make_campaign: Callable[..., Campaign],
        make_advertiser: Callable[..., Advertiser],
        make_publisher: Callable[..., Publisher],
        fake_tx_repo: Any,
    ) -> None:
        # verified_at set → late unsubscribe is ignored (Variant A), no money moves.
        issue = make_issue(status=IssueStatus.UNSUBSCRIBED, reward_rub=D("2.0000"), verified_at=NOW)
        campaign = make_campaign(budget_reserved_rub=D("10.0000"))
        advertiser = make_advertiser(reserved_rub=D("10.0000"), balance_rub=D("0"))
        publisher = make_publisher(total_unsubscriptions=0)
        svc = _service(
            campaign=campaign, advertiser=advertiser,
            publisher=publisher, tx_repo=fake_tx_repo,
        )

        await svc.apply_revert(issue)

        assert campaign.budget_reserved_rub == D("10.0000")
        assert advertiser.balance_rub == D("0")
        assert publisher.total_unsubscriptions == 0
        assert fake_tx_repo.created == []
