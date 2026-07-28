from __future__ import annotations

import json
import sqlite3
from pathlib import Path

_DND_CHAR_TABLE = """
CREATE TABLE IF NOT EXISTS dnd_characters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    owner_id INTEGER NOT NULL,
    splat TEXT NOT NULL,
    name TEXT NOT NULL,
    json TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(guild_id, owner_id, name)
);
"""


def _get_conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema(db_path: str) -> None:
    with _get_conn(db_path) as conn:
        conn.execute(_DND_CHAR_TABLE)


def save_character(db_path: str, guild_id: int, owner_id: int, splat: str, name: str, payload: dict) -> None:
    with _get_conn(db_path) as conn:
        conn.execute(
            "INSERT INTO dnd_characters(guild_id, owner_id, splat, name, json) VALUES(?,?,?,?,?) "
            "ON CONFLICT(guild_id, owner_id, name) DO UPDATE SET json=excluded.json, splat=excluded.splat, updated_at=CURRENT_TIMESTAMP",
            (int(guild_id), int(owner_id), splat, str(name)[:50], json.dumps(payload, ensure_ascii=False)),
        )


def delete_character(db_path: str, guild_id: int, owner_id: int, name: str) -> bool:
    with _get_conn(db_path) as conn:
        cur = conn.execute("DELETE FROM dnd_characters WHERE guild_id=? AND owner_id=? AND name=?", (int(guild_id), int(owner_id), str(name)))
        return cur.rowcount > 0


def find_character(db_path: str, guild_id: int, owner_id: int, name: str) -> dict | None:
    with _get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT id, guild_id, owner_id, splat, name, json, updated_at FROM dnd_characters WHERE guild_id=? AND owner_id=? AND name=?",
            (int(guild_id), int(owner_id), str(name)),
        ).fetchone()
        if not row:
            return None
        return {"id": row["id"], "guild_id": row["guild_id"], "owner_id": row["owner_id"], "splat": row["splat"], "name": row["name"], "data": json.loads(row["json"]), "updated_at": row["updated_at"]}


def list_characters(db_path: str, guild_id: int, owner_id: int) -> list[dict]:
    with _get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT name, splat FROM dnd_characters WHERE guild_id=? AND owner_id=? ORDER BY updated_at DESC",
            (int(guild_id), int(owner_id)),
        ).fetchall()
        return [{"name": r["name"], "splat": r["splat"]} for r in rows]
