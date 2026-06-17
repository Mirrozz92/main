"""/api/v1/me — return info about authenticated publisher.

Useful for testing token validity.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.api.dependencies import get_current_publisher, get_current_token
from src.core.db.models import Publisher, PublisherApiToken

router = APIRouter(prefix="/api/v1", tags=["publishers"])


class TokenInfo(BaseModel):
    id: int
    label: str
    prefix: str = Field(description="First chars of the token (UI display)")
    requests_count: int
    last_used_at: datetime | None


class PublisherInfo(BaseModel):
    id: int
    project_name: str
    tg_username: str | None
    balance_rub: Decimal
    hold_rub: Decimal
    total_earned_rub: Decimal
    is_vip: bool
    retention_rate: Decimal
    current_token: TokenInfo


@router.get("/me", response_model=PublisherInfo)
async def me(
    publisher: Publisher = Depends(get_current_publisher),
    token: PublisherApiToken = Depends(get_current_token),
) -> PublisherInfo:
    """Return info about the authenticated publisher.

    Requires `Authorization: Bearer <token>`.
    """
    return PublisherInfo(
        id=publisher.id,
        project_name=publisher.project_name,
        tg_username=publisher.tg_username,
        balance_rub=publisher.balance_rub,
        hold_rub=publisher.hold_rub,
        total_earned_rub=publisher.total_earned_rub,
        is_vip=publisher.is_vip,
        retention_rate=publisher.retention_rate,
        current_token=TokenInfo(
            id=token.id,
            label=token.label,
            prefix=token.token_prefix,
            requests_count=token.requests_count,
            last_used_at=token.last_used_at,
        ),
    )
