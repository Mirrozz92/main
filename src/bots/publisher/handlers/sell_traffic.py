"""Sell traffic section: list of publisher's bots + add bot FSM."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bots.publisher import texts
from src.bots.publisher.keyboards import (
    add_bot_cancel_kb,
    add_bot_choice_kb,
    main_menu_kb,
    sell_traffic_kb,
)
from src.bots.publisher.states import BotAddStates
from src.core.db.models import Publisher
from src.core.logging import get_logger
from src.domain.api_tokens import ApiTokenService
from src.domain.exceptions import DomainError
from src.domain.publisher_bots import PublisherBotRepository, PublisherBotService

router = Router(name="publisher_sell_traffic")
log = get_logger("publisher.sell_traffic")


# ---------- List ----------


@router.callback_query(F.data == texts.CB_SELL_TRAFFIC)
async def show_bots_list(
    callback: CallbackQuery,
    state: FSMContext,
    publisher: Publisher | None,
    session: AsyncSession,
) -> None:
    await state.clear()
    if publisher is None:
        await callback.answer("Сначала пришлите /start", show_alert=True)
        return

    repo = PublisherBotRepository(session)
    bots = await repo.list_for_publisher(publisher.id)
    items = [(b.id, b.name, b.is_active) for b in bots]

    text = texts.sell_traffic_header(len(items))
    try:
        await callback.message.edit_text(text, reply_markup=sell_traffic_kb(items))
    except TelegramBadRequest:
        pass
    await callback.answer()


# ---------- Add bot FSM ----------


@router.callback_query(F.data == texts.CB_ADD_BOT)
async def add_bot_intro(callback: CallbackQuery) -> None:
    try:
        await callback.message.edit_text(
            texts.ADD_BOT_INTRO, reply_markup=add_bot_choice_kb(),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.callback_query(F.data == texts.CB_ADD_WITH_TOKEN)
async def add_with_token_prompt(
    callback: CallbackQuery,
    state: FSMContext,
    publisher: Publisher | None,
) -> None:
    if publisher is None:
        await callback.answer("Сначала пришлите /start", show_alert=True)
        return
    await state.set_state(BotAddStates.entering_token)
    try:
        await callback.message.edit_text(
            texts.ADD_BOT_PROMPT_TOKEN, reply_markup=add_bot_cancel_kb(),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.callback_query(F.data == texts.CB_ADD_WITHOUT_TOKEN)
async def add_without_token_prompt(
    callback: CallbackQuery,
    state: FSMContext,
    publisher: Publisher | None,
) -> None:
    if publisher is None:
        await callback.answer("Сначала пришлите /start", show_alert=True)
        return
    await state.set_state(BotAddStates.entering_name)
    try:
        await callback.message.edit_text(
            texts.ADD_BOT_PROMPT_NAME, reply_markup=add_bot_cancel_kb(),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.message(BotAddStates.entering_token, F.text)
async def receive_token(
    message: Message,
    state: FSMContext,
    publisher: Publisher | None,
    session: AsyncSession,
) -> None:
    if publisher is None:
        await state.clear()
        await message.answer("Сначала пришлите /start")
        return

    token_raw = (message.text or"").strip()
    # Try to delete the user's message so plaintext doesn't sit in chat
    try:
        await message.delete()
    except Exception:
        pass

    status_msg = await message.answer("Проверяю токен через Telegram…")

    bot_svc = PublisherBotService(session)
    try:
        bot = await bot_svc.add_bot(
            publisher_id=publisher.id,
            tg_bot_token=token_raw,
        )
    except DomainError as e:
        await status_msg.edit_text(
            f"{e.user_message}", reply_markup=add_bot_cancel_kb(),
        )
        return

    # Auto-create an API token for this new bot
    tok_svc = ApiTokenService(session)
    token_result = await tok_svc.create_for_bot(
        publisher_id=publisher.id,
        publisher_bot_id=bot.id,
        label="Default",
    )

    await state.clear()
    await status_msg.delete()

    await message.answer(
        texts.add_bot_success(bot.name, bot.tg_bot_username),
    )
    # Show the new token immediately
    await message.answer(
        texts.token_revealed(token_result.plaintext),
    )

    # Then return to bot list — fetch updated list
    repo = PublisherBotRepository(session)
    bots = await repo.list_for_publisher(publisher.id)
    items = [(b.id, b.name, b.is_active) for b in bots]
    await message.answer(
        texts.sell_traffic_header(len(items)),
        reply_markup=sell_traffic_kb(items),
    )


@router.message(BotAddStates.entering_name, F.text)
async def receive_name(
    message: Message,
    state: FSMContext,
    publisher: Publisher | None,
    session: AsyncSession,
) -> None:
    if publisher is None:
        await state.clear()
        await message.answer("Сначала пришлите /start")
        return

    name = (message.text or"").strip()
    bot_svc = PublisherBotService(session)
    try:
        bot = await bot_svc.add_bot(publisher_id=publisher.id, name=name)
    except DomainError as e:
        await message.answer(f"{e.user_message}", reply_markup=add_bot_cancel_kb())
        return

    # Auto-create token
    tok_svc = ApiTokenService(session)
    token_result = await tok_svc.create_for_bot(
        publisher_id=publisher.id,
        publisher_bot_id=bot.id,
        label="Default",
    )

    await state.clear()
    await message.answer(
        texts.add_bot_success(bot.name, None),
    )
    await message.answer(
        texts.token_revealed(token_result.plaintext),
    )

    repo = PublisherBotRepository(session)
    bots = await repo.list_for_publisher(publisher.id)
    items = [(b.id, b.name, b.is_active) for b in bots]
    await message.answer(
        texts.sell_traffic_header(len(items)),
        reply_markup=sell_traffic_kb(items),
    )
