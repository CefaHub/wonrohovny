from __future__ import annotations

import random
import sqlite3
from datetime import datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.types import Message

from database import Database
from keyboards import child_remove_keyboard, proposal_keyboard, store_keyboard
from services import ProcessManager
from utils import (
    PROFESSIONS,
    display_name,
    escape,
    fmt_status,
    human_timedelta,
    is_admin,
    is_creator,
    parse_command,
    parse_datetime,
    resolve_target_and_strip,
)

router = Router(name="commands")


def _bank_name_and_amount(args: list[str]) -> tuple[str | None, int | None]:
    if len(args) < 2:
        return None, None
    try:
        amount = int(args[-1])
    except ValueError:
        return None, None
    name = " ".join(args[:-1]).strip()
    return name or None, amount


def _status_ok_for_relationship(row) -> bool:
    return row and row["relationship_status"] == "single"


@router.message(F.text | F.caption)
async def handle_all_messages(message: Message, bot: Bot) -> None:
    if message.chat.type not in {"group", "supergroup"}:
        return
    if not message.from_user or message.from_user.is_bot:
        return

    db: Database = bot.db
    db.register_message(message.from_user.id, message.from_user.username)

    command, _ = parse_command(message.text)
    if not command:
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
        "перевод": cmd_transfer,
        "создать_банк": cmd_create_bank,
        "банк_добавить": cmd_bank_add,
        "банк_удалить": cmd_bank_remove,
        "снять_с_банка": cmd_bank_withdraw,
        "банк": cmd_bank_info,
        "магазин": cmd_show_shop,
        "аптека": cmd_show_pharmacy,
        "купить": cmd_buy,
        "подарить": cmd_gift,
        "инвентарь": cmd_inventory,
        "работа": cmd_job,
        "стопберем": cmd_stop_pregnancy,
        "установить_шанс_берем": cmd_set_pregnancy_chance,
        "сброс": cmd_reset_user,
        "setbalance": cmd_set_balance,
        "добавить_товар": cmd_add_item,
        "удалить_товар": cmd_remove_item,
        "товары": cmd_all_items,
    }
    handler = handlers.get(command)
    if handler:
        await handler(message, bot, db)


async def cmd_info(message: Message, bot: Bot, db: Database) -> None:
    target, _ = await resolve_target_and_strip(message, bot)
    if target:
        db.ensure_user(target["id"], target.get("username"))
        row = db.get_user(target["id"])
        t_display = display_name(target)
    else:
        row = db.get_user(message.from_user.id)
        t_display = display_name(message.from_user)

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
        f"<b>👤 Информация о {t_display}</b>\n"
        f"<b>—————————————</b>\n"
        f"🎭 <b>Роль:</b> {escape(row['custom_role'] or 'нет')}\n"
        f"⚥ <b>Пол:</b> {gender_map.get(row['gender'], 'не указан')}\n"
        f"💬 <b>Сообщений:</b> всего {row['total_messages']} | сегодня {row['daily_messages']}\n"
        f"📅 <b>В чате с:</b> {escape(row['first_seen'][:10])}\n"
        f"❤️ <b>Статус:</b> {fmt_status(row['relationship_status'], row['gender'], partner_name)}\n"
        f"👶 <b>Дети:</b>\n{child_text}\n"
        f"💰 <b>Баланс:</b> {row['balance']} ВРК\n"
        f"🏦 <b>Банки:</b>\n{bank_text}\n"
        f"🎁 <b>Подарки:</b>\n{gifts_text}"
    )
    await message.reply(text, reply_markup=markup)


async def cmd_gender(message: Message, bot: Bot, db: Database) -> None:
    _, args = parse_command(message.text)
    if not args or args[0].lower() not in {"м", "ж"}:
        await message.reply("<b>💡 Формат:</b> <code>пол м</code> или <code>пол ж</code>")
        return
    db.update_user_field(message.from_user.id, "gender", args[0].lower())
    await message.reply("<b>✨ Пол обновлён.</b>")


