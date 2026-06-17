"""Integration handlers: show current API token, regenerate."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from src.bots.publisher import texts
from src.bots.publisher.keyboards import (
    integration_kb,
    regenerate_confirm_kb,
)
from src.core.db.models import Publisher
from src.core.logging import get_logger
from src.domain.api_tokens import ApiTokenService
from src.domain.publisher_bots import PublisherBotRepository

router = Router(name="publisher_integration")
log = get_logger("publisher.integration")


async def _verify_ownership(callback, publisher, session, bot_id):
    if publisher is None:
        await callback.answer("Сначала пришлите /start", show_alert=True)
        return None
    repo = PublisherBotRepository(session)
    bot = await repo.get_by_id(bot_id)
    if bot is None or bot.publisher_id != publisher.id:
        await callback.answer("Бот не найден", show_alert=True)
        return None
    return bot


# ---------- View integration ----------


@router.callback_query(F.data.startswith(texts.CB_BOT_INTEGRATION))
async def show_integration(
    callback: CallbackQuery,
    publisher: Publisher | None,
    session: AsyncSession,
) -> None:
    try:
        bot_id = int(callback.data.removeprefix(texts.CB_BOT_INTEGRATION))
    except ValueError:
        await callback.answer("Неверный ID", show_alert=True)
        return

    bot = await _verify_ownership(callback, publisher, session, bot_id)
    if bot is None:
        return

    tok_svc = ApiTokenService(session)
    active_token = await tok_svc.get_active_for_bot(bot.id)

    token_prefix = active_token.token_prefix if active_token else None
    requests_count = active_token.requests_count if active_token else 0
    last_used_at = None
    if active_token and active_token.last_used_at:
        last_used_at = active_token.last_used_at.strftime("%Y-%m-%d %H:%M UTC")

    text = texts.integration_view(
        bot_name=bot.name,
        token_prefix=token_prefix,
        requests_count=requests_count,
        last_used_at=last_used_at,
    )
    try:
        await callback.message.edit_text(text, reply_markup=integration_kb(bot.id))
    except TelegramBadRequest:
        pass
    await callback.answer()


# ---------- Regenerate prompt ----------


@router.callback_query(F.data.startswith(texts.CB_TOKEN_REGEN_PROMPT))
async def regenerate_prompt(
    callback: CallbackQuery,
    publisher: Publisher | None,
    session: AsyncSession,
) -> None:
    # Need to be careful: CB_TOKEN_REGEN_PROMPT ("pub:tr:") is a prefix of
    # CB_TOKEN_REGEN_CONFIRM ("pub:trc:"). Guard against false match.
    if callback.data.startswith(texts.CB_TOKEN_REGEN_CONFIRM):
        return # handled by other handler

    try:
        bot_id = int(callback.data.removeprefix(texts.CB_TOKEN_REGEN_PROMPT))
    except ValueError:
        await callback.answer("Неверный ID", show_alert=True)
        return

    bot = await _verify_ownership(callback, publisher, session, bot_id)
    if bot is None:
        return

    try:
        await callback.message.edit_text(
            texts.REGENERATE_CONFIRM,
            reply_markup=regenerate_confirm_kb(bot.id),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


# ---------- Regenerate confirmed ----------


@router.callback_query(F.data.startswith(texts.CB_TOKEN_REGEN_CONFIRM))
async def regenerate_confirmed(
    callback: CallbackQuery,
    publisher: Publisher | None,
    session: AsyncSession,
) -> None:
    try:
        bot_id = int(callback.data.removeprefix(texts.CB_TOKEN_REGEN_CONFIRM))
    except ValueError:
        await callback.answer("Неверный ID", show_alert=True)
        return

    bot = await _verify_ownership(callback, publisher, session, bot_id)
    if bot is None:
        return

    tok_svc = ApiTokenService(session)
    result = await tok_svc.regenerate_for_bot(
        publisher_id=publisher.id,
        publisher_bot_id=bot.id,
        label="Regenerated",
    )

    # Show new plaintext in separate message
    await callback.message.answer(texts.token_revealed(result.plaintext))

    # Reload integration view
    text = texts.integration_view(
        bot_name=bot.name,
        token_prefix=result.token_record.token_prefix,
        requests_count=0,
        last_used_at=None,
    )
    try:
        await callback.message.edit_text(text, reply_markup=integration_kb(bot.id))
    except TelegramBadRequest:
        pass
    await callback.answer("Ключ перевыпущен")
