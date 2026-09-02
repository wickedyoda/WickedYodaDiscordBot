from __future__ import annotations

import datetime
import json

from dnd.chronicle_schema import _get_conn

_DEFAULT_TIMESTAMP = "1970-01-01T00:00:00"


def _utc_now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def _ensure_guild(db_path: str, guild_id: int, owner_id: int = 0, name: str = "Chronicle") -> None:
    with _get_conn(db_path) as conn:
        conn.execute(
            "INSERT INTO dnd_chronicles(guild_id, name, owner_id, created_at, updated_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(guild_id) DO NOTHING",
            (int(guild_id), name, owner_id, _utc_now(), _utc_now()),
        )
        conn.commit()


def get_chronicle(db_path: str, guild_id: int) -> dict | None:
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
            "edition": row["edition"],
            "edition_setup_completed": bool(row["edition_setup_completed"]),
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
    if not fields:
        return
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
    unknown = [k for k in fields if k not in allowed]
    if unknown:
        raise ValueError(f"Unknown chronicle fields: {', '.join(unknown)}")
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
        # nosec B608: column names validated against 'allowed' allow-list on lines 65-77
        # all f"{k} = ?" interpolations come from a hardcoded allow-list, not user input
        conn.execute(f"UPDATE dnd_chronicles SET {', '.join(sets)} WHERE guild_id = ?", values)
        conn.commit()


def list_members(db_path: str, guild_id: int) -> list[dict]:
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


def list_member_rankings(db_path: str, guild_id: int, limit: int = 50) -> list[dict]:
    guild_id = int(guild_id)
    with _get_conn(db_path) as conn:
        rows = conn.execute(
            """
            SELECT m.user_id, m.nickname, m.default_character, m.storyteller, m.admin,
                   COALESCE(p.pool, 0) AS xp
            FROM dnd_chronicle_members m
            LEFT JOIN dnd_xp_pools p ON p.guild_id = m.guild_id AND p.user_id = m.user_id
            WHERE m.guild_id = ?
            ORDER BY xp DESC, m.user_id ASC
            LIMIT ?
            """,
            (guild_id, int(limit)),
        ).fetchall()
        return [
            {
                "user_id": int(r["user_id"]),
                "nickname": str(r["nickname"] or ""),
                "default_character": str(r["default_character"] or ""),
                "storyteller": bool(r["storyteller"]),
                "admin": bool(r["admin"]),
                "xp": float(r["xp"] or 0),
            }
            for r in rows
        ]


def upsert_member(
    db_path: str,
    guild_id: int,
    user_id: int,
    nickname: str = "",
    avatar_url: str = "",
    admin: bool = False,
    storyteller: bool = False,
    default_character: str = "",
) -> None:
    _ensure_guild(db_path, guild_id)
    with _get_conn(db_path) as conn:
        conn.execute(
            "INSERT INTO dnd_chronicle_members(guild_id, user_id, storyteller, admin, nickname, avatar_url, default_character) VALUES(?,?,?,?,?,?,?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET storyteller=excluded.storyteller, admin=excluded.admin, nickname=excluded.nickname, avatar_url=excluded.avatar_url, default_character=excluded.default_character",
            (int(guild_id), int(user_id), int(storyteller), int(admin), nickname, avatar_url, default_character),
        )
        conn.commit()


# ---- XP helpers ----


def add_xp(db_path: str, guild_id: int, user_id: int, amount: float, reason: str = "") -> None:
    if amount == 0:
        return
    guild_id = int(guild_id)
    user_id = int(user_id)
    with _get_conn(db_path) as conn:
        conn.execute(
            "INSERT INTO dnd_xp_pools(guild_id, user_id, pool) VALUES(?,?,?) ON CONFLICT(guild_id, user_id) DO UPDATE SET pool=pool+?",
            (guild_id, user_id, amount, amount),
        )
        conn.execute(
            "INSERT INTO dnd_xp_entries(guild_id, user_id, amount, reason, created_at) VALUES(?,?,?,?,?)",
            (guild_id, user_id, amount, reason, _utc_now()),
        )
        conn.commit()


def get_xp_balance(db_path: str, guild_id: int, user_id: int) -> float:
    with _get_conn(db_path) as conn:
        row = conn.execute("SELECT pool FROM dnd_xp_pools WHERE guild_id=? AND user_id=?", (int(guild_id), int(user_id))).fetchone()
        return float(row["pool"]) if row else 0.0


def list_xp_entries(db_path: str, guild_id: int, user_id: int, limit: int = 50) -> list[dict]:
    with _get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT id, guild_id, user_id, amount, reason, created_at FROM dnd_xp_entries WHERE guild_id=? AND user_id=? ORDER BY id DESC LIMIT ?",
            (int(guild_id), int(user_id), int(limit)),
        ).fetchall()
        return [dict(r) for r in rows]


# ---- Reward helpers ----


def create_reward_rule(db_path: str, guild_id: int, name: str = "Reward Rule") -> dict:
    guild_id = int(guild_id)
    with _get_conn(db_path) as conn:
        now = _utc_now()
        cur = conn.execute(
            "INSERT INTO dnd_reward_rules(guild_id, name, created_at, updated_at) VALUES(?,?,?,?)",
            (guild_id, name, now, now),
        )
        conn.commit()
        rule_id = int(cur.lastrowid)
    return {"id": rule_id, "name": name}


def upsert_reward_tier(db_path: str, rule_id: int, idx: int = 0, threshold: int = 1, reward: float = 1.0) -> None:
    with _get_conn(db_path) as conn:
        conn.execute(
            "INSERT INTO dnd_reward_tiers(rule_id, idx, threshold, reward) VALUES(?,?,?,?) "
            "ON CONFLICT(rule_id, idx) DO UPDATE SET threshold=excluded.threshold, reward=excluded.reward",
            (int(rule_id), int(idx), int(threshold), float(reward)),
        )
        conn.commit()


def list_reward_rules(db_path: str, guild_id: int) -> list[dict]:
    with _get_conn(db_path) as conn:
        rows = conn.execute("SELECT * FROM dnd_reward_rules WHERE guild_id=?", (int(guild_id),)).fetchall()
        return [dict(r) for r in rows]


def evaluate_rewards(db_path: str, guild_id: int, user_id: int) -> list[dict]:
    guild_id = int(guild_id)
    user_id = int(user_id)
    rules = list_reward_rules(db_path, guild_id)
    results: list[dict] = []
    for rule in rules:
        if not rule.get("enabled", 1):
            continue
        threshold = max(1, rule.get("period_count", 7))
        with _get_conn(db_path) as conn:
            tier_row = conn.execute(
                "SELECT threshold, reward FROM dnd_reward_tiers WHERE rule_id=? ORDER BY idx ASC LIMIT 1", (rule["id"],)
            ).fetchone()
            if not tier_row:
                continue
            current_count = conn.execute(
                "SELECT COUNT(*) AS count FROM dnd_xp_entries WHERE guild_id=? AND user_id=? AND created_at>=date('now', ? || ' days')",
                (guild_id, user_id, f"-{threshold}"),
            ).fetchone()
            count = int(current_count["count"]) if current_count else 0
        reward_threshold = int(tier_row["threshold"])
        results.append(
            {
                "id": rule["id"],
                "name": rule["name"],
                "threshold": reward_threshold,
                "reward": float(tier_row["reward"]),
                "current_count": count,
            }
        )
    return results
