from __future__ import annotations

import asyncio
import json
import random
from datetime import datetime, timedelta

from aiogram import Bot

from database import Database
from keyboards import pill_keyboard
from utils import RARITY_SELL_PRICE, choose_weighted_rarity, display_name


class ProcessManager:
    def __init__(self, bot: Bot, db: Database, config):
        self.bot = bot
        self.db = db
        self.config = config
        self.tasks: dict[str, asyncio.Task] = {}

    def key(self, prefix: str, *parts: object) -> str:
        return ":".join([prefix, *map(str, parts)])

    def schedule_sex(self, chat_id: int, user1: dict, user2: dict, end_time: datetime | None = None) -> None:
        pair = tuple(sorted([user1["id"], user2["id"]]))
        key = self.key("sex", chat_id, pair[0], pair[1])
        if key in self.tasks and not self.tasks[key].done():
            return
        self.tasks[key] = asyncio.create_task(self._sex_flow(chat_id, user1, user2, key, end_time))

    def schedule_pregnancy(self, chat_id: int, pregnant_user: dict, partner: dict, end_time: datetime | None = None) -> None:
        key = self.key("pregnancy", chat_id, pregnant_user["id"])
        if key in self.tasks and not self.tasks[key].done():
            return
        self.tasks[key] = asyncio.create_task(self._pregnancy_flow(chat_id, pregnant_user, partner, key, end_time))

    async def _sex_flow(self, chat_id: int, user1: dict, user2: dict, key: str, end_time: datetime | None) -> None:
        end_time = end_time or (datetime.now() + timedelta(seconds=self.config.sex_duration_seconds))
        delay = max(0, (end_time - datetime.now()).total_seconds())
        await asyncio.sleep(delay)
        pair = self.db.get_process_pair("sex", user1["id"], user2["id"])
        if not pair or any(row["cancelled"] for row in pair):
            self.db.delete_process_pair("sex", user1["id"], user2["id"])
            self.tasks.pop(key, None)
            return

        self.db.delete_process_pair("sex", user1["id"], user2["id"])
        await self.bot.send_message(chat_id, "<b>👶 Процесс завершён.</b>", parse_mode="HTML")

        pregnant_user, partner = self._pregnant_candidate(user1, user2)
        chance = self.db.get_pregnancy_chance(chat_id)
        if chance >= 100 or random.randint(1, 100) <= chance:
            preg_end = datetime.now() + timedelta(seconds=self.config.pregnancy_duration_seconds)
            self.db.update_user_field(pregnant_user["id"], "pregnant", 1)
            self.db.update_user_field(pregnant_user["id"], "pregnancy_end_time", preg_end.isoformat())
            self.db.create_process(chat_id, pregnant_user["id"], "pregnancy", preg_end.isoformat(), partner["id"], json.dumps({"nausea": 0, "pill_taken": False}))
            await self.bot.send_message(
                chat_id,
                f"<b>🤰 {display_name(pregnant_user)} забеременел(а)!</b> Роды через <b>5 минут</b> 💖",
                parse_mode="HTML",
            )
            self.schedule_pregnancy(chat_id, pregnant_user, partner, preg_end)
        self.tasks.pop(key, None)

    async def _pregnancy_flow(self, chat_id: int, pregnant_user: dict, partner: dict, key: str, end_time: datetime | None) -> None:
        process = self.db.get_process(pregnant_user["id"], "pregnancy")
        if not process:
            self.tasks.pop(key, None)
            return
        end_time = end_time or datetime.fromisoformat(process["end_time"])

        while datetime.now() < end_time:
            now = datetime.now()
            sleep_for = min(self.config.nausea_check_interval_seconds, max(0, int((end_time - now).total_seconds())))
            if sleep_for <= 0:
                break
            await asyncio.sleep(sleep_for)
            process = self.db.get_process(pregnant_user["id"], "pregnancy")
            if not process or process["cancelled"]:
                self.tasks.pop(key, None)
                return
            meta = json.loads(process["meta"] or "{}")
            if random.randint(1, 100) <= self.config.nausea_chance_percent:
                meta["pill_taken"] = False
                meta["nausea"] = meta.get("nausea", 0) + 1
                self.db.set_process_meta(pregnant_user["id"], "pregnancy", json.dumps(meta))
                await self.bot.send_message(
                    chat_id,
                    f"<b>🤢 {display_name(pregnant_user)} тошнит!</b> Нужно принять таблетку 💊",
                    parse_mode="HTML",
                    reply_markup=pill_keyboard(),
                )
                await asyncio.sleep(20)
                process = self.db.get_process(pregnant_user["id"], "pregnancy")
                if not process:
                    self.tasks.pop(key, None)
                    return
                meta = json.loads(process["meta"] or "{}")
                if not meta.get("pill_taken"):
                    self.db.update_user_field(pregnant_user["id"], "pregnant", 0)
                    self.db.update_user_field(pregnant_user["id"], "pregnancy_end_time", None)
                    self.db.delete_process(pregnant_user["id"], "pregnancy")
                    await self.bot.send_message(chat_id, f"<b>💔 У {display_name(pregnant_user)} случился выкидыш...</b>", parse_mode="HTML")
                    self.tasks.pop(key, None)
                    return
                meta["pill_taken"] = False
                self.db.set_process_meta(pregnant_user["id"], "pregnancy", json.dumps(meta))

        self.db.update_user_field(pregnant_user["id"], "pregnant", 0)
        self.db.update_user_field(pregnant_user["id"], "pregnancy_end_time", None)
        self.db.delete_process(pregnant_user["id"], "pregnancy")
        msg = await self.bot.send_message(
            chat_id,
            f"<b>🎉 У {display_name(pregnant_user)} родился ребёнок!</b>\nНапиши в ответ: <code>имя &lt;мальчик/девочка&gt; &lt;имя&gt;</code>",
            parse_mode="HTML",
        )
        self.db.create_pending_birth(chat_id, pregnant_user["id"], partner["id"], msg.message_id)
        self.tasks.pop(key, None)

    def take_pill(self, user_id: int) -> bool:
        process = self.db.get_process(user_id, "pregnancy")
        if not process:
            return False
        if not self.db.remove_inventory_item(user_id, "Таблетка от тошноты", 1):
            return False
        meta = json.loads(process["meta"] or "{}")
        meta["pill_taken"] = True
        self.db.set_process_meta(user_id, "pregnancy", json.dumps(meta))
        return True

    async def restore_from_db(self) -> None:
        for row in self.db.get_active_processes("sex"):
            partner = row["partner_id"]
            if not partner or row["user_id"] > partner:
                continue
            user1 = self.db.get_user(row["user_id"])
            user2 = self.db.get_user(partner)
            if not user1 or not user2:
                continue
            self.schedule_sex(row["chat_id"], {"id": user1["user_id"], "username": user1["username"], "gender": user1["gender"]}, {"id": user2["user_id"], "username": user2["username"], "gender": user2["gender"]}, datetime.fromisoformat(row["end_time"]))
        for row in self.db.get_active_processes("pregnancy"):
            user1 = self.db.get_user(row["user_id"])
            user2 = self.db.get_user(row["partner_id"]) if row["partner_id"] else None
            if not user1 or not user2:
                continue
            self.schedule_pregnancy(row["chat_id"], {"id": user1["user_id"], "username": user1["username"], "gender": user1["gender"]}, {"id": user2["user_id"], "username": user2["username"], "gender": user2["gender"]}, datetime.fromisoformat(row["end_time"]))

    @staticmethod
    def _pregnant_candidate(user1: dict, user2: dict) -> tuple[dict, dict]:
        g1 = user1.get("gender")
        g2 = user2.get("gender")
        if g1 == "ж" and g2 != "ж":
            return user1, user2
        if g2 == "ж" and g1 != "ж":
            return user2, user1
        return random.choice([(user1, user2), (user2, user1)])


class GachaService:
    def __init__(self, db: Database):
        self.db = db

    def roll(self, user_id: int, gacha_type: str, price: int, currency: str) -> tuple[str, object | None]:
        user = self.db.get_user(user_id)
        if not user:
            return "Профиль не найден.", None
        if currency == "VRK" and user["balance"] < price:
            return "Недостаточно ВРК.", None
        if currency == "VH" and user["vh_balance"] < price:
            return "Недостаточно ВХ.", None
        cards = self.db.get_cards_for_gacha(gacha_type)
        if not cards:
            return "В этой гаче пока нет карточек.", None

        rarity = choose_weighted_rarity(gacha_type)
        pool = [c for c in cards if c["rarity"] == rarity]
        if not pool:
            pool = cards
        card = random.choice(pool)
        self.db.add_balance(user_id, -price, currency)
        self.db.add_user_card(user_id, card["id"])
        return "ok", card

    @staticmethod
    def sell_price(rarity: str) -> int:
        return RARITY_SELL_PRICE.get(rarity, 100)
