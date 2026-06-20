"""Хранилище подписок и уже показанных объявлений (SQLite).

Методы синхронные; в async-коде вызывай через asyncio.to_thread,
поэтому соединение открывается на каждую операцию (потокобезопасно).
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

_SCHEMA = """
CREATE TABLE IF NOT EXISTS subscriptions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id     INTEGER NOT NULL,
    offer_type  INTEGER NOT NULL,
    query       TEXT NOT NULL DEFAULT '',
    arbeitszeit TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS seen (
    subscription_id INTEGER NOT NULL,
    refnr           TEXT NOT NULL,
    seen_at         TEXT NOT NULL,
    PRIMARY KEY (subscription_id, refnr),
    FOREIGN KEY (subscription_id) REFERENCES subscriptions(id) ON DELETE CASCADE
);
"""


@dataclass(frozen=True)
class Subscription:
    id: int
    chat_id: int
    offer_type: int
    query: str
    arbeitszeit: str


def _now() -> str:
    return datetime.now(UTC).isoformat()


class Storage:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            self._migrate(conn)

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(subscriptions)").fetchall()
        }
        if "arbeitszeit" not in columns:
            conn.execute(
                "ALTER TABLE subscriptions ADD COLUMN "
                "arbeitszeit TEXT NOT NULL DEFAULT ''"
            )

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def add_subscription(
        self, chat_id: int, offer_type: int, query: str, arbeitszeit: str
    ) -> tuple[int, bool]:
        """Создаёт подписку или возвращает существующую идентичную.

        Возвращает (id, created): created=False, если такая подписка уже была.
        Защищает от дублей при случайном повторном нажатии.
        """
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM subscriptions WHERE chat_id = ? AND offer_type = ? "
                "AND query = ? AND arbeitszeit = ?",
                (chat_id, offer_type, query, arbeitszeit),
            ).fetchone()
            if existing is not None:
                return int(existing["id"]), False
            cur = conn.execute(
                "INSERT INTO subscriptions "
                "(chat_id, offer_type, query, arbeitszeit, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (chat_id, offer_type, query, arbeitszeit, _now()),
            )
            return int(cur.lastrowid), True

    def list_subscriptions(self, chat_id: int) -> list[Subscription]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, chat_id, offer_type, query, arbeitszeit "
                "FROM subscriptions WHERE chat_id = ? ORDER BY id",
                (chat_id,),
            ).fetchall()
        return [Subscription(**dict(row)) for row in rows]

    def all_subscriptions(self) -> list[Subscription]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, chat_id, offer_type, query, arbeitszeit "
                "FROM subscriptions ORDER BY id"
            ).fetchall()
        return [Subscription(**dict(row)) for row in rows]

    def remove_subscription(self, chat_id: int, sub_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM subscriptions WHERE id = ? AND chat_id = ?",
                (sub_id, chat_id),
            )
            return cur.rowcount > 0

    def filter_new_refnrs(self, sub_id: int, refnrs: list[str]) -> set[str]:
        """Возвращает refnr, которых ещё нет в seen для этой подписки."""
        if not refnrs:
            return set()
        with self._connect() as conn:
            placeholders = ",".join("?" * len(refnrs))
            rows = conn.execute(
                f"SELECT refnr FROM seen WHERE subscription_id = ? "
                f"AND refnr IN ({placeholders})",
                (sub_id, *refnrs),
            ).fetchall()
        known = {row["refnr"] for row in rows}
        return {r for r in refnrs if r not in known}

    def mark_seen(self, sub_id: int, refnrs: list[str]) -> None:
        if not refnrs:
            return
        now = _now()
        with self._connect() as conn:
            conn.executemany(
                "INSERT OR IGNORE INTO seen (subscription_id, refnr, seen_at) "
                "VALUES (?, ?, ?)",
                [(sub_id, refnr, now) for refnr in refnrs],
            )