async def cmd_role(message: Message, bot: Bot, db: Database) -> None:
    if not await is_admin(bot, message.chat.id, message.from_user.id):
        await message.reply("<b>⛔ Только администратор может назначать роли.</b>")
        return
    target, stripped = await resolve_target_and_strip(message, bot)
    if not target:
        await message.reply("<b>💡 Формат:</b> <code>роль @user текст</code> или ответом.")
        return
    role_text = stripped.replace("роль", "", 1).strip()
    if not role_text:
        await message.reply("<b>💡 Укажи текст роли после пользователя.</b>")
        return
    db.ensure_user(target["id"], target.get("username"))
    db.update_user_field(target["id"], "custom_role", role_text)
    await message.reply(f"<b>🎭 Роль для {display_name(target)} установлена:</b> {escape(role_text)}")


async def _proposal_common(message: Message, bot: Bot, db: Database, proposal_type: str, text: str) -> None:
    target, _ = await resolve_target_and_strip(message, bot)
    if not target:
        await message.reply("<b>💡 Укажи пользователя через @username или ответом.</b>")
        return
    if target["id"] == message.from_user.id:
        await message.reply("<b>😹 Себе такое отправлять нельзя.</b>")
        return
    db.ensure_user(target["id"], target.get("username"))
    me = db.get_user(message.from_user.id)
    other = db.get_user(target["id"])
    if not me or not other:
        await message.reply("<b>😿 Профиль не найден.</b>")
        return

    if proposal_type == "relationship":
        if not (_status_ok_for_relationship(me) and _status_ok_for_relationship(other)):
            await message.reply("<b>💔 Кто-то из вас уже не свободен.</b>")
            return
    elif proposal_type == "marriage":
        me_ok = me["relationship_status"] == "single" or (me["relationship_status"] == "relationship" and me["partner_id"] == other["user_id"])
        other_ok = other["relationship_status"] == "single" or (other["relationship_status"] == "relationship" and other["partner_id"] == me["user_id"])
        if not (me_ok and other_ok):
            await message.reply("<b>💍 Брак доступен только свободным или уже состоящим в отношениях друг с другом.</b>")
            return
    else:
        if me["partner_id"] != other["user_id"]:
            await message.reply("<b>💔 У тебя нет отношений с этим пользователем.</b>")
            return

    proposal_id = db.create_proposal(message.chat.id, message.from_user.id, target["id"], proposal_type)
    await message.reply(text.format(me=display_name(message.from_user), target=display_name(target)), reply_markup=proposal_keyboard(proposal_id))


async def cmd_relationship(message: Message, bot: Bot, db: Database) -> None:
    await _proposal_common(message, bot, db, "relationship", "<b>💖 {me} предлагает {target} начать отношения!</b>")


async def cmd_marriage(message: Message, bot: Bot, db: Database) -> None:
    await _proposal_common(message, bot, db, "marriage", "<b>💍 {me} делает предложение {target}!</b>")


async def cmd_breakup(message: Message, bot: Bot, db: Database) -> None:
    me = db.get_user(message.from_user.id)
    if not me or not me["partner_id"]:
        await message.reply("<b>😿 Сейчас ты ни с кем не состоишь в отношениях.</b>")
        return
    partner = db.get_user(me["partner_id"])
    if not partner:
        db.clear_relationship(message.from_user.id, None)
        await message.reply("<b>💔 Статус очищен.</b>")
        return
    proposal_id = db.create_proposal(message.chat.id, message.from_user.id, partner["user_id"], "breakup")
    await message.reply(
        f"<b>💔 {display_name(message.from_user)} хочет разорвать отношения с {display_name({'id': partner['user_id'], 'username': partner['username']})}.</b>",
        reply_markup=proposal_keyboard(proposal_id),
    )


