"""FSM states for publisher bot."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class BotAddStates(StatesGroup):
    """Adding a new PublisherBot."""
    entering_token = State()
    entering_name = State()


class BotSettingsStates(StatesGroup):
    entering_sponsors_count = State()
    entering_ttl_minutes = State()
    selecting_themes = State()


class WithdrawStates(StatesGroup):
    entering_amount = State()
