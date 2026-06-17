"""Validate that a Telegram chat is suitable for adding to a campaign.

Performs checks:
1. getChat — chat exists and we (the checker-bot) can access it
2. getChatMember(me) — we are admin with can_invite_users
3. Determine type (channel/group) and member count
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from aiogram import Bot
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError

from src.core.db.models import CheckerBot
from src.core.db.models.enums import ResourceType
from src.core.logging import get_logger
from src.domain.exceptions import ChatNotFoundError, CheckerNotAdminError, ResourceValidationError
from src.domain.resources.chat_parser import ChatReference
from src.integrations.telegram import get_checker_pool

log = get_logger("chat_validator")


ChatKind = Literal["channel", "supergroup", "group", "bot"]


@dataclass
class ChatProbeResult:
    """Outcome of probing a chat for campaign-eligibility."""

    tg_chat_id: int
    title: str
    username: str | None
    is_private: bool        # т.е. без @username
    resource_type: ResourceType
    member_count: int | None
    invite_link: str | None         # если уже есть привязанная (мы её не создаём здесь)
    checker_bot: CheckerBot         # какой именно бот это проверил
    can_invite_users: bool


async def probe_chat(
    ref: ChatReference,
    *,
    candidate_checker_bots: list[CheckerBot],
) -> ChatProbeResult:
    """Resolve a ChatReference using the first checker bot that works.

    Tries each bot in `candidate_checker_bots` order until one succeeds.

    Raises:
        ChatNotFoundError: if no bot can resolve the chat
        CheckerNotAdminError: if chat exists but no bot is admin
        ResourceValidationError: for other validation issues
    """
    if not candidate_checker_bots:
        raise ResourceValidationError("Нет доступных проверочных ботов. Свяжитесь с админом.")

    pool = get_checker_pool()

    last_error: str | None = None
    for cb in candidate_checker_bots:
        bot = pool.get_by_index(cb.token_index)
        if bot is None:
            log.warning("checker_pool_no_bot_for_index", index=cb.token_index)
            continue

        result = await _probe_with_bot(bot, cb, ref)
        if result is not None:
            return result

    # No bot succeeded
    raise ChatNotFoundError(
        f"Не удалось найти чат {ref.display}. "
        f"Убедитесь, что бот @{candidate_checker_bots[0].username} "
        f"добавлен в чат администратором."
    )


async def _probe_with_bot(
    bot: Bot,
    checker_bot: CheckerBot,
    ref: ChatReference,
) -> ChatProbeResult | None:
    """Try to probe chat with this specific bot. Returns None if this bot can't see the chat."""

    if ref.kind == "invite_hash":
        # Не можем напрямую через Bot API. Юзер должен сначала добавить нашего бота
        # как админа, тогда у канала появится chat_id, доступный нам через chat_member events.
        # На стадии создания кампании предлагаем юзеру использовать @username или forward.
        raise ResourceValidationError(
            "Для приватных каналов добавьте сначала "
            f"@{checker_bot.username} админом, затем форвардните любое сообщение "
            "из канала боту или укажите его юзернейм (если есть)."
        )

    chat_identifier = f"@{ref.value}"

    try:
        chat = await bot.get_chat(chat_identifier)
    except TelegramBadRequest as e:
        # "chat not found" / "Bad Request: chat not found"
        if "not found" in str(e).lower() or "no such" in str(e).lower():
            return None
        log.warning("getChat_bad_request", chat=chat_identifier, error=str(e))
        return None
    except TelegramForbiddenError:
        # Бот забанен в этом чате
        return None
    except TelegramAPIError as e:
        log.warning("getChat_api_error", chat=chat_identifier, error=str(e))
        return None

    # Determine type
    if chat.type == ChatType.CHANNEL:
        resource_type = ResourceType.CHANNEL
    elif chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        resource_type = ResourceType.GROUP
    elif chat.type == ChatType.PRIVATE:
        # ChatType.PRIVATE for getChat means a private user chat — но для бота это будет тоже,
        # если username принадлежит боту. Различаем по наличию свойства is_bot у chat —
        # на самом деле у Chat нет is_bot, но username бота заканчивается на "bot".
        # Используем сам факт: если username существует и заканчивается на 'bot' → bot_start
        if chat.username and chat.username.lower().endswith("bot"):
            resource_type = ResourceType.BOT_START
        else:
            raise ResourceValidationError(
                "Указанный объект — это личный пользователь. "
                "Можно добавлять только каналы, группы и боты."
            )
    else:
        raise ResourceValidationError(f"Неподдерживаемый тип чата: {chat.type}")

    # For bot_start — no membership check, we just need username
    if resource_type == ResourceType.BOT_START:
        return ChatProbeResult(
            tg_chat_id=chat.id,
            title=chat.title or chat.first_name or chat.username or "",
            username=chat.username,
            is_private=False,
            resource_type=resource_type,
            member_count=None,
            invite_link=None,
            checker_bot=checker_bot,
            can_invite_users=False,  # N/A
        )

    # For channels/groups — check we're admin with can_invite_users
    try:
        me = await bot.get_me()
        member = await bot.get_chat_member(chat.id, me.id)
    except TelegramAPIError as e:
        log.warning("getChatMember_failed", chat=chat_identifier, error=str(e))
        raise CheckerNotAdminError() from e

    if member.status not in ("administrator", "creator"):
        raise CheckerNotAdminError(
            f"Бот @{checker_bot.username} не админ в этом чате.\n\n"
            "Добавьте его администратором с правом «Приглашать пользователей по ссылке» "
            "и попробуйте снова."
        )

    can_invite = getattr(member, "can_invite_users", None)
    if can_invite is False:
        raise CheckerNotAdminError(
            f"Бот @{checker_bot.username} админ, но без права «Приглашать пользователей по ссылке».\n\n"
            "Откройте настройки чата → Администраторы → выберите этого бота → "
            "включите право «Приглашать пользователей по ссылке»."
        )

    # Get approximate member count
    member_count: int | None = None
    try:
        member_count = await bot.get_chat_member_count(chat.id)
    except TelegramAPIError:
        pass

    return ChatProbeResult(
        tg_chat_id=chat.id,
        title=chat.title or "",
        username=chat.username,
        is_private=chat.username is None,
        resource_type=resource_type,
        member_count=member_count,
        invite_link=None,
        checker_bot=checker_bot,
        can_invite_users=bool(can_invite),
    )
