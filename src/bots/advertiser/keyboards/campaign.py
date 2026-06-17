"""Keyboards for campaign creation and listing flows."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.bots.advertiser import texts


# ---------- Callback namespaces ----------

# Create flow
CB_CAMP_CANCEL ="camp:cancel"
CB_CAMP_REWARD_PRESET ="camp:reward:"# + decimal as str
CB_CAMP_REWARD_CUSTOM ="camp:reward_custom"
CB_CAMP_TARGET_PRESET ="camp:target:"# + int as str
CB_CAMP_TARGET_CUSTOM ="camp:target_custom"
CB_CAMP_MORE_YES ="camp:more:yes"
CB_CAMP_MORE_NO ="camp:more:no"
CB_CAMP_SUBMIT ="camp:submit"
CB_CAMP_BACK_TO_RESOURCES ="camp:back_resources"
# Targeting
CB_TGT_AGE ="camp:tgt_age:"          # + value
CB_TGT_GENDER ="camp:tgt_gender:"    # + value (toggle)
CB_TGT_GENDER_NEXT ="camp:tgt_gender_next"
CB_TGT_COUNTRY ="camp:tgt_country:"  # + value (toggle)
CB_TGT_COUNTRY_NEXT ="camp:tgt_country_next"
CB_TGT_AUD ="camp:tgt_aud:"          # + key (toggle)
CB_TGT_AUD_NEXT ="camp:tgt_aud_next"
CB_TGT_RATING ="camp:tgt_rating:"    # + value
CB_TGT_SKIP_ALL ="camp:tgt_skip_all"

# Start of create flow
CB_CAMP_CREATE ="camp:create"

# Listing flow
CB_CAMP_LIST_PAGE ="camp:list_page:"# + page number
CB_CAMP_VIEW ="camp:view:"# + campaign_id
CB_CAMP_CANCEL_DRAFT ="camp:cancel_draft:"# + campaign_id


# ---------- Presets ----------

REWARD_PRESETS_RUB: tuple[str, ...] = ("1","2","3","5","10")
TARGET_PRESETS: tuple[int, ...] = (100, 500, 1000, 5000, 10000)


# ---------- Keyboards ----------


def cancel_only_kb() -> InlineKeyboardMarkup:
    """Single cancel button during text input."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Отменить", callback_data=CB_CAMP_CANCEL)],
    ])


def campaigns_empty_kb() -> InlineKeyboardMarkup:
    """When user has no campaigns — show 'Create' and back."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Создать кампанию", callback_data=CB_CAMP_CREATE)],
        [InlineKeyboardButton(text=texts.btn_back(), callback_data=texts.CB_MENU)],
    ])


def reward_presets_kb() -> InlineKeyboardMarkup:
    """Preset reward values + custom + cancel."""
    rows: list[list[InlineKeyboardButton]] = []
    chunk: list[InlineKeyboardButton] = []
    for rub in REWARD_PRESETS_RUB:
        chunk.append(
            InlineKeyboardButton(
                text=f"{rub} ₽",
                callback_data=f"{CB_CAMP_REWARD_PRESET}{rub}",
            )
        )
        if len(chunk) == 3:
            rows.append(chunk); chunk = []
    if chunk:
        rows.append(chunk)
    rows.append([
        InlineKeyboardButton(text="Своя цена", callback_data=CB_CAMP_REWARD_CUSTOM),
    ])
    rows.append([
        InlineKeyboardButton(text="Отменить", callback_data=CB_CAMP_CANCEL),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def target_presets_kb() -> InlineKeyboardMarkup:
    """Preset target counts."""
    rows: list[list[InlineKeyboardButton]] = []
    chunk: list[InlineKeyboardButton] = []
    for n in TARGET_PRESETS:
        chunk.append(
            InlineKeyboardButton(
                text=f"{n}",
                callback_data=f"{CB_CAMP_TARGET_PRESET}{n}",
            )
        )
        if len(chunk) == 3:
            rows.append(chunk); chunk = []
    if chunk:
        rows.append(chunk)
    rows.append([
        InlineKeyboardButton(text="Своё значение", callback_data=CB_CAMP_TARGET_CUSTOM),
    ])
    rows.append([
        InlineKeyboardButton(text="Отменить", callback_data=CB_CAMP_CANCEL),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def more_resources_kb() -> InlineKeyboardMarkup:
    """Add another resource? yes / no / cancel."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Добавить ещё", callback_data=CB_CAMP_MORE_YES),
            InlineKeyboardButton(text="Хватит, далее", callback_data=CB_CAMP_MORE_NO),
        ],
        [InlineKeyboardButton(text="Отменить кампанию", callback_data=CB_CAMP_CANCEL)],
    ])


