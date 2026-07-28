from __future__ import annotations

import json
import sqlite3
from typing import Optional

from .initiative import InitiativeTracker, InitiativeCharacter


_INIT_SCHEMA = """
CREATE TABLE IF NOT EXISTS dnd_initiative_trackers (
    channel_id INTEGER PRIMARY KEY,
    guild_id INTEGER NOT NULL,
    owner_id INTEGER NOT NULL,
    json TEXT NOT NULL
);
"""


def _get_conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.row_factory = sqlite3.Row
    conn.execute(_INIT_SCHEMA)
    return conn


def ensure_schema(db_path: str) -> None:
    with _get_conn(db_path) as conn:
        conn.commit()


def load_tracker(db_path: str, channel_id: int) -> Optional[InitiativeTracker]:
    with _get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT guild_id, owner_id, json FROM dnd_initiative_trackers WHERE channel_id = ?",
            (channel_id,),
        ).fetchone()
        if not row:
            return None
        data = json.loads(row["json"])
        chars = [InitiativeCharacter(**c) for c in data.get("characters", [])]
        return InitiativeTracker(
            channel_id=channel_id,
            guild_id=row["guild_id"],
            owner_id=row["owner_id"],
            characters=chars,
            phase=data.get("phase", "roll"),
            round=int(data.get("round", 1)),
        )


def save_tracker(db_path: str, tracker: InitiativeTracker) -> None:
    payload = {
        "guild_id": tracker.guild_id,
        "owner_id": tracker.owner_id,
        "characters": [
            {
                "member_id": c.member_id,
                "display_name": c.display_name,
                "dex_wits": c.dex_wits,
                "modifier": c.modifier,
                "extra_actions": c.extra_actions,
                "roll": c.roll,
                "total": c.total,
            }
            for c in tracker.characters
        ],
        "phase": tracker.phase,
        "round": tracker.round,
    }
    with _get_conn(db_path) as conn:
        conn.execute(
            "INSERT INTO dnd_initiative_trackers(channel_id, guild_id, owner_id, json) VALUES(?,?,?,?) "
            "ON CONFLICT(channel_id) DO UPDATE SET json=excluded.json, guild_id=excluded.guild_id, owner_id=excluded.owner_id",
            (tracker.channel_id, tracker.guild_id, tracker.owner_id, json.dumps(payload, ensure_ascii=False)),
        )
        conn.commit()
