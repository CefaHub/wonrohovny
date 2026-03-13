from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def proposal_keyboard(proposal_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Принять", callback_data=f"proposal:accept:{proposal_id}"),
                InlineKeyboardButton(text="❌ Отказать", callback_data=f"proposal:decline:{proposal_id}"),
            ]
        ]
    )


def child_remove_keyboard(child_name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"🗑 Отказаться от {child_name}", callback_data=f"drop_child:{child_name}")]
        ]
    )


def pill_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="💊 Выпить таблетку", callback_data="pregnancy:take_pill")]]
    )