async def cmd_sex(message: Message, bot: Bot, db: Database) -> None:
    target, _ = await resolve_target_and_strip(message, bot)
    if not target:
        await message.reply("<b>💡 Формат:</b> <code>секс @партнёр</code> или ответом.")
        return
    if target["id"] == message.from_user.id:
        await message.reply("<b>😳 Нет, так не пойдёт.</b>")
        return
    db.ensure_user(target["id"], target.get("username"))
    pair = db.get_process_pair("sex", message.from_user.id, target["id"])
    if pair:
        await message.reply("<b>⏳ Такой процесс уже активен.</b>")
        return
    proposal_id = db.create_proposal(message.chat.id, message.from_user.id, target["id"], "sex")
    await message.reply(
        f"<b>🔞 {display_name(message.from_user)} хочет начать процесс с {display_name(target)}.</b>\n"
        f"<i>Кнопки видны всем, но нажать по-настоящему может только адресат.</i>",
        reply_markup=proposal_keyboard(proposal_id),
    )


async def cmd_cancel_process(message: Message, bot: Bot, db: Database) -> None:
    sex = db.get_process(message.from_user.id, "sex")
    if sex and sex["partner_id"]:
        db.cancel_process_pair("sex", message.from_user.id, sex["partner_id"])
        await message.reply("<b>🛑 Процесс отменён.</b>")
        return
    await message.reply("<b>😶 Нечего отменять.</b>")


async def cmd_take_pill(message: Message, bot: Bot, db: Database) -> None:
    _, args = parse_command(message.text)
    if len(args) >= 1 and args[0].lower() == "таблетку":
        ok = bot.process_manager.take_pill(message.from_user.id)
        await message.reply("<b>💊 Таблетка принята.</b>" if ok else "<b>😿 Таблетки нет или сейчас она не нужна.</b>")


async def cmd_name_child(message: Message, bot: Bot, db: Database) -> None:
    if not message.reply_to_message:
        return
    pending = db.get_pending_birth_by_message(message.chat.id, message.reply_to_message.message_id)
    if not pending:
        return
    _, args = parse_command(message.text)
    if len(args) < 2:
        await message.reply("<b>💡 Формат:</b> <code>имя мальчик Минхо</code>")
        return
    gender = args[0].lower()
    if gender not in {"мальчик", "девочка"}:
        await message.reply("<b>💡 Пол ребёнка: мальчик или девочка.</b>")
        return
    name = " ".join(args[1:]).strip()
    if not name:
        await message.reply("<b>💡 Укажи имя ребёнка.</b>")
        return
    db.add_child_for_parents([pending["mother_id"], pending["father_id"]], name, gender)
    db.delete_pending_birth(pending["id"])
    await message.reply(f"<b>🎉 Добро пожаловать, {escape(name)}!</b> Пол: {gender}")


async def cmd_drop_child(message: Message, bot: Bot, db: Database) -> None:
    _, args = parse_command(message.text)
    if not args:
        await message.reply("<b>💡 Формат:</b> <code>отказаться Имя</code>")
        return
    name = " ".join(args)
    removed = db.remove_child(message.from_user.id, name)
    me = db.get_user(message.from_user.id)
    if me and me["partner_id"]:
        db.remove_child(me["partner_id"], name)
    await message.reply(f"<b>🗑 {escape(name)} удалён из профиля.</b>" if removed else "<b>😿 Такой ребёнок не найден.</b>")


