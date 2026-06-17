"""Service layer for Publisher.

Stage 3a v2 — registration is now zero-friction: no project name asked,
just a record created from TG identity.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db.models import Publisher
from src.core.logging import get_logger
from src.domain.exceptions import DomainError
from src.domain.publishers.repository import PublisherRepository

log = get_logger("publishers")


class PublisherBannedError(DomainError):
    user_message = "Ваш аккаунт заблокирован. Свяжитесь с поддержкой."


class PublisherService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = PublisherRepository(session)

    async def get_or_create(
        self,
        *,
        tg_user_id: int,
        tg_username: str | None,
        full_name: str | None,
    ) -> Publisher:
        """Get existing publisher or auto-create on first /start."""
        pub = await self.repo.get_by_tg_id(tg_user_id)
        if pub is None:
            pub = await self.repo.create(
                tg_user_id=tg_user_id,
                tg_username=tg_username,
                full_name=full_name,
                project_name="Default",  # legacy field
            )
            log.info("publisher_registered", publisher_id=pub.id, tg_user_id=tg_user_id)
            return pub

        if pub.is_banned:
            raise PublisherBannedError(pub.ban_reason or "")

        if tg_username and pub.tg_username != tg_username:
            pub.tg_username = tg_username
        if full_name and pub.full_name != full_name:
            pub.full_name = full_name

        return pub

    @staticmethod
    def validate_project_name(name: str) -> str:
        """Kept for backward-compat (used by /register web form)."""
        clean = name.strip() if name else ""
        if not clean:
            return "Default"
        if len(clean) > 128:
            raise DomainError("Название проекта должно быть до 128 символов.")
        return clean
