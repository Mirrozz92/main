"""Service layer for Advertiser entity."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db.models import Advertiser
from src.domain.advertisers.repository import AdvertiserRepository
from src.domain.exceptions import AdvertiserBannedError


class AdvertiserService:
    """Business operations on Advertiser."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = AdvertiserRepository(session)

    async def get_or_create(
        self,
        *,
        tg_user_id: int,
        tg_username: str | None = None,
        full_name: str | None = None,
    ) -> Advertiser:
        """Get existing advertiser or create new one.

        Updates username/full_name if changed.
        Raises AdvertiserBannedError if account is banned.
        """
        adv = await self.repo.get_by_tg_id(tg_user_id)
        if adv is None:
            return await self.repo.create(
                tg_user_id=tg_user_id,
                tg_username=tg_username,
                full_name=full_name,
            )

        if adv.is_banned:
            raise AdvertiserBannedError(adv.ban_reason or "")

        # Обновим username/full_name при изменении (они меняются в TG)
        if tg_username and adv.tg_username != tg_username:
            adv.tg_username = tg_username
        if full_name and adv.full_name != full_name:
            adv.full_name = full_name

        return adv
