from __future__ import annotations

import sqlite3

_INIT_SCHEMA = """
CREATE TABLE IF NOT EXISTS dnd_chronicles (
    guild_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL DEFAULT 'Chronicle',
    tracker_channel_id INTEGER,
    xp_tracking_enabled INTEGER NOT NULL DEFAULT 0,
    auto_reward_enabled INTEGER NOT NULL DEFAULT 0,
    monitored_channel_ids TEXT NOT NULL DEFAULT '[]',
    excluded_channel_ids TEXT NOT NULL DEFAULT '[]',
    discord_roles TEXT NOT NULL DEFAULT '[]',
    allowed_splats TEXT NOT NULL DEFAULT '["vampire20th"]',
    xp_feed_channel_id INTEGER,
    xp_reward_feed_channel_id INTEGER,
    owner_id INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT '1970-01-01T00:00:00',
    updated_at TEXT NOT NULL DEFAULT '1970-01-01T00:00:00'
);

CREATE TABLE IF NOT EXISTS dnd_chronicle_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    storyteller INTEGER NOT NULL DEFAULT 0,
    admin INTEGER NOT NULL DEFAULT 0,
    nickname TEXT NOT NULL DEFAULT '',
    avatar_url TEXT NOT NULL DEFAULT '',
    default_character TEXT NOT NULL DEFAULT '',
    UNIQUE(guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS dnd_proxies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    owner_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    template TEXT NOT NULL DEFAULT '',
    thumbnail_url TEXT NOT NULL DEFAULT '',
    avatar_url TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT '1970-01-01T00:00:00',
    updated_at TEXT NOT NULL DEFAULT '1970-01-01T00:00:00',
    UNIQUE(guild_id, owner_id, name)
);

CREATE TABLE IF NOT EXISTS dnd_proxied_messages (
    message_id TEXT PRIMARY KEY,
    proxy_id INTEGER NOT NULL,
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    owner_id INTEGER NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT '1970-01-01T00:00:00'
);

CREATE TABLE IF NOT EXISTS dnd_xp_pools (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    pool REAL NOT NULL DEFAULT 0,
    PRIMARY KEY(guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS dnd_xp_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    amount REAL NOT NULL DEFAULT 0,
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT '1970-01-01T00:00:00'
);

CREATE TABLE IF NOT EXISTS dnd_reward_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    name TEXT NOT NULL DEFAULT 'Reward Rule',
    enabled INTEGER NOT NULL DEFAULT 1,
    period_count INTEGER NOT NULL DEFAULT 7,
    period_unit TEXT NOT NULL DEFAULT 'week',
    period_anchor_day INTEGER NOT NULL DEFAULT 0,
    period_anchor_hour INTEGER NOT NULL DEFAULT 0,
    excluded_role_ids TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT '1970-01-01T00:00:00',
    updated_at TEXT NOT NULL DEFAULT '1970-01-01T00:00:00'
);

CREATE TABLE IF NOT EXISTS dnd_reward_tiers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id INTEGER NOT NULL,
    idx INTEGER NOT NULL DEFAULT 0,
    threshold INTEGER NOT NULL DEFAULT 1,
    reward REAL NOT NULL DEFAULT 1,
    UNIQUE(rule_id, idx)
);

CREATE TABLE IF NOT EXISTS dnd_reward_awards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    tier_index INTEGER NOT NULL DEFAULT 0,
    period_ordinal INTEGER NOT NULL DEFAULT 0,
    awarded_at TEXT NOT NULL DEFAULT '1970-01-01T00:00:00',
    triggering_message_id TEXT,
    UNIQUE(rule_id, user_id, tier_index, period_ordinal)
);
"""


def _get_conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.row_factory = sqlite3.Row
    conn.executescript(_INIT_SCHEMA)
    return conn


def ensure_schema(db_path: str) -> None:
    with _get_conn(db_path) as conn:
        conn.commit()
