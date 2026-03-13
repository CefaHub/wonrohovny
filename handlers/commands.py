from __future__ import annotations

import random
from datetime import date, datetime
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.types import Message

from database import Database
from keyboards import child_remove_keyboard, proposal_keyboard, store_keyboard
from services import GachaService
from utils import (
    FUN_ACTIONS,
    PROFESSIONS,
    RARITY_ORDER,
    display_name,
    escape,
    fmt_status,
    human_timedelta,
    is_admin,
    is_creator,
    load_adventures,
    parse_card_caption,
    parse_command,
    parse_datetime,
    resolve_target_and_strip,
)

router = Router(name="commands")
ADVENTURES = load_adventures(Path(__file__).resolve().parents[1] / "data" / "adventures.json")


def _status_ok_for_relationship(row) -> bool:
    return row and row["relationship_status"] == "single"


def _bank_name_and_amount(args: list[str]) -> tuple[str | None, int | None]:
    if len(args) < 2:
        return None, None
    try:
        amount = int(args[-1])
    except ValueError:
        return None, None
    name = " ".join(args[:-1]).strip()
    return name or None, amount


async def _send_store(message: Message, db: Database, user_id: int, category: str, title: str) -> None:
    items = db.get_shop_items(category)
    currency = "ВХ" if category == "vhshop" else "ВРК"
    if not items:
        await message.reply(f"<b>🛒 {title}</b>\nПока пусто.", parse_mode="HTML")
        return
    lines = [f"<b>🛒 {title}</b>"]
    for i in items:
        lines.append(f"{i['id']}. {escape(i['name'])} — {i['price']} {currency}")
    await message.reply("\n".join(lines), parse_mode="HTML", reply_markup=store_keyboard(user_id, category, items))


@router.message(F.photo)
async def handle_photo_uploads(message: Message, bot: Bot) -> None:
    if message.chat.type not in {"group", "supergroup"} or not message.from_user or message.from_user.is_bot:
        return
    db: Database = bot.db
    db.ensure_user(message.from_user.id, message.from_user.username)
    pending = db.get_pending_card_upload(message.from_user.id)
    if not pending:
        return
    if not await is_admin(bot, message.chat.id, message.from_user.id):
        db.clear_pending_card_upload(message.from_user.id)
        return
    photo = message.photo[-1]
    caption = message.caption or "Без названия"
    parsed = parse_card_caption(caption)
    price_map = {"обычная": 60, "редкая": 180, "эпическая": 450, "легендарная": 1200, "секрет": 3000}
    card_id = db.add_card(
        title=parsed["title"],
        idol_name=parsed["idol_name"],
        group_name=parsed["group_name"],
        album_name=parsed["album_name"],
        rarity=pending["rarity"],
        gacha_type=pending["gacha_type"],
        caption=caption,
        photo_file_id=photo.file_id,
        sell_price=price_map.get(pending["rarity"], 100),
        created_by=message.from_user.id,
    )
    db.clear_pending_card_upload(message.from_user.id)
    await message.reply(f"<b>🃏 Карточка добавлена!</b> ID: {card_id}\nТип гачи: <b>{'элитная' if pending['gacha_type']=='elite' else 'обычная'}</b>\nРедкость: <b>{pending['rarity']}</b>", parse_mode="HTML")


@router.message(F.text | F.caption)
async def handle_all_messages(message: Message, bot: Bot) -> None:
    if message.chat.type not in {"group", "supergroup"}:
        return
    if not message.from_user or message.from_user.is_bot:
        return

    db: Database = bot.db
    db.register_message(message.from_user.id, message.from_user.username)

    text = message.text or message.caption or ""
    command, args = parse_command(text)
    if not command:
        return

    if command == "магазин" and args and args[0].lower() == "купить":
        await cmd_buy_by_category(message, bot, db, "shop", args[1:] if len(args) > 1 else [])
        return
    if command == "аптека" and args and args[0].lower() == "купить":
        await cmd_buy_by_category(message, bot, db, "pharmacy", args[1:] if len(args) > 1 else [])
        return
    if command == "вхмагазин" and args and args[0].lower() == "купить":
        await cmd_buy_by_category(message, bot, db, "vhshop", args[1:] if len(args) > 1 else [])
        return
    if command == "работа" and args and args[0].lower() == "стать":
        await cmd_job_choose(message, bot, db, args[1:])
        return
    if command == "активность" and args and args[0].lower() == "всех":
        await cmd_activity_all(message, bot, db)
        return
    if command == "гача" and args and args[0].lower() == "вх":
        await cmd_gacha(message, bot, db, elite=True)
        return
    if command == "дети":
        if not args:
            await cmd_children_list(message, bot, db)
            return
        sub = args[0].lower()
        if sub in {"покормить", "обнять", "лечить", "тренировать", "школа", "танцы", "вокал"}:
            await cmd_child_action(message, bot, db, sub, args[1:])
            return
        if sub in {"играть", "дружить", "дуэт", "ссора"}:
            await cmd_children_interaction(message, bot, db, sub, args[1:])
            return
        await cmd_children_list(message, bot, db)
        return

    handlers = {
        "инфо": cmd_info,
        "пол": cmd_gender,
        "роль": cmd_role,
        "отношения": cmd_relationship,
        "брак": cmd_marriage,
        "свадьба": cmd_marriage,
        "развод": cmd_breakup,
        "расставание": cmd_breakup,
        "секс": cmd_sex,
        "отмена": cmd_cancel_process,
        "выпить": cmd_take_pill,
        "имя": cmd_name_child,
        "отказаться": cmd_drop_child,
        "ребёнок": cmd_child_profile,
        "перевод": cmd_transfer,
        "создать_банк": cmd_create_bank,
        "банк_добавить": cmd_bank_add,
        "банк_удалить": cmd_bank_remove,
        "снять_с_банка": cmd_bank_withdraw,
        "банк": cmd_bank_info,
        "магазин": lambda m, b, d: cmd_show_store(m, b, d, "shop"),
        "аптека": lambda m, b, d: cmd_show_store(m, b, d, "pharmacy"),
        "вхмагазин": lambda m, b, d: cmd_show_store(m, b, d, "vhshop"),
        "купить": cmd_buy,
        "подарить": cmd_gift,
        "инвентарь": cmd_inventory,
        "работа": cmd_job,
        "стопберем": cmd_stop_pregnancy,
        "установить_шанс_берем": cmd_set_pregnancy_chance,
        "сброс": cmd_reset_user,
        "setbalance": cmd_set_balance,
        "setвх": cmd_set_vh,
        "добавить_товар": cmd_add_item,
        "удалить_товар": cmd_remove_item,
        "товары": cmd_all_items,
        "бонус": cmd_daily_bonus,
        "активность": cmd_activity,
        "гача": lambda m, b, d: cmd_gacha(m, b, d, elite=False),
        "карточки": cmd_cards,
        "карточка": cmd_card_info,
        "продать": cmd_sell_card,
        "передать_карточку": cmd_give_card,
        "карточки_все": cmd_all_cards,
        "добавить": cmd_add_to_gacha,
        "удалить_карточку": cmd_delete_card,
        "выдать_карточку": cmd_grant_card,
        "забрать_карточку": cmd_take_card,
        "добавить_группу": cmd_add_group,
        "удалить_группу": cmd_remove_group,
        "группы": cmd_groups,
        "добавить_альбом": cmd_add_album,
        "удалить_альбом": cmd_remove_album,
        "альбомы": cmd_albums,
        "рпг": cmd_rpg_profile,
        "приключение": cmd_adventure,
        "концерт": cmd_concert,
        "хейтеры": cmd_haters,
        "репутация": cmd_reputation,
        "вх": cmd_vh_balance,
        "обнять": cmd_fun_action,
        "поцеловать": cmd_fun_action,
        "погладить": cmd_fun_action,
        "ударить": cmd_fun_action,
        "укусить": cmd_fun_action,
        "засмущать": cmd_fun_action,
        "похвалить": cmd_fun_action,
        "шип": cmd_ship,
        "кто": cmd_who,
        "ктоя": cmd_whoami,
    }
    handler = handlers.get(command)
    if handler:
        await handler(message, bot, db)


