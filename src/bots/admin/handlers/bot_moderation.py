"""Publisher bot moderation handlers.

Флоу:
  Главное меню → «Боты на проверке» → список немодерированных ботов
  → карточка бота → выставить тематику/аудиторию → одобрить / заметка + одобрить
"""

from __future__ import annotations

import html
import math
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.bots.admin import keyboards as kb
from src.bots.admin.states import BotModerationStates
from src.core.db.models import PublisherBot
from src.core.logging import get_logger
from src.domain.publisher_bots.repository import PublisherBotRepository

router = Router(name="admin_bot_moderation")
log = get_logger("admin.bot_moderation")

PAGE_SIZE = 10

# ---------- Allowed values (must match migration 0009) ----------

NICHE_LABELS: dict[str, str] = {
    "crypto":        "Крипто / Web3",
    "gaming":        "Игры",
    "sport":         "Спорт",
    "news":          "Новости",
    "finance":       "Финансы",
    "entertainment": "Развлечения",
    "education":     "Образование",
    "other":         "Другое",
}

AGE_LABELS: dict[str, str] = {
    "14_plus": "14+",
    "16_plus": "16+",
    "18_plus": "18+",
    "mixed":   "Смешанная",
}

GENDER_LABELS: dict[str, str] = {
    "male":   "Преим. мужская",
    "female": "Преим. женская",
    "mixed":  "Смешанная",
}


# ---------- Helpers ----------

async def _count_unmoderated(session: AsyncSession) -> int:
    result = await session.execute(
        select(func.count(PublisherBot.id)).where(PublisherBot.is_moderated == False)  # noqa: E712
    )
    return result.scalar_one()


