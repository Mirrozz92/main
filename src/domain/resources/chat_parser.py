"""Parse user input describing a Telegram chat.

Supports:
  - @username
  - https://t.me/username
  - https://t.me/+abcXyz... (invite link)
  - https://t.me/joinchat/abcXyz... (legacy invite)
  - tg://resolve?domain=username
  - just "username" (without @)

Returns a ChatReference that tells downstream code how to look up the chat.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


ChatRefKind = Literal["username", "invite_hash"]


@dataclass(frozen=True)
class ChatReference:
    kind: ChatRefKind
    # If kind=="username" → just the bare username, no @, no URL
    # If kind=="invite_hash" → the hash part after https://t.me/+
    value: str

    @property
    def display(self) -> str:
        if self.kind == "username":
            return f"@{self.value}"
        return f"invite: …{self.value[-6:]}"


USERNAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{3,31}$")


def parse_chat_input(raw: str) -> ChatReference | None:
    """Parse any user input → ChatReference, or None if unrecognized."""
    s = (raw or "").strip()
    if not s:
        return None

    # 1. tg://resolve?domain=...
    m = re.match(r"^tg://resolve\?domain=([a-zA-Z][a-zA-Z0-9_]+)", s)
    if m:
        return ChatReference(kind="username", value=m.group(1))

    # 2. https://t.me/+HASH or https://t.me/joinchat/HASH (invite link)
    m = re.match(r"^https?://t\.me/(?:joinchat/|\+)([A-Za-z0-9_-]+)/?$", s)
    if m:
        return ChatReference(kind="invite_hash", value=m.group(1))

    # 3. https://t.me/username or t.me/username
    m = re.match(r"^(?:https?://)?t\.me/([a-zA-Z][a-zA-Z0-9_]+)/?$", s)
    if m:
        username = m.group(1)
        if USERNAME_RE.match(username):
            return ChatReference(kind="username", value=username)

    # 4. @username
    if s.startswith("@"):
        username = s[1:]
        if USERNAME_RE.match(username):
            return ChatReference(kind="username", value=username)

    # 5. Bare username
    if USERNAME_RE.match(s):
        return ChatReference(kind="username", value=s)

    return None


def parse_forwarded_message(forward_from_chat_id: int | None, forward_from_chat_username: str | None) -> ChatReference | None:
    """Build a ChatReference from a forwarded message.

    If the chat has a username — return it. Otherwise we can't proceed via
    username, but we still know the chat_id (caller handles separately).
    """
    if forward_from_chat_username:
        return ChatReference(kind="username", value=forward_from_chat_username)
    return None  # caller should use forward_from_chat_id directly