async def cmd_info(message: Message, bot: Bot, db: Database) -> None:
    target, _ = await resolve_target_and_strip(message, bot)
    target_id = target["id"] if target else message.from_user.id
    row = db.get_user(target_id)
    if not row:
        await message.reply("<b>😿 Профиль не найден.</b>")
        return
    partner_name = None
    if row["partner_id"]:
        partner = db.get_user(row["partner_id"])
        if partner:
            partner_name = display_name({"id": partner["user_id"], "username": partner["username"]})
    children = db.get_children(row["user_id"])
    child_text = "нет"
    markup = None
    if children:
        child_text = "\n".join([f"• {escape(ch['name'])} ({ch['gender']})" for ch in children])
        if row["user_id"] == message.from_user.id:
            markup = child_remove_keyboard(children[0]["name"])
    banks = db.get_user_banks(row["user_id"])
    bank_text = "\n".join([f"• {escape(b['name'])} — {b['balance']} ВРК" for b in banks]) if banks else "нет"
    gifts = db.get_inventory(row["user_id"])
    gifts_text = "\n".join([f"• {escape(g['item_name'])} ({g['quantity']})" for g in gifts]) if gifts else "нет"
    gender_map = {"м": "мужской", "ж": "женский", None: "не указан"}
    text = (
        f"<b>👤 Информация о {display_name({'id': row['user_id'], 'username': row['username']})}</b>\n"
        f"<b>—————————————</b>\n"
        f"🎭 <b>Роль:</b> {escape(row['custom_role'] or 'нет')}\n"
        f"⚥ <b>Пол:</b> {gender_map.get(row['gender'], 'не указан')}\n"
        f"💬 <b>Сообщений:</b> всего {row['total_messages']} | сегодня {row['daily_messages']}\n"
        f"📅 <b>В чате с:</b> {escape(row['first_seen'][:10])}\n"
        f"❤️ <b>Статус:</b> {fmt_status(row['relationship_status'], partner_name)}\n"
        f"👶 <b>Дети:</b>\n{child_text}\n"
        f"💰 <b>Баланс:</b> {row['balance']} ВРК | {row['vh_balance']} ВХ\n"
        f"🏦 <b>Банки:</b>\n{bank_text}\n"
        f"🎁 <b>Инвентарь:</b>\n{gifts_text}"
    )
    await message.reply(text, parse_mode="HTML", reply_markup=markup)


async def cmd_gender(message: Message, bot: Bot, db: Database) -> None:
    _, args = parse_command(message.text)
    if not args or args[0].lower() not in {"м", "ж"}:
        await message.reply("<b>💡 Формат:</b> <code>пол м</code> или <code>пол ж</code>")
        return
    db.update_user_field(message.from_user.id, "gender", args[0].lower())
    await message.reply("<b>✨ Пол обновлён.</b>")


async def cmd_role(message: Message, bot: Bot, db: Database) -> None:
    if not await is_admin(bot, message.chat.id, message.from_user.id):
        await message.reply("<b>⛔ Только админы могут назначать роли.</b>")
        return
    target, stripped = await resolve_target_and_strip(message, bot)
    if not target:
        await message.reply("<b>💡 Формат:</b> <code>роль @user текст</code> или ответом.")
        return
    role_text = stripped.split(maxsplit=1)[1] if len(stripped.split(maxsplit=1)) > 1 else ""
    if not role_text:
        await message.reply("<b>💡 После пользователя нужно указать текст роли.</b>")
        return
    db.ensure_user(target["id"], target.get("username"))
    db.update_user_field(target["id"], "custom_role", role_text.strip())
    await message.reply(f"<b>🎭 Роль для {display_name(target)}:</b> {escape(role_text.strip())}")


async def _proposal_common(message: Message, bot: Bot, db: Database, proposal_type: str, text: str) -> None:
    target, _ = await resolve_target_and_strip(message, bot)
    if not target:
        await message.reply("<b>💡 Укажи пользователя через @username или ответом.</b>")
        return
    if target["id"] == message.from_user.id:
        await message.reply("<b>😹 На себя это не работает.</b>")
        return
    db.ensure_user(target["id"], target.get("username"))
    me = db.get_user(message.from_user.id)
    other = db.get_user(target["id"])
    if proposal_type == "relationship":
        if not (_status_ok_for_relationship(me) and _status_ok_for_relationship(other)):
            await message.reply("<b>💔 Кто-то из вас уже не свободен.</b>")
            return
    elif proposal_type == "marriage":
        me_ok = me["relationship_status"] in {"single", "relationship"} and (me["partner_id"] in {None, other['user_id']})
        other_ok = other["relationship_status"] in {"single", "relationship"} and (other["partner_id"] in {None, me['user_id']})
        if not (me_ok and other_ok):
            await message.reply("<b>💍 Брак доступен свободным или уже паре друг с другом.</b>")
            return
    elif proposal_type == "breakup":
        if not me or me["partner_id"] != other["user_id"]:
            await message.reply("<b>💔 У тебя нет отношений с этим пользователем.</b>")
            return
    proposal_id = db.create_proposal(message.chat.id, message.from_user.id, target["id"], proposal_type)
    await message.reply(text.format(me=display_name(message.from_user), target=display_name(target)), parse_mode="HTML", reply_markup=proposal_keyboard(proposal_id))


async def cmd_relationship(message: Message, bot: Bot, db: Database) -> None:
    await _proposal_common(message, bot, db, "relationship", "<b>💖 {me} предлагает {target} начать отношения!</b>")


async def cmd_marriage(message: Message, bot: Bot, db: Database) -> None:
    await _proposal_common(message, bot, db, "marriage", "<b>💍 {me} делает предложение {target}!</b>")


