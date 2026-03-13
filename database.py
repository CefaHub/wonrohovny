from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from typing import Any, Iterable, Optional


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.init_db()

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
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
                    last_message_date TEXT NOT NULL,
                    relationship_status TEXT NOT NULL DEFAULT 'single',
                    partner_id INTEGER,
                    balance INTEGER NOT NULL DEFAULT 100,
                    profession TEXT,
                    last_work_time TEXT,
                    pregnant INTEGER NOT NULL DEFAULT 0,
                    pregnancy_end_time TEXT,
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
                    category TEXT NOT NULL CHECK(category IN ('shop', 'pharmacy'))
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
                    UNIQUE(user_id, type),
                    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
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
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS pending_births (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    mother_id INTEGER NOT NULL,
                    father_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            self._ensure_column(conn, "processes", "chat_id", "INTEGER")
            self._ensure_column(conn, "processes", "meta", "TEXT")
            self._ensure_column(conn, "users", "pregnant", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "users", "pregnancy_end_time", "TEXT")

    def ensure_chat_settings(self, chat_id: int) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO chat_settings(chat_id, pregnancy_chance) VALUES (?, 10)",
                (chat_id,),
            )

    def get_pregnancy_chance(self, chat_id: int) -> int:
        self.ensure_chat_settings(chat_id)
        with self.connect() as conn:
            row = conn.execute("SELECT pregnancy_chance FROM chat_settings WHERE chat_id = ?", (chat_id,)).fetchone()
            return int(row["pregnancy_chance"])

    def set_pregnancy_chance(self, chat_id: int, chance: int) -> None:
        self.ensure_chat_settings(chat_id)
        with self.connect() as conn:
            conn.execute("UPDATE chat_settings SET pregnancy_chance = ? WHERE chat_id = ?", (chance, chat_id))

    def ensure_user(self, user_id: int, username: Optional[str]) -> None:
        today = date.today().isoformat()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO users(
                        user_id, username, first_seen, total_messages, daily_messages, last_message_date
                    ) VALUES (?, ?, ?, 0, 0, ?)
                    """,
                    (user_id, username, now, today),
                )
            else:
                conn.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))

    def register_message(self, user_id: int, username: Optional[str]) -> None:
        self.ensure_user(user_id, username)
        today = date.today().isoformat()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT total_messages, daily_messages, last_message_date FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            daily = row["daily_messages"] if row["last_message_date"] == today else 0
            conn.execute(
                """
                UPDATE users
                SET total_messages = ?, daily_messages = ?, last_message_date = ?, username = ?
                WHERE user_id = ?
                """,
                (row["total_messages"] + 1, daily + 1, today, username, user_id),
            )

    def get_user(self, user_id: int) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()

    def get_user_by_username(self, username: str) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM users WHERE lower(username) = lower(?)", (username,)).fetchone()

    def delete_user(self, user_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM users WHERE user_id = ?", (user_id,))

    def update_user_field(self, user_id: int, field: str, value: Any) -> None:
        allowed = {
            "gender", "custom_role", "relationship_status", "partner_id", "balance",
            "profession", "last_work_time", "pregnant", "pregnancy_end_time", "username"
        }
        if field not in allowed:
            raise ValueError("Unsupported field")
        with self.connect() as conn:
            conn.execute(f"UPDATE users SET {field} = ? WHERE user_id = ?", (value, user_id))

    def set_relationship(self, user1: int, user2: int, status: str) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE users SET relationship_status = ?, partner_id = ? WHERE user_id = ?", (status, user2, user1))
            conn.execute("UPDATE users SET relationship_status = ?, partner_id = ? WHERE user_id = ?", (status, user1, user2))

    def clear_relationship(self, user1: int, user2: Optional[int]) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE users SET relationship_status = 'single', partner_id = NULL WHERE user_id = ?", (user1,))
            if user2:
                conn.execute("UPDATE users SET relationship_status = 'single', partner_id = NULL WHERE user_id = ?", (user2,))

    def add_child_for_parents(self, parent_ids: Iterable[int], name: str, gender: str) -> None:
        with self.connect() as conn:
            for parent_id in parent_ids:
                conn.execute(
                    "INSERT INTO children(parent_id, name, gender) VALUES (?, ?, ?)",
                    (parent_id, name, gender),
                )

    def get_children(self, parent_id: int) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM children WHERE parent_id = ? ORDER BY id", (parent_id,)).fetchall()

    def remove_child(self, parent_id: int, child_name: str) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                "DELETE FROM children WHERE parent_id = ? AND lower(name) = lower(?)",
                (parent_id, child_name),
            )
            return cur.rowcount

    def add_balance(self, user_id: int, amount: int) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))

    def transfer_balance(self, from_user: int, to_user: int, amount: int) -> bool:
        with self.connect() as conn:
            row = conn.execute("SELECT balance FROM users WHERE user_id = ?", (from_user,)).fetchone()
            if row is None or row["balance"] < amount:
                return False
            conn.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, from_user))
            conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, to_user))
            return True

    def create_bank(self, name: str, owner_id: int) -> None:
        with self.connect() as conn:
            cur = conn.execute("INSERT INTO banks(name, owner_id, balance) VALUES (?, ?, 0)", (name, owner_id))
            bank_id = cur.lastrowid
            conn.execute(
                "INSERT INTO bank_members(bank_id, user_id, can_withdraw) VALUES (?, ?, 1)",
                (bank_id, owner_id),
            )

    def get_bank(self, name: str) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM banks WHERE lower(name) = lower(?)", (name,)).fetchone()

    def get_user_banks(self, user_id: int) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT b.* FROM banks b
                JOIN bank_members bm ON bm.bank_id = b.id
                WHERE bm.user_id = ?
                ORDER BY b.name
                """,
                (user_id,),
            ).fetchall()

    def get_bank_members(self, bank_id: int) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT u.user_id, u.username, bm.can_withdraw
                FROM bank_members bm
                JOIN users u ON u.user_id = bm.user_id
                WHERE bm.bank_id = ?
                ORDER BY u.username
                """,
                (bank_id,),
            ).fetchall()

    def add_bank_member(self, bank_id: int, user_id: int, can_withdraw: int = 1) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO bank_members(bank_id, user_id, can_withdraw) VALUES (?, ?, ?)",
                (bank_id, user_id, can_withdraw),
            )

    def remove_bank_member(self, bank_id: int, user_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM bank_members WHERE bank_id = ? AND user_id = ?", (bank_id, user_id))

    def deposit_to_bank(self, bank_id: int, user_id: int, amount: int) -> bool:
        with self.connect() as conn:
            balance = conn.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)).fetchone()["balance"]
            if balance < amount:
                return False
            conn.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
            conn.execute("UPDATE banks SET balance = balance + ? WHERE id = ?", (amount, bank_id))
            return True

    def withdraw_from_bank(self, bank_id: int, user_id: int, amount: int) -> bool:
        with self.connect() as conn:
            member = conn.execute(
                "SELECT can_withdraw FROM bank_members WHERE bank_id = ? AND user_id = ?",
                (bank_id, user_id),
            ).fetchone()
            bank = conn.execute("SELECT balance FROM banks WHERE id = ?", (bank_id,)).fetchone()
            if member is None or bank is None or not member["can_withdraw"] or bank["balance"] < amount:
                return False
            conn.execute("UPDATE banks SET balance = balance - ? WHERE id = ?", (amount, bank_id))
            conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
            return True

    def add_shop_item(self, name: str, price: int, category: str) -> None:
        with self.connect() as conn:
            conn.execute("INSERT INTO shop_items(name, price, category) VALUES (?, ?, ?)", (name, price, category))

    def remove_shop_item(self, name: str) -> int:
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM shop_items WHERE lower(name) = lower(?)", (name,))
            return cur.rowcount

    def get_shop_items(self, category: Optional[str] = None) -> list[sqlite3.Row]:
        with self.connect() as conn:
            if category:
                return conn.execute(
                    "SELECT * FROM shop_items WHERE category = ? ORDER BY price, name",
                    (category,),
                ).fetchall()
            return conn.execute("SELECT * FROM shop_items ORDER BY category, price, name").fetchall()

    def get_shop_item_by_name(self, name: str) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM shop_items WHERE lower(name) = lower(?)", (name,)).fetchone()

    def add_inventory_item(self, user_id: int, item_name: str, quantity: int = 1) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO inventory(user_id, item_name, quantity)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, item_name)
                DO UPDATE SET quantity = quantity + excluded.quantity
                """,
                (user_id, item_name, quantity),
            )

    def remove_inventory_item(self, user_id: int, item_name: str, quantity: int = 1) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT quantity FROM inventory WHERE user_id = ? AND lower(item_name) = lower(?)",
                (user_id, item_name),
            ).fetchone()
            if row is None or row["quantity"] < quantity:
                return False
            new_quantity = row["quantity"] - quantity
            if new_quantity == 0:
                conn.execute(
                    "DELETE FROM inventory WHERE user_id = ? AND lower(item_name) = lower(?)",
                    (user_id, item_name),
                )
            else:
                conn.execute(
                    "UPDATE inventory SET quantity = ? WHERE user_id = ? AND lower(item_name) = lower(?)",
                    (new_quantity, user_id, item_name),
                )
            return True

    def get_inventory(self, user_id: int) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM inventory WHERE user_id = ? ORDER BY item_name", (user_id,)).fetchall()

    def create_process(self, chat_id: int, user_id: int, process_type: str, end_time: str, partner_id: Optional[int], meta: str | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO processes(chat_id, user_id, type, end_time, partner_id, cancelled, meta)
                VALUES (?, ?, ?, ?, ?, 0, ?)
                """,
                (chat_id, user_id, process_type, end_time, partner_id, meta),
            )

    def get_process(self, user_id: int, process_type: str) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM processes WHERE user_id = ? AND type = ?",
                (user_id, process_type),
            ).fetchone()

    def set_process_meta(self, user_id: int, process_type: str, meta: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE processes SET meta = ? WHERE user_id = ? AND type = ?",
                (meta, user_id, process_type),
            )

    def get_process_pair(self, process_type: str, user_id: int, partner_id: int) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM processes WHERE type = ? AND ((user_id = ? AND partner_id = ?) OR (user_id = ? AND partner_id = ?))",
                (process_type, user_id, partner_id, partner_id, user_id),
            ).fetchall()

    def cancel_process_pair(self, process_type: str, user_id: int, partner_id: int) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE processes SET cancelled = 1 WHERE type = ? AND ((user_id = ? AND partner_id = ?) OR (user_id = ? AND partner_id = ?))",
                (process_type, user_id, partner_id, partner_id, user_id),
            )

    def delete_process_pair(self, process_type: str, user_id: int, partner_id: int) -> None:
        with self.connect() as conn:
            conn.execute(
                "DELETE FROM processes WHERE type = ? AND ((user_id = ? AND partner_id = ?) OR (user_id = ? AND partner_id = ?))",
                (process_type, user_id, partner_id, partner_id, user_id),
            )

    def delete_process(self, user_id: int, process_type: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM processes WHERE user_id = ? AND type = ?", (user_id, process_type))

    def get_active_processes(self, process_type: str) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM processes WHERE type = ? AND cancelled = 0", (process_type,)).fetchall()

    def create_proposal(self, chat_id: int, initiator_id: int, target_id: int, proposal_type: str) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO pending_proposals(chat_id, initiator_id, target_id, proposal_type, created_at) VALUES (?, ?, ?, ?, ?)",
                (chat_id, initiator_id, target_id, proposal_type, datetime.now().isoformat()),
            )
            return int(cur.lastrowid)

    def get_proposal(self, proposal_id: int) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM pending_proposals WHERE id = ?", (proposal_id,)).fetchone()

    def delete_proposal(self, proposal_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM pending_proposals WHERE id = ?", (proposal_id,))

    def create_pending_birth(self, chat_id: int, mother_id: int, father_id: int, message_id: int) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO pending_births(chat_id, mother_id, father_id, message_id, created_at) VALUES (?, ?, ?, ?, ?)",
                (chat_id, mother_id, father_id, message_id, datetime.now().isoformat()),
            )

    def get_pending_birth_by_message(self, chat_id: int, message_id: int) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM pending_births WHERE chat_id = ? AND message_id = ?",
                (chat_id, message_id),
            ).fetchone()

    def delete_pending_birth(self, pending_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM pending_births WHERE id = ?", (pending_id,))
