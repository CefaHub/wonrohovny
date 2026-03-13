from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup



def proposal_keyboard(proposal_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="✅ Принять", callback_data=f"proposal:accept:{proposal_id}"),
            InlineKeyboardButton(text="❌ Отказать", callback_data=f"proposal:decline:{proposal_id}"),
        ]]
    )



def child_remove_keyboard(child_name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🗑 Отказаться", callback_data=f"drop_child:{child_name}")]]
    )



def pill_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="💊 Выпить таблетку", callback_data="pregnancy:take_pill")]]
    )



def store_keyboard(user_id: int, category: str, items: list) -> InlineKeyboardMarkup:
    rows = []
    for item in items[:10]:
        rows.append([InlineKeyboardButton(text=f"🛍 Купить #{item['id']}", callback_data=f"storebuy:{user_id}:{category}:{item['id']}")])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else InlineKeyboardMarkup(inline_keyboard=[])