async def cmd_breakup(message: Message, bot: Bot, db: Database) -> None:
    me = db.get_user(message.from_user.id)
    if not me or not me["partner_id"]:
        await message.reply("<b>😿 Сейчас у тебя нет партнёра.</b>")
        return
    partner = db.get_user(me["partner_id"])
    if not partner:
        db.clear_relationship(message.from_user.id, None)
        await message.reply("<b>💔 Статус очищен.</b>")
        return
    proposal_id = db.create_proposal(message.chat.id, message.from_user.id, partner["user_id"], "breakup")
    await message.reply(f"<b>💔 {display_name(message.from_user)} хочет завершить отношения с {display_name({'id': partner['user_id'], 'username': partner['username']})}.</b>", parse_mode="HTML", reply_markup=proposal_keyboard(proposal_id))


async def cmd_sex(message: Message, bot: Bot, db: Database) -> None:
    target, _ = await resolve_target_and_strip(message, bot)
    if not target:
        await message.reply("<b>💡 Формат:</b> <code>секс @user</code> или ответом.")
        return
    if target["id"] == message.from_user.id:
        await message.reply("<b>😳 Нельзя с собой.</b>")
        return
    pair = db.get_process_pair("sex", message.from_user.id, target["id"])
    if pair:
        await message.reply("<b>⏳ Процесс уже идёт.</b>")
        return
    proposal_id = db.create_proposal(message.chat.id, message.from_user.id, target["id"], "sex")
    await message.reply(f"<b>🔞 {display_name(message.from_user)} предлагает {display_name(target)} начать процесс...</b>", parse_mode="HTML", reply_markup=proposal_keyboard(proposal_id))


async def cmd_cancel_process(message: Message, bot: Bot, db: Database) -> None:
    my = db.get_process(message.from_user.id, "sex")
    if not my:
        await message.reply("<b>😿 У тебя нет активного процесса.</b>")
        return
    db.cancel_process_pair("sex", message.from_user.id, my["partner_id"])
    await message.reply("<b>🛑 Процесс отменён.</b>")


async def cmd_take_pill(message: Message, bot: Bot, db: Database) -> None:
    _, args = parse_command(message.text)
    if len(args) >= 1 and args[0].lower() == "таблетку":
        if bot.process_manager.take_pill(message.from_user.id):
            await message.reply("<b>💊 Таблетка принята.</b>")
        else:
            await message.reply("<b>😿 Таблетки нет или ты не беременен(на).</b>")


async def cmd_name_child(message: Message, bot: Bot, db: Database) -> None:
    if not message.reply_to_message:
        await message.reply("<b>💡 Ответь на сообщение о родах.</b>")
        return
    birth = db.get_pending_birth(message.reply_to_message.message_id)
    if not birth:
        await message.reply("<b>😿 Это не сообщение о родах.</b>")
        return
    _, args = parse_command(message.text)
    if len(args) < 2 or args[0].lower() not in {"мальчик", "девочка"}:
        await message.reply("<b>💡 Формат:</b> <code>имя девочка Саша</code>")
        return
    gender = args[0].lower()
    name = " ".join(args[1:]).strip()
    if not name:
        await message.reply("<b>😿 Имя не может быть пустым.</b>")
        return
    db.add_child_for_parents([birth["mother_id"], birth["father_id"]], name, gender)
    db.delete_pending_birth(message.reply_to_message.message_id)
    await message.reply(f"<b>🎀 Ребёнок записан:</b> {escape(name)} ({gender})")


async def cmd_drop_child(message: Message, bot: Bot, db: Database) -> None:
    _, args = parse_command(message.text)
    if not args:
        await message.reply("<b>💡 Формат:</b> <code>отказаться имя</code>")
        return
    name = " ".join(args)
    removed = db.remove_child(message.from_user.id, name)
    me = db.get_user(message.from_user.id)
    if me and me["partner_id"]:
        db.remove_child(me["partner_id"], name)
    await message.reply("<b>🗑 Удалено.</b>" if removed else "<b>😿 Ребёнок не найден.</b>")


async def cmd_children_list(message: Message, bot: Bot, db: Database) -> None:
    children = db.get_children(message.from_user.id)
    if not children:
        await message.reply("<b>👶 У тебя пока нет детей.</b>")
        return
    lines = ["<b>👶 Твои дети</b>"]
    for ch in children:
        lines.append(f"• {escape(ch['name'])} — {ch['age']} г. | {ch['stage']} | ❤ {ch['mood']} | 🩺 {ch['health']}{' | аутизм' if ch['autism'] else ''}")
    await message.reply("\n".join(lines), parse_mode='HTML')


async def cmd_child_profile(message: Message, bot: Bot, db: Database) -> None:
    _, args = parse_command(message.text)
    name = " ".join(args).strip()
    if not name:
        await message.reply("<b>💡 Формат:</b> <code>ребёнок имя</code>")
        return
    ch = db.get_child_for_parent(message.from_user.id, name)
    if not ch:
        await message.reply("<b>😿 Такой ребёнок не найден.</b>")
        return
    relations = db.get_child_relations(ch['id'])
    rel_text = []
    for rel in relations[:5]:
        other_id = rel['child2_id'] if rel['child1_id'] == ch['id'] else rel['child1_id']
        other = None
        for c in db.get_children(message.from_user.id):
            if c['id'] == other_id:
                other = c
                break
        rel_text.append(f"• {rel['relation_type']} ({rel['relation_value']})")
    text = (
        f"<b>👶 Ребёнок: {escape(ch['name'])}</b>\n"
        f"Возраст: {ch['age']}\n"
        f"Этап: {ch['stage']}\n"
        f"Здоровье: {ch['health']}\n"
        f"Настроение: {ch['mood']}\n"
        f"Сытость: {ch['satiety']}\n"
        f"Энергия: {ch['energy']}\n"
        f"Воспитание: {ch['upbringing']}\n"
        f"Вокал: {ch['talent_vocal']} | Танцы: {ch['talent_dance']} | Рэп: {ch['talent_rap']} | Актёрство: {ch['talent_acting']}\n"
        f"Харизма: {ch['charisma']} | Дисциплина: {ch['discipline']}\n"
        f"Особенность: {'аутизм' if ch['autism'] else 'нет'}"
    )
    await message.reply(text, parse_mode='HTML')


