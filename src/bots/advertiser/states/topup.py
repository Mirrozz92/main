"""FSM states for top-up flow."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class TopupStates(StatesGroup):
    """Top-up flow.

    Entry: user clicked"Пополнить"or chose"Своя сумма"preset.
    Exit: invoice link is shown (or flow is cancelled).
    """

    choosing_amount = State() # User picks preset or types own amount
    entering_custom = State() # User is typing the custom amount