async def cmd_transfer(message: Message, bot: Bot, db: Database) -> None:
    _, args = parse_command(message.text)
    if args and args[0].lower() == "банк":
        if len(args) < 3:
            await message.reply("<b>💡 Формат:</b> <code>перевод банк Название 100</code>")
            return
        bank_name, amount = _bank_name_and_amount(args[1:])
        if not bank_name or not amount or amount <= 0:
            await message.reply("<b>😿 Неверная сумма или название банка.</b>")
            return
        bank = db.get_bank(bank_name)
        if not bank:
            await message.reply("<b>🏦 Банк не найден.</b>")
            return
        ok = db.deposit_to_bank(bank["id"], message.from_user.id, amount)
        await message.reply(f"<b>🏦 В банк «{escape(bank_name)}» внесено {amount} ВРК.</b>" if ok else "<b>😿 Недостаточно средств.</b>")
        return

    target, stripped = await resolve_target_and_strip(message, bot)
    if not target:
        await message.reply("<b>💡 Формат:</b> <code>перевод @user 100</code>")
        return
    parts = stripped.split()
    if not parts:
        await message.reply("<b>😿 Укажи сумму.</b>")
        return
    try:
        amount = int(parts[-1])
    except ValueError:
        await message.reply("<b>😿 Сумма должна быть числом.</b>")
        return
    db.ensure_user(target["id"], target.get("username"))
    ok = db.transfer_balance(message.from_user.id, target["id"], amount)
    await message.reply(f"<b>💸 Переведено {amount} ВРК пользователю {display_name(target)}.</b>" if ok else "<b>😿 Недостаточно средств.</b>")


async def cmd_create_bank(message: Message, bot: Bot, db: Database) -> None:
    _, args = parse_command(message.text)
    name = " ".join(args).strip()
    if not name:
        await message.reply("<b>💡 Формат:</b> <code>создать_банк Название</code>")
        return
    try:
        db.create_bank(name, message.from_user.id)
        await message.reply(f"<b>🏦 Банк «{escape(name)}» создан.</b>")
    except sqlite3.IntegrityError:
        await message.reply("<b>😿 Банк с таким названием уже существует.</b>")


async def cmd_bank_add(message: Message, bot: Bot, db: Database) -> None:
    target, stripped = await resolve_target_and_strip(message, bot)
    if not target:
        await message.reply("<b>💡 Формат:</b> <code>банк_добавить Название @user</code></b>")
        return
    parts = stripped.split()[1:]
    bank_name = " ".join(parts).strip()
    bank = db.get_bank(bank_name)
    if not bank:
        await message.reply("<b>🏦 Банк не найден.</b>")
        return
    if bank["owner_id"] != message.from_user.id:
        await message.reply("<b>⛔ Только владелец банка может добавлять участников.</b>")
        return
    db.ensure_user(target["id"], target.get("username"))
    db.add_bank_member(bank["id"], target["id"], 1)
    await message.reply(f"<b>✨ {display_name(target)} добавлен(а) в банк «{escape(bank_name)}».</b>")


async def cmd_bank_remove(message: Message, bot: Bot, db: Database) -> None:
    target, stripped = await resolve_target_and_strip(message, bot)
    if not target:
        await message.reply("<b>💡 Формат:</b> <code>банк_удалить Название @user</code>")
        return
    parts = stripped.split()[1:]
    bank_name = " ".join(parts).strip()
    bank = db.get_bank(bank_name)
    if not bank:
        await message.reply("<b>🏦 Банк не найден.</b>")
        return
    if bank["owner_id"] != message.from_user.id:
        await message.reply("<b>⛔ Только владелец банка может удалять участников.</b>")
        return
    db.remove_bank_member(bank["id"], target["id"])
    await message.reply(f"<b>🗑 {display_name(target)} удалён(а) из банка «{escape(bank_name)}».</b>")


async def cmd_bank_withdraw(message: Message, bot: Bot, db: Database) -> None:
    _, args = parse_command(message.text)
    bank_name, amount = _bank_name_and_amount(args)
    if not bank_name or not amount or amount <= 0:
        await message.reply("<b>💡 Формат:</b> <code>снять_с_банка Название 100</code>")
        return
    bank = db.get_bank(bank_name)
    if not bank:
        await message.reply("<b>🏦 Банк не найден.</b>")
        return
    ok = db.withdraw_from_bank(bank["id"], message.from_user.id, amount)
    await message.reply(f"<b>💸 С банка «{escape(bank_name)}» снято {amount} ВРК.</b>" if ok else "<b>😿 Недостаточно прав или средств.</b>")


