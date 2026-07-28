from __future__ import annotations

import json
import datetime
from typing import List, Optional

from dnd.chronicle_schema import _get_conn

_DEFAULT_TIMESTAMP = "1970-01-01T00:00:00"


def _utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _ensure_guild(db_path: str, guild_id: int, owner_id: int = 0, name: str = "Chronicle") -> None:
    with _get_conn(db_path) as conn:
        conn.execute(
            "INSERT INTO dnd_chronicles(guild_id, name, owner_id, created_at, updated_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(guild_id) DO NOTHING",
            (int(guild_id), name, owner_id, _utc_now(), _utc_now()),
        )
        conn.commit()


def get_chronicle(db_path: str, guild_id: int) -> Optional[dict]:
    with _get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM dnd_chronicles WHERE guild_id = ?", (int(guild_id),)).fetchone()
        if not row:
            return None
        return {
            "guild_id": row["guild_id"],
            "name": row["name"],
            "tracker_channel_id": row["tracker_channel_id"],
            "xp_tracking_enabled": bool(row["xp_tracking_enabled"]),
            "auto_reward_enabled": bool(row["auto_reward_enabled"]),
            "monitored_channel_ids": json.loads(row["monitored_channel_ids"]),
            "excluded_channel_ids": json.loads(row["excluded_channel_ids"]),
            "discord_roles": json.loads(row["discord_roles"]),
            "allowed_splats": json.loads(row["allowed_splats"]),
            "xp_feed_channel_id": row["xp_feed_channel_id"],
            "xp_reward_feed_channel_id": row["xp_reward_feed_channel_id"],
            "owner_id": row["owner_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


def create_chronicle(db_path: str, guild_id: int, owner_id: int, name: str = "Chronicle") -> dict:
    with _get_conn(db_path) as conn:
        conn.execute(
            "INSERT INTO dnd_chronicles(guild_id, name, owner_id, created_at, updated_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(guild_id) DO UPDATE SET name=excluded.name, updated_at=excluded.updated_at",
            (int(guild_id), name, owner_id, _utc_now(), _utc_now()),
        )
        conn.commit()
    return get_chronicle(db_path, guild_id)


def update_chronicle(db_path: str, guild_id: int, **fields) -> None:
    _ensure_guild(db_path, guild_id)
    allowed = {
        "name",
        "tracker_channel_id",
        "xp_tracking_enabled",
        "auto_reward_enabled",
        "monitored_channel_ids",
        "excluded_channel_ids",
        "discord_roles",
        "allowed_splats",
        "xp_feed_channel_id",
        "xp_reward_feed_channel_id",
        "owner_id",
    }
    sets = ["updated_at = ?"]
    values = [_utc_now()]
    for k, v in fields.items():
        if k not in allowed:
            continue
        sets.append(f"{k} = ?")
        if isinstance(v, (list, dict)):
            v = json.dumps(v, ensure_ascii=False)
        values.append(v)
    values.append(int(guild_id))
    with _get_conn(db_path) as conn:
        conn.execute(f"UPDATE dnd_chronicles SET {', '.join(sets)} WHERE guild_id = ?", values)
        conn.commit()


def list_members(db_path: str, guild_id: int) -> List[dict]:
    with _get_conn(db_path) as conn:
        rows = conn.execute("SELECT * FROM dnd_chronicle_members WHERE guild_id = ?", (int(guild_id),)).fetchall()
        return [
            {
                "id": r["id"],
                "guild_id": r["guild_id"],
                "user_id": r["user_id"],
                "storyteller": bool(r["storyteller"]),
                "admin": bool(r["admin"]),
                "nickname": r["nickname"],
                "avatar_url": r["avatar_url"],
                "default_character": r["default_character"],
            }
            for r in rows
        ]


def upsert_member(db_path: str, guild_id: int, user_id: int, nickname: str = "", avatar_url: str = "", admin: bool = False, storyteller: bool = False, default_character: str = "") -> None:
    _ensure_guild(db_path, guild_id)
    with _get_conn(db_path) as conn:
        conn.execute(
            "INSERT INTO dnd_chronicle_members(guild_id, user_id, storyteller, admin, nickname, avatar_url, default_character) VALUES(?,?,?,?,?,?,?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET storyteller=excluded.storyteller, admin=excluded.admin, nickname=excluded.nickname, avatar_url=excluded.avatar_url, default_character=excluded.default_character",
            (int(guild_id), int(user_id), int(storyteller), int(admin), nickname, avatar_url, default_character),
        )
        conn.commit()
