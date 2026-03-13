from __future__ import annotations

import json
import random
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Optional


class Database:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    gender TEXT,
                    custom_role TEXT,
                    first_seen TEXT NOT NULL,
                    total_messages INTEGER NOT NULL DEFAULT 0,
                    daily_messages INTEGER NOT NULL DEFAULT 0,
                    last_message_date TEXT,
                    relationship_status TEXT NOT NULL DEFAULT 'single',
                    partner_id INTEGER,
                    balance INTEGER NOT NULL DEFAULT 100,
                    vh_balance INTEGER NOT NULL DEFAULT 0,
                    profession TEXT,
                    last_work_time TEXT,
                    pregnant INTEGER NOT NULL DEFAULT 0,
                    pregnancy_end_time TEXT,
                    daily_bonus_at TEXT,
                    FOREIGN KEY(partner_id) REFERENCES users(user_id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS children (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    parent_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    gender TEXT NOT NULL,
                    FOREIGN KEY(parent_id) REFERENCES users(user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS inventory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    item_name TEXT NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(user_id, item_name),
                    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS banks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    owner_id INTEGER NOT NULL,
                    balance INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY(owner_id) REFERENCES users(user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS bank_members (
                    bank_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    can_withdraw INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY(bank_id, user_id),
                    FOREIGN KEY(bank_id) REFERENCES banks(id) ON DELETE CASCADE,
                    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS shop_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    price INTEGER NOT NULL,
                    category TEXT NOT NULL CHECK(category IN ('shop', 'pharmacy', 'vhshop')),
                    currency TEXT NOT NULL DEFAULT 'VRK'
                );

                CREATE TABLE IF NOT EXISTS processes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    user_id INTEGER NOT NULL,
                    type TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    partner_id INTEGER,
                    cancelled INTEGER NOT NULL DEFAULT 0,
                    meta TEXT,
                    UNIQUE(user_id, type)
                );

                CREATE TABLE IF NOT EXISTS chat_settings (
                    chat_id INTEGER PRIMARY KEY,
                    pregnancy_chance INTEGER NOT NULL DEFAULT 10
                );

                CREATE TABLE IF NOT EXISTS pending_proposals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    initiator_id INTEGER NOT NULL,
                    target_id INTEGER NOT NULL,
                    proposal_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    extra TEXT
                );

                CREATE TABLE IF NOT EXISTS pending_births (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    mother_id INTEGER NOT NULL,
                    father_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS family_children (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    parent1_id INTEGER NOT NULL,
                    parent2_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    gender TEXT NOT NULL,
                    birth_date TEXT NOT NULL,
                    last_age_update TEXT NOT NULL,
                    age INTEGER NOT NULL DEFAULT 0,
                    stage TEXT NOT NULL DEFAULT 'младенец',
                    health INTEGER NOT NULL DEFAULT 100,
                    mood INTEGER NOT NULL DEFAULT 100,
                    satiety INTEGER NOT NULL DEFAULT 100,
                    energy INTEGER NOT NULL DEFAULT 100,
                    love_parent1 INTEGER NOT NULL DEFAULT 50,
                    love_parent2 INTEGER NOT NULL DEFAULT 50,
                    upbringing INTEGER NOT NULL DEFAULT 50,
                    talent_vocal INTEGER NOT NULL DEFAULT 0,
                    talent_dance INTEGER NOT NULL DEFAULT 0,
                    talent_rap INTEGER NOT NULL DEFAULT 0,
                    talent_acting INTEGER NOT NULL DEFAULT 0,
                    charisma INTEGER NOT NULL DEFAULT 0,
                    discipline INTEGER NOT NULL DEFAULT 0,
                    autism INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS child_relations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    child1_id INTEGER NOT NULL,
                    child2_id INTEGER NOT NULL,
                    relation_type TEXT NOT NULL,
                    relation_value INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(child1_id, child2_id, relation_type)
                );

                CREATE TABLE IF NOT EXISTS groups_kpop (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE
                );

                CREATE TABLE IF NOT EXISTS albums (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id INTEGER,
                    name TEXT NOT NULL UNIQUE,
                    FOREIGN KEY(group_id) REFERENCES groups_kpop(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS cards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    idol_name TEXT,
                    group_name TEXT,
                    album_name TEXT,
                    rarity TEXT NOT NULL,
                    gacha_type TEXT NOT NULL CHECK(gacha_type IN ('normal', 'elite')),
                    caption TEXT,
                    photo_file_id TEXT NOT NULL,
                    sell_price INTEGER NOT NULL DEFAULT 0,
                    created_by INTEGER,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS user_cards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    card_id INTEGER NOT NULL,
                    obtained_at TEXT NOT NULL,
                    UNIQUE(user_id, card_id, obtained_at),
                    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY(card_id) REFERENCES cards(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS pending_card_uploads (
                    user_id INTEGER PRIMARY KEY,
                    chat_id INTEGER NOT NULL,
                    gacha_type TEXT NOT NULL,
                    rarity TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS rpg_profiles (
                    user_id INTEGER PRIMARY KEY,
                    level INTEGER NOT NULL DEFAULT 1,
                    exp INTEGER NOT NULL DEFAULT 0,
                    reputation INTEGER NOT NULL DEFAULT 0,
                    energy INTEGER NOT NULL DEFAULT 10,
                    concerts INTEGER NOT NULL DEFAULT 0,
                    haters_defeated INTEGER NOT NULL DEFAULT 0,
                    adventures_done INTEGER NOT NULL DEFAULT 0,
                    stage_name TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );
                """
            )
            self._ensure_column(conn, "users", "vh_balance", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "users", "daily_bonus_at", "TEXT")
            self._ensure_column(conn, "shop_items", "currency", "TEXT NOT NULL DEFAULT 'VRK'")

    # user basics
    def ensure_user(self, user_id: int, username: Optional[str]) -> None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        today = date.today().isoformat()
        with self.connect() as conn:
            row = conn.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO users(user_id, username, first_seen, last_message_date) VALUES (?, ?, ?, ?)",
                    (user_id, username, now, today),
                )
                conn.execute("INSERT OR IGNORE INTO rpg_profiles(user_id) VALUES (?)", (user_id,))
            else:
                conn.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
                conn.execute("INSERT OR IGNORE INTO rpg_profiles(user_id) VALUES (?)", (user_id,))

    def register_message(self, user_id: int, username: Optional[str]) -> None:
        self.ensure_user(user_id, username)
        today = date.today().isoformat()
        with self.connect() as conn:
            row = conn.execute("SELECT total_messages, daily_messages, last_message_date FROM users WHERE user_id = ?", (user_id,)).fetchone()
            daily = row["daily_messages"] if row["last_message_date"] == today else 0
            conn.execute(
                "UPDATE users SET total_messages=?, daily_messages=?, last_message_date=?, username=? WHERE user_id=?",
                (row["total_messages"] + 1, daily + 1, today, username, user_id),
            )

    def get_user(self, user_id: int) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()

    def get_user_by_username(self, username: str) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM users WHERE lower(username)=lower(?)", (username,)).fetchone()

    def update_user_field(self, user_id: int, field: str, value: Any) -> None:
        allowed = {
            "gender", "custom_role", "relationship_status", "partner_id", "balance", "vh_balance",
            "profession", "last_work_time", "pregnant", "pregnancy_end_time", "daily_bonus_at", "username"
        }
        if field not in allowed:
            raise ValueError("Unsupported field")
        with self.connect() as conn:
            conn.execute(f"UPDATE users SET {field} = ? WHERE user_id = ?", (value, user_id))

    def delete_user(self, user_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM users WHERE user_id = ?", (user_id,))

    def add_balance(self, user_id: int, amount: int, currency: str = "VRK") -> None:
        field = "balance" if currency.upper() == "VRK" else "vh_balance"
        with self.connect() as conn:
            conn.execute(f"UPDATE users SET {field} = {field} + ? WHERE user_id = ?", (amount, user_id))

    def transfer_balance(self, from_user: int, to_user: int, amount: int) -> bool:
        with self.connect() as conn:
            row = conn.execute("SELECT balance FROM users WHERE user_id=?", (from_user,)).fetchone()
            if not row or row["balance"] < amount:
                return False
            conn.execute("UPDATE users SET balance=balance-? WHERE user_id=?", (amount, from_user))
            conn.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (amount, to_user))
            return True

    def set_relationship(self, user1: int, user2: int, status: str) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE users SET relationship_status=?, partner_id=? WHERE user_id=?", (status, user2, user1))
            conn.execute("UPDATE users SET relationship_status=?, partner_id=? WHERE user_id=?", (status, user1, user2))

    def clear_relationship(self, user1: int, user2: Optional[int]) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE users SET relationship_status='single', partner_id=NULL WHERE user_id=?", (user1,))
            if user2:
                conn.execute("UPDATE users SET relationship_status='single', partner_id=NULL WHERE user_id=?", (user2,))

    # children / family system
    def _child_stage(self, age: int) -> str:
        if age <= 0:
            return 'младенец'
        if age <= 3:
            return 'малыш'
        if age <= 6:
            return 'дошкольник'
        if age <= 12:
            return 'ребёнок'
        if age <= 17:
            return 'подросток'
        return 'взрослый'

    def _age_child_if_needed(self, conn: sqlite3.Connection, row: sqlite3.Row) -> None:
        today = date.today().isoformat()
        last = row['last_age_update'] or today
        if last == today:
            return
        try:
            last_d = date.fromisoformat(last)
        except Exception:
            last_d = date.today()
        years = (date.today() - last_d).days
        if years <= 0:
            return
        new_age = row['age'] + years
        new_stage = self._child_stage(new_age)
        conn.execute("UPDATE family_children SET age=?, stage=?, last_age_update=? WHERE id=?", (new_age, new_stage, today, row['id']))

    def add_child_for_parents(self, parent_ids: Iterable[int], name: str, gender: str) -> None:
        pids = list(parent_ids)
        if len(pids) < 2:
            return
        parent1, parent2 = pids[0], pids[1]
        today = date.today().isoformat()
        autism = 1 if random.randint(1, 100) <= 5 else 0
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO family_children(parent1_id, parent2_id, name, gender, birth_date, last_age_update, autism) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (parent1, parent2, name, gender, today, today, autism),
            )

    def get_children(self, parent_id: int) -> list[sqlite3.Row]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM family_children WHERE parent1_id=? OR parent2_id=? ORDER BY id", (parent_id, parent_id)).fetchall()
            for row in rows:
                self._age_child_if_needed(conn, row)
            rows = conn.execute("SELECT * FROM family_children WHERE parent1_id=? OR parent2_id=? ORDER BY id", (parent_id, parent_id)).fetchall()
            return rows

    def get_child_for_parent(self, parent_id: int, child_name: str) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM family_children WHERE (parent1_id=? OR parent2_id=?) AND lower(name)=lower(?) ORDER BY id LIMIT 1",
                (parent_id, parent_id, child_name),
            ).fetchone()
            if row:
                self._age_child_if_needed(conn, row)
                row = conn.execute("SELECT * FROM family_children WHERE id=?", (row['id'],)).fetchone()
            return row

    def update_child_fields(self, child_id: int, **fields: Any) -> None:
        allowed = {'health','mood','satiety','energy','love_parent1','love_parent2','upbringing','talent_vocal','talent_dance','talent_rap','talent_acting','charisma','discipline','age','stage','last_age_update'}
        if not fields:
            return
        for k in fields:
            if k not in allowed:
                raise ValueError(f'Unsupported child field: {k}')
        clause = ', '.join(f"{k}=?" for k in fields)
        values = list(fields.values()) + [child_id]
        with self.connect() as conn:
            conn.execute(f"UPDATE family_children SET {clause} WHERE id=?", values)

    def remove_child(self, parent_id: int, child_name: str) -> int:
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM family_children WHERE (parent1_id=? OR parent2_id=?) AND lower(name)=lower(?)", (parent_id, parent_id, child_name))
            return cur.rowcount

    def set_child_relation(self, child1_id: int, child2_id: int, relation_type: str, delta: int = 10) -> None:
        if child1_id == child2_id:
            return
        a, b = sorted([child1_id, child2_id])
        with self.connect() as conn:
            row = conn.execute("SELECT relation_value FROM child_relations WHERE child1_id=? AND child2_id=? AND relation_type=?", (a, b, relation_type)).fetchone()
            if row:
                conn.execute("UPDATE child_relations SET relation_value=? WHERE child1_id=? AND child2_id=? AND relation_type=?", (row['relation_value'] + delta, a, b, relation_type))
            else:
                conn.execute("INSERT INTO child_relations(child1_id, child2_id, relation_type, relation_value) VALUES (?, ?, ?, ?)", (a, b, relation_type, delta))

    def get_child_relations(self, child_id: int) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM child_relations WHERE child1_id=? OR child2_id=? ORDER BY relation_value DESC",
                (child_id, child_id),
            ).fetchall()

    # inventory/shop
    def add_inventory_item(self, user_id: int, item_name: str, quantity: int = 1) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO inventory(user_id, item_name, quantity) VALUES (?, ?, ?) ON CONFLICT(user_id, item_name) DO UPDATE SET quantity=quantity+excluded.quantity",
                (user_id, item_name, quantity),
            )

    def remove_inventory_item(self, user_id: int, item_name: str, quantity: int = 1) -> bool:
        with self.connect() as conn:
            row = conn.execute("SELECT quantity FROM inventory WHERE user_id=? AND lower(item_name)=lower(?)", (user_id, item_name)).fetchone()
            if not row or row["quantity"] < quantity:
                return False
            newq = row["quantity"] - quantity
            if newq <= 0:
                conn.execute("DELETE FROM inventory WHERE user_id=? AND lower(item_name)=lower(?)", (user_id, item_name))
            else:
                conn.execute("UPDATE inventory SET quantity=? WHERE user_id=? AND lower(item_name)=lower(?)", (newq, user_id, item_name))
            return True

    def get_inventory(self, user_id: int) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM inventory WHERE user_id=? ORDER BY item_name", (user_id,)).fetchall()

    def add_shop_item(self, name: str, price: int, category: str, currency: str = "VRK") -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO shop_items(name, price, category, currency) VALUES (?, ?, ?, ?) ON CONFLICT(name) DO UPDATE SET price=excluded.price, category=excluded.category, currency=excluded.currency",
                (name, price, category, currency),
            )

    def remove_shop_item(self, name: str) -> int:
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM shop_items WHERE lower(name)=lower(?)", (name,))
            return cur.rowcount

    def get_shop_items(self, category: str) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM shop_items WHERE category=? ORDER BY id", (category,)).fetchall()

    def get_shop_item_by_name(self, name: str) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM shop_items WHERE lower(name)=lower(?)", (name,)).fetchone()

    def get_shop_item_by_id_and_category(self, item_id: int, category: str) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM shop_items WHERE id=? AND category=?", (item_id, category)).fetchone()

    def list_all_items(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM shop_items ORDER BY category, id").fetchall()

    # banks
    def create_bank(self, name: str, owner_id: int) -> None:
        with self.connect() as conn:
            cur = conn.execute("INSERT INTO banks(name, owner_id, balance) VALUES (?, ?, 0)", (name, owner_id))
            bank_id = cur.lastrowid
            conn.execute("INSERT INTO bank_members(bank_id, user_id, can_withdraw) VALUES (?, ?, 1)", (bank_id, owner_id))

    def get_bank(self, name: str) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM banks WHERE lower(name)=lower(?)", (name,)).fetchone()

    def get_bank_members(self, bank_id: int) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT bm.*, u.username FROM bank_members bm JOIN users u ON u.user_id=bm.user_id WHERE bm.bank_id=? ORDER BY u.username",
                (bank_id,),
            ).fetchall()

    def add_bank_member(self, bank_id: int, user_id: int, can_withdraw: int = 1) -> None:
        with self.connect() as conn:
            conn.execute("INSERT OR REPLACE INTO bank_members(bank_id, user_id, can_withdraw) VALUES (?, ?, ?)", (bank_id, user_id, can_withdraw))

    def remove_bank_member(self, bank_id: int, user_id: int) -> int:
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM bank_members WHERE bank_id=? AND user_id=?", (bank_id, user_id))
            return cur.rowcount

    def user_can_withdraw(self, bank_id: int, user_id: int) -> bool:
        with self.connect() as conn:
            row = conn.execute("SELECT can_withdraw FROM bank_members WHERE bank_id=? AND user_id=?", (bank_id, user_id)).fetchone()
            return bool(row and row["can_withdraw"])

    def bank_deposit(self, bank_id: int, user_id: int, amount: int) -> bool:
        with self.connect() as conn:
            bal = conn.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)).fetchone()
            if not bal or bal["balance"] < amount:
                return False
            conn.execute("UPDATE users SET balance=balance-? WHERE user_id=?", (amount, user_id))
            conn.execute("UPDATE banks SET balance=balance+? WHERE id=?", (amount, bank_id))
            return True

    def bank_withdraw(self, bank_id: int, user_id: int, amount: int) -> bool:
        with self.connect() as conn:
            bank = conn.execute("SELECT balance FROM banks WHERE id=?", (bank_id,)).fetchone()
            member = conn.execute("SELECT can_withdraw FROM bank_members WHERE bank_id=? AND user_id=?", (bank_id, user_id)).fetchone()
            if not bank or not member or not member["can_withdraw"] or bank["balance"] < amount:
                return False
            conn.execute("UPDATE banks SET balance=balance-? WHERE id=?", (amount, bank_id))
            conn.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (amount, user_id))
            return True

    def get_user_banks(self, user_id: int) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT b.* FROM banks b JOIN bank_members bm ON bm.bank_id=b.id WHERE bm.user_id=? ORDER BY b.name",
                (user_id,),
            ).fetchall()

    # settings/processes/proposals
    def ensure_chat_settings(self, chat_id: int) -> None:
        with self.connect() as conn:
            conn.execute("INSERT OR IGNORE INTO chat_settings(chat_id, pregnancy_chance) VALUES (?, 10)", (chat_id,))

    def get_pregnancy_chance(self, chat_id: int) -> int:
        self.ensure_chat_settings(chat_id)
        with self.connect() as conn:
            return int(conn.execute("SELECT pregnancy_chance FROM chat_settings WHERE chat_id=?", (chat_id,)).fetchone()["pregnancy_chance"])

    def set_pregnancy_chance(self, chat_id: int, chance: int) -> None:
        self.ensure_chat_settings(chat_id)
        with self.connect() as conn:
            conn.execute("UPDATE chat_settings SET pregnancy_chance=? WHERE chat_id=?", (chance, chat_id))

    def create_process(self, chat_id: int, user_id: int, ptype: str, end_time: str, partner_id: Optional[int], meta: Optional[str]) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO processes(chat_id, user_id, type, end_time, partner_id, cancelled, meta) VALUES (?, ?, ?, ?, ?, 0, ?)",
                (chat_id, user_id, ptype, end_time, partner_id, meta),
            )

    def get_process(self, user_id: int, ptype: str) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM processes WHERE user_id=? AND type=?", (user_id, ptype)).fetchone()

    def get_process_pair(self, ptype: str, user1: int, user2: int) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM processes WHERE type=? AND ((user_id=? AND partner_id=?) OR (user_id=? AND partner_id=?))",
                (ptype, user1, user2, user2, user1),
            ).fetchall()

    def delete_process(self, user_id: int, ptype: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM processes WHERE user_id=? AND type=?", (user_id, ptype))

    def delete_process_pair(self, ptype: str, user1: int, user2: int) -> None:
        with self.connect() as conn:
            conn.execute(
                "DELETE FROM processes WHERE type=? AND ((user_id=? AND partner_id=?) OR (user_id=? AND partner_id=?))",
                (ptype, user1, user2, user2, user1),
            )

    def cancel_process_pair(self, ptype: str, user1: int, user2: int) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE processes SET cancelled=1 WHERE type=? AND ((user_id=? AND partner_id=?) OR (user_id=? AND partner_id=?))",
                (ptype, user1, user2, user2, user1),
            )

    def set_process_meta(self, user_id: int, ptype: str, meta: str) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE processes SET meta=? WHERE user_id=? AND type=?", (meta, user_id, ptype))

    def get_active_processes(self, ptype: str) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM processes WHERE type=? AND cancelled=0", (ptype,)).fetchall()

    def create_proposal(self, chat_id: int, initiator_id: int, target_id: int, proposal_type: str, extra: Optional[dict] = None) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO pending_proposals(chat_id, initiator_id, target_id, proposal_type, created_at, extra) VALUES (?, ?, ?, ?, ?, ?)",
                (chat_id, initiator_id, target_id, proposal_type, datetime.now().isoformat(), json.dumps(extra or {})),
            )
            return int(cur.lastrowid)

    def get_proposal(self, proposal_id: int) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM pending_proposals WHERE id=?", (proposal_id,)).fetchone()

    def delete_proposal(self, proposal_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM pending_proposals WHERE id=?", (proposal_id,))

    def create_pending_birth(self, chat_id: int, mother_id: int, father_id: int, message_id: int) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO pending_births(chat_id, mother_id, father_id, message_id, created_at) VALUES (?, ?, ?, ?, ?)",
                (chat_id, mother_id, father_id, message_id, datetime.now().isoformat()),
            )

    def get_pending_birth(self, message_id: int) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM pending_births WHERE message_id=?", (message_id,)).fetchone()

    def delete_pending_birth(self, message_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM pending_births WHERE message_id=?", (message_id,))

    # activity and daily bonus
    def top_daily_activity(self, limit: int = 20) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM users ORDER BY daily_messages DESC, total_messages DESC LIMIT ?", (limit,)).fetchall()

    def can_take_daily_bonus(self, user_id: int) -> bool:
        row = self.get_user(user_id)
        if not row:
            return False
        today = date.today().isoformat()
        return row["daily_bonus_at"] != today

    # groups/albums/cards
    def add_group(self, name: str) -> None:
        with self.connect() as conn:
            conn.execute("INSERT OR IGNORE INTO groups_kpop(name) VALUES (?)", (name,))

    def remove_group(self, name: str) -> int:
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM groups_kpop WHERE lower(name)=lower(?)", (name,))
            return cur.rowcount

    def list_groups(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM groups_kpop ORDER BY name").fetchall()

    def add_album(self, name: str, group_name: Optional[str] = None) -> None:
        gid = None
        if group_name:
            self.add_group(group_name)
            with self.connect() as conn:
                row = conn.execute("SELECT id FROM groups_kpop WHERE lower(name)=lower(?)", (group_name,)).fetchone()
                gid = row["id"] if row else None
                conn.execute("INSERT OR IGNORE INTO albums(name, group_id) VALUES (?, ?)", (name, gid))
        else:
            with self.connect() as conn:
                conn.execute("INSERT OR IGNORE INTO albums(name) VALUES (?)", (name,))

    def list_albums(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute("SELECT a.*, g.name as group_name FROM albums a LEFT JOIN groups_kpop g ON g.id=a.group_id ORDER BY a.name").fetchall()

    def remove_album(self, name: str) -> int:
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM albums WHERE lower(name)=lower(?)", (name,))
            return cur.rowcount

    def set_pending_card_upload(self, user_id: int, chat_id: int, gacha_type: str, rarity: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO pending_card_uploads(user_id, chat_id, gacha_type, rarity, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, chat_id, gacha_type, rarity, datetime.now().isoformat()),
            )

    def get_pending_card_upload(self, user_id: int) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM pending_card_uploads WHERE user_id=?", (user_id,)).fetchone()

    def clear_pending_card_upload(self, user_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM pending_card_uploads WHERE user_id=?", (user_id,))

    def add_card(self, title: str, idol_name: str, group_name: str, album_name: str, rarity: str, gacha_type: str, caption: str, photo_file_id: str, sell_price: int, created_by: int) -> int:
        if group_name:
            self.add_group(group_name)
        if album_name:
            self.add_album(album_name, group_name if group_name else None)
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO cards(title, idol_name, group_name, album_name, rarity, gacha_type, caption, photo_file_id, sell_price, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (title, idol_name, group_name, album_name, rarity, gacha_type, caption, photo_file_id, sell_price, created_by, datetime.now().isoformat()),
            )
            return int(cur.lastrowid)

    def delete_card_by_title(self, title: str) -> int:
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM cards WHERE lower(title)=lower(?)", (title,))
            return cur.rowcount

    def list_cards(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM cards ORDER BY gacha_type, rarity, title").fetchall()

    def get_card_by_title(self, title: str) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM cards WHERE lower(title)=lower(?)", (title,)).fetchone()

    def get_cards_for_gacha(self, gacha_type: str) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM cards WHERE gacha_type=?", (gacha_type,)).fetchall()

    def add_user_card(self, user_id: int, card_id: int) -> None:
        with self.connect() as conn:
            conn.execute("INSERT INTO user_cards(user_id, card_id, obtained_at) VALUES (?, ?, ?)", (user_id, card_id, datetime.now().isoformat()))

    def list_user_cards(self, user_id: int) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT uc.id as user_card_id, c.* FROM user_cards uc JOIN cards c ON c.id=uc.card_id WHERE uc.user_id=? ORDER BY c.rarity DESC, c.title",
                (user_id,),
            ).fetchall()

    def remove_user_card_by_title(self, user_id: int, title: str) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT uc.id as user_card_id, c.* FROM user_cards uc JOIN cards c ON c.id=uc.card_id WHERE uc.user_id=? AND lower(c.title)=lower(?) ORDER BY uc.id LIMIT 1",
                (user_id, title),
            ).fetchone()
            if row:
                conn.execute("DELETE FROM user_cards WHERE id=?", (row["user_card_id"],))
            return row

    def give_user_card_by_title(self, user_id: int, title: str) -> bool:
        card = self.get_card_by_title(title)
        if not card:
            return False
        self.add_user_card(user_id, card["id"])
        return True

    def transfer_user_card(self, from_user: int, to_user: int, title: str) -> bool:
        row = self.remove_user_card_by_title(from_user, title)
        if not row:
            return False
        self.add_user_card(to_user, row["id"])
        return True

    # rpg
    def get_rpg_profile(self, user_id: int) -> sqlite3.Row:
        self.ensure_user(user_id, None)
        with self.connect() as conn:
            return conn.execute("SELECT * FROM rpg_profiles WHERE user_id=?", (user_id,)).fetchone()

    def update_rpg_profile(self, user_id: int, **fields: Any) -> None:
        if not fields:
            return
        allowed = {"level", "exp", "reputation", "energy", "concerts", "haters_defeated", "adventures_done", "stage_name"}
        for key in fields:
            if key not in allowed:
                raise ValueError(f"Unsupported RPG field: {key}")
        clause = ", ".join(f"{k}=?" for k in fields)
        values = list(fields.values()) + [user_id]
        with self.connect() as conn:
            conn.execute(f"UPDATE rpg_profiles SET {clause} WHERE user_id=?", values)