async def cmd_child_action(message: Message, bot: Bot, db: Database, action: str, args: list[str]) -> None:
    if not args:
        await message.reply(f"<b>💡 Формат:</b> <code>дети {action} имя</code>")
        return
    name = " ".join(args).strip()
    ch = db.get_child_for_parent(message.from_user.id, name)
    if not ch:
        await message.reply("<b>😿 Такой ребёнок не найден.</b>")
        return
    fields = {}
    love_field = 'love_parent1' if ch['parent1_id'] == message.from_user.id else 'love_parent2'
    text = ''
    def clamp(v):
        return max(0, min(100, v))
    if action == 'покормить':
        fields = {'satiety': clamp(ch['satiety'] + 25), 'mood': clamp(ch['mood'] + 8), love_field: clamp(ch[love_field] + 5)}
        text = f"🍲 {escape(ch['name'])} сыт(а) и доволен(на)."
    elif action == 'обнять':
        fields = {'mood': clamp(ch['mood'] + 15), love_field: clamp(ch[love_field] + 10)}
        text = f"🤍 {escape(ch['name'])} почувствовал(а) заботу."
    elif action == 'лечить':
        fields = {'health': clamp(ch['health'] + 20), 'mood': clamp(ch['mood'] + 5)}
        text = f"💊 {escape(ch['name'])} чувствует себя лучше."
    elif action == 'тренировать':
        fields = {'energy': clamp(ch['energy'] - 10), 'discipline': clamp(ch['discipline'] + 5), 'upbringing': clamp(ch['upbringing'] + 3)}
        text = f"🏋️ {escape(ch['name'])} потренировался(ась)."
    elif action == 'школа':
        fields = {'discipline': clamp(ch['discipline'] + 7), 'energy': clamp(ch['energy'] - 5), 'upbringing': clamp(ch['upbringing'] + 4)}
        text = f"📚 {escape(ch['name'])} сходил(а) в школу."
    elif action == 'танцы':
        fields = {'talent_dance': clamp(ch['talent_dance'] + 6), 'energy': clamp(ch['energy'] - 8), 'mood': clamp(ch['mood'] + 4)}
        text = f"🩰 {escape(ch['name'])} прокачал(а) танцы."
    elif action == 'вокал':
        fields = {'talent_vocal': clamp(ch['talent_vocal'] + 6), 'energy': clamp(ch['energy'] - 8), 'mood': clamp(ch['mood'] + 4)}
        text = f"🎤 {escape(ch['name'])} позанимался(ась) вокалом."
    db.update_child_fields(ch['id'], **fields)
    await message.reply(f"<b>{text}</b>", parse_mode='HTML')


async def cmd_children_interaction(message: Message, bot: Bot, db: Database, action: str, args: list[str]) -> None:
    if len(args) < 2:
        await message.reply(f"<b>💡 Формат:</b> <code>дети {action} имя1 имя2</code>")
        return
    name1 = args[0]
    name2 = " ".join(args[1:]).strip()
    ch1 = db.get_child_for_parent(message.from_user.id, name1)
    ch2 = db.get_child_for_parent(message.from_user.id, name2)
    if not ch1 or not ch2:
        await message.reply("<b>😿 Один из детей не найден.</b>")
        return
    rel_type = {'играть':'friend','дружить':'friend','дуэт':'duo','ссора':'conflict'}[action]
    delta = 12 if action in {'играть','дружить','дуэт'} else -12
    db.set_child_relation(ch1['id'], ch2['id'], rel_type, abs(delta))
    def clamp(v):
        return max(0, min(100, v))
    if action in {'играть','дружить'}:
        db.update_child_fields(ch1['id'], mood=clamp(ch1['mood'] + 8))
        db.update_child_fields(ch2['id'], mood=clamp(ch2['mood'] + 8))
        txt = f"🧸 {escape(ch1['name'])} и {escape(ch2['name'])} отлично провели время вместе."
    elif action == 'дуэт':
        db.update_child_fields(ch1['id'], talent_vocal=clamp(ch1['talent_vocal'] + 3), talent_dance=clamp(ch1['talent_dance'] + 3))
        db.update_child_fields(ch2['id'], talent_vocal=clamp(ch2['talent_vocal'] + 3), talent_dance=clamp(ch2['talent_dance'] + 3))
        txt = f"🎶 {escape(ch1['name'])} и {escape(ch2['name'])} устроили дуэт."
    else:
        db.update_child_fields(ch1['id'], mood=clamp(ch1['mood'] - 10))
        db.update_child_fields(ch2['id'], mood=clamp(ch2['mood'] - 10))
        txt = f"💥 {escape(ch1['name'])} и {escape(ch2['name'])} поссорились."
    await message.reply(f"<b>{txt}</b>", parse_mode='HTML')


async def cmd_transfer(message: Message, bot: Bot, db: Database) -> None:
    _, args = parse_command(message.text)
    if args and args[0].lower() == "банк":
        name, amount = _bank_name_and_amount(args[1:])
        if not name or not amount or amount <= 0:
            await message.reply("<b>💡 Формат:</b> <code>перевод банк название сумма</code>")
            return
        bank = db.get_bank(name)
        if not bank:
            await message.reply("<b>🏦 Банк не найден.</b>")
            return
        if db.bank_deposit(bank["id"], message.from_user.id, amount):
            await message.reply(f"<b>🏦 Переведено в банк:</b> {amount} ВРК")
        else:
            await message.reply("<b>😿 Недостаточно средств.</b>")
        return
    target, stripped = await resolve_target_and_strip(message, bot)
    clean = stripped.split()
    if not target or not clean:
        await message.reply("<b>💡 Формат:</b> <code>перевод @user сумма</code> или ответом.")
        return
    try:
        amount = int(clean[-1])
    except ValueError:
        await message.reply("<b>💡 Сумма должна быть числом.</b>")
        return
    if amount <= 0:
        await message.reply("<b>😿 Сумма должна быть больше 0.</b>")
        return
    db.ensure_user(target["id"], target.get("username"))
    if db.transfer_balance(message.from_user.id, target["id"], amount):
        await message.reply(f"<b>💸 Перевод выполнен:</b> {amount} ВРК → {display_name(target)}")
    else:
        await message.reply("<b>😿 Недостаточно средств.</b>")


async def cmd_create_bank(message: Message, bot: Bot, db: Database) -> None:
    _, args = parse_command(message.text)
    name = " ".join(args).strip()
    if not name:
        await message.reply("<b>💡 Формат:</b> <code>создать_банк название</code>")
        return
    try:
        db.create_bank(name, message.from_user.id)
        await message.reply(f"<b>🏦 Банк создан:</b> {escape(name)}")
    except Exception:
        await message.reply("<b>😿 Такой банк уже существует.</b>")


async def cmd_bank_add(message: Message, bot: Bot, db: Database) -> None:
    target, stripped = await resolve_target_and_strip(message, bot)
    if not target:
        await message.reply("<b>💡 Формат:</b> <code>банк_добавить название @user</code>")
        return
    bank_name = stripped.replace("банк_добавить", "", 1).strip()
    bank_name = bank_name.split()[0] if bank_name else ""
    bank = db.get_bank(bank_name)
    if not bank:
        await message.reply("<b>🏦 Банк не найден.</b>")
        return
    if bank["owner_id"] != message.from_user.id:
        await message.reply("<b>⛔ Только владелец банка может добавлять участников.</b>")
        return
    db.ensure_user(target["id"], target.get("username"))
    db.add_bank_member(bank["id"], target["id"], 1)
    await message.reply(f"<b>🏦 {display_name(target)} добавлен(а) в банк {escape(bank_name)}.</b>")


async def cmd_bank_remove(message: Message, bot: Bot, db: Database) -> None:
    target, stripped = await resolve_target_and_strip(message, bot)
    if not target:
        await message.reply("<b>💡 Формат:</b> <code>банк_удалить название @user</code>")
        return
    bank_name = stripped.replace("банк_удалить", "", 1).strip().split()[0]
    bank = db.get_bank(bank_name)
    if not bank:
        await message.reply("<b>🏦 Банк не найден.</b>")
        return
    if bank["owner_id"] != message.from_user.id:
        await message.reply("<b>⛔ Только владелец банка может удалять участников.</b>")
        return
    db.remove_bank_member(bank["id"], target["id"])
    await message.reply(f"<b>🗑 {display_name(target)} удалён(а) из банка {escape(bank_name)}.</b>")


