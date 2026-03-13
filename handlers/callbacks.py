from __future__ import annotations

import json
from datetime import datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery

from database import Database
from utils import display_name

router = Router(name="callbacks")


@router.callback_query(F.data.startswith("proposal:"))
async def proposal_callback(callback: CallbackQuery, bot: Bot) -> None:
    db: Database = bot.db
    _, action, proposal_id = callback.data.split(":")
    proposal = db.get_proposal(int(proposal_id))
    if not proposal:
        await callback.answer("Предложение устарело", show_alert=True)
        return
    if callback.from_user.id != proposal["target_id"]:
        await callback.answer("Эта кнопка не для тебя 💅", show_alert=True)
        return
    initiator = db.get_user(proposal["initiator_id"])
    target = db.get_user(proposal["target_id"])
    if not initiator or not target:
        db.delete_proposal(proposal["id"])
        await callback.answer("Профиль не найден", show_alert=True)
        return

    if action == "decline":
        db.delete_proposal(proposal["id"])
        await callback.message.edit_text("<b>💔 Предложение отклонено.</b>", parse_mode="HTML")
        await callback.answer()
        return

    ptype = proposal["proposal_type"]
    if ptype == "relationship":
        db.set_relationship(initiator["user_id"], target["user_id"], "relationship")
        text = f"<b>💖 Теперь {display_name({'id': initiator['user_id'], 'username': initiator['username']})} и {display_name({'id': target['user_id'], 'username': target['username']})} в отношениях!</b>"
    elif ptype == "marriage":
        db.set_relationship(initiator["user_id"], target["user_id"], "married")
        text = f"<b>💍 Теперь {display_name({'id': initiator['user_id'], 'username': initiator['username']})} и {display_name({'id': target['user_id'], 'username': target['username']})} в браке!</b>"
    elif ptype == "sex":
        end_time = (datetime.now() + timedelta(seconds=bot.config.sex_duration_seconds)).isoformat()
        db.create_process(proposal["chat_id"], initiator["user_id"], "sex", end_time, target["user_id"], None)
        db.create_process(proposal["chat_id"], target["user_id"], "sex", end_time, initiator["user_id"], None)
        bot.process_manager.schedule_sex(
            proposal["chat_id"],
            {"id": initiator["user_id"], "username": initiator["username"], "gender": initiator["gender"]},
            {"id": target["user_id"], "username": target["username"], "gender": target["gender"]},
        )
        text = f"<b>🔞 {display_name({'id': initiator['user_id'], 'username': initiator['username']})} и {display_name({'id': target['user_id'], 'username': target['username']})} начали...</b>\nНапиши <code>отмена</code> в течение минуты, чтобы остановить процесс."
    else:
        db.clear_relationship(initiator["user_id"], target["user_id"])
        text = "<b>💔 Всё завершено. Теперь оба свободны.</b>"

    db.delete_proposal(proposal["id"])
    await callback.message.edit_text(text, parse_mode="HTML")
    await callback.answer("Готово ✨")


@router.callback_query(F.data.startswith("drop_child:"))
async def drop_child_callback(callback: CallbackQuery, bot: Bot) -> None:
    db: Database = bot.db
    name = callback.data.split(":", 1)[1]
    me = db.get_user(callback.from_user.id)
    if not me:
        await callback.answer("Профиль не найден", show_alert=True)
        return
    removed = db.remove_child(callback.from_user.id, name)
    if me["partner_id"]:
        db.remove_child(me["partner_id"], name)
    if removed:
        await callback.answer("Удалено")
        await callback.message.reply(f"<b>🗑 {name} удалён(а) из профиля.</b>", parse_mode="HTML")
    else:
        await callback.answer("Не найдено", show_alert=True)


@router.callback_query(F.data == "pregnancy:take_pill")
async def take_pill_callback(callback: CallbackQuery, bot: Bot) -> None:
    if bot.process_manager.take_pill(callback.from_user.id):
        await callback.answer("Таблетка принята 💊", show_alert=True)
    else:
        await callback.answer("Таблетки нет или уже поздно", show_alert=True)


@router.callback_query(F.data.startswith("storebuy:"))
async def store_buy_callback(callback: CallbackQuery, bot: Bot) -> None:
    db: Database = bot.db
    _, allowed_uid, category, item_id = callback.data.split(":")
    if callback.from_user.id != int(allowed_uid):
        await callback.answer("Эта кнопка не для тебя 💅", show_alert=True)
        return
    item = db.get_shop_item_by_id_and_category(int(item_id), category)
    if not item:
        await callback.answer("Товар не найден", show_alert=True)
        return
    user = db.get_user(callback.from_user.id)
    balance_field = "balance" if item["currency"] == "VRK" else "vh_balance"
    if not user or user[balance_field] < item["price"]:
        await callback.answer(f"Недостаточно {item['currency']}", show_alert=True)
        return
    db.add_balance(callback.from_user.id, -item["price"], item["currency"])
    db.add_inventory_item(callback.from_user.id, item["name"], 1)
    await callback.answer(f"Куплено: {item['name']}", show_alert=True)