async def cmd_bank_info(message: Message, bot: Bot, db: Database) -> None:
    _, args = parse_command(message.text)
    name = " ".join(args).strip()
    if not name:
        await message.reply("<b>💡 Формат:</b> <code>банк Название</code>")
        return
    bank = db.get_bank(name)
    if not bank:
        await message.reply("<b>🏦 Банк не найден.</b>")
        return
    members = db.get_bank_members(bank["id"])
    members_text = "\n".join([f"• {display_name({'id': m['user_id'], 'username': m['username']})}" for m in members]) or "нет"
    await message.reply(f"<b>🏦 Банк: {escape(bank['name'])}</b>\n💰 Баланс: <b>{bank['balance']} ВРК</b>\n👥 Участники:\n{members_text}")


async def _show_items(message: Message, db: Database, category: str, title: str) -> None:
    items = db.get_shop_items(category)
    if not items:
        await message.reply(f"<b>{title}</b>\nПока пусто 😿")
        return
    lines = [f"{i + 1}. <b>{escape(row['name'])}</b> — {row['price']} ВРК" for i, row in enumerate(items)]
    await message.reply(
        f"<b>{title}</b>\n" + "\n".join(lines) + "\n\n<i>Можно купить кнопкой ниже или командой вида: магазин купить 1 / аптека купить 1</i>",
        reply_markup=store_keyboard(category, len(items), message.from_user.id),
    )


async def cmd_show_shop(message: Message, bot: Bot, db: Database) -> None:
    _, args = parse_command(message.text)
    if args and args[0].lower() == "купить":
        await _buy_by_context(message, db, "shop", args[1:])
        return
    await _show_items(message, db, "shop", "🛍 Магазин")


async def cmd_show_pharmacy(message: Message, bot: Bot, db: Database) -> None:
    _, args = parse_command(message.text)
    if args and args[0].lower() == "купить":
        await _buy_by_context(message, db, "pharmacy", args[1:])
        return
    await _show_items(message, db, "pharmacy", "💊 Аптека")


async def _buy_item(message: Message, db: Database, item) -> None:
    user = db.get_user(message.from_user.id)
    if not user or user["balance"] < item["price"]:
        await message.reply("<b>😿 Недостаточно ВРК.</b>")
        return
    db.add_balance(message.from_user.id, -item["price"])
    db.add_inventory_item(message.from_user.id, item["name"], 1)
    await message.reply(f"<b>🛒 Куплено:</b> {escape(item['name'])} за {item['price']} ВРК")


async def _buy_by_context(message: Message, db: Database, category: str, args: list[str]) -> None:
    if not args:
        await message.reply("<b>💡 Пример:</b> <code>магазин купить 1</code>")
        return
    value = " ".join(args).strip()
    items = db.get_shop_items(category)
    item = None
    if value.isdigit():
        idx = int(value)
        if 1 <= idx <= len(items):
            item = items[idx - 1]
    if item is None:
        for row in items:
            if row['name'].lower() == value.lower():
                item = row
                break
    if item is None:
        await message.reply("<b>😿 Такой товар не найден в этом разделе.</b>")
        return
    await _buy_item(message, db, item)


async def cmd_buy(message: Message, bot: Bot, db: Database) -> None:
    _, args = parse_command(message.text)
    value = " ".join(args).strip()
    if not value:
        await message.reply("<b>💡 Формат:</b> <code>купить Название</code> или <code>магазин купить 1</code>")
        return
    if value.isdigit():
        await message.reply("<b>💡 Для покупки по номеру используй:</b> <code>магазин купить 1</code> или <code>аптека купить 1</code>")
        return
    item = db.get_shop_item_by_name(value)
    if not item:
        await message.reply("<b>😿 Такой товар не найден.</b>")
        return
    await _buy_item(message, db, item)