async def cmd_bank_withdraw(message: Message, bot: Bot, db: Database) -> None:
    _, args = parse_command(message.text)
    name, amount = _bank_name_and_amount(args)
    if not name or not amount:
        await message.reply("<b>💡 Формат:</b> <code>снять_с_банка название сумма</code>")
        return
    bank = db.get_bank(name)
    if not bank:
        await message.reply("<b>🏦 Банк не найден.</b>")
        return
    if db.bank_withdraw(bank["id"], message.from_user.id, amount):
        await message.reply(f"<b>💰 С банка снято:</b> {amount} ВРК")
    else:
        await message.reply("<b>😿 Нет прав или недостаточно средств на счёте банка.</b>")


async def cmd_bank_info(message: Message, bot: Bot, db: Database) -> None:
    _, args = parse_command(message.text)
    name = " ".join(args).strip()
    if not name:
        await message.reply("<b>💡 Формат:</b> <code>банк название</code>")
        return
    bank = db.get_bank(name)
    if not bank:
        await message.reply("<b>🏦 Банк не найден.</b>")
        return
    members = db.get_bank_members(bank["id"])
    lines = [f"<b>🏦 Банк {escape(bank['name'])}</b>", f"Баланс: {bank['balance']} ВРК", "Участники:"]
    for m in members:
        lines.append(f"• {display_name({'id': m['user_id'], 'username': m['username']})}")
    await message.reply("\n".join(lines), parse_mode="HTML")


async def cmd_show_store(message: Message, bot: Bot, db: Database, category: str) -> None:
    title = {"shop": "Магазин", "pharmacy": "Аптека", "vhshop": "ВХ-магазин"}[category]
    await _send_store(message, db, message.from_user.id, category, title)


async def cmd_buy_by_category(message: Message, bot: Bot, db: Database, category: str, args: list[str]) -> None:
    if not args:
        await message.reply("<b>💡 Укажи ID товара.</b>")
        return
    try:
        item_id = int(args[0])
    except ValueError:
        await message.reply("<b>😿 ID должен быть числом.</b>")
        return
    item = db.get_shop_item_by_id_and_category(item_id, category)
    if not item:
        await message.reply("<b>😿 Товар не найден.</b>")
        return
    user = db.get_user(message.from_user.id)
    balance_field = "balance" if item["currency"] == "VRK" else "vh_balance"
    if not user or user[balance_field] < item["price"]:
        await message.reply(f"<b>😿 Недостаточно {item['currency']}.</b>")
        return
    db.add_balance(message.from_user.id, -item["price"], item["currency"])
    db.add_inventory_item(message.from_user.id, item["name"], 1)
    await message.reply(f"<b>🛍 Куплено:</b> {escape(item['name'])}")


async def cmd_buy(message: Message, bot: Bot, db: Database) -> None:
    _, args = parse_command(message.text)
    name = " ".join(args).strip()
    if not name:
        await message.reply("<b>💡 Формат:</b> <code>купить название</code>")
        return
    item = db.get_shop_item_by_name(name)
    if not item:
        await message.reply("<b>😿 Товар не найден.</b>")
        return
    user = db.get_user(message.from_user.id)
    balance_field = "balance" if item["currency"] == "VRK" else "vh_balance"
    if not user or user[balance_field] < item["price"]:
        await message.reply(f"<b>😿 Недостаточно {item['currency']}.</b>")
        return
    db.add_balance(message.from_user.id, -item["price"], item["currency"])
    db.add_inventory_item(message.from_user.id, item["name"], 1)
    await message.reply(f"<b>🛍 Куплено:</b> {escape(item['name'])}")


async def cmd_gift(message: Message, bot: Bot, db: Database) -> None:
    target, stripped = await resolve_target_and_strip(message, bot)
    if not target:
        await message.reply("<b>💡 Формат:</b> <code>подарить @user название</code>")
        return
    item_name = stripped.split(maxsplit=1)[1] if len(stripped.split(maxsplit=1)) > 1 else ""
    if not item_name:
        await message.reply("<b>💡 Укажи предмет.</b>")
        return
    if not db.remove_inventory_item(message.from_user.id, item_name, 1):
        await message.reply("<b>😿 У тебя нет такого предмета.</b>")
        return
    db.ensure_user(target['id'], target.get('username'))
    db.add_inventory_item(target['id'], item_name, 1)
    await message.reply(f"<b>🎁 {display_name(target)} получил(а):</b> {escape(item_name)}")


async def cmd_inventory(message: Message, bot: Bot, db: Database) -> None:
    items = db.get_inventory(message.from_user.id)
    if not items:
        await message.reply("<b>🎁 Инвентарь пуст.</b>")
        return
    lines = ["<b>🎁 Твой инвентарь</b>"]
    for item in items:
        lines.append(f"• {escape(item['item_name'])} ({item['quantity']})")
    await message.reply("\n".join(lines), parse_mode="HTML")


async def cmd_job_choose(message: Message, bot: Bot, db: Database, args: list[str]) -> None:
    prof = " ".join(args).strip().lower()
    if prof not in PROFESSIONS:
        await message.reply("<b>💼 Доступно:</b> айдол, продюсер, фотограф, стажёр")
        return
    db.update_user_field(message.from_user.id, "profession", prof)
    db.update_user_field(message.from_user.id, "last_work_time", None)
    await message.reply(f"<b>✨ Профессия выбрана:</b> {escape(prof)}")


async def cmd_job(message: Message, bot: Bot, db: Database) -> None:
    me = db.get_user(message.from_user.id)
    if not me or not me["profession"]:
        await message.reply("<b>💼 Сначала выбери профессию:</b> <code>работа стать айдол</code>")
        return
    info = PROFESSIONS[me["profession"]]
    last = parse_datetime(me["last_work_time"])
    if last:
        remain = info["cooldown"] - int((datetime.now() - last).total_seconds())
        if remain > 0:
            await message.reply(f"<b>⏳ До следующей работы:</b> {human_timedelta(remain)}")
            return
    low, high = info["income"]
    amount = random.randint(low, high)
    if me["profession"] == "фотограф" and random.randint(1, 100) <= 25:
        amount *= 2
    db.add_balance(message.from_user.id, amount)
    db.update_user_field(message.from_user.id, "last_work_time", datetime.now().isoformat())
    await message.reply(f"<b>💸 Работа выполнена!</b> +{amount} ВРК")


async def cmd_daily_bonus(message: Message, bot: Bot, db: Database) -> None:
    if not db.can_take_daily_bonus(message.from_user.id):
        await message.reply("<b>🎁 Сегодня бонус уже получен.</b>")
        return
    db.add_balance(message.from_user.id, bot.config.daily_bonus_vrk)
    db.update_user_field(message.from_user.id, "daily_bonus_at", date.today().isoformat())
    await message.reply(f"<b>🎁 Ежедневный бонус:</b> +{bot.config.daily_bonus_vrk} ВРК")


async def cmd_activity(message: Message, bot: Bot, db: Database) -> None:
    me = db.get_user(message.from_user.id)
    await message.reply(f"<b>📈 Твоя активность:</b> сегодня {me['daily_messages']} | всего {me['total_messages']}")


