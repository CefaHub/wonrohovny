from __future__ import annotations

import html
import re
from datetime import datetime, timedelta
from typing import Optional

from aiogram import Bot
from aiogram.types import Message, User

MENTION_RE = re.compile(r"@([A-Za-z0-9_]{3,32})")

PROFESSIONS = {
    "айдол": {"cooldown": 24 * 3600, "title": "Айдол"},
    "продюсер": {"cooldown": 12 * 3600, "title": "Продюсер"},
    "фотограф": {"cooldown": 6 * 3600, "title": "Фотограф"},
    "стажёр": {"cooldown": 2 * 3600, "title": "Стажёр"},
}


def escape(text: str | None) -> str:
    return html.escape(text or "", quote=False)


def user_tag(user_id: int, username: str | None = None, full_name: str | None = None) -> str:
    if username:
        return f"@{escape(username)}"
    title = full_name or f"user_{user_id}"
    return f"<a href='tg://user?id={user_id}'>{escape(title)}</a>"


def display_name(user: User | dict | None, fallback_id: Optional[int] = None) -> str:
    if user is None:
        return f"user_{fallback_id}" if fallback_id else "пользователь"
    if isinstance(user, dict):
        return user_tag(
            user_id=user.get("id") or user.get("user_id") or fallback_id or 0,
            username=user.get("username"),
            full_name=user.get("full_name") or user.get("first_name"),
        )
    return user_tag(user.id, user.username, user.full_name)


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

    admins = await bot.get_chat_administrators(message.chat.id)
    for member in admins:
        if member.user.username and member.user.username.lower() == username:
            return {"id": member.user.id, "username": member.user.username, "full_name": member.user.full_name}
    return None


async def resolve_target_and_strip(message: Message, bot: Bot) -> tuple[Optional[dict], str]:
    text = message.text or ""
    target = await resolve_target_user(message, bot)
    if target and target.get("username"):
        text = re.sub(rf"@{re.escape(target['username'])}", "", text, count=1, flags=re.I).strip()
    return target, text


async def ensure_target_user(target: dict, bot: Bot) -> dict:
    db = getattr(bot, "db")
    db.ensure_user(target["id"], target.get("username"))
    row = db.get_user(target["id"])
    return {"id": row["user_id"], "username": row["username"]}


def fmt_status(status: str, gender: Optional[str], partner_name: Optional[str]) -> str:
    if status == "single":
        return "свободен"
    if status == "relationship":
        return f"в отношениях с {partner_name}" if partner_name else "в отношениях"
    if status == "married":
        word = "замужем" if gender == "ж" else "женат"
        return f"{word} с {partner_name}" if partner_name else word
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