async def _list_unmoderated(
    session: AsyncSession, *, limit: int, offset: int
) -> list[PublisherBot]:
    result = await session.execute(
        select(PublisherBot)
        .where(PublisherBot.is_moderated == False)  # noqa: E712
        .order_by(PublisherBot.created_at.asc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


def _bot_card_text(bot: PublisherBot) -> str:
    lines = [f"<b>Бот #{bot.id} — модерация</b>\n"]
    lines.append(f"<b>Название:</b> {html.escape(bot.name)}")
    if bot.tg_bot_username:
        lines.append(f"<b>TG:</b> @{html.escape(bot.tg_bot_username)}")
    lines.append(f"<b>Паблишер ID:</b> {bot.publisher_id}")
    lines.append(f"<b>Создан:</b> {bot.created_at:%Y-%m-%d %H:%M UTC}")
    lines.append("")
    lines.append(f"<b>Тематика:</b> {NICHE_LABELS.get(bot.niche or '', '—') if bot.niche else '—'}")
    lines.append(f"<b>Возраст:</b> {AGE_LABELS.get(bot.age_audience or '', '—') if bot.age_audience else '—'}")
    lines.append(f"<b>Гендер:</b> {GENDER_LABELS.get(bot.gender_audience or '', '—') if bot.gender_audience else '—'}")
    countries = ", ".join(bot.country_audience) if bot.country_audience else "—"
    lines.append(f"<b>Страны:</b> {countries}")
    if bot.moderation_note:
        lines.append(f"\n<b>Заметка:</b> <i>{html.escape(bot.moderation_note)}</i>")
    return "\n".join(lines)


# ============================================================
# List
# ============================================================

@router.callback_query(F.data == kb.CB_BOT_MOD_LIST)
async def show_bot_list(callback: CallbackQuery, session: AsyncSession) -> None:
    await _render_bot_list(callback, session, page=0)


@router.callback_query(F.data.startswith(kb.CB_BOT_MOD_PAGE))
async def bot_mod_page(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        page = int(callback.data.removeprefix(kb.CB_BOT_MOD_PAGE))
    except ValueError:
        await callback.answer("Неверная страница", show_alert=True)
        return
    await _render_bot_list(callback, session, page=page)


async def _render_bot_list(
    callback: CallbackQuery, session: AsyncSession, *, page: int
) -> None:
    total = await _count_unmoderated(session)
    if total == 0:
        try:
            await callback.message.edit_text(
                "<b>Боты на проверке</b>\n\nОчередь пуста — все боты обработаны",
                reply_markup=kb.bot_mod_empty_kb(),
            )
        except TelegramBadRequest:
            pass
        await callback.answer()
        return

    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = max(0, min(page, total_pages - 1))
    bots = await _list_unmoderated(session, limit=PAGE_SIZE, offset=page * PAGE_SIZE)

    items: list[tuple[int, str]] = []
    for b in bots:
        label = f"@{b.tg_bot_username}" if b.tg_bot_username else b.name
        if len(label) > 28:
            label = label[:25] + "…"
        items.append((b.id, label))

    try:
        await callback.message.edit_text(
            f"<b>Боты на проверке</b> ({total})\n\nВыберите бота:",
            reply_markup=kb.bot_mod_list_kb(items, page=page, total_pages=total_pages),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


# ============================================================
# Bot card
# ============================================================

@router.callback_query(F.data.startswith(kb.CB_BOT_MOD_VIEW))
async def view_bot(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        bot_id = int(callback.data.removeprefix(kb.CB_BOT_MOD_VIEW))
    except ValueError:
        await callback.answer("Неверный ID", show_alert=True)
        return
    repo = PublisherBotRepository(session)
    bot = await repo.get_by_id(bot_id)
    if bot is None:
        await callback.answer("Бот не найден", show_alert=True)
        return
    try:
        await callback.message.edit_text(
            _bot_card_text(bot),
            reply_markup=kb.bot_mod_card_kb(bot.id),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


# ============================================================
# Set niche
# ============================================================

@router.callback_query(F.data.startswith(kb.CB_BOT_SET_NICHE_MENU))
async def set_niche_menu(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        bot_id = int(callback.data.removeprefix(kb.CB_BOT_SET_NICHE_MENU))
    except ValueError:
        await callback.answer("Неверный ID", show_alert=True)
        return
    repo = PublisherBotRepository(session)
    bot = await repo.get_by_id(bot_id)
    if bot is None:
        await callback.answer("Бот не найден", show_alert=True)
        return
    try:
        await callback.message.edit_text(
            f"<b>Тематика бота #{bot_id}</b>\n\nВыберите тематику:",
            reply_markup=kb.niche_select_kb(bot_id, current=bot.niche),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith(kb.CB_BOT_NICHE_SET))
async def apply_niche(callback: CallbackQuery, session: AsyncSession) -> None:
    raw = callback.data.removeprefix(kb.CB_BOT_NICHE_SET)
    try:
        bot_id_str, niche = raw.split(":", 1)
        bot_id = int(bot_id_str)
    except (ValueError, AttributeError):
        await callback.answer("Неверные данные", show_alert=True)
        return
    if niche not in NICHE_LABELS:
        await callback.answer("Неизвестная тематика", show_alert=True)
        return
    repo = PublisherBotRepository(session)
    bot = await repo.get_by_id(bot_id)
    if bot is None:
        await callback.answer("Бот не найден", show_alert=True)
        return
    bot.niche = niche
    await callback.answer(f"Тематика: {NICHE_LABELS[niche]}")
    try:
        await callback.message.edit_text(
            _bot_card_text(bot), reply_markup=kb.bot_mod_card_kb(bot.id),
        )
    except TelegramBadRequest:
        pass


# ============================================================
# Set age audience
# ============================================================

@router.callback_query(F.data.startswith(kb.CB_BOT_SET_AGE_MENU))
async def set_age_menu(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        bot_id = int(callback.data.removeprefix(kb.CB_BOT_SET_AGE_MENU))
    except ValueError:
        await callback.answer("Неверный ID", show_alert=True)
        return
    repo = PublisherBotRepository(session)
    bot = await repo.get_by_id(bot_id)
    if bot is None:
        await callback.answer("Бот не найден", show_alert=True)
        return
    try:
        await callback.message.edit_text(
            f"<b>Возрастная аудитория бота #{bot_id}</b>\n\nВыберите категорию:",
            reply_markup=kb.age_select_kb(bot_id, current=bot.age_audience),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith(kb.CB_BOT_AGE_SET))
async def apply_age(callback: CallbackQuery, session: AsyncSession) -> None:
    raw = callback.data.removeprefix(kb.CB_BOT_AGE_SET)
    try:
        bot_id_str, age = raw.split(":", 1)
        bot_id = int(bot_id_str)
    except (ValueError, AttributeError):
        await callback.answer("Неверные данные", show_alert=True)
        return
    if age not in AGE_LABELS:
        await callback.answer("Неизвестная категория", show_alert=True)
        return
    repo = PublisherBotRepository(session)
    bot = await repo.get_by_id(bot_id)
    if bot is None:
        await callback.answer("Бот не найден", show_alert=True)
        return
    bot.age_audience = age
    await callback.answer(f"Возраст: {AGE_LABELS[age]}")
    try:
        await callback.message.edit_text(
            _bot_card_text(bot), reply_markup=kb.bot_mod_card_kb(bot.id),
        )
    except TelegramBadRequest:
        pass


# ============================================================
# Set gender audience
# ============================================================

@router.callback_query(F.data.startswith(kb.CB_BOT_SET_GENDER_MENU))
async def set_gender_menu(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        bot_id = int(callback.data.removeprefix(kb.CB_BOT_SET_GENDER_MENU))
    except ValueError:
        await callback.answer("Неверный ID", show_alert=True)
        return
    repo = PublisherBotRepository(session)
    bot = await repo.get_by_id(bot_id)
    if bot is None:
        await callback.answer("Бот не найден", show_alert=True)
        return
    try:
        await callback.message.edit_text(
            f"<b>Гендерная аудитория бота #{bot_id}</b>\n\nВыберите категорию:",
            reply_markup=kb.gender_select_kb(bot_id, current=bot.gender_audience),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith(kb.CB_BOT_GENDER_SET))
async def apply_gender(callback: CallbackQuery, session: AsyncSession) -> None:
    raw = callback.data.removeprefix(kb.CB_BOT_GENDER_SET)
    try:
        bot_id_str, gender = raw.split(":", 1)
        bot_id = int(bot_id_str)
    except (ValueError, AttributeError):
        await callback.answer("Неверные данные", show_alert=True)
        return
    if gender not in GENDER_LABELS:
        await callback.answer("Неизвестный гендер", show_alert=True)
        return
    repo = PublisherBotRepository(session)
    bot = await repo.get_by_id(bot_id)
    if bot is None:
        await callback.answer("Бот не найден", show_alert=True)
        return
    bot.gender_audience = gender
    await callback.answer(f"Гендер: {GENDER_LABELS[gender]}")
    try:
        await callback.message.edit_text(
            _bot_card_text(bot), reply_markup=kb.bot_mod_card_kb(bot.id),
        )
    except TelegramBadRequest:
        pass


# ============================================================
# Note prompt (optional before approve)
# ============================================================

@router.callback_query(F.data.startswith(kb.CB_BOT_MOD_NOTE_PROMPT))
async def note_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        bot_id = int(callback.data.removeprefix(kb.CB_BOT_MOD_NOTE_PROMPT))
    except ValueError:
        await callback.answer("Неверный ID", show_alert=True)
        return
    await state.set_state(BotModerationStates.entering_note)
    await state.update_data(moderating_bot_id=bot_id)
    try:
        await callback.message.edit_text(
            f"<b>Заметка к боту #{bot_id}</b>\n\n"
            "Введите заметку (до 500 символов) или нажмите «Пропустить».",
            reply_markup=kb.bot_mod_note_kb(bot_id),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith(kb.CB_BOT_MOD_NOTE_SKIP))
async def note_skip(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    admin_tg_id: int,
) -> None:
    try:
        bot_id = int(callback.data.removeprefix(kb.CB_BOT_MOD_NOTE_SKIP))
    except ValueError:
        await callback.answer("Неверный ID", show_alert=True)
        return
    await state.clear()
    await _do_approve(callback, session, bot_id=bot_id, admin_tg_id=admin_tg_id, note=None)


@router.message(BotModerationStates.entering_note, F.text)
async def receive_note(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    admin_tg_id: int,
) -> None:
    note = (message.text or "").strip()
    if len(note) > 500:
        await message.answer("Заметка не должна превышать 500 символов.")
        return
    data = await state.get_data()
    bot_id = data.get("moderating_bot_id")
    if bot_id is None:
        await message.answer("Данные утеряны. Начните заново.")
        await state.clear()
        return
    await state.clear()

    class _FakeCallback:
        def __init__(self, msg: Message) -> None:
            self.message = msg
        async def answer(self, *_a: object, **_kw: object) -> None:
            pass

    await _do_approve(
        _FakeCallback(message),  # type: ignore[arg-type]
        session,
        bot_id=bot_id,
        admin_tg_id=admin_tg_id,
        note=note or None,
    )


# ============================================================
# Approve
# ============================================================

@router.callback_query(F.data.startswith(kb.CB_BOT_MOD_APPROVE))
async def approve_bot(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    admin_tg_id: int,
) -> None:
    try:
        bot_id = int(callback.data.removeprefix(kb.CB_BOT_MOD_APPROVE))
    except ValueError:
        await callback.answer("Неверный ID", show_alert=True)
        return
    await state.clear()
    await _do_approve(callback, session, bot_id=bot_id, admin_tg_id=admin_tg_id, note=None)


async def _do_approve(
    callback: CallbackQuery,
    session: AsyncSession,
    *,
    bot_id: int,
    admin_tg_id: int,
    note: str | None,
) -> None:
    repo = PublisherBotRepository(session)
    bot = await repo.get_by_id(bot_id)
    if bot is None:
        await callback.answer("Бот не найден", show_alert=True)
        return
    if not bot.niche:
        await callback.answer("Сначала выставьте тематику бота", show_alert=True)
        return

    bot.is_moderated = True
    bot.moderated_at = datetime.now(timezone.utc)
    bot.moderated_by_tg_id = admin_tg_id
    if note:
        bot.moderation_note = note

    log.info(
        "publisher_bot_approved",
        bot_id=bot.id,
        publisher_id=bot.publisher_id,
        niche=bot.niche,
        admin_tg_id=admin_tg_id,
    )

    remaining = await _count_unmoderated(session)
    result_text = (
        f"<b>✅ Бот #{bot.id} одобрен</b>\n\n"
        f"<b>Название:</b> {html.escape(bot.name)}\n"
        f"<b>Тематика:</b> {NICHE_LABELS.get(bot.niche, bot.niche)}\n"
        f"<b>Возраст:</b> {AGE_LABELS.get(bot.age_audience or '', '—')}\n"
        f"<b>Гендер:</b> {GENDER_LABELS.get(bot.gender_audience or '', '—')}\n"
    )
    if note:
        result_text += f"<b>Заметка:</b> <i>{html.escape(note)}</i>\n"
    result_text += f"\n<i>В очереди ещё: {remaining}</i>"

    try:
        await callback.message.edit_text(result_text, reply_markup=kb.bot_mod_after_kb())
    except TelegramBadRequest:
        pass
    await callback.answer()