async def cmd_activity_all(message: Message, bot: Bot, db: Database) -> None:
    rows = db.top_daily_activity(20)
    lines = ["<b>📈 Активность всех</b>"]
    for idx, row in enumerate(rows, start=1):
        lines.append(f"{idx}. {display_name({'id': row['user_id'], 'username': row['username']})} — {row['daily_messages']} сегодня | {row['total_messages']} всего")
    await message.reply("\n".join(lines), parse_mode="HTML")


async def cmd_stop_pregnancy(message: Message, bot: Bot, db: Database) -> None:
    if not await is_creator(bot, message.chat.id, message.from_user.id):
        await message.reply("<b>⛔ Только владелец чата.</b>")
        return
    target, _ = await resolve_target_and_strip(message, bot)
    if not target:
        await message.reply("<b>💡 Формат:</b> <code>стопберем @user</code>")
        return
    db.update_user_field(target['id'], 'pregnant', 0)
    db.update_user_field(target['id'], 'pregnancy_end_time', None)
    db.delete_process(target['id'], 'pregnancy')
    await message.reply("<b>🛑 Беременность прервана.</b>")


async def cmd_set_pregnancy_chance(message: Message, bot: Bot, db: Database) -> None:
    if not await is_creator(bot, message.chat.id, message.from_user.id):
        await message.reply("<b>⛔ Только владелец чата.</b>")
        return
    _, args = parse_command(message.text)
    if not args:
        await message.reply("<b>💡 Формат:</b> <code>установить_шанс_берем 15</code>")
        return
    try:
        chance = max(0, min(100, int(args[0])))
    except ValueError:
        await message.reply("<b>😿 Нужен процент числом.</b>")
        return
    db.set_pregnancy_chance(message.chat.id, chance)
    await message.reply(f"<b>⚙ Шанс беременности:</b> {chance}%")


async def cmd_reset_user(message: Message, bot: Bot, db: Database) -> None:
    if not await is_creator(bot, message.chat.id, message.from_user.id):
        await message.reply("<b>⛔ Только владелец чата.</b>")
        return
    target, _ = await resolve_target_and_strip(message, bot)
    if not target:
        await message.reply("<b>💡 Формат:</b> <code>сброс @user</code>")
        return
    db.delete_user(target['id'])
    await message.reply("<b>🗑 Профиль удалён.</b>")


async def cmd_set_balance(message: Message, bot: Bot, db: Database) -> None:
    if not await is_creator(bot, message.chat.id, message.from_user.id):
        await message.reply("<b>⛔ Только владелец чата.</b>")
        return
    target, stripped = await resolve_target_and_strip(message, bot)
    if not target:
        await message.reply("<b>💡 Формат:</b> <code>setbalance @user сумма</code>")
        return
    try:
        amount = int(stripped.split()[-1])
    except ValueError:
        await message.reply("<b>😿 Нужна числовая сумма.</b>")
        return
    db.update_user_field(target['id'], 'balance', amount)
    await message.reply(f"<b>💰 Баланс обновлён:</b> {amount} ВРК")


async def cmd_set_vh(message: Message, bot: Bot, db: Database) -> None:
    if not await is_creator(bot, message.chat.id, message.from_user.id):
        await message.reply("<b>⛔ Только владелец чата.</b>")
        return
    target, stripped = await resolve_target_and_strip(message, bot)
    if not target:
        await message.reply("<b>💡 Формат:</b> <code>setвх @user сумма</code>")
        return
    try:
        amount = int(stripped.split()[-1])
    except ValueError:
        await message.reply("<b>😿 Нужна числовая сумма.</b>")
        return
    db.update_user_field(target['id'], 'vh_balance', amount)
    await message.reply(f"<b>💎 Баланс ВХ обновлён:</b> {amount} ВХ")


async def cmd_add_item(message: Message, bot: Bot, db: Database) -> None:
    if not await is_creator(bot, message.chat.id, message.from_user.id):
        await message.reply("<b>⛔ Только владелец чата.</b>")
        return
    _, args = parse_command(message.text)
    if len(args) < 3:
        await message.reply("<b>💡 Формат:</b> <code>добавить_товар название цена категория</code>")
        return
    try:
        price = int(args[-2])
    except ValueError:
        await message.reply("<b>😿 Цена должна быть числом.</b>")
        return
    category = args[-1].lower()
    name = " ".join(args[:-2]).strip()
    if category not in {"shop", "pharmacy", "vhshop"}:
        await message.reply("<b>💡 Категории:</b> shop / pharmacy / vhshop")
        return
    currency = "VH" if category == "vhshop" else "VRK"
    db.add_shop_item(name, price, category, currency)
    await message.reply(f"<b>🛍 Товар добавлен:</b> {escape(name)}")


async def cmd_remove_item(message: Message, bot: Bot, db: Database) -> None:
    if not await is_creator(bot, message.chat.id, message.from_user.id):
        await message.reply("<b>⛔ Только владелец чата.</b>")
        return
    _, args = parse_command(message.text)
    name = " ".join(args).strip()
    if not name:
        await message.reply("<b>💡 Формат:</b> <code>удалить_товар название</code>")
        return
    db.remove_shop_item(name)
    await message.reply("<b>🗑 Товар удалён.</b>")


async def cmd_all_items(message: Message, bot: Bot, db: Database) -> None:
    items = db.list_all_items()
    if not items:
        await message.reply("<b>🛒 Товаров нет.</b>")
        return
    lines = ["<b>🛒 Все товары</b>"]
    for item in items:
        lines.append(f"{item['id']}. {escape(item['name'])} — {item['price']} {item['currency']} ({item['category']})")
    await message.reply("\n".join(lines), parse_mode="HTML")


async def cmd_gacha(message: Message, bot: Bot, db: Database, elite: bool) -> None:
    gacha = GachaService(db)
    status, card = gacha.roll(message.from_user.id, "elite" if elite else "normal", bot.config.elite_gacha_price_vh if elite else bot.config.normal_gacha_price, "VH" if elite else "VRK")
    if status != "ok":
        await message.reply(f"<b>🎴 {status}</b>")
        return
    caption = (
        f"<b>🎴 Тебе выпала карточка!</b>\n"
        f"Имя: <b>{escape(card['idol_name'] or card['title'])}</b>\n"
        f"Группа: <b>{escape(card['group_name'] or '—')}</b>\n"
        f"Редкость: <b>{escape(card['rarity'])}</b>\n"
        f"Альбом: <b>{escape(card['album_name'] or '—')}</b>\n\n"
        f"{escape(card['caption'] or '')}"
    )
    await message.reply_photo(card['photo_file_id'], caption=caption, parse_mode='HTML')


async def cmd_cards(message: Message, bot: Bot, db: Database) -> None:
    cards = db.list_user_cards(message.from_user.id)
    if not cards:
        await message.reply("<b>🃏 Коллекция пуста.</b>")
        return
    lines = ["<b>🃏 Твои карточки</b>"]
    for idx, c in enumerate(cards[:40], start=1):
        lines.append(f"{idx}. {escape(c['title'])} — {escape(c['rarity'])}")
    await message.reply("\n".join(lines), parse_mode="HTML")


