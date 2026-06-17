"""Campaign creation FSM handlers.

Flow:
  /start"Мои кампании"" Создать кампанию"
     entering_title (text)
     adding_resource_chat (text/forward)
         probe chat show preview
     adding_resource_reward (preset/text)
     adding_resource_target (preset/text)
     asking_more_resources (yes/no)
     confirming (summary + submit)
     submitted DB has campaign in PENDING_MODERATION
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bots.advertiser import texts
from src.bots.advertiser.keyboards import campaign as camp_kb
from src.bots.advertiser.keyboards.main_menu import main_menu_inline_kb
from src.bots.advertiser.states.campaign import CampaignCreate
from src.core.db.models import Advertiser
from src.core.logging import get_logger
from src.domain.campaigns import CampaignService
from src.domain.checker_bots import CheckerBotRepository
from src.domain.exceptions import (
    CampaignValidationError,
    ChatNotFoundError,
    CheckerNotAdminError,
    DomainError,
    DuplicateResourceError,
    InsufficientFundsError,
    ResourceValidationError,
)
from src.domain.resources.chat_parser import parse_chat_input, parse_forwarded_message
from src.domain.resources.chat_validator import probe_chat
from src.shared.money import to_money

router = Router(name="campaign_create")
log = get_logger("handler.campaign_create")


# ---------- Texts ----------

PROMPT_TITLE = (
    "<b>Новая кампания</b>\n\n"
    "Шаг 1/4. Введите название кампании.\n\n"
    "<i>От 3 до 255 символов. Видно только вам и админам.</i>"
)

PROMPT_CHAT = (
    "<b>Шаг 2/4. Добавьте ресурс</b>\n\n"
    "Пришлите один из вариантов:\n"
    "• Юзернейм канала/группы/бота: <code>@cryptonews</code>\n"
    "• Ссылка: <code>https://t.me/cryptonews</code>\n"
    "• Форвард любого сообщения из канала\n\n"
    "<b>Перед этим</b> добавьте бот <b>@fastsub_check1_bot</b>"
    "администратором в ваш канал/группу с правом"
    "«Приглашать пользователей по ссылке»."
)


def preview_resource(probe_title: str, probe_username: str | None, type_label: str, members: int | None) -> str:
    members_str = f"\n Подписчиков: <b>{members}</b>"if members else""
    username_str = f"\n @{probe_username}"if probe_username else""
    return (
        f"<b>Ресурс найден:</b>\n\n"
        f"<b>{probe_title}</b>{username_str}\n"
        f"Тип: {type_label}{members_str}\n\n"
        f"Я админ с правом «Приглашать»."
    )


PROMPT_REWARD = (
    "<b>Шаг 3/4. Цена за подписчика</b>\n\n"
    "Сколько вы готовы платить за каждого нового подписчика?\n\n"
    "<i>Допустимый диапазон: от 0.50 ₽ до 25 ₽.\n"
    "Рекомендуем 1–3 ₽ для каналов, 2–5 ₽ для ботов.</i>"
)

PROMPT_REWARD_CUSTOM = (
    "<b>Своя цена</b>\n\n"
    "Введите цену за подписчика в рублях.\n"
    "Например: <code>1.5</code> или <code>3</code>\n\n"
    "<i>От 0.50 до 25 ₽</i>"
)


PROMPT_TARGET = (
    "<b>Шаг 4/4. Сколько подписчиков нужно?</b>\n\n"
    "Выберите целевое количество подписчиков для этого ресурса.\n\n"
    "<i>От 100 до 100 000.</i>"
)

PROMPT_TARGET_CUSTOM = (
    "<b>Своё значение</b>\n\n"
    "Введите целевое количество подписчиков.\n"
    "Например: <code>250</code> или <code>1500</code>\n\n"
    "<i>От 100 до 100 000.</i>"
)


def asking_more_text(resources_count: int, budget: Decimal) -> str:
    return (
        f"<b>Ресурс добавлен!</b>\n\n"
        f"Всего в кампании: <b>{resources_count}</b>\n"
        f"Текущий бюджет: <b>{budget:.2f} ₽</b>\n\n"
        "Хотите добавить ещё один ресурс или продолжить?"
    )


def confirm_text(title: str, resources: list[tuple[str, Decimal, int]], budget: Decimal) -> str:
    """resources: list of (display_name, reward, target)."""
    lines = [
        "<b>Подтверждение кампании</b>\n",
        f"<b>Название:</b> {title}\n",
        "<b>Ресурсы:</b>",
    ]
    for name, reward, target in resources:
        cost = reward * Decimal(target)
        lines.append(f"• {name} — {reward:.2f} ₽ × {target} = {cost:.2f} ₽")
    lines.append("")
    lines.append(f"<b>Итого бюджет:</b> {budget:.2f} ₽")
    lines.append(
        "\n<i>После подтверждения деньги будут зарезервированы с вашего"
        "баланса. Кампания отправится на модерацию админам.</i>"
    )
    return"\n".join(lines)


# ---------- Entry: from menu or empty-campaigns screen ----------


@router.callback_query(F.data == camp_kb.CB_CAMP_CREATE)
async def start_create(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CampaignCreate.entering_title)
    await state.update_data(draft_campaign_id=None, current_probe=None)
    try:
        await callback.message.edit_text(
            PROMPT_TITLE, reply_markup=camp_kb.cancel_only_kb(),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


# ---------- Step 1: Title ----------


@router.message(CampaignCreate.entering_title, F.text)
async def receive_title(
    message: Message,
    state: FSMContext,
    advertiser: Advertiser,
    session: AsyncSession,
) -> None:
    title = (message.text or"").strip()
    if not (3 <= len(title) <= 255):
        await message.answer(
            "Название должно быть от 3 до 255 символов. Попробуйте ещё раз:",
            reply_markup=camp_kb.cancel_only_kb(),
        )
        return

    svc = CampaignService(session)
    try:
        campaign = await svc.create_draft(advertiser_id=advertiser.id, title=title)
    except CampaignValidationError as e:
        await message.answer(f"{e.user_message}", reply_markup=camp_kb.cancel_only_kb())
        return

    await state.update_data(draft_campaign_id=campaign.id)
    await state.set_state(CampaignCreate.adding_resource_chat)
    await message.answer(PROMPT_CHAT, reply_markup=camp_kb.cancel_only_kb())


# ---------- Step 2: Chat input ----------


@router.message(CampaignCreate.adding_resource_chat, F.text | F.forward_from_chat)
async def receive_chat(
    message: Message,
    state: FSMContext,
    advertiser: Advertiser,
    session: AsyncSession,
) -> None:
    # Try forward first
    ref = None
    if message.forward_from_chat:
        ref = parse_forwarded_message(
            message.forward_from_chat.id,
            message.forward_from_chat.username,
        )
        if ref is None:
            # Forward without username — could still work if checker is admin,
            # but for v1 ask user to use username/link if available
            await message.answer(
                "Канал без публичного юзернейма."
                "Пришлите ссылку <code>https://t.me/+...</code> или"
                "форвард сообщения из канала, где наш бот уже админ.",
                reply_markup=camp_kb.cancel_only_kb(),
            )
            return

    if ref is None and message.text:
        ref = parse_chat_input(message.text)

    if ref is None:
        await message.answer(
            "Не удалось распознать ввод. Пришлите @username, ссылку или форвард.",
            reply_markup=camp_kb.cancel_only_kb(),
        )
        return

    # Get all active checker-bots and try each
    cb_repo = CheckerBotRepository(session)
    checker_bots = await cb_repo.list_active()
    if not checker_bots:
        await message.answer(
            "Сервис временно недоступен (нет активных проверочных ботов)."
            "Свяжитесь с админом.",
            reply_markup=camp_kb.cancel_only_kb(),
        )
        return

    # Show"Checking..."stub
    status_msg = await message.answer("Проверяю чат…")

    try:
        probe = await probe_chat(ref, candidate_checker_bots=checker_bots)
    except ChatNotFoundError as e:
        await status_msg.delete()
        await message.answer(f"{e.user_message}", reply_markup=camp_kb.cancel_only_kb())
        return
    except CheckerNotAdminError as e:
        await status_msg.delete()
        await message.answer(f"{e.user_message}", reply_markup=camp_kb.cancel_only_kb())
        return
    except ResourceValidationError as e:
        await status_msg.delete()
        await message.answer(f"{e.user_message}", reply_markup=camp_kb.cancel_only_kb())
        return
    except DomainError as e:
        await status_msg.delete()
        await message.answer(f"{e.user_message}", reply_markup=camp_kb.cancel_only_kb())
        return

    # Cache probe in FSM state for next steps
    await state.update_data(
        probe_chat_id=probe.tg_chat_id,
        probe_title=probe.title,
        probe_username=probe.username,
        probe_type=probe.resource_type.value,
        probe_is_private=probe.is_private,
        probe_member_count=probe.member_count,
        probe_checker_bot_id=probe.checker_bot.id,
    )

    type_labels = {"channel":"Канал","group":"Группа","bot_start":"Бот (CPA, запуск)"}
    preview = preview_resource(
        probe.title,
        probe.username,
        type_labels.get(probe.resource_type.value, probe.resource_type.value),
        probe.member_count,
    )

    await status_msg.delete()
    await message.answer(preview)
    await state.set_state(CampaignCreate.adding_resource_reward)
    await message.answer(PROMPT_REWARD, reply_markup=camp_kb.reward_presets_kb())


# ---------- Step 3: Reward ----------


@router.callback_query(
    CampaignCreate.adding_resource_reward,
    F.data.startswith(camp_kb.CB_CAMP_REWARD_PRESET),
)
async def reward_preset(callback: CallbackQuery, state: FSMContext) -> None:
    raw = callback.data.removeprefix(camp_kb.CB_CAMP_REWARD_PRESET)
    try:
        reward = to_money(Decimal(raw))
    except InvalidOperation:
        await callback.answer("Неверное значение", show_alert=True)
        return
    await _save_reward_and_ask_target(callback, state, reward)


@router.callback_query(
    CampaignCreate.adding_resource_reward,
    F.data == camp_kb.CB_CAMP_REWARD_CUSTOM,
)
async def reward_custom_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        await callback.message.edit_text(
            PROMPT_REWARD_CUSTOM, reply_markup=camp_kb.cancel_only_kb(),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.message(CampaignCreate.adding_resource_reward, F.text)
async def reward_custom_input(message: Message, state: FSMContext) -> None:
    raw = (message.text or"").strip().replace(",",".")
    try:
        reward = to_money(Decimal(raw))
    except (InvalidOperation, ValueError):
        await message.answer(
            "Это не число. Введите цену, например <code>1.5</code>:",
            reply_markup=camp_kb.cancel_only_kb(),
        )
        return

    if reward < Decimal("0.50") or reward > Decimal("25"):
        await message.answer(
            "Цена должна быть от 0.50 ₽ до 25 ₽.",
            reply_markup=camp_kb.cancel_only_kb(),
        )
        return

    await state.update_data(resource_reward=str(reward))
    await state.set_state(CampaignCreate.adding_resource_target)
    await message.answer(PROMPT_TARGET, reply_markup=camp_kb.target_presets_kb())


async def _save_reward_and_ask_target(callback: CallbackQuery, state: FSMContext, reward: Decimal) -> None:
    if reward < Decimal("0.50") or reward > Decimal("25"):
        await callback.answer("Цена вне диапазона", show_alert=True)
        return
    await state.update_data(resource_reward=str(reward))
    await state.set_state(CampaignCreate.adding_resource_target)
    try:
        await callback.message.edit_text(PROMPT_TARGET, reply_markup=camp_kb.target_presets_kb())
    except TelegramBadRequest:
        pass
    await callback.answer()


# ---------- Step 4: Target ----------


@router.callback_query(
    CampaignCreate.adding_resource_target,
    F.data.startswith(camp_kb.CB_CAMP_TARGET_PRESET),
)
async def target_preset(
    callback: CallbackQuery,
    state: FSMContext,
    advertiser: Advertiser,
    session: AsyncSession,
) -> None:
    raw = callback.data.removeprefix(camp_kb.CB_CAMP_TARGET_PRESET)
    try:
        target = int(raw)
    except ValueError:
        await callback.answer("Неверное значение", show_alert=True)
        return
    await _save_target_and_continue(callback, state, advertiser, session, target)


@router.callback_query(
    CampaignCreate.adding_resource_target,
    F.data == camp_kb.CB_CAMP_TARGET_CUSTOM,
)
async def target_custom_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        await callback.message.edit_text(
            PROMPT_TARGET_CUSTOM, reply_markup=camp_kb.cancel_only_kb(),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.message(CampaignCreate.adding_resource_target, F.text)
async def target_custom_input(
    message: Message,
    state: FSMContext,
    advertiser: Advertiser,
    session: AsyncSession,
) -> None:
    raw = (message.text or"").strip().replace("","")
    try:
        target = int(raw)
    except ValueError:
        await message.answer(
            "Введите целое число.", reply_markup=camp_kb.cancel_only_kb(),
        )
        return
    if target < 100 or target > 100_000:
        await message.answer(
            "Значение должно быть от 100 до 100 000.",
            reply_markup=camp_kb.cancel_only_kb(),
        )
        return
    await _save_target_and_continue(None, state, advertiser, session, target, fallback_message=message)


async def _save_target_and_continue(
    callback: CallbackQuery | None,
    state: FSMContext,
    advertiser: Advertiser,
    session: AsyncSession,
    target: int,
    fallback_message: Message | None = None,
) -> None:
    """Add resource to draft, ask about more."""
    data = await state.get_data()
    campaign_id = data.get("draft_campaign_id")
    reward = Decimal(data.get("resource_reward","0"))

    if campaign_id is None or reward <= 0:
        msg = fallback_message or (callback.message if callback else None)
        if msg:
            await msg.answer("Состояние утеряно. Начните заново через меню.",
                             reply_markup=main_menu_inline_kb())
        await state.clear()
        if callback:
            await callback.answer()
        return

    svc = CampaignService(session)
    campaign = await svc.repo.get_by_id(campaign_id, with_resources=True)
    if campaign is None:
        msg = fallback_message or (callback.message if callback else None)
        if msg:
            await msg.answer("Кампания не найдена.", reply_markup=main_menu_inline_kb())
        await state.clear()
        if callback:
            await callback.answer()
        return

    # Build a transient ChatProbeResult from FSM data
    from src.core.db.models.enums import ResourceType
    from src.domain.resources.chat_validator import ChatProbeResult
    from src.domain.checker_bots import CheckerBotRepository as _CBR

    cb_repo = _CBR(session)
    checker_bot = await cb_repo.get_by_id(int(data["probe_checker_bot_id"]))
    if checker_bot is None:
        msg = fallback_message or (callback.message if callback else None)
        if msg:
            await msg.answer("Проверочный бот недоступен.", reply_markup=main_menu_inline_kb())
        await state.clear()
        if callback:
            await callback.answer()
        return

    probe = ChatProbeResult(
        tg_chat_id=int(data["probe_chat_id"]) if data.get("probe_chat_id") else None,
        title=data.get("probe_title",""),
        username=data.get("probe_username"),
        is_private=bool(data.get("probe_is_private")),
        resource_type=ResourceType(data["probe_type"]),
        member_count=data.get("probe_member_count"),
        invite_link=None,
        checker_bot=checker_bot,
        can_invite_users=True,
    )

    try:
        await svc.add_resource_to_draft(
            campaign=campaign,
            probe=probe,
            reward_rub=reward,
            target_subscribers=target,
        )
    except (ResourceValidationError, DuplicateResourceError) as e:
        msg = fallback_message or (callback.message if callback else None)
        if msg:
            await msg.answer(f"{e.user_message}", reply_markup=camp_kb.cancel_only_kb())
        if callback:
            await callback.answer()
        return

    # Force-refresh resources relationship (cached selectinload won't re-fetch
    # by itself; refresh() invalidates the cached collection).
    await session.flush()
    await session.refresh(campaign, attribute_names=["resources"])
    resources_count = len(campaign.resources)
    budget = campaign.budget_total_rub

    await state.set_state(CampaignCreate.asking_more_resources)
    text = asking_more_text(resources_count, budget)
    kb = camp_kb.more_resources_kb()

    if callback:
        try:
            await callback.message.edit_text(text, reply_markup=kb)
        except TelegramBadRequest:
            pass
        await callback.answer("Добавлено")
    elif fallback_message:
        await fallback_message.answer(text, reply_markup=kb)


# ---------- Step 5: More? ----------


@router.callback_query(
    CampaignCreate.asking_more_resources,
    F.data == camp_kb.CB_CAMP_MORE_YES,
)
async def add_more(callback: CallbackQuery, state: FSMContext) -> None:
    # Reset probe data
    await state.update_data(
        probe_chat_id=None, probe_title=None, probe_username=None,
        probe_type=None, probe_is_private=None, probe_member_count=None,
        probe_checker_bot_id=None, resource_reward=None,
    )
    await state.set_state(CampaignCreate.adding_resource_chat)
    try:
        await callback.message.edit_text(PROMPT_CHAT, reply_markup=camp_kb.cancel_only_kb())
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.callback_query(
    CampaignCreate.asking_more_resources,
    F.data == camp_kb.CB_CAMP_MORE_NO,
)
async def start_targeting(
    callback: CallbackQuery,
    state: FSMContext,
    advertiser: Advertiser,
    session: AsyncSession,
) -> None:
    """After resources are added, ask targeting (optional)."""
    data = await state.get_data()
    if not data.get("draft_campaign_id"):
        await callback.answer("Кампания не найдена", show_alert=True)
        return
    # Init targeting accumulator
    await state.update_data(
        tgt_min_age="any",
        tgt_genders=[],
        tgt_countries=[],
        tgt_audience={},
        tgt_min_rating=0,
    )
    await state.set_state(CampaignCreate.targeting_age)
    try:
        await callback.message.edit_text(
            "<b>Таргетинг: возраст аудитории</b>\n\n"
            "Выберите минимальный возраст, или пропустите весь таргетинг "
            "(кампания будет показываться всем).",
            reply_markup=camp_kb.targeting_age_kb(),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


# ---------- Targeting: age ----------

@router.callback_query(
    CampaignCreate.targeting_age,
    F.data == camp_kb.CB_TGT_SKIP_ALL,
)
async def skip_all_targeting(
    callback: CallbackQuery,
    state: FSMContext,
    advertiser: Advertiser,
    session: AsyncSession,
) -> None:
    # Leave defaults (everyone) and go straight to confirm
    await _save_targeting(state, session)
    await _show_confirm(callback, state, session)


@router.callback_query(
    CampaignCreate.targeting_age,
    F.data.startswith(camp_kb.CB_TGT_AGE),
)
async def pick_age(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    value = callback.data.split(":")[-1]
    await state.update_data(tgt_min_age=value)
    await state.set_state(CampaignCreate.targeting_gender)
    data = await state.get_data()
    try:
        await callback.message.edit_text(
            "<b>Таргетинг: пол аудитории</b>\n\n"
            "Отметьте подходящие варианты (можно несколько). "
            "Если ничего не выбрать — пол не учитывается.",
            reply_markup=camp_kb.targeting_gender_kb(data.get("tgt_genders", [])),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


# ---------- Targeting: gender ----------

@router.callback_query(
    CampaignCreate.targeting_gender,
    F.data.startswith(camp_kb.CB_TGT_GENDER) & ~F.data.contains("next"),
)
async def toggle_gender(callback: CallbackQuery, state: FSMContext) -> None:
    value = callback.data.split(":")[-1]
    data = await state.get_data()
    genders = list(data.get("tgt_genders", []))
    if value in genders:
        genders.remove(value)
    else:
        genders.append(value)
    await state.update_data(tgt_genders=genders)
    try:
        await callback.message.edit_reply_markup(
            reply_markup=camp_kb.targeting_gender_kb(genders)
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.callback_query(
    CampaignCreate.targeting_gender,
    F.data == camp_kb.CB_TGT_GENDER_NEXT,
)
async def gender_next(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CampaignCreate.targeting_country)
    data = await state.get_data()
    try:
        await callback.message.edit_text(
            "<b>Таргетинг: страны аудитории</b>\n\n"
            "Отметьте подходящие страны (можно несколько). "
            "Если ничего не выбрать — страна не учитывается.",
            reply_markup=camp_kb.targeting_country_kb(data.get("tgt_countries", [])),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


# ---------- Targeting: country ----------

@router.callback_query(
    CampaignCreate.targeting_country,
    F.data.startswith(camp_kb.CB_TGT_COUNTRY) & ~F.data.contains("next"),
)
async def toggle_country(callback: CallbackQuery, state: FSMContext) -> None:
    value = callback.data.split(":")[-1]
    data = await state.get_data()
    countries = list(data.get("tgt_countries", []))
    if value in countries:
        countries.remove(value)
    else:
        countries.append(value)
    await state.update_data(tgt_countries=countries)
    try:
        await callback.message.edit_reply_markup(
            reply_markup=camp_kb.targeting_country_kb(countries)
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.callback_query(
    CampaignCreate.targeting_country,
    F.data == camp_kb.CB_TGT_COUNTRY_NEXT,
)
async def country_next(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CampaignCreate.targeting_audience)
    data = await state.get_data()
    try:
        await callback.message.edit_text(
            "<b>Таргетинг: требования к аудитории</b>\n\n"
            "Отметьте обязательные признаки подписчика. Эти данные передаёт "
            "партнёр; если он их не передал — кампания такому юзеру не покажется.\n\n"
            "Чем больше требований — тем уже аудитория.",
            reply_markup=camp_kb.targeting_audience_kb(data.get("tgt_audience", {})),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


# ---------- Targeting: audience ----------

@router.callback_query(
    CampaignCreate.targeting_audience,
    F.data.startswith(camp_kb.CB_TGT_AUD) & ~F.data.contains("next"),
)
async def toggle_audience(callback: CallbackQuery, state: FSMContext) -> None:
    key = callback.data.split(":")[-1]
    data = await state.get_data()
    aud = dict(data.get("tgt_audience", {}))
    aud[key] = not aud.get(key, False)
    await state.update_data(tgt_audience=aud)
    try:
        await callback.message.edit_reply_markup(
            reply_markup=camp_kb.targeting_audience_kb(aud)
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.callback_query(
    CampaignCreate.targeting_audience,
    F.data == camp_kb.CB_TGT_AUD_NEXT,
)
async def audience_next(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CampaignCreate.targeting_rating)
    try:
        await callback.message.edit_text(
            "<b>Таргетинг: минимальный рейтинг паблишера</b>\n\n"
            "Чем выше требуемый рейтинг — тем качественнее трафик, но тем "
            "меньше паблишеров покажут вашу кампанию, поэтому подписчики "
            "будут набираться медленнее.\n\n"
            "Рекомендуем «Без ограничения» или «От 7.0».",
            reply_markup=camp_kb.targeting_rating_kb(),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


# ---------- Targeting: rating → confirm ----------

@router.callback_query(
    CampaignCreate.targeting_rating,
    F.data.startswith(camp_kb.CB_TGT_RATING),
)
async def pick_rating(
    callback: CallbackQuery,
    state: FSMContext,
    advertiser: Advertiser,
    session: AsyncSession,
) -> None:
    value = callback.data.split(":")[-1]
    await state.update_data(tgt_min_rating=int(value))
    await _save_targeting(state, session)
    await _show_confirm(callback, state, session)


async def _save_targeting(state: FSMContext, session: AsyncSession) -> None:
    """Persist accumulated targeting into campaign.targeting JSONB."""
    data = await state.get_data()
    campaign_id = data.get("draft_campaign_id")
    if not campaign_id:
        return
    svc = CampaignService(session)
    campaign = await svc.repo.get_by_id(campaign_id, with_resources=False)
    if campaign is None:
        return
    aud = data.get("tgt_audience", {})
    targeting = {
        "min_age": data.get("tgt_min_age", "any"),
        "genders": data.get("tgt_genders", []),
        "countries": data.get("tgt_countries", []),
        "require_premium": bool(aud.get("require_premium")),
        "require_photo": bool(aud.get("require_photo")),
        "require_username": bool(aud.get("require_username")),
        "require_bio": bool(aud.get("require_bio")),
        "require_stories": bool(aud.get("require_stories")),
        "min_publisher_rating": data.get("tgt_min_rating", 0),
    }
    campaign.targeting = targeting
    await session.flush()


async def _show_confirm(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    data = await state.get_data()
    campaign_id = data.get("draft_campaign_id")
    svc = CampaignService(session)
    campaign = await svc.repo.get_by_id(campaign_id, with_resources=True)
    if not campaign:
        await callback.answer("Кампания не найдена", show_alert=True)
        return

    resources_data: list[tuple[str, Decimal, int]] = []
    for r in campaign.resources:
        display = r.username and f"@{r.username}" or r.title
        resources_data.append((display, r.reward_rub, r.target_subscribers))

    text = confirm_text(campaign.title, resources_data, campaign.budget_total_rub)
    text += "\n\n" + _format_targeting_summary(campaign.targeting)
    await state.set_state(CampaignCreate.confirming)
    try:
        await callback.message.edit_text(text, reply_markup=camp_kb.confirm_submit_kb())
    except TelegramBadRequest:
        pass
    await callback.answer()


def _format_targeting_summary(targeting: dict | None) -> str:
    if not targeting:
        return "<b>Таргетинг:</b> не задан (показывается всем)"
    parts: list[str] = []
    age = targeting.get("min_age", "any")
    age_map = {
        "any": "любой", "min_14_plus": "14+",
        "min_16_plus": "16+", "min_18_plus": "18+",
    }
    if age != "any":
        parts.append(f"возраст {age_map.get(age, age)}")
    genders = targeting.get("genders", [])
    if genders:
        gmap = {"male": "муж", "female": "жен", "undisclosed": "не указан"}
        parts.append("пол: " + ", ".join(gmap.get(g, g) for g in genders))
    countries = targeting.get("countries", [])
    if countries:
        parts.append("страны: " + ", ".join(countries))
    aud_labels = {
        "require_premium": "Premium",
        "require_photo": "фото",
        "require_username": "юзернейм",
        "require_bio": "bio",
        "require_stories": "истории",
    }
    aud = [lbl for key, lbl in aud_labels.items() if targeting.get(key)]
    if aud:
        parts.append("требования: " + ", ".join(aud))
    min_rating = targeting.get("min_publisher_rating", 0)
    if min_rating and float(min_rating) > 0:
        parts.append(f"рейтинг паблишера ≥ {min_rating}")

    if not parts:
        return "<b>Таргетинг:</b> не задан (показывается всем)"
    return "<b>Таргетинг:</b> " + "; ".join(parts)




# ---------- Step 6: Submit ----------


@router.callback_query(
    CampaignCreate.confirming,
    F.data == camp_kb.CB_CAMP_SUBMIT,
)
async def submit(
    callback: CallbackQuery,
    state: FSMContext,
    advertiser: Advertiser,
    session: AsyncSession,
) -> None:
    data = await state.get_data()
    campaign_id = data.get("draft_campaign_id")
    if not campaign_id:
        await callback.answer("Кампания не найдена", show_alert=True)
        return

    svc = CampaignService(session)
    campaign = await svc.repo.get_by_id(campaign_id)
    if not campaign:
        await callback.answer("Кампания не найдена", show_alert=True)
        return

    try:
        await svc.submit_for_moderation(campaign=campaign, advertiser=advertiser)
    except InsufficientFundsError as e:
        # Не оставляем сиротский draft — отменяем его при недостатке средств
        try:
            await svc.cancel_draft(campaign=campaign)
        except CampaignValidationError:
            pass
        try:
            await callback.message.edit_text(
                f"{e.user_message}\n\nПополните баланс и создайте кампанию заново.",
                reply_markup=main_menu_inline_kb(),
            )
        except TelegramBadRequest:
            pass
        await state.clear()
        await callback.answer()
        return
    except CampaignValidationError as e:
        # При validation error также чистим draft (например, не дотягивает до 300 ₽)
        try:
            await svc.cancel_draft(campaign=campaign)
        except CampaignValidationError:
            pass
        try:
            await callback.message.edit_text(
                f"{e.user_message}", reply_markup=main_menu_inline_kb(),
            )
        except TelegramBadRequest:
            pass
        await state.clear()
        await callback.answer()
        return

    try:
        await callback.message.edit_text(
            f"<b>Кампания отправлена на модерацию!</b>\n\n"
            f"Название: <b>{campaign.title}</b>\n"
            f"Бюджет: <b>{campaign.budget_total_rub:.2f} ₽</b>\n\n"
            f"Мы уведомим вас, когда кампания пройдёт модерацию (обычно"
            f"в течение нескольких часов).",
            reply_markup=main_menu_inline_kb(),
        )
    except TelegramBadRequest:
        pass

    # Notify admins (non-blocking via TaskIQ)
    try:
        from src.workers.notifications import notify_admin_new_campaign
        adv_label = (
            f"@{advertiser.tg_username}"if advertiser.tg_username
            else (advertiser.full_name or f"id:{advertiser.id}")
        )
        resources = await svc.repo.list_resources(campaign.id)
        await notify_admin_new_campaign.kiq(
            campaign_id=campaign.id,
            advertiser_label=adv_label,
            title=campaign.title,
            budget_rub=str(campaign.budget_total_rub),
            resources_count=len(resources),
        )
    except Exception as e:
        log.warning("admin_notify_enqueue_failed", error=str(e))

    await state.clear()
    await callback.answer("Отправлено")


@router.callback_query(
    CampaignCreate.confirming,
    F.data == camp_kb.CB_CAMP_BACK_TO_RESOURCES,
)
async def back_to_more(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    """Go back from confirming to asking_more_resources screen."""
    data = await state.get_data()
    campaign_id = data.get("draft_campaign_id")
    if not campaign_id:
        await callback.answer("Кампания утеряна", show_alert=True)
        return

    svc = CampaignService(session)
    campaign = await svc.repo.get_by_id(campaign_id, with_resources=True)
    if campaign is None:
        await callback.answer("Кампания не найдена", show_alert=True)
        return

    await state.set_state(CampaignCreate.asking_more_resources)
    text = asking_more_text(len(campaign.resources), campaign.budget_total_rub)
    try:
        await callback.message.edit_text(text, reply_markup=camp_kb.more_resources_kb())
    except TelegramBadRequest:
        pass
    await callback.answer()


# ---------- Cancel ----------


@router.callback_query(F.data == camp_kb.CB_CAMP_CANCEL)
async def cancel(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Cancel an in-progress draft. Also delete it from DB if exists."""
    data = await state.get_data()
    campaign_id = data.get("draft_campaign_id")
    if campaign_id:
        svc = CampaignService(session)
        campaign = await svc.repo.get_by_id(campaign_id)
        if campaign is not None:
            try:
                await svc.cancel_draft(campaign=campaign)
            except CampaignValidationError:
                pass # already non-draft, ignore

    await state.clear()
    try:
        await callback.message.edit_text(
            texts.MENU_PROMPT, reply_markup=main_menu_inline_kb(),
        )
    except TelegramBadRequest:
        pass
    await callback.answer("Отменено")
