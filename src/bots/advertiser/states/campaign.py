"""FSM states for campaign creation flow."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class CampaignCreate(StatesGroup):
    """Multi-step campaign creation.

    Flow:
      entering_title user types campaign name
      adding_resource_chat user sends @username, forward, or t.me/...
      adding_resource_reward user picks/types reward per subscriber
      adding_resource_target user picks/types target subscriber count
      asking_more_resources"add another resource?"yes/no/cancel
      confirming final summary +"Submit for moderation"
    """

    entering_title = State()
    adding_resource_chat = State()
    adding_resource_reward = State()
    adding_resource_target = State()
    asking_more_resources = State()
    # Targeting (all optional, asked once per campaign before confirm)
    targeting_age = State()
    targeting_gender = State()
    targeting_country = State()
    targeting_audience = State()
    targeting_rating = State()
    confirming = State()