async def cmd_card_info(message: Message, bot: Bot, db: Database) -> None:
    _, args = parse_command(message.text)
    title = " ".join(args).strip()
    if not title:
        await message.reply("<b>💡 Формат:</b> <code>карточка название</code>")
        return
    card = db.get_card_by_title(title)
    if not card:
        await message.reply("<b>😿 Карточка не найдена.</b>")
        return
    await message.reply_photo(card['photo_file_id'], caption=f"<b>{escape(card['title'])}</b>\nГруппа: {escape(card['group_name'] or '—')}\nРедкость: {escape(card['rarity'])}\nГача: {'элитная' if card['gacha_type']=='elite' else 'обычная'}\nПродажа: {card['sell_price']} ВРК", parse_mode='HTML')


async def cmd_sell_card(message: Message, bot: Bot, db: Database) -> None:
    _, args = parse_command(message.text)
    if not args or args[0].lower() != 'карточку' or len(args) < 2:
        await message.reply("<b>💡 Формат:</b> <code>продать карточку название</code>")
        return
    title = " ".join(args[1:]).strip()
    card = db.remove_user_card_by_title(message.from_user.id, title)
    if not card:
        await message.reply("<b>😿 Такой карточки у тебя нет.</b>")
        return
    db.add_balance(message.from_user.id, card['sell_price'])
    await message.reply(f"<b>💸 Карточка продана:</b> +{card['sell_price']} ВРК")


async def cmd_give_card(message: Message, bot: Bot, db: Database) -> None:
    target, stripped = await resolve_target_and_strip(message, bot)
    if not target:
        await message.reply("<b>💡 Формат:</b> <code>передать_карточку @user название</code>")
        return
    title = stripped.split(maxsplit=1)[1] if len(stripped.split(maxsplit=1)) > 1 else ''
    if not title:
        await message.reply("<b>😿 Укажи название карточки.</b>")
        return
    db.ensure_user(target['id'], target.get('username'))
    if db.transfer_user_card(message.from_user.id, target['id'], title):
        await message.reply(f"<b>🎁 Карточка передана {display_name(target)}.</b>")
    else:
        await message.reply("<b>😿 У тебя нет такой карточки.</b>")


async def cmd_add_to_gacha(message: Message, bot: Bot, db: Database) -> None:
    text = (message.text or '').strip().lower()
    if not text.startswith('добавить в '):
        return
    if not await is_admin(bot, message.chat.id, message.from_user.id):
        await message.reply("<b>⛔ Только админы могут добавлять карточки.</b>")
        return
    if 'гачу' not in text:
        await message.reply("<b>💡 Формат:</b> <code>добавить в обычную гачу редкая</code>")
        return
    gacha_type = 'elite' if 'элитную' in text else 'normal'
    rarity = None
    for r in RARITY_ORDER:
        if r in text:
            rarity = r
            break
    if not rarity:
        await message.reply("<b>😿 Укажи редкость: обычная / редкая / эпическая / легендарная / секрет.</b>")
        return
    db.set_pending_card_upload(message.from_user.id, message.chat.id, gacha_type, rarity)
    await message.reply("<b>🖼 Теперь отправь фото карточки с подписью.</b>")


async def cmd_all_cards(message: Message, bot: Bot, db: Database) -> None:
    if not await is_admin(bot, message.chat.id, message.from_user.id):
        await message.reply("<b>⛔ Только админы.</b>")
        return
    cards = db.list_cards()
    if not cards:
        await message.reply("<b>🃏 Карточек пока нет.</b>")
        return
    lines = ["<b>🃏 Все карточки</b>"]
    for c in cards[:100]:
        lines.append(f"• {escape(c['title'])} — {escape(c['rarity'])} / {'элитная' if c['gacha_type']=='elite' else 'обычная'}")
    await message.reply("\n".join(lines), parse_mode='HTML')


async def cmd_delete_card(message: Message, bot: Bot, db: Database) -> None:
    if not await is_admin(bot, message.chat.id, message.from_user.id):
        await message.reply("<b>⛔ Только админы.</b>")
        return
    _, args = parse_command(message.text)
    title = " ".join(args).strip()
    if not title:
        await message.reply("<b>💡 Формат:</b> <code>удалить_карточку название</code>")
        return
    db.delete_card_by_title(title)
    await message.reply("<b>🗑 Карточка удалена.</b>")


async def cmd_grant_card(message: Message, bot: Bot, db: Database) -> None:
    if not await is_admin(bot, message.chat.id, message.from_user.id):
        await message.reply("<b>⛔ Только админы.</b>")
        return
    target, stripped = await resolve_target_and_strip(message, bot)
    if not target:
        await message.reply("<b>💡 Формат:</b> <code>выдать_карточку @user название</code>")
        return
    title = stripped.split(maxsplit=1)[1] if len(stripped.split(maxsplit=1)) > 1 else ''
    if db.give_user_card_by_title(target['id'], title):
        await message.reply("<b>🃏 Карточка выдана.</b>")
    else:
        await message.reply("<b>😿 Карточка не найдена.</b>")


async def cmd_take_card(message: Message, bot: Bot, db: Database) -> None:
    if not await is_admin(bot, message.chat.id, message.from_user.id):
        await message.reply("<b>⛔ Только админы.</b>")
        return
    target, stripped = await resolve_target_and_strip(message, bot)
    if not target:
        await message.reply("<b>💡 Формат:</b> <code>забрать_карточку @user название</code>")
        return
    title = stripped.split(maxsplit=1)[1] if len(stripped.split(maxsplit=1)) > 1 else ''
    if db.remove_user_card_by_title(target['id'], title):
        await message.reply("<b>🗑 Карточка забрана.</b>")
    else:
        await message.reply("<b>😿 У пользователя нет такой карточки.</b>")


async def cmd_add_group(message: Message, bot: Bot, db: Database) -> None:
    if not await is_admin(bot, message.chat.id, message.from_user.id):
        await message.reply("<b>⛔ Только админы.</b>")
        return
    _, args = parse_command(message.text)
    name = " ".join(args).strip()
    if not name:
        await message.reply("<b>💡 Формат:</b> <code>добавить_группу название</code>")
        return
    db.add_group(name)
    await message.reply(f"<b>🎤 Группа добавлена:</b> {escape(name)}")


async def cmd_remove_group(message: Message, bot: Bot, db: Database) -> None:
    if not await is_admin(bot, message.chat.id, message.from_user.id):
        await message.reply("<b>⛔ Только админы.</b>")
        return
    _, args = parse_command(message.text)
    name = " ".join(args).strip()
    db.remove_group(name)
    await message.reply("<b>🗑 Группа удалена.</b>")


async def cmd_groups(message: Message, bot: Bot, db: Database) -> None:
    rows = db.list_groups()
    await message.reply("<b>🎤 Группы:</b>\n" + ("\n".join(f"• {escape(r['name'])}" for r in rows) if rows else "пока нет"), parse_mode='HTML')


