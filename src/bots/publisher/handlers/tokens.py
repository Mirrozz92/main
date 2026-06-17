"""Token management handlers: list, create (FSM), view, revoke."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bots.publisher import texts
from src.bots.publisher.keyboards import (
    cancel_only_kb,
    revoke_confirm_kb,
    token_detail_kb,
    tokens_list_kb,
)
from src.bots.publisher.states import TokenStates
from src.core.db.models import Publisher
from src.core.logging import get_logger
from src.domain.api_tokens import ApiTokenService
from src.domain.exceptions import DomainError

router = Router(name="publisher_tokens")
log = get_logger("publisher.tokens")


# ---------- List ----------


@router.callback_query(F.data == texts.CB_TOKENS)
async def show_tokens_list(
    callback: CallbackQuery,
    state: FSMContext,
    publisher: Publisher | None,
    session: AsyncSession,
) -> None:
    await state.clear()
    if publisher is None:
        await callback.answer("Сначала зарегистрируйтесь через /start", show_alert=True)
        return

    svc = ApiTokenService(session)
    tokens = await svc.repo.list_for_publisher(publisher.id, include_revoked=False)

    text = texts.tokens_list_header(len(tokens))
    items = [(t.id, t.label, t.token_prefix) for t in tokens]
    try:
        await callback.message.edit_text(text, reply_markup=tokens_list_kb(items))
    except TelegramBadRequest:
        pass
    await callback.answer()


# ---------- Create ----------


@router.callback_query(F.data == texts.CB_TOKEN_CREATE)
async def create_token_prompt(
    callback: CallbackQuery,
    state: FSMContext,
    publisher: Publisher | None,
) -> None:
    if publisher is None:
        await callback.answer("Сначала зарегистрируйтесь через /start", show_alert=True)
        return

    await state.set_state(TokenStates.entering_label)
    try:
        await callback.message.edit_text(
            texts.CREATE_TOKEN_PROMPT, reply_markup=cancel_only_kb(),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.message(TokenStates.entering_label, F.text)
async def create_token_with_label(
    message: Message,
    state: FSMContext,
    publisher: Publisher | None,
    session: AsyncSession,
) -> None:
    if publisher is None:
        await state.clear()
        await message.answer("Сначала зарегистрируйтесь через /start")
        return

    label = (message.text or"").strip()
    svc = ApiTokenService(session)
    try:
        result = await svc.create_for_publisher(publisher_id=publisher.id, label=label)
    except DomainError as e:
        await message.answer(f"{e.user_message}\n\nПопробуйте ещё раз:",
                             reply_markup=cancel_only_kb())
        return

    await state.clear()
    # Send plaintext (one-time!) as separate message so user can copy easily
    await message.answer(
        texts.token_created(result.plaintext, result.token_record.label),
        reply_markup=tokens_list_kb([]), # button to go back to tokens list
    )


# ---------- View ----------


@router.callback_query(F.data.startswith(texts.CB_TOKEN_VIEW))
async def view_token(
    callback: CallbackQuery,
    publisher: Publisher | None,
    session: AsyncSession,
) -> None:
    if publisher is None:
        await callback.answer("Не зарегистрированы", show_alert=True)
        return

    try:
        token_id = int(callback.data.removeprefix(texts.CB_TOKEN_VIEW))
    except ValueError:
        await callback.answer("Неверный ID", show_alert=True)
        return

    svc = ApiTokenService(session)
    token = await svc.repo.get_by_id(token_id)
    if token is None or token.publisher_id != publisher.id:
        await callback.answer("Токен не найден", show_alert=True)
        return

    last_used_str = None
    if token.last_used_at:
        last_used_str = token.last_used_at.strftime("%Y-%m-%d %H:%M UTC")

    text = texts.token_detail(
        token_label=token.label,
        token_prefix=token.token_prefix,
        requests_count=token.requests_count,
        last_used_at=last_used_str,
    )
    try:
        await callback.message.edit_text(text, reply_markup=token_detail_kb(token.id))
    except TelegramBadRequest:
        pass
    await callback.answer()


# ---------- Revoke ----------


@router.callback_query(F.data.startswith(texts.CB_TOKEN_REVOKE_CONFIRM))
async def revoke_token_confirmed(
    callback: CallbackQuery,
    publisher: Publisher | None,
    session: AsyncSession,
) -> None:
    if publisher is None:
        await callback.answer("Не зарегистрированы", show_alert=True)
        return

    try:
        token_id = int(callback.data.removeprefix(texts.CB_TOKEN_REVOKE_CONFIRM))
    except ValueError:
        await callback.answer("Неверный ID", show_alert=True)
        return

    svc = ApiTokenService(session)
    token = await svc.repo.get_by_id(token_id)
    if token is None or token.publisher_id != publisher.id:
        await callback.answer("Токен не найден", show_alert=True)
        return

    await svc.revoke(token)

    # Reload list
    tokens = await svc.repo.list_for_publisher(publisher.id, include_revoked=False)
    text = texts.REVOKED +"\n\n"+ texts.tokens_list_header(len(tokens))
    items = [(t.id, t.label, t.token_prefix) for t in tokens]
    try:
        await callback.message.edit_text(text, reply_markup=tokens_list_kb(items))
    except TelegramBadRequest:
        pass
    await callback.answer("Отозван")


@router.callback_query(F.data.startswith(texts.CB_TOKEN_REVOKE))
async def revoke_token_prompt(
    callback: CallbackQuery,
    publisher: Publisher | None,
) -> None:
    if publisher is None:
        await callback.answer("Не зарегистрированы", show_alert=True)
        return

    # Guard: CB_TOKEN_REVOKE prefix shorter than CB_TOKEN_REVOKE_CONFIRM,
    # ensure we don't accidentally match confirm callback here.
    if callback.data.startswith(texts.CB_TOKEN_REVOKE_CONFIRM):
        return # handled by other handler

    try:
        token_id = int(callback.data.removeprefix(texts.CB_TOKEN_REVOKE))
    except ValueError:
        await callback.answer("Неверный ID", show_alert=True)
        return

    try:
        await callback.message.edit_text(
            texts.CONFIRM_REVOKE,
            reply_markup=revoke_confirm_kb(token_id),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()
