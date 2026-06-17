"""Registration / /start handler for publisher bot."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bots.publisher import texts
from src.bots.publisher.keyboards import main_menu_kb
from src.bots.publisher.states import RegisterStates
from src.core.db.models import Publisher
from src.core.logging import get_logger
from src.domain.exceptions import DomainError
from src.domain.publishers import PublisherService

router = Router(name="publisher_register")
log = get_logger("publisher.register")


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    state: FSMContext,
    publisher: Publisher | None,
) -> None:
    if publisher is None:
        # Need to register
        await state.set_state(RegisterStates.entering_project_name)
        await message.answer(texts.WELCOME_NEW)
        return

    # Already registered
    await state.clear()
    name = publisher.full_name or publisher.tg_username or"друг"
    await message.answer(
        texts.WELCOME_BACK.format(name=name),
        reply_markup=main_menu_kb(),
    )


@router.message(RegisterStates.entering_project_name, F.text)
async def receive_project_name(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    raw = (message.text or"").strip()
    try:
        project_name = PublisherService.validate_project_name(raw)
    except DomainError as e:
        await message.answer(f"{e.user_message}\n\nПопробуйте ещё раз:")
        return

    tg_user = message.from_user
    if tg_user is None:
        await message.answer("Не удалось получить данные пользователя.")
        return

    svc = PublisherService(session)
    publisher = await svc.get_or_create(
        tg_user_id=tg_user.id,
        tg_username=tg_user.username,
        full_name=tg_user.full_name,
        project_name=project_name,
    )
    await state.clear()

    log.info("publisher_registered_via_bot", publisher_id=publisher.id, project=project_name)

    await message.answer(
        f"<b>Регистрация завершена!</b>\n\n"
        f"Проект: <b>{publisher.project_name}</b>\n\n"
        "Теперь создайте свой первый API-токен — он понадобится для интеграции"
        "FastSub в ваш бот.",
        reply_markup=main_menu_kb(),
    )
