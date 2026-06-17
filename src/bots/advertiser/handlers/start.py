"""/start handler: registration / welcome."""

from __future__ import annotations
from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message, ReplyKeyboardRemove
from src.bots.advertiser import texts
from src.bots.advertiser.keyboards.main_menu import main_menu_inline_kb
from src.core.db.models import Advertiser
from src.core.logging import get_logger

router = Router(name="start")
log = get_logger("handler.start")


@router.message(CommandStart())
async def cmd_start(message: Message, advertiser: Advertiser) -> None:
    log.info("advertiser_start", advertiser_id=advertiser.id, tg_user_id=advertiser.tg_user_id)

    is_new = (
        advertiser.created_at == advertiser.updated_at
        or (advertiser.updated_at - advertiser.created_at).total_seconds() < 2
    )
    text = texts.welcome_new() if is_new else texts.welcome_back(
        advertiser.full_name or advertiser.tg_username or"друг"
    )

    await message.answer(text=text, reply_markup=main_menu_inline_kb())

    # Убираем reply-клавиатуру, если осталась от прошлой версии бота
    try:
        m = await message.answer("⌨", reply_markup=ReplyKeyboardRemove())
        await m.delete()
    except Exception:
        pass
