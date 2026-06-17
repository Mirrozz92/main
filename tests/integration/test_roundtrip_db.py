"""Integration tests that exercise real SQL: money movement, the global
uniqueness constraint, and the reporting/query repository methods.

Unlike the unit tests, nothing is stubbed here — the financial service runs its
real join/insert queries against PostgreSQL inside a rolled-back transaction.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db.models import ResourceIssue, Transaction
from src.core.db.models.enums import IssueStatus, TransactionType
from src.domain.issues import ResourceIssueRepository
from src.domain.issues.financial import IssueFinancialService

D = Decimal
_WIDE_SINCE = datetime(2025, 1, 1, tzinfo=UTC)
_WIDE_UNTIL = datetime(2027, 1, 1, tzinfo=UTC)


def _issue_kwargs(seed: SimpleNamespace) -> dict[str, object]:
    """FK columns linking an issue to the seeded graph."""
    return {
        "publisher_id": seed.publisher.id,
        "publisher_token_id": seed.token.id,
        "publisher_bot_id": seed.bot.id,
        "campaign_resource_id": seed.resource.id,
    }


async def test_apply_verify_persists_money_and_ledger(
    seed: SimpleNamespace,
    db_session: AsyncSession,
    make_db_issue: Callable[..., ResourceIssue],
) -> None:
    issue = make_db_issue(
        status=IssueStatus.SUBSCRIBED,
        reward_rub=D("2.0000"),
        publisher_payout_rub=D("1.5000"),
        platform_commission_rub=D("0.5000"),
        **_issue_kwargs(seed),
    )
    db_session.add(issue)
    await db_session.flush()

    await IssueFinancialService(db_session).apply_verify(issue)
    await db_session.flush()

    # Balances moved on the persisted rows.
    assert seed.campaign.budget_reserved_rub == D("98.0000")
    assert seed.campaign.budget_spent_rub == D("2.0000")
    assert seed.advertiser.reserved_rub == D("98.0000")
    assert seed.advertiser.total_spent_rub == D("2.0000")
    assert seed.publisher.balance_rub == D("1.5000")
    assert seed.publisher.total_earned_rub == D("1.5000")
    assert seed.publisher.verified_subs_in_window == 1

    # Ledger actually written to the transactions table.
    txs = (await db_session.execute(select(Transaction))).scalars().all()
    by_type = {t.type: t for t in txs}
    assert len(txs) == 3
    assert by_type[TransactionType.CAMPAIGN_SPEND].amount_rub == D("-2.0000")
    assert by_type[TransactionType.PUBLISHER_EARN].amount_rub == D("1.5000")
    assert by_type[TransactionType.PLATFORM_COMMISSION].amount_rub == D("0.5000")


async def test_global_uniqueness_blocks_double_issue(
    seed: SimpleNamespace,
    db_session: AsyncSession,
    make_db_issue: Callable[..., ResourceIssue],
) -> None:
    # Same (user_tg_id, campaign_resource_id) must not be issued twice — even
    # across publishers. The DB constraint uq_user_resource_global enforces it.
    first = make_db_issue(user_tg_id=777, **_issue_kwargs(seed))
    db_session.add(first)
    await db_session.flush()

    second = make_db_issue(user_tg_id=777, **_issue_kwargs(seed))
    db_session.add(second)
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_aggregate_and_history_queries(
    seed: SimpleNamespace,
    db_session: AsyncSession,
    make_db_issue: Callable[..., ResourceIssue],
) -> None:
    statuses = [
        IssueStatus.VERIFIED,
        IssueStatus.VERIFIED,
        IssueStatus.EXPIRED,
        IssueStatus.SUBSCRIBED,
    ]
    issues = [make_db_issue(status=s, **_issue_kwargs(seed)) for s in statuses]
    db_session.add_all(issues)
    await db_session.flush()

    repo = ResourceIssueRepository(db_session)

    # aggregate_for_publisher: per-status counts over the window.
    rows = await repo.aggregate_for_publisher(
        publisher_id=seed.publisher.id, since=_WIDE_SINCE, until=_WIDE_UNTIL
    )
    counts = {status.value: count for status, count, _payout, _bonus in rows}
    assert counts.get("verified") == 2
    assert counts.get("expired") == 1
    assert counts.get("subscribed") == 1

    # list_user_history: newest-first, joined with the resource, with paging.
    target = issues[0]
    page, has_more = await repo.list_user_history(
        user_tg_id=target.user_tg_id, publisher_id=seed.publisher.id, limit=10
    )
    assert [iss.link_id for iss, _res in page] == [target.link_id]
    assert has_more is False
    assert page[0][1].title == "Test channel"  # resource joined in

    # get_by_link_id_with_resource: single lookup with the resource.
    found = await repo.get_by_link_id_with_resource(target.link_id)
    assert found is not None
    assert found[0].link_id == target.link_id
    assert found[1].id == seed.resource.id


async def test_history_pagination(
    seed: SimpleNamespace,
    db_session: AsyncSession,
    make_db_issue: Callable[..., ResourceIssue],
) -> None:
    from src.core.db.models import CampaignResource
    from src.core.db.models.enums import ResourceStatus, ResourceType, VerificationMethod

    # One user needs several issues, but (user, resource) is globally unique — so
    # give the user a distinct resource per issue (all in the seeded campaign).
    user = 9090
    base = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    for i in range(3):
        res = CampaignResource(
            campaign_id=seed.campaign.id,
            type=ResourceType.CHANNEL,
            title=f"Channel {i}",
            reward_rub=D("2.0000"),
            target_subscribers=1000,
            actual_subscribers=0,
            status=ResourceStatus.ACTIVE,
            verify_method=VerificationMethod.GET_CHAT_MEMBER,
        )
        db_session.add(res)
        await db_session.flush()
        db_session.add(
            make_db_issue(
                user_tg_id=user,
                campaign_resource_id=res.id,
                issued_at=base - timedelta(minutes=i),  # newest first → i=0 leads
                publisher_id=seed.publisher.id,
                publisher_token_id=seed.token.id,
                publisher_bot_id=seed.bot.id,
            )
        )
    await db_session.flush()

    repo = ResourceIssueRepository(db_session)
    page1, more1 = await repo.list_user_history(
        user_tg_id=user, publisher_id=seed.publisher.id, limit=2
    )
    assert len(page1) == 2
    assert more1 is True

    page2, more2 = await repo.list_user_history(
        user_tg_id=user, publisher_id=seed.publisher.id, limit=2, offset=2
    )
    assert len(page2) == 1
    assert more2 is False
