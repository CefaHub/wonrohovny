from __future__ import annotations

import html
import json
import random
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from aiogram import Bot
from aiogram.types import Message, User

MENTION_RE = re.compile(r"@([A-Za-z0-9_]{3,32})")

PROFESSIONS = {
    "айдол": {"cooldown": 24 * 3600, "title": "Айдол", "income": (100, 100)},
    "продюсер": {"cooldown": 12 * 3600, "title": "Продюсер", "income": (50, 200)},
    "фотограф": {"cooldown": 6 * 3600, "title": "Фотограф", "income": (30, 60)},
    "стажёр": {"cooldown": 2 * 3600, "title": "Стажёр", "income": (10, 10)},
}

FUN_ACTIONS = {
    "обнять": ["нежно обнял(а)", "крепко прижал(а) к себе", "подарил(а) мягкие объятия"],
    "поцеловать": ["поцеловал(а)", "оставил(а) милый поцелуй", "чмокнул(а)"],
    "погладить": ["погладил(а) по голове", "бережно погладил(а)", "миленько погладил(а)"],
    "ударить": ["слегка шлёпнул(а)", "атаковал(а) хейтерским вайбом", "дал(а) комичный удар"],
    "укусить": ["кусьнул(а)", "оставил(а) игривый кусь", "цапнул(а)"],
    "засмущать": ["заставил(а) покраснеть", "вызвал(а) приступ смущения", "оставил(а) без слов"],
    "похвалить": ["сказал(а), что ты сияешь", "назвал(а) настоящей звездой", "осыпал(а) комплиментами"],
}

RARITY_ORDER = ["обычная", "редкая", "эпическая", "легендарная", "секрет"]
RARITY_WEIGHTS_NORMAL = {"обычная": 60, "редкая": 25, "эпическая": 10, "легендарная": 4, "секрет": 1}
RARITY_WEIGHTS_ELITE = {"обычная": 0, "редкая": 20, "эпическая": 45, "легендарная": 25, "секрет": 10}
RARITY_SELL_PRICE = {"обычная": 60, "редкая": 180, "эпическая": 450, "легендарная": 1200, "секрет": 3000}



def load_adventures(path: str | Path) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))



def escape(text: str | None) -> str:
    return html.escape(text or "", quote=False)



def user_link(user_id: int, username: str | None = None, full_name: str | None = None) -> str:
    if username:
        return f"@{escape(username)}"
    title = full_name or f"user_{user_id}"
    return f"<a href='tg://user?id={user_id}'>{escape(title)}</a>"



def display_name(user: User | dict | None, fallback_id: Optional[int] = None) -> str:
    if user is None:
        return f"user_{fallback_id}" if fallback_id else "пользователь"
    if isinstance(user, dict):
        return user_link(user.get("id") or user.get("user_id") or fallback_id or 0, user.get("username"), user.get("full_name") or user.get("first_name"))
    return user_link(user.id, user.username, user.full_name)


async def is_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    member = await bot.get_chat_member(chat_id, user_id)
    return member.status in {"administrator", "creator"}


async def is_creator(bot: Bot, chat_id: int, user_id: int) -> bool:
    member = await bot.get_chat_member(chat_id, user_id)
    return member.status == "creator"



def parse_command(text: str | None) -> tuple[str, list[str]]:
    if not text:
        return "", []
    parts = text.strip().split()
    if not parts:
        return "", []
    return parts[0].lower(), parts[1:]


async def resolve_target_user(message: Message, bot: Bot) -> Optional[dict]:
    if message.reply_to_message and message.reply_to_message.from_user and not message.reply_to_message.from_user.is_bot:
        u = message.reply_to_message.from_user
        return {"id": u.id, "username": u.username, "full_name": u.full_name}

    text = message.text or message.caption or ""
    match = MENTION_RE.search(text)
    if not match:
        return None
    username = match.group(1).lower()
    db = getattr(bot, "db", None)
    if db:
        row = db.get_user_by_username(username)
        if row:
            return {"id": row["user_id"], "username": row["username"]}
    return None


async def resolve_target_and_strip(message: Message, bot: Bot) -> tuple[Optional[dict], str]:
    text = (message.text or message.caption or "").strip()
    target = await resolve_target_user(message, bot)
    if target and target.get("username"):
        text = re.sub(rf"@{re.escape(target['username'])}", "", text, count=1, flags=re.I).strip()
    return target, text



def fmt_status(status: str, partner_name: Optional[str]) -> str:
    if status == "single":
        return "свободен(а)"
    if status == "relationship":
        return f"в отношениях с {partner_name}" if partner_name else "в отношениях"
    if status == "married":
        return f"в браке с {partner_name}" if partner_name else "в браке"
    return status



def human_timedelta(seconds: int) -> str:
    seconds = max(0, int(seconds))
    td = timedelta(seconds=seconds)
    days = td.days
    hours, rem = divmod(td.seconds, 3600)
    minutes, sec = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days} д")
    if hours:
        parts.append(f"{hours} ч")
    if minutes:
        parts.append(f"{minutes} мин")
    if sec and not days:
        parts.append(f"{sec} сек")
    return " ".join(parts) or "0 сек"



def parse_datetime(value: str | None) -> Optional[datetime]:
    return datetime.fromisoformat(value) if value else None



def choose_weighted_rarity(gacha_type: str) -> str:
    weights = RARITY_WEIGHTS_ELITE if gacha_type == "elite" else RARITY_WEIGHTS_NORMAL
    population = [r for r, w in weights.items() if w > 0]
    return random.choices(population, weights=[weights[r] for r in population], k=1)[0]



def parse_card_caption(caption: str) -> dict:
    data = {"title": caption.strip(), "idol_name": "", "group_name": "", "album_name": "", "caption": caption.strip()}
    for line in caption.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        if key in {"имя", "айдол", "idol"}:
            data["idol_name"] = value
        elif key in {"группа", "group"}:
            data["group_name"] = value
        elif key in {"альбом", "album"}:
            data["album_name"] = value
        elif key in {"название", "title"}:
            data["title"] = value
    if data["idol_name"] and data["group_name"] and data["title"] == caption.strip():
        data["title"] = f"{data['idol_name']} — {data['group_name']}"
    return data