async def cmd_add_album(message: Message, bot: Bot, db: Database) -> None:
    if not await is_admin(bot, message.chat.id, message.from_user.id):
        await message.reply("<b>⛔ Только админы.</b>")
        return
    _, args = parse_command(message.text)
    name = " ".join(args).strip()
    if not name:
        await message.reply("<b>💡 Формат:</b> <code>добавить_альбом название</code>")
        return
    db.add_album(name)
    await message.reply(f"<b>💿 Альбом добавлен:</b> {escape(name)}")


async def cmd_remove_album(message: Message, bot: Bot, db: Database) -> None:
    if not await is_admin(bot, message.chat.id, message.from_user.id):
        await message.reply("<b>⛔ Только админы.</b>")
        return
    _, args = parse_command(message.text)
    db.remove_album(" ".join(args).strip())
    await message.reply("<b>🗑 Альбом удалён.</b>")


async def cmd_albums(message: Message, bot: Bot, db: Database) -> None:
    rows = db.list_albums()
    lines = ["<b>💿 Альбомы</b>"]
    for r in rows:
        lines.append(f"• {escape(r['name'])}")
    await message.reply("\n".join(lines), parse_mode='HTML')


async def cmd_rpg_profile(message: Message, bot: Bot, db: Database) -> None:
    prof = db.get_rpg_profile(message.from_user.id)
    user = db.get_user(message.from_user.id)
    await message.reply(
        f"<b>🎤 RPG-профиль</b>\nУровень: {prof['level']}\nEXP: {prof['exp']}\nРепутация: {prof['reputation']}\nЭнергия: {prof['energy']}\nКонцерты: {prof['concerts']}\nПобеды над хейтерами: {prof['haters_defeated']}\nПриключения: {prof['adventures_done']}\nВХ: {user['vh_balance']}",
        parse_mode='HTML',
    )


async def _apply_rpg_rewards(db: Database, user_id: int, event: dict) -> tuple[int, int, int]:
    vrk = int(event.get('vrk', 0))
    vh = int(event.get('vh', 0))
    rep = int(event.get('rep', 0))
    if vrk:
        db.add_balance(user_id, vrk)
    if vh:
        db.add_balance(user_id, vh, 'VH')
    prof = db.get_rpg_profile(user_id)
    new_exp = prof['exp'] + int(event.get('exp', 1))
    new_level = prof['level']
    while new_exp >= new_level * 10:
        new_exp -= new_level * 10
        new_level += 1
    db.update_rpg_profile(user_id, exp=new_exp, level=new_level, reputation=prof['reputation'] + rep, adventures_done=prof['adventures_done'] + 1)
    return vrk, vh, rep


async def cmd_adventure(message: Message, bot: Bot, db: Database) -> None:
    event = random.choice(ADVENTURES)
    vrk, vh, rep = await _apply_rpg_rewards(db, message.from_user.id, event)
    extra = []
    if event.get('kind') == 'hater':
        prof = db.get_rpg_profile(message.from_user.id)
        db.update_rpg_profile(message.from_user.id, haters_defeated=prof['haters_defeated'] + 1)
    if event.get('kind') == 'concert':
        prof = db.get_rpg_profile(message.from_user.id)
        db.update_rpg_profile(message.from_user.id, concerts=prof['concerts'] + 1)
    extra.append(f"+{vrk} ВРК" if vrk else "+0 ВРК")
    extra.append(f"+{vh} ВХ" if vh else "+0 ВХ")
    extra.append(f"репутация {rep:+d}")
    await message.reply(f"<b>🎮 Приключение</b>\n{escape(event['text'])}\n\n<b>Награда:</b> {' | '.join(extra)}", parse_mode='HTML')


async def cmd_concert(message: Message, bot: Bot, db: Database) -> None:
    event = random.choice([e for e in ADVENTURES if e.get('kind') == 'concert'])
    vrk, vh, rep = await _apply_rpg_rewards(db, message.from_user.id, event)
    prof = db.get_rpg_profile(message.from_user.id)
    db.update_rpg_profile(message.from_user.id, concerts=prof['concerts'] + 1)
    await message.reply(f"<b>🎤 Концерт</b>\n{escape(event['text'])}\n+{vrk} ВРК | +{vh} ВХ | репутация {rep:+d}", parse_mode='HTML')


async def cmd_haters(message: Message, bot: Bot, db: Database) -> None:
    event = random.choice([e for e in ADVENTURES if e.get('kind') == 'hater'])
    vrk, vh, rep = await _apply_rpg_rewards(db, message.from_user.id, event)
    prof = db.get_rpg_profile(message.from_user.id)
    db.update_rpg_profile(message.from_user.id, haters_defeated=prof['haters_defeated'] + 1)
    await message.reply(f"<b>⚔ Битва с хейтерами</b>\n{escape(event['text'])}\n+{vrk} ВРК | +{vh} ВХ | репутация {rep:+d}", parse_mode='HTML')


async def cmd_reputation(message: Message, bot: Bot, db: Database) -> None:
    prof = db.get_rpg_profile(message.from_user.id)
    await message.reply(f"<b>🌟 Репутация:</b> {prof['reputation']}")


async def cmd_vh_balance(message: Message, bot: Bot, db: Database) -> None:
    me = db.get_user(message.from_user.id)
    await message.reply(f"<b>💎 Твой баланс ВХ:</b> {me['vh_balance']}")


async def cmd_fun_action(message: Message, bot: Bot, db: Database) -> None:
    command, _ = parse_command(message.text)
    target, _ = await resolve_target_and_strip(message, bot)
    if not target:
        await message.reply("<b>💡 Нужен @user или ответом.</b>")
        return
    action = random.choice(FUN_ACTIONS[command])
    await message.reply(f"<b>✨ {display_name(message.from_user)} {action} {display_name(target)}!</b>", parse_mode='HTML')


async def cmd_ship(message: Message, bot: Bot, db: Database) -> None:
    names = []
    if message.reply_to_message and message.reply_to_message.from_user:
        names = [display_name(message.from_user), display_name(message.reply_to_message.from_user)]
    else:
        parts = (message.text or '').split()[1:]
        if len(parts) >= 2:
            names = [escape(parts[0]), escape(parts[1])]
    if len(names) < 2:
        await message.reply("<b>💡 Формат:</b> <code>шип @u1 @u2</code> или ответом + @user")
        return
    percent = random.randint(1, 100)
    await message.reply(f"<b>💞 Шип:</b> {names[0]} + {names[1]} = <b>{percent}%</b>")


async def cmd_who(message: Message, bot: Bot, db: Database) -> None:
    rows = db.top_daily_activity(20)
    if not rows:
        return
    chosen = random.choice(rows)
    await message.reply(f"<b>🎲 Сегодня это:</b> {display_name({'id': chosen['user_id'], 'username': chosen['username']})}", parse_mode='HTML')


async def cmd_whoami(message: Message, bot: Bot, db: Database) -> None:
    titles = ['главный биас чата', 'легенда сцены', 'магнит для камбеков', 'король/королева эдитов', 'икона фанкама', 'владелец вайба']
    await message.reply(f"<b>🪞 Ты — {random.choice(titles)}</b>")