async def cmd_gift(message: Message, bot: Bot, db: Database) -> None:
    target, stripped = await resolve_target_and_strip(message, bot)
    if not target:
        await message.reply("<b>💡 Формат:</b> <code>подарить @user Название</code>")
        return
    parts = stripped.split(maxsplit=2)
    item_name = parts[2].strip() if len(parts) >= 3 else ""
    if not item_name:
        await message.reply("<b>😿 Укажи название подарка.</b>")
        return
    if not db.remove_inventory_item(message.from_user.id, item_name, 1):
        await message.reply("<b>😿 У тебя нет такого предмета.</b>")
        return
    db.ensure_user(target["id"], target.get("username"))
    db.add_inventory_item(target["id"], item_name, 1)
    await message.reply(f"<b>🎁 {escape(item_name)} подарен(а) пользователю {display_name(target)}!</b>")


async def cmd_inventory(message: Message, bot: Bot, db: Database) -> None:
    items = db.get_inventory(message.from_user.id)
    if not items:
        await message.reply("<b>🎒 Инвентарь пуст.</b>")
        return
    text = "\n".join([f"• {escape(i['item_name'])} ({i['quantity']})" for i in items])
    await message.reply(f"<b>🎒 Твой инвентарь:</b>\n{text}")


async def cmd_job(message: Message, bot: Bot, db: Database) -> None:
    _, args = parse_command(message.text)
    user = db.get_user(message.from_user.id)
    if args and args[0].lower() == "стать":
        prof = " ".join(args[1:]).strip().lower()
        if prof not in PROFESSIONS:
            await message.reply("<b>💼 Доступные профессии:</b> айдол, продюсер, фотограф, стажёр")
            return
        db.update_user_field(message.from_user.id, "profession", prof)
        db.update_user_field(message.from_user.id, "last_work_time", None)
        await message.reply(f"<b>✨ Теперь твоя профессия — {escape(PROFESSIONS[prof]['title'])}.</b>")
        return

    if not user or not user["profession"]:
        await message.reply("<b>💼 Сначала выбери профессию:</b> <code>работа стать айдол</code>")
        return

    prof = user["profession"]
    cooldown = PROFESSIONS[prof]["cooldown"]
    last_work = parse_datetime(user["last_work_time"])
    if last_work:
        remain = cooldown - int((datetime.now() - last_work).total_seconds())
        if remain > 0:
            await message.reply(f"<b>⏳ Рано!</b> До следующей смены осталось: <b>{human_timedelta(remain)}</b>")
            return

    if prof == "айдол":
        income = 100
        text = "🎤 Ты выступил(а) на шикарной сцене!"
    elif prof == "продюсер":
        income = random.randint(50, 200)
        text = "🎛 Ты спродюсировал(а) новый хит!"
    elif prof == "фотограф":
        income = 60 if random.randint(1, 100) <= 25 else 30
        text = "📸 Фотосессия удалась на ура!"
    else:
        income = 10
        text = "🫶 Ты усердно тренировался(лась) как стажёр!"

    db.add_balance(message.from_user.id, income)
    db.update_user_field(message.from_user.id, "last_work_time", datetime.now().isoformat())
    await message.reply(f"<b>{text}</b>\n💰 Получено: <b>{income} ВРК</b>")


async def cmd_stop_pregnancy(message: Message, bot: Bot, db: Database) -> None:
    if not await is_creator(bot, message.chat.id, message.from_user.id):
        await message.reply("<b>⛔ Только владелец чата может использовать эту команду.</b>")
        return
    target, _ = await resolve_target_and_strip(message, bot)
    if not target:
        await message.reply("<b>💡 Формат:</b> <code>стопберем @user</code>")
        return
    if not db.get_process(target["id"], "pregnancy"):
        await message.reply("<b>😿 У пользователя нет активной беременности.</b>")
        return
    db.delete_process(target["id"], "pregnancy")
    db.update_user_field(target["id"], "pregnant", 0)
    db.update_user_field(target["id"], "pregnancy_end_time", None)
    await message.reply(f"<b>🛑 Беременность у {display_name(target)} принудительно остановлена.</b>")


