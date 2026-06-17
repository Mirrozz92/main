"""Moderation handlers: list, view, approve, reject."""

from __future__ import annotations

import math
from decimal import Decimal

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bots.admin import keyboards as kb
from src.bots.admin.states import ModerationStates
from src.core.db.models.enums import ResourceType
from src.core.logging import get_logger
from src.domain.advertisers import AdvertiserRepository
from src.domain.campaigns import CampaignRepository, CampaignService
from src.domain.checker_bots import CheckerBotRepository
from src.domain.exceptions import CampaignValidationError
from src.domain.resources.invite_links import create_invite_link_for_resource
from src.workers.notifications import (
    notify_admin_new_campaign, # noqa: F401 (used elsewhere via .kiq)
    notify_campaign_approved,
    notify_campaign_rejected,
)

router = Router(name="admin_moderation")
log = get_logger("admin.moderation")


PAGE_SIZE = 10


# ---------- List pending ----------


@router.callback_query(F.data == kb.CB_PENDING_LIST)
async def show_pending_list(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    await _render_pending(callback, session, page=0)


@router.callback_query(F.data.startswith(kb.CB_PENDING_PAGE))
async def pending_page(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        page = int(callback.data.removeprefix(kb.CB_PENDING_PAGE))
    except ValueError:
        await callback.answer("Неверная страница", show_alert=True)
        return
    await _render_pending(callback, session, page=page)


async def _render_pending(
    callback: CallbackQuery,
    session: AsyncSession,
    *,
    page: int,
) -> None:
    svc = CampaignService(session)
    total = await svc.count_pending()

    if total == 0:
        try:
            await callback.message.edit_text(
                "<b>На модерации</b>\n\n"
                "Очередь пуста — все кампании обработаны",
                reply_markup=kb.main_menu_kb(0),
            )
        except TelegramBadRequest:
            pass
        await callback.answer()
        return

    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = max(0, min(page, total_pages - 1))
    campaigns = await svc.list_pending_for_admin(
        limit=PAGE_SIZE, offset=page * PAGE_SIZE,
    )

    # Load advertisers for labels
    adv_repo = AdvertiserRepository(session)
    items: list[tuple[int, str, str]] = []
    for c in campaigns:
        adv = await adv_repo.get_by_id(c.advertiser_id)
        adv_label = f"@{adv.tg_username}"if adv and adv.tg_username else f"adv#{c.advertiser_id}"
        title = c.title if len(c.title) <= 20 else c.title[:17] +"…"
        items.append((c.id, f"{adv_label} — «{title}»", f"{c.budget_total_rub:.0f}₽"))

    try:
        await callback.message.edit_text(
            f"<b>На модерации</b> ({total})\n\n"
            "Выберите кампанию для просмотра:",
            reply_markup=kb.pending_list_kb(items, page=page, total_pages=total_pages),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


# ---------- View campaign ----------


@router.callback_query(F.data.startswith(kb.CB_VIEW_CAMPAIGN))
async def view_campaign(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    try:
        campaign_id = int(callback.data.removeprefix(kb.CB_VIEW_CAMPAIGN))
    except ValueError:
        await callback.answer("Неверный ID", show_alert=True)
        return

    repo = CampaignRepository(session)
    campaign = await repo.get_by_id(campaign_id, with_resources=True)
    if campaign is None:
        await callback.answer("Не найдена", show_alert=True)
        return

    adv_repo = AdvertiserRepository(session)
    adv = await adv_repo.get_by_id(campaign.advertiser_id)
    adv_label = (
        f"@{adv.tg_username}"if adv and adv.tg_username
        else (adv.full_name or f"id:{campaign.advertiser_id}") if adv
        else f"id:{campaign.advertiser_id}"
    )

    lines = [
        f"<b>Кампания #{campaign.id}</b>\n",
        f"<b>Название:</b> {campaign.title}",
        f"<b>Рекламодатель:</b> {adv_label}",
    ]
    if adv:
        lines.append(
            f"<b>Баланс рекламодателя:</b> {adv.balance_rub:.2f} ₽"
            f"(в резерве: {adv.reserved_rub:.2f} ₽)"
        )
    lines.append(f"<b>Бюджет кампании:</b> {campaign.budget_total_rub:.2f} ₽")
    lines.append(f"<b>Отправлена:</b> {campaign.created_at:%Y-%m-%d %H:%M UTC}")

    type_labels = {"channel":"Канал","group":"Группа","bot_start":"Бот"}
    lines.append("\n<b>Ресурсы:</b>")
    for r in campaign.resources:
        name = (r.username and f"@{r.username}") or r.title or f"chat {r.tg_chat_id}"
        type_label = type_labels.get(r.type.value, r.type.value)
        cost = r.reward_rub * Decimal(r.target_subscribers)
        lines.append(
            f"• {name} ({type_label}) — {r.reward_rub:.2f} ₽ ×"
            f"{r.target_subscribers} = {cost:.2f} ₽"
        )

    try:
        await callback.message.edit_text(
            "\n".join(lines),
            reply_markup=kb.campaign_actions_kb(campaign.id),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


# ---------- Approve ----------


@router.callback_query(F.data.startswith(kb.CB_APPROVE))
async def approve_campaign(
    callback: CallbackQuery,
    session: AsyncSession,
    admin_tg_id: int,
) -> None:
    try:
        campaign_id = int(callback.data.removeprefix(kb.CB_APPROVE))
    except ValueError:
        await callback.answer("Неверный ID", show_alert=True)
        return

    repo = CampaignRepository(session)
    campaign = await repo.get_by_id(campaign_id, with_resources=True)
    if campaign is None:
        await callback.answer("Не найдена", show_alert=True)
        return

    await callback.answer("Одобряю и создаю invite-links…")

    # Step 1: Create invite links via checker-bot. We need token_index for each
    # resource. Look up the checker_bot for each resource.
    cb_repo = CheckerBotRepository(session)
    invite_links: dict[int, str] = {}
    invite_errors: list[str] = []

    for r in campaign.resources:
        if r.type == ResourceType.BOT_START:
            continue # no invite link for bot resources
        if r.checker_bot_id is None or r.tg_chat_id is None:
            continue
        cb = await cb_repo.get_by_id(r.checker_bot_id)
        if cb is None:
            invite_errors.append(f"resource #{r.id}: checker bot not found")
            continue
        result = await create_invite_link_for_resource(
            r, checker_bot_token_index=cb.token_index, campaign_id=campaign.id,
        )
        if result.invite_link:
            invite_links[r.id] = result.invite_link
        elif result.error:
            invite_errors.append(f"resource #{r.id}: {result.error}")

    # Step 2: Actually approve via service
    svc = CampaignService(session)
    try:
        await svc.approve(
            campaign=campaign, admin_tg_id=admin_tg_id, invite_links=invite_links,
        )
    except CampaignValidationError as e:
        try:
            await callback.message.edit_text(
                f"{e.user_message}", reply_markup=kb.main_menu_kb(0),
            )
        except TelegramBadRequest:
            pass
        return

    # Step 3: Show confirmation
    summary_lines = [
        f"<b>Кампания #{campaign.id} одобрена</b>\n",
        f"<b>Название:</b> {campaign.title}",
        f"<b>Бюджет:</b> {campaign.budget_total_rub:.2f} ₽",
        f"\n<b>Invite-ссылки созданы:</b> {len(invite_links)}/{len([r for r in campaign.resources if r.type != ResourceType.BOT_START])}",
    ]
    if invite_errors:
        summary_lines.append("\n<b> Ошибки:</b>")
        for err in invite_errors[:5]:
            summary_lines.append(f"• {err}")

    try:
        await callback.message.edit_text(
            "\n".join(summary_lines),
            reply_markup=kb.pending_list_kb([], page=0, total_pages=1),
        )
    except TelegramBadRequest:
        pass

    # Step 4: Enqueue notification to advertiser
    adv_repo = AdvertiserRepository(session)
    adv = await adv_repo.get_by_id(campaign.advertiser_id)
    if adv is not None:
        try:
            await notify_campaign_approved.kiq(
                tg_user_id=adv.tg_user_id,
                campaign_id=campaign.id,
                campaign_title=campaign.title,
                budget_rub=str(campaign.budget_total_rub),
            )
        except Exception as e:
            log.warning("notify_approve_enqueue_failed", error=str(e))


# ---------- Reject ----------


@router.callback_query(F.data.startswith(kb.CB_REJECT_PROMPT))
async def reject_prompt(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    try:
        campaign_id = int(callback.data.removeprefix(kb.CB_REJECT_PROMPT))
    except ValueError:
        await callback.answer("Неверный ID", show_alert=True)
        return

    await state.set_state(ModerationStates.entering_rejection_reason)
    await state.update_data(rejecting_campaign_id=campaign_id)
    try:
        await callback.message.edit_text(
            f"<b>Отклонение кампании #{campaign_id}</b>\n\n"
            "Напишите причину отклонения. Она будет показана рекламодателю.\n\n"
            "<i>От 5 до 500 символов.</i>",
            reply_markup=kb.reject_cancel_kb(),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.callback_query(F.data == kb.CB_REJECT_CANCEL)
async def reject_cancel(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    cid = data.get("rejecting_campaign_id")
    await state.clear()
    if cid:
        # Возвращаемся к карточке кампании
        callback.data = f"{kb.CB_VIEW_CAMPAIGN}{cid}"
        await view_campaign(callback, session)
    else:
        callback.data = kb.CB_PENDING_LIST
        await show_pending_list(callback, session)


@router.message(ModerationStates.entering_rejection_reason, F.text)
async def reject_with_reason(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    admin_tg_id: int,
) -> None:
    reason = (message.text or"").strip()
    if not (5 <= len(reason) <= 500):
        await message.answer(
            "Причина должна быть от 5 до 500 символов.",
            reply_markup=kb.reject_cancel_kb(),
        )
        return

    data = await state.get_data()
    campaign_id = data.get("rejecting_campaign_id")
    if campaign_id is None:
        await message.answer("Кампания утеряна. Начните заново.")
        await state.clear()
        return

    repo = CampaignRepository(session)
    campaign = await repo.get_by_id(campaign_id)
    if campaign is None:
        await message.answer("Кампания не найдена.")
        await state.clear()
        return

    svc = CampaignService(session)
    try:
        await svc.reject(campaign=campaign, admin_tg_id=admin_tg_id, reason=reason)
    except CampaignValidationError as e:
        await message.answer(f"{e.user_message}")
        await state.clear()
        return

    await state.clear()
    await message.answer(
        f"<b>Кампания #{campaign.id} отклонена</b>\n\n"
        f"<b>Бюджет {campaign.budget_total_rub:.2f} ₽ возвращён рекламодателю.</b>\n"
        f"Причина: <i>{reason}</i>",
        reply_markup=kb.main_menu_kb(await svc.count_pending()),
    )

    # Notify advertiser
    adv_repo = AdvertiserRepository(session)
    adv = await adv_repo.get_by_id(campaign.advertiser_id)
    if adv is not None:
        try:
            await notify_campaign_rejected.kiq(
                tg_user_id=adv.tg_user_id,
                campaign_id=campaign.id,
                campaign_title=campaign.title,
                refund_rub=str(campaign.budget_total_rub),
                reason=reason,
            )
        except Exception as e:
            log.warning("notify_reject_enqueue_failed", error=str(e))
