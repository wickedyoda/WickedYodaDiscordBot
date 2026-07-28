from __future__ import annotations

import datetime
from typing import List, Optional

from dnd.chronicle_schema import _get_conn


def _utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def create_proxy(db_path: str, guild_id: int, owner_id: int, name: str, template: str = "", thumbnail_url: str = "", avatar_url: str = "", description: str = "") -> dict:
    with _get_conn(db_path) as conn:
        now = _utc_now()
        conn.execute(
            "INSERT INTO dnd_proxies(guild_id, owner_id, name, template, thumbnail_url, avatar_url, description, created_at, updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(guild_id, owner_id, name) DO UPDATE SET template=excluded.template, thumbnail_url=excluded.thumbnail_url, avatar_url=excluded.avatar_url, description=excluded.description, updated_at=excluded.updated_at",
            (int(guild_id), int(owner_id), name, template, thumbnail_url, avatar_url, description, now, now),
        )
        conn.commit()
    row = _get_conn(db_path).execute("SELECT * FROM dnd_proxies WHERE guild_id=? AND owner_id=? AND name=?", (int(guild_id), int(owner_id), name)).fetchone()
    return dict(row)


def get_proxy(db_path: str, guild_id: int, owner_id: int, name: str) -> Optional[dict]:
    with _get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM dnd_proxies WHERE guild_id=? AND owner_id=? AND name=?", (int(guild_id), int(owner_id), name)).fetchone()
        return dict(row) if row else None


def list_proxies(db_path: str, guild_id: int, owner_id: int) -> List[dict]:
    with _get_conn(db_path) as conn:
        rows = conn.execute("SELECT * FROM dnd_proxies WHERE guild_id=? AND owner_id=? ORDER BY id ASC", (int(guild_id), int(owner_id))).fetchall()
        return [dict(r) for r in rows]


def delete_proxy(db_path: str, guild_id: int, owner_id: int, name: str) -> bool:
    with _get_conn(db_path) as conn:
        cur = conn.execute("DELETE FROM dnd_proxies WHERE guild_id=? AND owner_id=? AND name=?", (int(guild_id), int(owner_id), name))
        conn.commit()
        return cur.rowcount > 0


def save_proxied_message(db_path: str, message_id: str, proxy_id: int, guild_id: int, channel_id: int, owner_id: int, content: str = "") -> None:
    with _get_conn(db_path) as conn:
        conn.execute(
            "INSERT INTO dnd_proxied_messages(message_id, proxy_id, guild_id, channel_id, owner_id, content, created_at) VALUES(?,?,?,?,?,?,?) "
            "ON CONFLICT(message_id) DO NOTHING",
            (message_id, int(proxy_id), int(guild_id), int(channel_id), int(owner_id), content, _utc_now()),
        )
        conn.commit()


def add_proxy_identity(db_path: str, guild_id: int, owner_id: int, name: str, display_name: str, avatar_url: str = "") -> dict:
    existing = get_proxy(db_path, int(guild_id), int(owner_id), name)
    if existing:
        existing["name"] = display_name
        existing["avatar_url"] = avatar_url
        return existing
    template = "{name}: {content}"
    return create_proxy(db_path, int(guild_id), int(owner_id), name, template=template, avatar_url=avatar_url)
