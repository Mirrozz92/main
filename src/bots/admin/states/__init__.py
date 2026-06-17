from aiogram.fsm.state import State, StatesGroup


class ModerationStates(StatesGroup):
    """States for admin's moderation flow."""
    entering_rejection_reason = State()


class BotModerationStates(StatesGroup):
    """States for admin's publisher-bot moderation flow."""
    entering_note = State()


class WithdrawalStates(StatesGroup):
    """States for admin's withdrawal processing flow."""
    entering_reject_reason = State()
