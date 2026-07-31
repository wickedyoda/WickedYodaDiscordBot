from __future__ import annotations

import datetime
from typing import Any

from dnd.chronicle_schema import _get_conn


def _utc_now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def create_proxy_group(db_path: str, guild_id: int, owner_id: int, name: str, description: str = "") -> dict[str, Any]:
    guild_id = int(guild_id)
    owner_id = int(owner_id)
    with _get_conn(db_path) as conn:
        now = _utc_now()
        conn.execute(
            "INSERT INTO dnd_proxy_groups(guild_id, owner_id, name, description, created_at, updated_at) VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(guild_id, owner_id, name) DO UPDATE SET description=excluded.description, updated_at=excluded.updated_at",
            (guild_id, owner_id, name, description, now, now),
        )
        conn.commit()
    row = (
        _get_conn(db_path)
        .execute("SELECT * FROM dnd_proxy_groups WHERE guild_id=? AND owner_id=? AND name=?", (guild_id, owner_id, name))
        .fetchone()
    )
    return dict(row) if row else {}


def list_proxy_groups(db_path: str, guild_id: int, owner_id: int) -> list[dict[str, Any]]:
    guild_id = int(guild_id)
    owner_id = int(owner_id)
    rows = (
        _get_conn(db_path)
        .execute("SELECT * FROM dnd_proxy_groups WHERE guild_id=? AND owner_id=? ORDER BY id ASC", (guild_id, owner_id))
        .fetchall()
    )
    return [dict(r) for r in rows]


def add_proxy_to_group(db_path: str, guild_id: int, owner_id: int, group_name: str, proxy_name: str) -> dict[str, Any]:
    with _get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT id FROM dnd_proxies WHERE guild_id=? AND owner_id=? AND name=?",
            (int(guild_id), int(owner_id), proxy_name),
        ).fetchone()
        if not row:
            return {}
        proxy_id = int(row["id"])
        conn.execute(
            "INSERT OR IGNORE INTO dnd_proxy_group_members(group_name, guild_id, owner_id, proxy_id) VALUES(?,?,?,?)",
            (group_name, int(guild_id), int(owner_id), proxy_id),
        )
        conn.commit()
    return {"group": group_name, "proxy": proxy_name, "proxy_id": proxy_id}


def remove_proxy_from_group(db_path: str, guild_id: int, owner_id: int, group_name: str, proxy_name: str) -> bool:
    row = (
        _get_conn(db_path)
        .execute(
            "SELECT id FROM dnd_proxies WHERE guild_id=? AND owner_id=? AND name=?",
            (int(guild_id), int(owner_id), proxy_name),
        )
        .fetchone()
    )
    if not row:
        return False
    with _get_conn(db_path) as conn:
        cur = conn.execute(
            "DELETE FROM dnd_proxy_group_members WHERE group_name=? AND guild_id=? AND owner_id=? AND proxy_id=?",
            (group_name, int(guild_id), int(owner_id), int(row["id"])),
        )
        conn.commit()
        return cur.rowcount > 0


def list_group_proxies(db_path: str, guild_id: int, owner_id: int, group_name: str) -> list[dict[str, Any]]:
    rows = (
        _get_conn(db_path)
        .execute(
            "SELECT p.* FROM dnd_proxy_group_members m JOIN dnd_proxies p ON p.id = m.proxy_id "
            "WHERE m.group_name=? AND m.guild_id=? AND m.owner_id=? ORDER BY p.id ASC",
            (group_name, int(guild_id), int(owner_id)),
        )
        .fetchall()
    )
    return [dict(r) for r in rows]


def record_reproxy(db_path: str, guild_id: int, target_channel_id: int, owner_id: int, group_name: str, proxy_id: int, source_message_id: str = "", content: str = "") -> dict[str, Any]:
    with _get_conn(db_path) as conn:
        now = _utc_now()
        conn.execute(
            "INSERT INTO dnd_reproxy_jobs(guild_id, target_channel_id, owner_id, group_name, proxy_id, source_message_id, content, created_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (int(guild_id), int(target_channel_id), int(owner_id), group_name, int(proxy_id), source_message_id, content, now),
        )
        conn.commit()
    return {
        "guild_id": int(guild_id),
        "target_channel_id": int(target_channel_id),
        "owner_id": int(owner_id),
        "group_name": group_name,
        "proxy_id": int(proxy_id),
        "source_message_id": source_message_id,
        "content": content,
    }


def list_reproxy_jobs(db_path: str, guild_id: int, owner_id: int, limit: int = 50) -> list[dict[str, Any]]:
    rows = (
        _get_conn(db_path)
        .execute(
            "SELECT * FROM dnd_reproxy_jobs WHERE guild_id=? AND owner_id=? ORDER BY id DESC LIMIT ?",
            (int(guild_id), int(owner_id), int(limit)),
        )
        .fetchall()
    )
    return [dict(r) for r in rows]