def confirm_submit_kb() -> InlineKeyboardMarkup:
    """Final confirm screen."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Отправить на модерацию", callback_data=CB_CAMP_SUBMIT)],
        [InlineKeyboardButton(text="« Назад к ресурсам", callback_data=CB_CAMP_BACK_TO_RESOURCES)],
        [InlineKeyboardButton(text="Отменить кампанию", callback_data=CB_CAMP_CANCEL)],
    ])


# ---------- Listing ----------


def campaign_list_kb(
    campaigns_data: list[tuple[int, str, str]],
    *,
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    """Build keyboard for /campaigns listing.

    Args:
        campaigns_data: list of (campaign_id, title, status_emoji)
        page: current page (0-indexed)
        total_pages: total pages count
    """
    rows: list[list[InlineKeyboardButton]] = []

    for cid, title, status_emoji in campaigns_data:
        # Truncate title
        display = title if len(title) <= 30 else title[:27] +"…"
        rows.append([
            InlineKeyboardButton(
                text=f"{status_emoji} {display}",
                callback_data=f"{CB_CAMP_VIEW}{cid}",
            )
        ])

    # Pagination
    if total_pages > 1:
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(InlineKeyboardButton(
                text="« Назад", callback_data=f"{CB_CAMP_LIST_PAGE}{page - 1}",
            ))
        nav.append(InlineKeyboardButton(
            text=f"{page + 1}/{total_pages}", callback_data="noop",
        ))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(
                text="Вперёд »", callback_data=f"{CB_CAMP_LIST_PAGE}{page + 1}",
            ))
        rows.append(nav)

    rows.append([
        InlineKeyboardButton(text="Создать", callback_data=CB_CAMP_CREATE),
        InlineKeyboardButton(text=texts.btn_back(), callback_data=texts.CB_MENU),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def campaign_detail_kb(campaign_id: int, *, can_cancel_draft: bool) -> InlineKeyboardMarkup:
    """Buttons under a single campaign card."""
    rows: list[list[InlineKeyboardButton]] = []
    if can_cancel_draft:
        rows.append([
            InlineKeyboardButton(
                text="Удалить черновик",
                callback_data=f"{CB_CAMP_CANCEL_DRAFT}{campaign_id}",
            )
        ])
    rows.append([
        InlineKeyboardButton(text="« К списку", callback_data=f"{CB_CAMP_LIST_PAGE}0"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)



# ---------- Targeting keyboards ----------

def targeting_age_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Любой возраст", callback_data=f"{CB_TGT_AGE}any")],
        [InlineKeyboardButton(text="14+", callback_data=f"{CB_TGT_AGE}min_14_plus")],
        [InlineKeyboardButton(text="16+", callback_data=f"{CB_TGT_AGE}min_16_plus")],
        [InlineKeyboardButton(text="18+", callback_data=f"{CB_TGT_AGE}min_18_plus")],
        [InlineKeyboardButton(text="Пропустить весь таргетинг", callback_data=CB_TGT_SKIP_ALL)],
    ])


def targeting_gender_kb(selected: list[str]) -> InlineKeyboardMarkup:
    def mark(v, label):
        return ("[x] " if v in selected else "[ ] ") + label
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=mark("male", "Мужской"), callback_data=f"{CB_TGT_GENDER}male")],
        [InlineKeyboardButton(text=mark("female", "Женский"), callback_data=f"{CB_TGT_GENDER}female")],
        [InlineKeyboardButton(text=mark("undisclosed", "Не указан"), callback_data=f"{CB_TGT_GENDER}undisclosed")],
        [InlineKeyboardButton(text="Далее", callback_data=CB_TGT_GENDER_NEXT)],
    ])


def targeting_country_kb(selected: list[str]) -> InlineKeyboardMarkup:
    def mark(v, label):
        return ("[x] " if v in selected else "[ ] ") + label
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=mark("RU", "Россия"), callback_data=f"{CB_TGT_COUNTRY}RU")],
        [InlineKeyboardButton(text=mark("UA", "Украина"), callback_data=f"{CB_TGT_COUNTRY}UA")],
        [InlineKeyboardButton(text=mark("BY", "Беларусь"), callback_data=f"{CB_TGT_COUNTRY}BY")],
        [InlineKeyboardButton(text=mark("KZ", "Казахстан"), callback_data=f"{CB_TGT_COUNTRY}KZ")],
        [InlineKeyboardButton(text=mark("OTHER", "Другие"), callback_data=f"{CB_TGT_COUNTRY}OTHER")],
        [InlineKeyboardButton(text="Далее", callback_data=CB_TGT_COUNTRY_NEXT)],
    ])


def targeting_audience_kb(flags: dict) -> InlineKeyboardMarkup:
    def mark(k, label):
        return ("[x] " if flags.get(k) else "[ ] ") + label
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=mark("require_premium", "Telegram Premium"), callback_data=f"{CB_TGT_AUD}require_premium")],
        [InlineKeyboardButton(text=mark("require_photo", "Фото профиля"), callback_data=f"{CB_TGT_AUD}require_photo")],
        [InlineKeyboardButton(text=mark("require_username", "Юзернейм"), callback_data=f"{CB_TGT_AUD}require_username")],
        [InlineKeyboardButton(text=mark("require_bio", "Описание (bio)"), callback_data=f"{CB_TGT_AUD}require_bio")],
        [InlineKeyboardButton(text=mark("require_stories", "Истории"), callback_data=f"{CB_TGT_AUD}require_stories")],
        [InlineKeyboardButton(text="Далее", callback_data=CB_TGT_AUD_NEXT)],
    ])


def targeting_rating_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Без ограничения", callback_data=f"{CB_TGT_RATING}0")],
        [InlineKeyboardButton(text="От 5.0", callback_data=f"{CB_TGT_RATING}5")],
        [InlineKeyboardButton(text="От 7.0", callback_data=f"{CB_TGT_RATING}7")],
        [InlineKeyboardButton(text="От 8.0", callback_data=f"{CB_TGT_RATING}8")],
        [InlineKeyboardButton(text="От 9.0", callback_data=f"{CB_TGT_RATING}9")],
    ])
