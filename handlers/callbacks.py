from __future__ import annotations

from datetime import datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery

from database import Database
from services import ProcessManager
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
    if action == "decline":
        db.delete_proposal(proposal["id"])
        await callback.message.edit_text("<b>💔 Предложение отклонено.</b>", parse_mode="HTML")
        await callback.answer()
        return

    ptype = proposal["proposal_type"]
    if ptype == "relationship":
        db.set_relationship(proposal["initiator_id"], proposal["target_id"], "relationship")
        text = f"<b>💖 Теперь {display_name({'username': initiator['username'], 'id': initiator['user_id']})} и {display_name({'username': target['username'], 'id': target['user_id']})} в отношениях!</b>"
    elif ptype == "marriage":
        db.set_relationship(proposal["initiator_id"], proposal["target_id"], "married")
        text = f"<b>💍 Ура! Теперь {display_name({'username': initiator['username'], 'id': initiator['user_id']})} и {display_name({'username': target['username'], 'id': target['user_id']})} женаты!</b>"
    elif ptype == "sex":
        end_time = (datetime.now() + timedelta(seconds=bot.config.sex_duration_seconds)).isoformat()
        db.create_process(proposal["chat_id"], proposal["initiator_id"], "sex", end_time, proposal["target_id"], None)
        db.create_process(proposal["chat_id"], proposal["target_id"], "sex", end_time, proposal["initiator_id"], None)
        user1 = {"id": initiator["user_id"], "username": initiator["username"], "gender": initiator["gender"]}
        user2 = {"id": target["user_id"], "username": target["username"], "gender": target["gender"]}
        bot.process_manager.schedule_sex(proposal["chat_id"], user1, user2)
        text = f"<b>🔞 {display_name({'username': initiator['username'], 'id': initiator['user_id']})} и {display_name({'username': target['username'], 'id': target['user_id']})} начали...</b>\nНапиши <code>отмена</code> в течение минуты, чтобы остановить процесс."
    else:
        db.clear_relationship(proposal["initiator_id"], proposal["target_id"])
        text = "<b>💔 Отношения завершены. Теперь оба свободны.</b>"

    db.delete_proposal(proposal["id"])
    await callback.message.edit_text(text, parse_mode="HTML")
    await callback.answer("Готово ✨")


@router.callback_query(F.data.startswith("drop_child:"))
async def drop_child_callback(callback: CallbackQuery, bot: Bot) -> None:
    db: Database = bot.db
    name = callback.data.split(":", 1)[1]
    removed = db.remove_child(callback.from_user.id, name)
    me = db.get_user(callback.from_user.id)
    if me and me["partner_id"]:
        db.remove_child(me["partner_id"], name)
    if removed:
        await callback.answer("Ребёнок удалён")
        await callback.message.reply(f"<b>🗑 {name} удалён из профиля.</b>", parse_mode="HTML")
    else:
        await callback.answer("Не найден", show_alert=True)


@router.callback_query(F.data == "pregnancy:take_pill")
async def take_pill_callback(callback: CallbackQuery, bot: Bot) -> None:
    pm: ProcessManager = bot.process_manager
    if pm.take_pill(callback.from_user.id):
        await callback.answer("Таблетка принята 💊", show_alert=True)
    else:
        await callback.answer("Таблетки нет или уже поздно 😿", show_alert=True)


@router.callback_query(F.data.startswith("storebuy:"))
async def store_buy_callback(callback: CallbackQuery, bot: Bot) -> None:
    db: Database = bot.db
    _, allowed_user_id, category, idx = callback.data.split(":")
    if callback.from_user.id != int(allowed_user_id):
        await callback.answer("Эта кнопка не для тебя 💅", show_alert=True)
        return
    items = db.get_shop_items(category)
    index = int(idx)
    if index < 1 or index > len(items):
        await callback.answer("Товар не найден", show_alert=True)
        return
    item = items[index - 1]
    user = db.get_user(callback.from_user.id)
    if not user or user["balance"] < item["price"]:
        await callback.answer("Недостаточно ВРК", show_alert=True)
        return
    db.add_balance(callback.from_user.id, -item["price"])
    db.add_inventory_item(callback.from_user.id, item["name"], 1)
    await callback.answer(f"Куплено: {item['name']}", show_alert=True)
