"""Campaign listing and detail handlers."""

from __future__ import annotations

import math

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from src.bots.advertiser import texts
from src.bots.advertiser.keyboards import campaign as camp_kb
from src.bots.advertiser.keyboards.main_menu import back_to_menu_kb
from src.core.db.models import Advertiser
from src.core.db.models.enums import CampaignStatus
from src.core.logging import get_logger
from src.domain.campaigns import CampaignRepository, CampaignService
from src.domain.exceptions import CampaignValidationError

router = Router(name="campaign_list")
log = get_logger("handler.campaign_list")


PAGE_SIZE = 10


STATUS_EMOJI: dict[CampaignStatus, str] = {
    CampaignStatus.DRAFT:"",
    CampaignStatus.PENDING_MODERATION:"",
    CampaignStatus.ACTIVE:"",
    CampaignStatus.PAUSED:"",
    CampaignStatus.COMPLETED:"",
    CampaignStatus.REJECTED:"",
    CampaignStatus.CANCELED:"",
}


STATUS_LABEL: dict[CampaignStatus, str] = {
    CampaignStatus.DRAFT:"Черновик",
    CampaignStatus.PENDING_MODERATION:"На модерации",
    CampaignStatus.ACTIVE:"Активна",
    CampaignStatus.PAUSED:"Пауза",
    CampaignStatus.COMPLETED:"Завершена",
    CampaignStatus.REJECTED:"Отклонена",
    CampaignStatus.CANCELED:"Отменена",
}


# ---------- Override: CB_CAMPAIGNS now shows real list ----------


@router.callback_query(F.data == texts.CB_CAMPAIGNS)
async def show_my_campaigns(
    callback: CallbackQuery,
    advertiser: Advertiser,
    session: AsyncSession,
) -> None:
    await _render_page(callback, advertiser, session, page=0)


@router.callback_query(F.data.startswith(camp_kb.CB_CAMP_LIST_PAGE))
async def list_page(
    callback: CallbackQuery,
    advertiser: Advertiser,
    session: AsyncSession,
) -> None:
    try:
        page = int(callback.data.removeprefix(camp_kb.CB_CAMP_LIST_PAGE))
    except ValueError:
        await callback.answer("Неверная страница", show_alert=True)
        return
    await _render_page(callback, advertiser, session, page=page)


async def _render_page(
    callback: CallbackQuery,
    advertiser: Advertiser,
    session: AsyncSession,
    *,
    page: int,
) -> None:
    repo = CampaignRepository(session)
    total = await repo.count_for_advertiser(advertiser.id)

    if total == 0:
        try:
            await callback.message.edit_text(
                "<b>Кампании</b>\n\n"
                "У вас пока нет ни одной кампании.\n\n"
                "Нажмите «Создать», чтобы начать.",
                reply_markup=camp_kb.campaigns_empty_kb(),
            )
        except TelegramBadRequest:
            pass
        await callback.answer()
        return

    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = max(0, min(page, total_pages - 1))

    campaigns = await repo.list_for_advertiser(
        advertiser.id, limit=PAGE_SIZE, offset=page * PAGE_SIZE,
    )

    rows: list[tuple[int, str, str]] = []
    for c in campaigns:
        emoji = STATUS_EMOJI.get(c.status,"•")
        rows.append((c.id, c.title, emoji))

    text = (
        f"<b>Мои кампании</b> ({total} шт.)\n\n"
        "Нажмите на кампанию для подробностей."
    )
    try:
        await callback.message.edit_text(
            text,
            reply_markup=camp_kb.campaign_list_kb(
                rows, page=page, total_pages=total_pages,
            ),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


# ---------- Detail ----------


@router.callback_query(F.data.startswith(camp_kb.CB_CAMP_VIEW))
async def view_campaign(
    callback: CallbackQuery,
    advertiser: Advertiser,
    session: AsyncSession,
) -> None:
    try:
        campaign_id = int(callback.data.removeprefix(camp_kb.CB_CAMP_VIEW))
    except ValueError:
        await callback.answer("Неверный ID", show_alert=True)
        return

    repo = CampaignRepository(session)
    campaign = await repo.get_by_id(campaign_id, with_resources=True)

    if campaign is None or campaign.advertiser_id != advertiser.id:
        await callback.answer("Кампания не найдена", show_alert=True)
        return

    lines = [
        f"{STATUS_EMOJI.get(campaign.status, '•')} <b>{campaign.title}</b>\n",
        f"<b>Статус:</b> {STATUS_LABEL.get(campaign.status, str(campaign.status.value))}",
        f"<b>Бюджет:</b> {campaign.budget_total_rub:.2f} ₽",
    ]
    if campaign.budget_spent_rub > 0:
        lines.append(f"<b>Потрачено:</b> {campaign.budget_spent_rub:.2f} ₽")
    if campaign.budget_reserved_rub > 0:
        lines.append(f"<b>В резерве:</b> {campaign.budget_reserved_rub:.2f} ₽")

    if campaign.status == CampaignStatus.REJECTED and campaign.rejection_reason:
        lines.append(f"\n<b>Причина отклонения:</b>\n<i>{campaign.rejection_reason}</i>")

    lines.append("\n<b>Ресурсы:</b>")
    for r in campaign.resources:
        name = (r.username and f"@{r.username}") or r.title or f"chat {r.tg_chat_id}"
        lines.append(
            f"• {name} — {r.reward_rub:.2f} ₽ × {r.target_subscribers}"
            f"(набрано {r.actual_subscribers})"
        )

    text ="\n".join(lines)
    can_cancel = (campaign.status == CampaignStatus.DRAFT)

    try:
        await callback.message.edit_text(
            text, reply_markup=camp_kb.campaign_detail_kb(
                campaign.id, can_cancel_draft=can_cancel,
            ),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith(camp_kb.CB_CAMP_CANCEL_DRAFT))
async def cancel_draft(
    callback: CallbackQuery,
    advertiser: Advertiser,
    session: AsyncSession,
) -> None:
    try:
        campaign_id = int(callback.data.removeprefix(camp_kb.CB_CAMP_CANCEL_DRAFT))
    except ValueError:
        await callback.answer("Неверный ID", show_alert=True)
        return

    svc = CampaignService(session)
    campaign = await svc.repo.get_by_id(campaign_id)
    if campaign is None or campaign.advertiser_id != advertiser.id:
        await callback.answer("Кампания не найдена", show_alert=True)
        return

    try:
        await svc.cancel_draft(campaign=campaign)
    except CampaignValidationError as e:
        await callback.answer(e.user_message, show_alert=True)
        return

    await callback.answer("Черновик удалён")
    # Return to list
    await _render_page(callback, advertiser, session, page=0)
