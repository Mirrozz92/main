"""/start — auto-register publisher, show main menu."""

from __future__ import annotations

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bots.publisher import texts
from src.bots.publisher.keyboards import main_menu_kb
from src.core.db.models import Publisher
from src.core.logging import get_logger
from src.domain.exceptions import DomainError
from src.domain.publishers import PublisherService

router = Router(name="publisher_start")
log = get_logger("publisher.start")


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    state: FSMContext,
    publisher: Publisher | None,
    session: AsyncSession,
) -> None:
    """Auto-register on first /start. No questions asked."""
    await state.clear()

    if publisher is None:
        if message.from_user is None:
            await message.answer("Не удалось определить пользователя.")
            return
        svc = PublisherService(session)
        try:
            publisher = await svc.get_or_create(
                tg_user_id=message.from_user.id,
                tg_username=message.from_user.username,
                full_name=message.from_user.full_name,
            )
        except DomainError as e:
            await message.answer(f"{e.user_message}")
            return
        await message.answer(texts.WELCOME, reply_markup=main_menu_kb())
        return

    # Already registered
    await message.answer(texts.MENU_PROMPT, reply_markup=main_menu_kb())