async def cmd_set_pregnancy_chance(message: Message, bot: Bot, db: Database) -> None:
    if not await is_creator(bot, message.chat.id, message.from_user.id):
        await message.reply("<b>⛔ Только владелец чата может менять шанс беременности.</b>")
        return
    _, args = parse_command(message.text)
    if not args:
        await message.reply("<b>💡 Формат:</b> <code>установить_шанс_берем 15</code>")
        return
    try:
        chance = int(args[0])
    except ValueError:
        await message.reply("<b>😿 Процент должен быть числом.</b>")
        return
    chance = max(0, min(100, chance))
    db.set_pregnancy_chance(message.chat.id, chance)
    await message.reply(f"<b>🤰 Шанс беременности установлен: {chance}%</b>")


async def cmd_reset_user(message: Message, bot: Bot, db: Database) -> None:
    if not await is_creator(bot, message.chat.id, message.from_user.id):
        await message.reply("<b>⛔ Только владелец чата может сбрасывать профили.</b>")
        return
    target, _ = await resolve_target_and_strip(message, bot)
    if not target:
        await message.reply("<b>💡 Формат:</b> <code>сброс @user</code>")
        return
    db.delete_user(target["id"])
    await message.reply(f"<b>🗑 Профиль {display_name(target)} удалён.</b>")


async def cmd_set_balance(message: Message, bot: Bot, db: Database) -> None:
    if not await is_creator(bot, message.chat.id, message.from_user.id):
        await message.reply("<b>⛔ Только владелец чата может менять баланс.</b>")
        return
    target, stripped = await resolve_target_and_strip(message, bot)
    if not target:
        await message.reply("<b>💡 Формат:</b> <code>setbalance @user 500</code>")
        return
    try:
        amount = int(stripped.split()[-1])
    except Exception:
        await message.reply("<b>😿 Неверная сумма.</b>")
        return
    db.ensure_user(target["id"], target.get("username"))
    db.update_user_field(target["id"], "balance", amount)
    await message.reply(f"<b>💰 Баланс {display_name(target)} теперь {amount} ВРК.</b>")


async def cmd_add_item(message: Message, bot: Bot, db: Database) -> None:
    if not await is_creator(bot, message.chat.id, message.from_user.id):
        await message.reply("<b>⛔ Только владелец чата может добавлять товары.</b>")
        return
    _, args = parse_command(message.text)
    if len(args) < 3:
        await message.reply("<b>💡 Формат:</b> <code>добавить_товар Роза 50 shop</code>")
        return
    category = args[-1].lower()
    try:
        price = int(args[-2])
    except ValueError:
        await message.reply("<b>😿 Цена должна быть числом.</b>")
        return
    name = " ".join(args[:-2]).strip()
    if category not in {"shop", "pharmacy"}:
        await message.reply("<b>😿 Категория должна быть: shop или pharmacy.</b>")
        return
    try:
        db.add_shop_item(name, price, category)
        await message.reply(f"<b>🛍 Товар добавлен:</b> {escape(name)} — {price} ВРК ({category})")
    except sqlite3.IntegrityError:
        await message.reply("<b>😿 Такой товар уже существует.</b>")


async def cmd_remove_item(message: Message, bot: Bot, db: Database) -> None:
    if not await is_creator(bot, message.chat.id, message.from_user.id):
        await message.reply("<b>⛔ Только владелец чата может удалять товары.</b>")
        return
    _, args = parse_command(message.text)
    name = " ".join(args).strip()
    if not name:
        await message.reply("<b>💡 Формат:</b> <code>удалить_товар Роза</code>")
        return
    removed = db.remove_shop_item(name)
    await message.reply(f"<b>🗑 Товар {escape(name)} удалён.</b>" if removed else "<b>😿 Товар не найден.</b>")


async def cmd_all_items(message: Message, bot: Bot, db: Database) -> None:
    items = db.get_shop_items()
    if not items:
        await message.reply("<b>🛍 Список товаров пуст.</b>")
        return
    lines = [f"• <b>{escape(i['name'])}</b> — {i['price']} ВРК [{i['category']}]" for i in items]
    await message.reply("<b>🧾 Все товары:</b>\n" + "\n".join(lines))
