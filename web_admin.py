import io
import json
import logging
import os
import secrets
import sqlite3
import threading
import time
import zipfile
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from flask import Flask, flash, redirect, render_template_string, request, send_file, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from web_admin_constants import (
    AUTH_MODE_REMEMBER,
    AUTH_MODE_STANDARD,
    AUTO_REFRESH_INTERVAL_OPTIONS,
    FEED_INTERVAL_OPTIONS,
    LOG_EMAIL_PATTERN,
    LOG_FILE_OPTIONS,
    LOG_SECRET_PATTERN,
    PASSWORD_MIN_LENGTH,
    PASSWORD_ROTATION_DAYS,
    REMEMBER_LOGIN_DAYS,
    SENSITIVE_ENV_KEYS,
    SETTINGS_DROPDOWN_OPTIONS,
    SETTINGS_FIELD_ORDER,
    SQLITE_TIMEOUT_SECONDS,
    UPTIME_MONITOR_INTERVAL_OPTIONS,
    UPTIME_MONITOR_TIMEOUT_OPTIONS,
)


def _is_sensitive_key(key: str) -> bool:
    if key in SENSITIVE_ENV_KEYS:
        return True
    upper_key = key.upper()
    return "TOKEN" in upper_key or "PASSWORD" in upper_key or "SECRET" in upper_key


def _normalize_feed_interval(raw_value: str | int | None, default: int = 300) -> int:
    allowed = {value for value, _label in FEED_INTERVAL_OPTIONS}
    if isinstance(raw_value, int):
        return raw_value if raw_value in allowed else default
    candidate = str(raw_value or "").strip()
    if candidate.isdigit():
        parsed = int(candidate)
        if parsed in allowed:
            return parsed
    return default


def _feed_interval_label(seconds: int | str | None) -> str:
    normalized = _normalize_feed_interval(seconds)
    for value, label in FEED_INTERVAL_OPTIONS:
        if value == normalized:
            return label
    return "5 minutes"


def _normalize_monitor_interval(raw_value: str | int | None, default: int = 60) -> int:
    allowed = {value for value, _label in UPTIME_MONITOR_INTERVAL_OPTIONS}
    if isinstance(raw_value, int):
        return raw_value if raw_value in allowed else default
    candidate = str(raw_value or "").strip()
    if candidate.isdigit():
        parsed = int(candidate)
        if parsed in allowed:
            return parsed
    return default


def _monitor_interval_label(seconds: int | str | None) -> str:
    normalized = _normalize_monitor_interval(seconds)
    for value, label in UPTIME_MONITOR_INTERVAL_OPTIONS:
        if value == normalized:
            return label
    return "1 minute"


def _normalize_monitor_timeout(raw_value: str | int | None, default: int = 8) -> int:
    allowed = set(UPTIME_MONITOR_TIMEOUT_OPTIONS)
    if isinstance(raw_value, int):
        return raw_value if raw_value in allowed else default
    candidate = str(raw_value or "").strip()
    if candidate.isdigit():
        parsed = int(candidate)
        if parsed in allowed:
            return parsed
    return default


def _normalize_reddit_source(raw_value: str) -> tuple[str, str]:
    candidate = str(raw_value or "").strip()
    if not candidate:
        raise ValueError("Reddit forum is required.")
    if candidate.startswith("r/"):
        candidate = candidate[2:]
    if "://" in candidate:
        parsed = urlparse(candidate)
        host = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        if host != "reddit.com":
            raise ValueError("Reddit URL must be on reddit.com.")
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) < 2 or parts[0].lower() != "r":
            raise ValueError("Reddit URL must point to a subreddit like /r/example.")
        candidate = parts[1]
    normalized = candidate.strip().lower()
    if not normalized or not normalized.replace("_", "").isalnum():
        raise ValueError("Reddit forum must be a valid subreddit name.")
    return normalized, f"https://www.reddit.com/r/{normalized}"


def _normalize_wordpress_source(raw_value: str) -> str:
    candidate = str(raw_value or "").strip()
    if not candidate:
        raise ValueError("WordPress site URL is required.")
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("WordPress site URL must be a valid http(s) URL.")
    path = parsed.path.rstrip("/")
    normalized = urlunparse((parsed.scheme, parsed.netloc, path or "/", "", "", ""))
    return normalized.rstrip("/") if normalized != f"{parsed.scheme}://{parsed.netloc}/" else normalized


def _normalize_monitor_target(raw_value: str, monitor_type: str) -> str:
    candidate = str(raw_value or "").strip()
    if not candidate:
        raise ValueError("Monitor target is required.")
    if monitor_type == "http":
        if "://" not in candidate:
            candidate = f"https://{candidate}"
        parsed = urlparse(candidate)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("HTTP monitor target must be a valid http(s) URL.")
        return urlunparse(parsed)
    if monitor_type == "statuspage":
        if "://" not in candidate:
            candidate = f"https://{candidate}"
        parsed = urlparse(candidate)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Status page URL must be a valid http(s) URL.")
        path = parsed.path.rstrip("/")
        if not path.endswith("/api/v2/status.json"):
            path = f"{path}/api/v2/status.json" if path else "/api/v2/status.json"
        return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))
    if monitor_type == "tcp":
        if candidate.startswith("tcp://"):
            candidate = candidate[6:]
        if "/" in candidate:
            candidate = candidate.split("/", 1)[0]
        if ":" not in candidate:
            raise ValueError("TCP targets must be in host:port format.")
        host, port_text = candidate.rsplit(":", 1)
        if not host.strip():
            raise ValueError("TCP target must include a host.")
        if not port_text.strip().isdigit():
            raise ValueError("TCP target port must be numeric.")
        port = int(port_text.strip())
        if port <= 0 or port > 65535:
            raise ValueError("TCP target port must be between 1 and 65535.")
        return f"{host.strip()}:{port}"
    raise ValueError("Monitor type must be http, tcp, or statuspage.")


def _normalize_linkedin_source(raw_value: str) -> str:
    candidate = str(raw_value or "").strip()
    if not candidate:
        raise ValueError("LinkedIn profile URL is required.")
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("LinkedIn profile URL must be a valid http(s) URL.")
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if host != "linkedin.com":
        raise ValueError("LinkedIn URL must be on linkedin.com.")
    path = parsed.path.rstrip("/")
    valid_prefixes = ("/in/", "/company/", "/school/", "/showcase/")
    if not any(path.startswith(prefix) for prefix in valid_prefixes):
        raise ValueError("LinkedIn URL must point to a public profile or company page.")
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def _apply_best_effort_permissions(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError:
        return


def _ensure_private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _apply_best_effort_permissions(path, 0o700)


def _secure_sqlite_sidecars(path: Path) -> None:
    for suffix in ("", "-wal", "-shm"):
        target = path if not suffix else path.with_name(f"{path.name}{suffix}")
        if target.exists():
            _apply_best_effort_permissions(target, 0o600)


def _sqlite_connect(db_path: str) -> sqlite3.Connection:
    db_file = Path(db_path).expanduser()
    parent = db_file.parent
    if str(parent) not in {"", "."}:
        _ensure_private_directory(parent)
    conn = sqlite3.connect(str(db_file), timeout=SQLITE_TIMEOUT_SECONDS)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {SQLITE_TIMEOUT_SECONDS * 1000}")
    _secure_sqlite_sidecars(db_file)
    return conn


def _parse_stored_datetime(raw_value: object) -> datetime | None:
    raw_text = str(raw_value or "").strip()
    if not raw_text:
        return None
    for candidate in (raw_text, raw_text.replace("Z", "+00:00")):
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        except ValueError:
            continue
    for fmt in ("%Y-%m-%d %H:%M:%S",):
        try:
            return datetime.strptime(raw_text, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _password_policy_error(password: str) -> str | None:
    if len(password) < PASSWORD_MIN_LENGTH:
        return f"Password must be at least {PASSWORD_MIN_LENGTH} characters."
    digit_count = sum(char.isdigit() for char in password)
    symbol_count = sum(not char.isalnum() for char in password)
    if digit_count < 2:
        return "Password must include at least 2 numbers."
    if symbol_count < 1:
        return "Password must include at least 1 symbol."
    return None


def _password_hash_needs_upgrade(password_hash: str) -> bool:
    return not str(password_hash or "").startswith("scrypt:")


def _ensure_actions_table(db_path: str) -> None:
    directory = os.path.dirname(db_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with _sqlite_connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                action TEXT NOT NULL,
                status TEXT NOT NULL,
                moderator TEXT,
                target TEXT,
                reason TEXT,
                guild TEXT
            )
            """
        )
        conn.commit()


def _ensure_youtube_subscriptions_table(db_path: str) -> None:
    directory = os.path.dirname(db_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with _sqlite_connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS youtube_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                source_url TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                channel_title TEXT NOT NULL,
                target_channel_id INTEGER NOT NULL,
                target_channel_name TEXT NOT NULL,
                poll_interval_seconds INTEGER NOT NULL DEFAULT 300,
                include_uploads INTEGER NOT NULL DEFAULT 1,
                include_community_posts INTEGER NOT NULL DEFAULT 0,
                last_video_id TEXT,
                last_video_title TEXT,
                last_published_at TEXT,
                last_community_post_id TEXT,
                last_community_post_title TEXT,
                last_community_published_at TEXT,
                last_checked_at TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                UNIQUE(channel_id, target_channel_id)
            )
            """
        )
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(youtube_subscriptions)").fetchall()}
        migrations = {
            "poll_interval_seconds": "ALTER TABLE youtube_subscriptions ADD COLUMN poll_interval_seconds INTEGER NOT NULL DEFAULT 300",
            "include_uploads": "ALTER TABLE youtube_subscriptions ADD COLUMN include_uploads INTEGER NOT NULL DEFAULT 1",
            "include_community_posts": "ALTER TABLE youtube_subscriptions ADD COLUMN include_community_posts INTEGER NOT NULL DEFAULT 0",
            "last_community_post_id": "ALTER TABLE youtube_subscriptions ADD COLUMN last_community_post_id TEXT",
            "last_community_post_title": "ALTER TABLE youtube_subscriptions ADD COLUMN last_community_post_title TEXT",
            "last_community_published_at": "ALTER TABLE youtube_subscriptions ADD COLUMN last_community_published_at TEXT",
            "last_checked_at": "ALTER TABLE youtube_subscriptions ADD COLUMN last_checked_at TEXT",
        }
        for column, statement in migrations.items():
            if column not in columns:
                conn.execute(statement)
        conn.execute(
            "UPDATE youtube_subscriptions SET poll_interval_seconds = 300 WHERE poll_interval_seconds IS NULL OR poll_interval_seconds <= 0"
        )
        conn.commit()


def _ensure_reddit_feeds_table(db_path: str) -> None:
    directory = os.path.dirname(db_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with _sqlite_connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reddit_feeds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                subreddit_name TEXT NOT NULL,
                source_url TEXT NOT NULL,
                target_channel_id INTEGER NOT NULL,
                target_channel_name TEXT NOT NULL,
                poll_interval_seconds INTEGER NOT NULL DEFAULT 300,
                last_post_id TEXT,
                last_post_title TEXT,
                last_post_url TEXT,
                last_published_at TEXT,
                last_checked_at TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                UNIQUE(subreddit_name, target_channel_id)
            )
            """
        )
        conn.commit()


def _ensure_wordpress_feeds_table(db_path: str) -> None:
    directory = os.path.dirname(db_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with _sqlite_connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS wordpress_feeds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                site_url TEXT NOT NULL,
                feed_url TEXT NOT NULL,
                site_title TEXT NOT NULL,
                target_channel_id INTEGER NOT NULL,
                target_channel_name TEXT NOT NULL,
                poll_interval_seconds INTEGER NOT NULL DEFAULT 300,
                last_post_id TEXT,
                last_post_title TEXT,
                last_post_url TEXT,
                last_published_at TEXT,
                last_checked_at TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                UNIQUE(feed_url, target_channel_id)
            )
            """
        )
        conn.commit()


def _ensure_linkedin_feeds_table(db_path: str) -> None:
    directory = os.path.dirname(db_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with _sqlite_connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS linkedin_feeds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                profile_url TEXT NOT NULL,
                activity_url TEXT NOT NULL,
                profile_label TEXT NOT NULL,
                target_channel_id INTEGER NOT NULL,
                target_channel_name TEXT NOT NULL,
                poll_interval_seconds INTEGER NOT NULL DEFAULT 300,
                last_post_id TEXT,
                last_post_title TEXT,
                last_post_url TEXT,
                last_published_at TEXT,
                last_checked_at TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                UNIQUE(activity_url, target_channel_id)
            )
            """
        )
        conn.commit()


def _ensure_uptime_monitors_table(db_path: str) -> None:
    directory = os.path.dirname(db_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with _sqlite_connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS uptime_monitors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                monitor_type TEXT NOT NULL,
                target TEXT NOT NULL,
                interval_seconds INTEGER NOT NULL DEFAULT 60,
                timeout_seconds INTEGER NOT NULL DEFAULT 8,
                enabled INTEGER NOT NULL DEFAULT 1,
                alert_channel_id INTEGER,
                last_status TEXT,
                last_checked_at TEXT,
                last_change_at TEXT,
                last_error TEXT,
                last_latency_ms INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_uptime_monitors_guild ON uptime_monitors(guild_id)")
        conn.commit()


def _ensure_spicy_prompt_tables(db_path: str) -> None:
    directory = os.path.dirname(db_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with _sqlite_connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS spicy_prompt_packs (
                pack_id TEXT PRIMARY KEY,
                pack_name TEXT NOT NULL,
                source_path TEXT NOT NULL,
                prompt_count INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS spicy_prompt_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pack_id TEXT NOT NULL,
                prompt_id TEXT NOT NULL,
                prompt_type TEXT NOT NULL,
                category TEXT NOT NULL,
                rating TEXT NOT NULL,
                text TEXT NOT NULL,
                tags_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(pack_id, prompt_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS spicy_prompt_sync_state (
                state_id INTEGER PRIMARY KEY CHECK (state_id = 1),
                repo_url TEXT NOT NULL,
                repo_branch TEXT NOT NULL,
                manifest_path TEXT NOT NULL,
                manifest_url TEXT NOT NULL,
                last_refresh_at TEXT,
                last_success_at TEXT,
                last_error TEXT,
                pack_count INTEGER NOT NULL DEFAULT 0,
                prompt_count INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.commit()


def _fetch_actions(db_path: str, limit: int = 200, guild_id: int | None = None) -> list[dict]:
    _ensure_actions_table(db_path)
    query = """
        SELECT created_at, action, status, moderator, target, reason, guild
        FROM actions
    """
    params: list[object] = []
    if guild_id is not None:
        query += " WHERE guild = ?"
        params.append(str(guild_id))
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    with _sqlite_connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, tuple(params)).fetchall()
    return [dict(row) for row in rows]


def _fetch_youtube_subscriptions(db_path: str, limit: int = 300, channel_ids: list[int] | None = None) -> list[dict]:
    _ensure_youtube_subscriptions_table(db_path)
    query = """
        SELECT id, created_at, source_url, channel_id, channel_title, target_channel_id,
               target_channel_name, poll_interval_seconds, include_uploads, include_community_posts,
               last_video_id, last_video_title, last_published_at, last_community_post_id,
               last_community_post_title, last_community_published_at, last_checked_at, enabled
        FROM youtube_subscriptions
    """
    params: list[object] = []
    if channel_ids is not None:
        if not channel_ids:
            return []
        placeholders = ",".join(["?"] * len(channel_ids))
        query += f" WHERE target_channel_id IN ({placeholders})"
        params.extend(channel_ids)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    with _sqlite_connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, tuple(params)).fetchall()
    return [dict(row) for row in rows]


def _fetch_reddit_feeds(db_path: str, limit: int = 300, channel_ids: list[int] | None = None) -> list[dict]:
    _ensure_reddit_feeds_table(db_path)
    query = """
        SELECT id, created_at, subreddit_name, source_url, target_channel_id, target_channel_name,
               poll_interval_seconds, last_post_id, last_post_title, last_post_url, last_published_at,
               last_checked_at, enabled
        FROM reddit_feeds
    """
    params: list[object] = []
    if channel_ids is not None:
        if not channel_ids:
            return []
        placeholders = ",".join(["?"] * len(channel_ids))
        query += f" WHERE target_channel_id IN ({placeholders})"
        params.extend(channel_ids)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    with _sqlite_connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, tuple(params)).fetchall()
    return [dict(row) for row in rows]


def _fetch_wordpress_feeds(db_path: str, limit: int = 300, channel_ids: list[int] | None = None) -> list[dict]:
    _ensure_wordpress_feeds_table(db_path)
    query = """
        SELECT id, created_at, site_url, feed_url, site_title, target_channel_id, target_channel_name,
               poll_interval_seconds, last_post_id, last_post_title, last_post_url, last_published_at,
               last_checked_at, enabled
        FROM wordpress_feeds
    """
    params: list[object] = []
    if channel_ids is not None:
        if not channel_ids:
            return []
        placeholders = ",".join(["?"] * len(channel_ids))
        query += f" WHERE target_channel_id IN ({placeholders})"
        params.extend(channel_ids)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    with _sqlite_connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, tuple(params)).fetchall()
    return [dict(row) for row in rows]


def _fetch_linkedin_feeds(db_path: str, limit: int = 300, channel_ids: list[int] | None = None) -> list[dict]:
    _ensure_linkedin_feeds_table(db_path)
    query = """
        SELECT id, created_at, profile_url, activity_url, profile_label, target_channel_id, target_channel_name,
               poll_interval_seconds, last_post_id, last_post_title, last_post_url, last_published_at,
               last_checked_at, enabled
        FROM linkedin_feeds
    """
    params: list[object] = []
    if channel_ids is not None:
        if not channel_ids:
            return []
        placeholders = ",".join(["?"] * len(channel_ids))
        query += f" WHERE target_channel_id IN ({placeholders})"
        params.extend(channel_ids)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    with _sqlite_connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, tuple(params)).fetchall()
    return [dict(row) for row in rows]


def _fetch_uptime_monitors(db_path: str, guild_id: int, limit: int = 300) -> list[dict]:
    _ensure_uptime_monitors_table(db_path)
    query = """
        SELECT id, guild_id, name, monitor_type, target, interval_seconds, timeout_seconds, enabled,
               alert_channel_id, last_status, last_checked_at, last_change_at, last_error, last_latency_ms,
               created_at, updated_at
        FROM uptime_monitors
        WHERE guild_id = ?
        ORDER BY id DESC
        LIMIT ?
    """
    with _sqlite_connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, (int(guild_id), int(limit))).fetchall()
    return [dict(row) for row in rows]


def _insert_uptime_monitor(
    db_path: str,
    *,
    guild_id: int,
    name: str,
    monitor_type: str,
    target: str,
    interval_seconds: int,
    timeout_seconds: int,
    alert_channel_id: int | None,
) -> None:
    _ensure_uptime_monitors_table(db_path)
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    with _sqlite_connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO uptime_monitors (
                guild_id, name, monitor_type, target, interval_seconds, timeout_seconds,
                alert_channel_id, enabled, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                int(guild_id),
                name,
                monitor_type,
                target,
                int(interval_seconds),
                int(timeout_seconds),
                alert_channel_id,
                now,
                now,
            ),
        )
        conn.commit()


def _set_uptime_monitor_enabled(db_path: str, monitor_id: int, enabled: bool) -> bool:
    _ensure_uptime_monitors_table(db_path)
    with _sqlite_connect(db_path) as conn:
        cursor = conn.execute(
            "UPDATE uptime_monitors SET enabled = ?, updated_at = ? WHERE id = ?",
            (1 if enabled else 0, datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"), int(monitor_id)),
        )
        conn.commit()
    return cursor.rowcount > 0


def _delete_uptime_monitor(db_path: str, monitor_id: int) -> bool:
    _ensure_uptime_monitors_table(db_path)
    with _sqlite_connect(db_path) as conn:
        cursor = conn.execute("DELETE FROM uptime_monitors WHERE id = ?", (int(monitor_id),))
        conn.commit()
    return cursor.rowcount > 0


def _fetch_spicy_prompt_status(db_path: str) -> dict:
    _ensure_spicy_prompt_tables(db_path)
    with _sqlite_connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        state_row = conn.execute(
            """
            SELECT repo_url, repo_branch, manifest_path, manifest_url, last_refresh_at, last_success_at,
                   last_error, pack_count, prompt_count
            FROM spicy_prompt_sync_state
            WHERE state_id = 1
            """
        ).fetchone()
        pack_rows = conn.execute(
            """
            SELECT pack_id, pack_name, source_path, prompt_count, updated_at
            FROM spicy_prompt_packs
            ORDER BY pack_name ASC, pack_id ASC
            LIMIT 100
            """
        ).fetchall()
        preview_rows = conn.execute(
            """
            SELECT pack_id, prompt_id, prompt_type, category, rating, text, tags_json
            FROM spicy_prompt_entries
            ORDER BY pack_id ASC, prompt_id ASC
            LIMIT 25
            """
        ).fetchall()
    state = dict(state_row) if state_row else {}
    preview: list[dict] = []
    for row in preview_rows:
        item = dict(row)
        try:
            tags = json.loads(str(item.get("tags_json", "[]")))
        except json.JSONDecodeError:
            tags = []
        item["tags"] = [str(tag).strip() for tag in tags if str(tag).strip()]
        preview.append(item)
    return {
        "repo_url": state.get("repo_url", os.getenv("SPICY_PROMPTS_REPO_URL", "")),
        "repo_branch": state.get("repo_branch", os.getenv("SPICY_PROMPTS_REPO_BRANCH", "main")),
        "manifest_path": state.get("manifest_path", os.getenv("SPICY_PROMPTS_MANIFEST_PATH", "manifests/index.json")),
        "manifest_url": state.get("manifest_url", ""),
        "last_refresh_at": state.get("last_refresh_at", ""),
        "last_success_at": state.get("last_success_at", ""),
        "last_error": state.get("last_error", ""),
        "pack_count": int(state.get("pack_count", len(pack_rows)) or 0),
        "prompt_count": int(state.get("prompt_count", len(preview)) or 0),
        "enabled": _env_bool("SPICY_PROMPTS_ENABLED", False),
        "packs": [dict(row) for row in pack_rows],
        "preview": preview,
    }


def _upsert_youtube_subscription(
    db_path: str,
    *,
    source_url: str,
    channel_id: str,
    channel_title: str,
    target_channel_id: int,
    target_channel_name: str,
    poll_interval_seconds: int,
    include_uploads: bool,
    include_community_posts: bool,
    last_video_id: str,
    last_video_title: str,
    last_published_at: str,
    last_community_post_id: str = "",
    last_community_post_title: str = "",
    last_community_published_at: str = "",
) -> None:
    _ensure_youtube_subscriptions_table(db_path)
    with _sqlite_connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO youtube_subscriptions (
                created_at, source_url, channel_id, channel_title, target_channel_id,
                target_channel_name, poll_interval_seconds, include_uploads, include_community_posts,
                last_video_id, last_video_title, last_published_at, last_community_post_id,
                last_community_post_title, last_community_published_at, enabled
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(channel_id, target_channel_id) DO UPDATE SET
                source_url=excluded.source_url,
                channel_title=excluded.channel_title,
                target_channel_name=excluded.target_channel_name,
                poll_interval_seconds=excluded.poll_interval_seconds,
                include_uploads=excluded.include_uploads,
                include_community_posts=excluded.include_community_posts,
                last_video_id=excluded.last_video_id,
                last_video_title=excluded.last_video_title,
                last_published_at=excluded.last_published_at,
                last_community_post_id=excluded.last_community_post_id,
                last_community_post_title=excluded.last_community_post_title,
                last_community_published_at=excluded.last_community_published_at,
                enabled=1
            """,
            (
                datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
                source_url,
                channel_id,
                channel_title,
                target_channel_id,
                target_channel_name,
                _normalize_feed_interval(poll_interval_seconds),
                int(include_uploads),
                int(include_community_posts),
                last_video_id,
                last_video_title,
                last_published_at,
                last_community_post_id,
                last_community_post_title,
                last_community_published_at,
            ),
        )
        conn.commit()


def _upsert_reddit_feed(
    db_path: str,
    *,
    subreddit_name: str,
    source_url: str,
    target_channel_id: int,
    target_channel_name: str,
    poll_interval_seconds: int,
    last_post_id: str = "",
    last_post_title: str = "",
    last_post_url: str = "",
    last_published_at: str = "",
) -> None:
    _ensure_reddit_feeds_table(db_path)
    with _sqlite_connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO reddit_feeds (
                created_at, subreddit_name, source_url, target_channel_id, target_channel_name,
                poll_interval_seconds, last_post_id, last_post_title, last_post_url, last_published_at, enabled
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(subreddit_name, target_channel_id) DO UPDATE SET
                source_url=excluded.source_url,
                target_channel_name=excluded.target_channel_name,
                poll_interval_seconds=excluded.poll_interval_seconds,
                last_post_id=excluded.last_post_id,
                last_post_title=excluded.last_post_title,
                last_post_url=excluded.last_post_url,
                last_published_at=excluded.last_published_at,
                enabled=1
            """,
            (
                datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
                subreddit_name,
                source_url,
                target_channel_id,
                target_channel_name,
                _normalize_feed_interval(poll_interval_seconds),
                last_post_id,
                last_post_title,
                last_post_url,
                last_published_at,
            ),
        )
        conn.commit()


def _upsert_wordpress_feed(
    db_path: str,
    *,
    site_url: str,
    feed_url: str,
    site_title: str,
    target_channel_id: int,
    target_channel_name: str,
    poll_interval_seconds: int,
    last_post_id: str = "",
    last_post_title: str = "",
    last_post_url: str = "",
    last_published_at: str = "",
) -> None:
    _ensure_wordpress_feeds_table(db_path)
    with _sqlite_connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO wordpress_feeds (
                created_at, site_url, feed_url, site_title, target_channel_id, target_channel_name,
                poll_interval_seconds, last_post_id, last_post_title, last_post_url, last_published_at, enabled
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(feed_url, target_channel_id) DO UPDATE SET
                site_url=excluded.site_url,
                site_title=excluded.site_title,
                target_channel_name=excluded.target_channel_name,
                poll_interval_seconds=excluded.poll_interval_seconds,
                last_post_id=excluded.last_post_id,
                last_post_title=excluded.last_post_title,
                last_post_url=excluded.last_post_url,
                last_published_at=excluded.last_published_at,
                enabled=1
            """,
            (
                datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
                site_url,
                feed_url,
                site_title,
                target_channel_id,
                target_channel_name,
                _normalize_feed_interval(poll_interval_seconds),
                last_post_id,
                last_post_title,
                last_post_url,
                last_published_at,
            ),
        )
        conn.commit()


def _upsert_linkedin_feed(
    db_path: str,
    *,
    profile_url: str,
    activity_url: str,
    profile_label: str,
    target_channel_id: int,
    target_channel_name: str,
    poll_interval_seconds: int,
    last_post_id: str = "",
    last_post_title: str = "",
    last_post_url: str = "",
    last_published_at: str = "",
) -> None:
    _ensure_linkedin_feeds_table(db_path)
    with _sqlite_connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO linkedin_feeds (
                created_at, profile_url, activity_url, profile_label, target_channel_id, target_channel_name,
                poll_interval_seconds, last_post_id, last_post_title, last_post_url, last_published_at, enabled
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(activity_url, target_channel_id) DO UPDATE SET
                profile_url=excluded.profile_url,
                profile_label=excluded.profile_label,
                target_channel_name=excluded.target_channel_name,
                poll_interval_seconds=excluded.poll_interval_seconds,
                last_post_id=excluded.last_post_id,
                last_post_title=excluded.last_post_title,
                last_post_url=excluded.last_post_url,
                last_published_at=excluded.last_published_at,
                enabled=1
            """,
            (
                datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
                profile_url,
                activity_url,
                profile_label,
                target_channel_id,
                target_channel_name,
                _normalize_feed_interval(poll_interval_seconds),
                last_post_id,
                last_post_title,
                last_post_url,
                last_published_at,
            ),
        )
        conn.commit()


def _delete_youtube_subscription(db_path: str, subscription_id: int) -> bool:
    _ensure_youtube_subscriptions_table(db_path)
    with _sqlite_connect(db_path) as conn:
        cursor = conn.execute("DELETE FROM youtube_subscriptions WHERE id = ?", (subscription_id,))
        conn.commit()
    return cursor.rowcount > 0


def _delete_reddit_feed(db_path: str, feed_id: int) -> bool:
    _ensure_reddit_feeds_table(db_path)
    with _sqlite_connect(db_path) as conn:
        cursor = conn.execute("DELETE FROM reddit_feeds WHERE id = ?", (feed_id,))
        conn.commit()
    return cursor.rowcount > 0


def _delete_wordpress_feed(db_path: str, feed_id: int) -> bool:
    _ensure_wordpress_feeds_table(db_path)
    with _sqlite_connect(db_path) as conn:
        cursor = conn.execute("DELETE FROM wordpress_feeds WHERE id = ?", (feed_id,))
        conn.commit()
    return cursor.rowcount > 0


def _delete_linkedin_feed(db_path: str, feed_id: int) -> bool:
    _ensure_linkedin_feeds_table(db_path)
    with _sqlite_connect(db_path) as conn:
        cursor = conn.execute("DELETE FROM linkedin_feeds WHERE id = ?", (feed_id,))
        conn.commit()
    return cursor.rowcount > 0


def _fetch_counts(db_path: str, guild_id: int | None = None) -> dict:
    _ensure_actions_table(db_path)
    with _sqlite_connect(db_path) as conn:
        if guild_id is None:
            total = conn.execute("SELECT COUNT(*) FROM actions").fetchone()[0]
            success = conn.execute("SELECT COUNT(*) FROM actions WHERE status = ?", ("success",)).fetchone()[0]
            failed = conn.execute("SELECT COUNT(*) FROM actions WHERE status = ?", ("failed",)).fetchone()[0]
        else:
            guild_value = str(guild_id)
            total = conn.execute("SELECT COUNT(*) FROM actions WHERE guild = ?", (guild_value,)).fetchone()[0]
            success = conn.execute(
                "SELECT COUNT(*) FROM actions WHERE guild = ? AND status = ?",
                (guild_value, "success"),
            ).fetchone()[0]
            failed = conn.execute(
                "SELECT COUNT(*) FROM actions WHERE guild = ? AND status = ?",
                (guild_value, "failed"),
            ).fetchone()[0]
    return {
        "total": total,
        "success": success,
        "failed": failed,
    }


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _resolve_env_file_path() -> Path:
    configured = os.getenv("WEB_ENV_FILE", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.cwd() / "env.env"


def _read_env_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def _write_env_file(path: Path, updates: dict[str, str]) -> None:
    existing = _read_env_file(path)
    existing.update(updates)
    _ensure_private_directory(path.parent)
    lines = [f"{key}={existing[key]}" for key in SETTINGS_FIELD_ORDER if key in existing]
    extra_keys = sorted(key for key in existing if key not in SETTINGS_FIELD_ORDER)
    lines.extend(f"{key}={existing[key]}" for key in extra_keys)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _apply_best_effort_permissions(path, 0o600)


def _build_settings_fields(channel_options: list[dict] | None = None) -> list[dict]:
    env_file_values = _read_env_file(_resolve_env_file_path())
    ordered_keys = list(SETTINGS_FIELD_ORDER)
    for key in sorted(env_file_values):
        if key not in ordered_keys:
            ordered_keys.append(key)
    for key in sorted(os.environ):
        if key.startswith("WEB_") and key not in ordered_keys:
            ordered_keys.append(key)

    channel_option_items: list[dict] = []
    if channel_options:
        channel_option_items = [
            {"value": "", "label": "Unset (use per-guild default)"},
            *[
                {"value": str(item.get("id", "")).strip(), "label": str(item.get("label", "")).strip() or str(item.get("name", "")).strip()}
                for item in channel_options
                if str(item.get("id", "")).strip()
            ],
        ]

    fields: list[dict] = []
    for key in ordered_keys:
        raw = os.getenv(key)
        value = env_file_values.get(key, raw or "")
        is_sensitive = _is_sensitive_key(key)
        options = SETTINGS_DROPDOWN_OPTIONS.get(key, ())
        if key == "Bot_Log_Channel" and channel_option_items:
            options = channel_option_items
        fields.append(
            {
                "key": key,
                "value": value,
                "masked_value": "********" if is_sensitive and value else value,
                "is_sensitive": is_sensitive,
                "runtime_value": raw or "",
                "pending_restart": str(value or "") != str(raw or ""),
                "options": options,
            }
        )
    return fields


def _validate_settings_payload(
    payload: dict[str, str],
    allowed_keys: list[str],
    options_lookup: dict[str, object] | None = None,
) -> tuple[dict[str, str], list[str]]:
    validated: dict[str, str] = {}
    errors: list[str] = []
    for key in allowed_keys:
        raw_value = payload.get(key, "").strip()
        options = (options_lookup or {}).get(key, SETTINGS_DROPDOWN_OPTIONS.get(key))
        if options:
            if isinstance(options, list) and options and isinstance(options[0], dict):
                allowed = {str(item.get("value", "")).strip() for item in options}
            else:
                allowed = {str(item).strip() for item in options}
            if raw_value and raw_value not in allowed:
                errors.append(f"{key} has an invalid option.")
                continue
        if (
            key
            in {
                "GUILD_ID",
                "Bot_Log_Channel",
                "WEB_PORT",
                "WEB_TLS_PORT",
                "WEB_AVATAR_MAX_UPLOAD_BYTES",
                "MEMBER_ACTIVITY_BACKFILL_GUILD_ID",
                "MEMBER_ACTIVITY_BACKFILL_PROGRESS_LOG_INTERVAL",
            }
            and raw_value
        ):
            if not raw_value.isdigit():
                errors.append(f"{key} must be numeric.")
                continue
        if key == "WEB_ADMIN_DEFAULT_USERNAME" and raw_value and not _is_valid_email(raw_value):
            errors.append("WEB_ADMIN_DEFAULT_USERNAME must be a valid email address.")
            continue
        if key == "WEB_ADMIN_DEFAULT_PASSWORD" and raw_value:
            password_policy_error = _password_policy_error(raw_value)
            if password_policy_error:
                errors.append(f"WEB_ADMIN_DEFAULT_PASSWORD: {password_policy_error}")
                continue
        validated[key] = raw_value

    tls_enabled = validated.get("WEB_TLS_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}
    web_port = validated.get("WEB_PORT", "").strip()
    tls_port = validated.get("WEB_TLS_PORT", "").strip()
    tls_cert = validated.get("WEB_TLS_CERT_FILE", "").strip()
    tls_key = validated.get("WEB_TLS_KEY_FILE", "").strip()
    if tls_enabled and bool(tls_cert) != bool(tls_key):
        errors.append("WEB_TLS_CERT_FILE and WEB_TLS_KEY_FILE must both be set when WEB_TLS_ENABLED is true.")
    if tls_enabled and web_port and tls_port and web_port == tls_port:
        errors.append("WEB_TLS_PORT must be different from WEB_PORT when WEB_TLS_ENABLED is true.")
    if validated.get("WEB_SESSION_COOKIE_SAMESITE", "") == "None" and validated.get("WEB_SESSION_COOKIE_SECURE", "").lower() != "true":
        errors.append("WEB_SESSION_COOKIE_SECURE must be true when WEB_SESSION_COOKIE_SAMESITE is None.")
    return validated, errors


def _resolve_log_directory(db_path: str) -> Path:
    configured = os.getenv("LOG_DIR", "").strip()
    fallback = Path(db_path).resolve().parent
    preferred = Path(configured).expanduser() if configured else Path("/logs")
    candidates = [preferred]
    if fallback != preferred:
        candidates.append(fallback)

    for candidate in candidates:
        try:
            _ensure_private_directory(candidate)
            test_path = candidate / ".wickedyoda-log-write-test"
            with test_path.open("a", encoding="utf-8"):
                pass
            test_path.unlink(missing_ok=True)
            return candidate
        except OSError:
            continue
    return fallback


def _resolve_log_path(log_dir: Path, selected_log: str) -> Path | None:
    if selected_log == "bot.log":
        return (log_dir / "bot.log").resolve()
    if selected_log == "bot_log.log":
        return (log_dir / "bot_log.log").resolve()
    if selected_log == "container_errors.log":
        return (log_dir / "container_errors.log").resolve()
    if selected_log == "web_admin.log":
        return (log_dir / "web_admin.log").resolve()
    if selected_log == "web_audit.log":
        return (log_dir / "web_audit.log").resolve()
    if selected_log == "web_gui_audit.log":
        return (log_dir / "web_gui_audit.log").resolve()
    return None


def _sanitize_log_text(text: str) -> str:
    if not text:
        return text
    sanitized = LOG_EMAIL_PATTERN.sub("[redacted-email]", text)
    sanitized = LOG_SECRET_PATTERN.sub(lambda match: f"{match.group(1)}=<redacted>", sanitized)
    return sanitized


def _tail_file(safe_path: Path, line_limit: int = 400) -> str:
    if safe_path.suffix.lower() != ".log":
        return "Invalid log file selection."
    if not safe_path.exists() or not safe_path.is_file():
        return f"Log file not found: {safe_path.name}"
    with safe_path.open("r", encoding="utf-8", errors="replace") as handle:
        lines = handle.readlines()
    if not lines:
        return "(empty log file)"
    return _sanitize_log_text("".join(lines[-line_limit:]))


def _build_logs_export_payload(log_dir: Path, available_paths: list[Path]) -> tuple[bytes, list[str]]:
    manifest_lines = [
        f"generated_at_utc={datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')}",
        f"log_dir={log_dir}",
        "",
        "files:",
    ]
    archive = io.BytesIO()
    exported_names: list[str] = []
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in available_paths:
            try:
                stat = path.stat()
                exported_names.append(path.name)
                manifest_lines.append(f"- {path.name} ({stat.st_size} bytes)")
                zf.write(path, arcname=path.name)
            except OSError:
                continue
        manifest_text = "\n".join(manifest_lines).strip() + "\n"
        zf.writestr("manifest.txt", manifest_text)
    archive.seek(0)
    return archive.getvalue(), exported_names


def _list_wiki_files() -> list[str]:
    wiki_root = Path.cwd() / "wiki"
    if not wiki_root.exists():
        return []
    files = sorted(path.name for path in wiki_root.glob("*.md") if path.is_file())
    return files


def _wiki_root() -> Path:
    return Path.cwd() / "wiki"


def _is_within_wiki_dir(path: Path) -> bool:
    wiki_root = _wiki_root()
    try:
        path.resolve().relative_to(wiki_root.resolve())
        return True
    except (OSError, ValueError):
        return False


def _get_wiki_page_map() -> dict[str, Path]:
    page_map: dict[str, Path] = {}
    wiki_root = _wiki_root()
    if not wiki_root.exists():
        return page_map
    for path in wiki_root.glob("*.md"):
        if not path.is_file() or path.name.startswith("_"):
            continue
        if not _is_within_wiki_dir(path):
            continue
        page_map[path.stem.casefold()] = path.resolve()
    return page_map


def _read_wiki_file(filename: str) -> str:
    wiki_root = _wiki_root()
    candidate = (wiki_root / filename).resolve()
    try:
        candidate.relative_to(wiki_root.resolve())
    except ValueError:
        return "Invalid wiki file path."
    if not candidate.exists() or not candidate.is_file():
        return "Wiki file not found."
    return candidate.read_text(encoding="utf-8", errors="replace")


def _wiki_label_from_filename(filename: str) -> str:
    return Path(filename).stem.replace("-", " ")


def _ensure_users_table(db_path: str) -> None:
    directory = os.path.dirname(db_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with _sqlite_connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS web_users (
                email TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                display_name TEXT NOT NULL DEFAULT '',
                first_name TEXT NOT NULL DEFAULT '',
                last_name TEXT NOT NULL DEFAULT '',
                is_admin INTEGER NOT NULL DEFAULT 0,
                is_guild_admin INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                password_changed_at TEXT NOT NULL
            )
            """
        )
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(web_users)").fetchall()}
        if "display_name" not in columns:
            conn.execute("ALTER TABLE web_users ADD COLUMN display_name TEXT NOT NULL DEFAULT ''")
        if "first_name" not in columns:
            conn.execute("ALTER TABLE web_users ADD COLUMN first_name TEXT NOT NULL DEFAULT ''")
        if "last_name" not in columns:
            conn.execute("ALTER TABLE web_users ADD COLUMN last_name TEXT NOT NULL DEFAULT ''")
        if "password_changed_at" not in columns:
            conn.execute("ALTER TABLE web_users ADD COLUMN password_changed_at TEXT")
            conn.execute("UPDATE web_users SET password_changed_at = COALESCE(password_changed_at, created_at)")
        if "is_guild_admin" not in columns:
            conn.execute("ALTER TABLE web_users ADD COLUMN is_guild_admin INTEGER NOT NULL DEFAULT 0")
        conn.commit()


def _ensure_guild_access_tables(db_path: str) -> None:
    directory = os.path.dirname(db_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with _sqlite_connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS guild_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS guild_group_guilds (
                group_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                UNIQUE(group_id, guild_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS guild_group_users (
                group_id INTEGER NOT NULL,
                user_email TEXT NOT NULL,
                UNIQUE(group_id, user_email)
            )
            """
        )
        conn.commit()


def _list_guild_groups(db_path: str) -> list[dict]:
    _ensure_guild_access_tables(db_path)
    with _sqlite_connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT id, name, created_at FROM guild_groups ORDER BY name ASC").fetchall()
    return [dict(row) for row in rows]


def _create_guild_group(db_path: str, name: str) -> None:
    _ensure_guild_access_tables(db_path)
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    with _sqlite_connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO guild_groups (name, created_at, updated_at)
            VALUES (?, ?, ?)
            """,
            (name.strip(), now, now),
        )
        conn.commit()


def _delete_guild_group(db_path: str, group_id: int) -> None:
    _ensure_guild_access_tables(db_path)
    with _sqlite_connect(db_path) as conn:
        conn.execute("DELETE FROM guild_group_guilds WHERE group_id = ?", (int(group_id),))
        conn.execute("DELETE FROM guild_group_users WHERE group_id = ?", (int(group_id),))
        conn.execute("DELETE FROM guild_groups WHERE id = ?", (int(group_id),))
        conn.commit()


def _set_guild_group_guilds(db_path: str, group_id: int, guild_ids: list[int]) -> None:
    _ensure_guild_access_tables(db_path)
    with _sqlite_connect(db_path) as conn:
        conn.execute("DELETE FROM guild_group_guilds WHERE group_id = ?", (int(group_id),))
        for guild_id in sorted({int(value) for value in guild_ids if int(value) > 0}):
            conn.execute(
                "INSERT OR IGNORE INTO guild_group_guilds (group_id, guild_id) VALUES (?, ?)",
                (int(group_id), int(guild_id)),
            )
        conn.commit()


def _set_guild_group_users(db_path: str, group_id: int, user_emails: list[str]) -> None:
    _ensure_guild_access_tables(db_path)
    normalized = sorted({email.strip().lower() for email in user_emails if email.strip()})
    with _sqlite_connect(db_path) as conn:
        conn.execute("DELETE FROM guild_group_users WHERE group_id = ?", (int(group_id),))
        for email in normalized:
            conn.execute(
                "INSERT OR IGNORE INTO guild_group_users (group_id, user_email) VALUES (?, ?)",
                (int(group_id), email),
            )
        conn.commit()


def _list_group_guild_ids(db_path: str, group_id: int) -> list[int]:
    _ensure_guild_access_tables(db_path)
    with _sqlite_connect(db_path) as conn:
        rows = conn.execute(
            "SELECT guild_id FROM guild_group_guilds WHERE group_id = ? ORDER BY guild_id ASC",
            (int(group_id),),
        ).fetchall()
    return [int(row[0]) for row in rows]


def _list_group_user_emails(db_path: str, group_id: int) -> list[str]:
    _ensure_guild_access_tables(db_path)
    with _sqlite_connect(db_path) as conn:
        rows = conn.execute(
            "SELECT user_email FROM guild_group_users WHERE group_id = ? ORDER BY user_email ASC",
            (int(group_id),),
        ).fetchall()
    return [str(row[0]) for row in rows]


def _allowed_guild_ids_for_user(db_path: str, user: dict | None) -> set[int] | None:
    if not user:
        return None
    if bool(user.get("is_admin")):
        return None
    if not bool(user.get("is_guild_admin")):
        return None
    email = str(user.get("email", "")).strip().lower()
    if not email:
        return set()
    _ensure_guild_access_tables(db_path)
    with _sqlite_connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT guild_id
            FROM guild_group_guilds
            WHERE group_id IN (
                SELECT group_id FROM guild_group_users WHERE user_email = ?
            )
            """,
            (email,),
        ).fetchall()
    return {int(row[0]) for row in rows}


def _build_display_name(display_name: str | None, first_name: str | None, last_name: str | None) -> str:
    candidate = (display_name or "").strip()
    if candidate:
        return candidate
    return " ".join(part.strip() for part in (first_name or "", last_name or "") if part and part.strip()).strip()


def _upsert_user(
    db_path: str,
    email: str,
    password_hash: str,
    is_admin: bool,
    is_guild_admin: bool = False,
    display_name: str | None = None,
    first_name: str = "",
    last_name: str = "",
    *,
    password_changed_at: str | None = None,
) -> None:
    _ensure_users_table(db_path)
    normalized_first_name = first_name.strip()
    normalized_last_name = last_name.strip()
    normalized_display_name = _build_display_name(display_name, normalized_first_name, normalized_last_name)
    created_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    resolved_password_changed_at = password_changed_at or created_at
    with _sqlite_connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO web_users (
                email, password_hash, display_name, first_name, last_name, is_admin, is_guild_admin, created_at, password_changed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
                password_hash = excluded.password_hash,
                display_name = excluded.display_name,
                first_name = excluded.first_name,
                last_name = excluded.last_name,
                password_changed_at = CASE
                    WHEN ? IS NULL THEN web_users.password_changed_at
                    ELSE excluded.password_changed_at
                END,
                is_admin = excluded.is_admin,
                is_guild_admin = excluded.is_guild_admin
            """,
            (
                email.lower(),
                password_hash,
                normalized_display_name,
                normalized_first_name,
                normalized_last_name,
                int(is_admin),
                int(is_guild_admin),
                created_at,
                resolved_password_changed_at,
                password_changed_at,
            ),
        )
        conn.commit()


def _get_user(db_path: str, email: str) -> dict | None:
    _ensure_users_table(db_path)
    with _sqlite_connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT email, password_hash, display_name, first_name, last_name, is_admin, is_guild_admin, created_at, password_changed_at
            FROM web_users
            WHERE email = ?
            """,
            (email.lower(),),
        ).fetchone()
    return dict(row) if row else None


def _list_users(db_path: str) -> list[dict]:
    _ensure_users_table(db_path)
    with _sqlite_connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT email, display_name, first_name, last_name, is_admin, is_guild_admin, created_at
            FROM web_users
            ORDER BY email ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def _delete_user(db_path: str, email: str) -> bool:
    _ensure_users_table(db_path)
    with _sqlite_connect(db_path) as conn:
        cursor = conn.execute("DELETE FROM web_users WHERE email = ?", (email.lower(),))
        conn.commit()
    return cursor.rowcount > 0


def _update_user_record(
    db_path: str,
    current_email: str,
    *,
    new_email: str,
    display_name: str,
    first_name: str = "",
    last_name: str = "",
    is_admin: bool,
    is_guild_admin: bool,
    password_hash: str | None = None,
) -> tuple[bool, str]:
    _ensure_users_table(db_path)
    existing = _get_user(db_path, current_email)
    if not existing:
        return False, "User not found."
    target_email = new_email.strip().lower()
    if not _is_valid_email(target_email):
        return False, "Please provide a valid email address."
    if target_email != current_email.strip().lower():
        conflict = _get_user(db_path, target_email)
        if conflict is not None:
            return False, "That email address is already in use."
    resolved_password_hash = password_hash or str(existing.get("password_hash", "")).strip()
    if not resolved_password_hash:
        return False, "Password hash is missing."
    password_changed_at = (
        datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        if password_hash is not None
        else str(existing.get("password_changed_at") or existing.get("created_at") or "").strip()
    )
    with _sqlite_connect(db_path) as conn:
        conn.execute(
            """
            UPDATE web_users
            SET email = ?, password_hash = ?, display_name = ?, first_name = ?, last_name = ?, is_admin = ?, is_guild_admin = ?, password_changed_at = ?
            WHERE email = ?
            """,
            (
                target_email,
                resolved_password_hash,
                _build_display_name(display_name, first_name, last_name),
                first_name.strip(),
                last_name.strip(),
                int(is_admin),
                int(is_guild_admin),
                password_changed_at,
                current_email.strip().lower(),
            ),
        )
        conn.commit()
    return True, "User updated."


def _update_user_password_hash_only(db_path: str, email: str, password_hash: str) -> None:
    _ensure_users_table(db_path)
    with _sqlite_connect(db_path) as conn:
        conn.execute(
            "UPDATE web_users SET password_hash = ? WHERE email = ?",
            (password_hash, email.strip().lower()),
        )
        conn.commit()


def _password_rotation_required(user: dict) -> bool:
    changed_at = _parse_stored_datetime(user.get("password_changed_at"))
    if changed_at is None:
        changed_at = _parse_stored_datetime(user.get("created_at"))
    if changed_at is None:
        return False
    return datetime.now(UTC) >= (changed_at + timedelta(days=PASSWORD_ROTATION_DAYS))


def _is_valid_email(email: str) -> bool:
    candidate = email.strip().lower()
    if not candidate or "@" not in candidate or "." not in candidate.rsplit("@", 1)[-1]:
        return False
    if len(candidate) > 254 or any(char.isspace() for char in candidate):
        return False
    return True


def _safe_read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except (PermissionError, OSError):
        return ""


def _format_bytes(value: int | float | None) -> str:
    if not isinstance(value, (int, float)):
        return "n/a"
    size = float(max(0, value))
    units = ["B", "KB", "MB", "GB", "TB"]
    idx = 0
    while size >= 1024.0 and idx < (len(units) - 1):
        size /= 1024.0
        idx += 1
    if idx == 0:
        return f"{int(size)} {units[idx]}"
    return f"{size:.2f} {units[idx]}"


def _format_uptime(seconds: int | float) -> str:
    try:
        total = max(0, int(float(seconds)))
    except (TypeError, ValueError):
        return "n/a"
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    if days > 0:
        return f"{days}d {hours}h {minutes}m {secs}s"
    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    if minutes > 0:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def _read_rss_bytes() -> int | None:
    for line in _safe_read_text(Path("/proc/self/status")).splitlines():
        if not line.startswith("VmRSS:"):
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[1].isdigit():
            return int(parts[1]) * 1024
    return None


def _read_process_io_bytes() -> dict[str, int | None]:
    read_bytes: int | None = None
    write_bytes: int | None = None
    for line in _safe_read_text(Path("/proc/self/io")).splitlines():
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        value = raw_value.strip()
        if not value.isdigit():
            continue
        if key.strip() == "read_bytes":
            read_bytes = int(value)
        elif key.strip() == "write_bytes":
            write_bytes = int(value)
    return {"read_bytes": read_bytes, "write_bytes": write_bytes}


PAGE_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="csrf-token" content="{{ csrf_token }}">
  <title>{{ title }}</title>
  <link rel="icon" href="{{ url_for('static', filename='wicked-yoda-favicon.png') }}">
  <link rel="apple-touch-icon" sizes="180x180" href="{{ url_for('static', filename='wicked-yoda-avatar.png') }}">
  <meta property="og:image" content="{{ url_for('static', filename='wicked-yoda-avatar.png') }}">
  <meta name="twitter:image" content="{{ url_for('static', filename='wicked-yoda-avatar.png') }}">
  {% if page == "status_public" and status_refresh_seconds and status_refresh_seconds > 0 %}
  <meta http-equiv="refresh" content="{{ status_refresh_seconds }}">
  {% endif %}
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    * { box-sizing: border-box; }
    html { -webkit-text-size-adjust: 100%; }
    :root {
      --bg: #0a0a0a;
      --bg-grad-a: #101010;
      --bg-grad-b: #141923;
      --fg: #e7edf7;
      --muted: #94a3b8;
      --card: #12161d;
      --border: #243047;
      --header: #06070a;
      --link: #7cc4ff;
      --btn-bg: #2563eb;
      --btn-secondary: #374151;
      --btn-danger: #dc2626;
      --flash-err-bg: #3b1318;
      --flash-err-fg: #fecaca;
      --flash-ok-bg: #102c1c;
      --flash-ok-fg: #bbf7d0;
      --input-bg: #0f141d;
      --input-fg: #e7edf7;
    }
    body[data-theme="light"] {
      --bg: #eef3fb;
      --bg-grad-a: #eef3fb;
      --bg-grad-b: #f8fbff;
      --fg: #1e293b;
      --muted: #64748b;
      --card: #ffffff;
      --border: #d6dee9;
      --header: #ffffff;
      --link: #1d4ed8;
      --btn-bg: #2563eb;
      --btn-secondary: #475569;
      --btn-danger: #dc2626;
      --flash-err-bg: #fee2e2;
      --flash-err-fg: #991b1b;
      --flash-ok-bg: #dcfce7;
      --flash-ok-fg: #166534;
      --input-bg: #ffffff;
      --input-fg: #1e293b;
    }
    body[data-theme="forest"] {
      --bg: #0b1511;
      --bg-grad-a: #102018;
      --bg-grad-b: #183329;
      --fg: #ecfdf5;
      --muted: #9ec7b2;
      --card: #11211a;
      --border: #24503d;
      --header: #09110d;
      --link: #86efac;
      --btn-bg: #15803d;
      --btn-secondary: #365346;
      --btn-danger: #b91c1c;
      --flash-err-bg: #3f1717;
      --flash-err-fg: #fecaca;
      --flash-ok-bg: #103522;
      --flash-ok-fg: #bbf7d0;
      --input-bg: #0f1a15;
      --input-fg: #ecfdf5;
    }
    body[data-theme="ember"] {
      --bg: #1a1010;
      --bg-grad-a: #241414;
      --bg-grad-b: #48221a;
      --fg: #fff4ec;
      --muted: #e4b8a0;
      --card: #241616;
      --border: #5c342b;
      --header: #140b0b;
      --link: #fdba74;
      --btn-bg: #ea580c;
      --btn-secondary: #6b463f;
      --btn-danger: #dc2626;
      --flash-err-bg: #491b1b;
      --flash-err-fg: #fecaca;
      --flash-ok-bg: #3a2411;
      --flash-ok-fg: #fde68a;
      --input-bg: #1d1111;
      --input-fg: #fff4ec;
    }
    body[data-theme="ice"] {
      --bg: #eef6fb;
      --bg-grad-a: #eef6fb;
      --bg-grad-b: #dbeafe;
      --fg: #102132;
      --muted: #4b6b84;
      --card: #f9fcff;
      --border: #bfd5e8;
      --header: #e9f4fb;
      --link: #0369a1;
      --btn-bg: #0284c7;
      --btn-secondary: #5b7a90;
      --btn-danger: #dc2626;
      --flash-err-bg: #fee2e2;
      --flash-err-fg: #991b1b;
      --flash-ok-bg: #d1fae5;
      --flash-ok-fg: #065f46;
      --input-bg: #ffffff;
      --input-fg: #102132;
    }
    body {
      font-family: "Trebuchet MS", "Lucida Sans", "Segoe UI", sans-serif;
      margin: 0;
      color: var(--fg);
      background:
        radial-gradient(1100px 450px at 20% -20%, var(--bg-grad-b), transparent 55%),
        radial-gradient(900px 360px at 100% 0%, #10213d, transparent 50%),
        var(--bg);
      min-height: 100vh;
      overflow-x: hidden;
    }
    a { color: var(--link); }
    header {
      background: var(--header);
      border-bottom: 1px solid var(--border);
      color: var(--fg);
      padding: 12px 18px;
      display: flex;
      flex-direction: column;
      align-items: stretch;
      gap: 14px;
      position: sticky;
      top: 0;
      z-index: 10;
    }
    .header-toprow { display: flex; align-items: center; justify-content: space-between; gap: 14px; }
    .header-brand { min-width: 170px; }
    .header-brand strong { display: block; }
    .header-version {
      display: inline-block;
      margin-top: 4px;
      font-size: 0.82rem;
      color: var(--muted);
      letter-spacing: 0.02em;
    }
    .header-tools { display: flex; align-items: center; gap: 12px; margin-left: auto; }
    .header-right { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; justify-content: center; }
    .desktop-nav { display: flex; }
    .mobile-quickbar { display: none; }
    .nav-controls { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; justify-content: center; }
    .nav-controls a { text-decoration: none; }
    .current-user { color: var(--muted); font-size: 0.95rem; }
    .current-user-email { color: var(--muted); font-size: 0.85rem; }
    .header-chip {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      min-height: 36px;
      padding: 7px 12px;
      border: 1px solid var(--border);
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.03);
      color: var(--fg);
      font-size: 0.88rem;
      line-height: 1.2;
    }
    .header-chip strong {
      font-size: 0.78rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .wrap { max-width: 1200px; margin: 22px auto; padding: 0 16px; }
    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 18px;
      margin-bottom: 16px;
    }
    .card-soft {
      border: 1px solid var(--border);
      background: var(--card);
      border-radius: 14px;
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
    }
    .flash { padding: 10px 12px; border-radius: 8px; margin-bottom: 10px; border: 1px solid var(--border); }
    .flash.error { background: var(--flash-err-bg); color: var(--flash-err-fg); }
    .flash.success { background: var(--flash-ok-bg); color: var(--flash-ok-fg); }
    table { width: 100%; border-collapse: collapse; }
    th, td { border-bottom: 1px solid var(--border); padding: 10px; text-align: left; vertical-align: top; }
    input[type=text], input[type=email], input[type=password], textarea, select, .form-control, .form-select {
      width: 100%;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 8px;
      min-height: 44px;
      font-size: 16px;
      background: var(--input-bg);
      color: var(--input-fg);
    }
    textarea { min-height: 220px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
    .btn {
      background: var(--btn-bg);
      border: 0;
      color: #fff;
      padding: 9px 14px;
      border-radius: 8px;
      cursor: pointer;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 44px;
    }
    .btn.secondary { background: var(--btn-secondary); }
    .btn.danger { background: var(--btn-danger); }
    .btn-primary { background: var(--btn-bg); border-color: var(--btn-bg); }
    .btn-outline-secondary { border-color: var(--border); color: var(--fg); }
    .btn-outline-secondary:hover { background: var(--btn-secondary); border-color: var(--btn-secondary); color: #fff; }
    .inline-form { display: inline-flex; margin-left: 0; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    .muted { color: var(--muted); font-size: 0.9rem; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
    .theme-switch { display: inline-flex; border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }
    .theme-btn {
      border: 0;
      background: transparent;
      color: var(--fg);
      padding: 7px 11px;
      cursor: pointer;
      font-weight: 700;
      letter-spacing: 0.02em;
    }
    .theme-btn.active { background: var(--btn-bg); color: #fff; }
    .nav-select {
      width: 280px;
      max-width: 70vw;
      min-width: 190px;
      padding: 7px 9px;
    }
    .mobile-nav { display: none; position: relative; }
    .mobile-nav summary {
      list-style: none;
      cursor: pointer;
      user-select: none;
      min-height: 44px;
      padding: 10px 14px;
      border-radius: 10px;
      background: var(--btn-bg);
      color: #fff;
      font-weight: 700;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      border: 0;
    }
    .mobile-nav summary::-webkit-details-marker { display: none; }
    .mobile-nav-panel {
      margin-top: 10px;
      padding: 14px;
      border: 1px solid var(--border);
      border-radius: 12px;
      background: var(--card);
      box-shadow: 0 16px 40px rgba(0, 0, 0, 0.2);
      display: grid;
      gap: 12px;
    }
    .mobile-user-block {
      display: grid;
      gap: 4px;
      padding-bottom: 8px;
      border-bottom: 1px solid var(--border);
    }
    .mobile-link-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }
    .mobile-panel-section { display: grid; gap: 8px; }
    .mobile-panel-title {
      margin: 0;
      color: var(--muted);
      font-size: 0.76rem;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }
    .mobile-link-grid .btn,
    .mobile-nav-panel .btn,
    .mobile-nav-panel .inline-form,
    .mobile-nav-panel .inline-form .btn,
    .mobile-nav-panel .nav-select {
      width: 100%;
    }
    .sr-only {
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      margin: -1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
      border: 0;
    }
    .dash-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
    .dashboard-shell { display: grid; gap: 18px; }
    .dashboard-hero {
      display: grid;
      grid-template-columns: minmax(0, 1.7fr) minmax(280px, 1fr);
      gap: 16px;
      align-items: stretch;
    }
    .dashboard-hero-main,
    .dashboard-hero-side,
    .dashboard-section,
    .dash-card {
      position: relative;
      overflow: hidden;
    }
    .dashboard-hero-main::before,
    .dashboard-hero-side::before,
    .dash-card::before {
      content: "";
      position: absolute;
      inset: 0 auto auto 0;
      width: 100%;
      height: 3px;
      background: linear-gradient(90deg, var(--btn-bg), transparent 78%);
      opacity: 0.75;
      pointer-events: none;
    }
    .dashboard-hero-main h2,
    .dashboard-hero-side h3,
    .dashboard-section-head h3,
    .dash-card h3 {
      margin-top: 0;
    }
    .dashboard-hero-main p,
    .dashboard-hero-side p,
    .dash-card p {
      margin-top: 0;
    }
    .dashboard-hero-main {
      display: grid;
      gap: 14px;
      align-content: start;
      padding-top: 20px;
    }
    .dashboard-hero-lead {
      font-size: 1.02rem;
      line-height: 1.55;
      max-width: 58ch;
    }
    .dashboard-pill-row {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }
    .dashboard-pill {
      display: grid;
      gap: 2px;
      min-width: 132px;
      padding: 11px 13px;
      border-radius: 12px;
      border: 1px solid var(--border);
      background: rgba(255, 255, 255, 0.03);
    }
    .dashboard-pill strong {
      font-size: 0.74rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .dashboard-pill span {
      font-size: 0.96rem;
      font-weight: 700;
      line-height: 1.3;
    }
    .dashboard-hero-side {
      display: grid;
      gap: 14px;
      align-content: start;
      padding-top: 20px;
    }
    .dashboard-list {
      display: grid;
      gap: 10px;
    }
    .dashboard-list-item {
      display: grid;
      gap: 4px;
      padding: 11px 12px;
      border-radius: 12px;
      border: 1px solid var(--border);
      background: rgba(255, 255, 255, 0.03);
    }
    .dashboard-list-item strong { font-size: 0.9rem; }
    .dashboard-section {
      display: grid;
      gap: 12px;
      padding-top: 18px;
    }
    .dashboard-section-head {
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 12px;
    }
    .dashboard-section-head p {
      margin: 0;
      max-width: 70ch;
    }
    .dashboard-section-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 14px;
    }
    .dash-card {
      display: grid;
      gap: 12px;
      align-content: start;
      min-height: 100%;
      padding-top: 20px;
    }
    .dash-card h3 { margin-bottom: 2px; }
    .dash-card p { min-height: 0; line-height: 1.5; }
    .dash-card.primary {
      background: linear-gradient(180deg, rgba(255, 255, 255, 0.03), transparent 48%), var(--card);
    }
    .dash-actions { display: flex; gap: 10px; flex-wrap: wrap; margin-top: auto; }
    .dash-actions .btn { min-width: 0; }
    .dashboard-note {
      margin: 0;
      color: var(--muted);
      font-size: 0.88rem;
      line-height: 1.45;
    }
    .table-wrap {
      overflow-x: auto;
      -webkit-overflow-scrolling: touch;
      border-radius: 12px;
      border: 1px solid var(--border);
    }
    .table-wrap table { min-width: 640px; }
    .status-pill { text-transform: capitalize; }
    .go-page-select { min-width: 180px; max-width: 40vw; }
    .mobile-pre {
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      word-break: break-word;
      max-height: 60vh;
      overflow: auto;
    }
    .documentation-sidebar {
      max-height: 56vh;
      overflow: auto;
    }
    .documentation-link {
      background: transparent;
      color: var(--fg);
      border-color: var(--border);
    }
    .documentation-link:hover {
      background: rgba(37, 99, 235, .08);
      color: var(--fg);
    }
    .documentation-link.active {
      background: var(--btn-bg);
      border-color: var(--btn-bg);
      color: #fff;
    }
    .documentation-link.active .text-secondary,
    .documentation-link.active .small {
      color: rgba(255, 255, 255, 0.78) !important;
    }
    @media (max-width: 1180px) {
      .dashboard-hero { grid-template-columns: 1fr; }
    }
    @media (max-width: 1024px) {
      .wrap { max-width: 960px; }
      .dashboard-section-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .dashboard-pill-row { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .dashboard-hero-main,
      .dashboard-hero-side,
      .dash-card { padding-top: 16px; }
      .nav-controls { gap: 8px; }
      .nav-select { width: 240px; }
    }
    @media (max-width: 1080px) { .dash-grid { grid-template-columns: 1fr 1fr; } }
    @media (max-width: 900px) {
      .grid { grid-template-columns: 1fr; }
      .dash-grid { grid-template-columns: 1fr; }
      .dashboard-section-head { align-items: start; flex-direction: column; }
      .dashboard-section-grid { grid-template-columns: 1fr 1fr; }
      .dashboard-pill-row { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
      header { padding: 10px 12px; align-items: center; }
      .wrap { margin: 14px auto; padding: 0 10px; }
      .card { padding: 14px; }
      .header-toprow { width: 100%; align-items: flex-start; }
      .header-tools { margin-left: 0; width: auto; flex-shrink: 0; }
      .header-right.desktop-nav { display: none; }
      .mobile-quickbar { display: grid; grid-template-columns: 1fr; gap: 10px; width: 100%; }
      .mobile-nav { display: block; width: 100%; }
      .nav-select { width: 100%; max-width: 100%; min-width: 0; }
      .theme-switch { width: 100%; }
      .header-tools .theme-switch { display: none; }
      .theme-btn { flex: 1; min-height: 42px; }
      .current-user-email { display: block; }
      .dash-actions .btn { width: 100%; }
      .dashboard-pill { min-width: 0; flex: 1 1 180px; }
      th, td { padding: 8px; }
      .table-wrap > table { min-width: 600px; }
      .table-wrap table { min-width: 520px; }
      .mobile-pre { max-height: 48vh; font-size: .875rem; }
      .documentation-sidebar { max-height: none; }
    }
    @media (max-width: 600px) {
      .card { border-radius: 10px; }
      .table-wrap > table { min-width: 520px; }
      .header-toprow { flex-direction: column; align-items: stretch; }
      .header-tools { width: 100%; flex-direction: column; align-items: stretch; }
      .dashboard-section-grid { grid-template-columns: 1fr; }
      .dashboard-pill-row { display: grid; grid-template-columns: 1fr; }
      .dashboard-pill { min-width: 0; }
      .dashboard-pill span { font-size: 0.92rem; }
      .header-version { font-size: 0.74rem; }
      .mobile-link-grid { grid-template-columns: 1fr; }
      main.container { padding-top: 1rem !important; padding-bottom: 1.25rem !important; }
    }
  </style>
</head>
<body data-theme="black">
  <header>
    <div class="header-toprow">
      <div class="header-brand">
        <strong>Wicked Yoda Bot Admin</strong>
        <span class="header-version">{{ snapshot.server_time if snapshot and snapshot.server_time else "n/a" }}</span>
      </div>
      <div class="header-tools">
        {% if session.get("user") %}
        <details class="mobile-nav">
          <summary>Menu</summary>
          <div class="mobile-nav-panel">
            <div class="mobile-user-block">
              <span class="current-user">{{ session.get("display_name") or session.get("user") }}{% if session.get("is_admin") %} (Admin){% elif session.get("is_guild_admin") %} (Guild Admin){% else %} (Read Only){% endif %}</span>
              {% if selected_guild_name %}<span class="current-user">Server: {{ selected_guild_name }}</span>{% endif %}
            </div>
            <div class="mobile-panel-section">
              <p class="mobile-panel-title">Quick Jump</p>
              <label class="sr-only" for="mobile-nav-page-select">Open page</label>
              <select id="mobile-nav-page-select" class="nav-select nav-page-select">
                <option value="">Go to page...</option>
                <option value="{{ url_for('dashboard') }}">Dashboard (Home)</option>
                <option value="{{ url_for('account') }}">Account</option>
                <option value="{{ url_for('overview') }}">Overview</option>
                <option value="{{ url_for('guilds_page') }}">Servers</option>
                <option value="{{ url_for('guild_settings') }}">Guild Settings</option>
                <option value="{{ url_for('moderation') }}">Moderation</option>
                <option value="{{ url_for('command_permissions') }}">Command Permissions</option>
                <option value="{{ url_for('bot_profile') }}">Bot Profile</option>
                <option value="{{ url_for('random_user_page') }}">Random User</option>
                <option value="{{ url_for('member_activity_page') }}">Member Activity</option>
                <option value="{{ url_for('actions') }}">Actions</option>
                <option value="{{ url_for('tag_responses') }}">Tag Responses</option>
                <option value="{{ url_for('spicy_prompts') }}">Spicy Prompts</option>
                <option value="{{ url_for('youtube_subscriptions') }}">YouTube</option>
                <option value="{{ url_for('reddit_feeds') }}">Reddit</option>
                <option value="{{ url_for('wordpress_feeds') }}">WordPress</option>
                <option value="{{ url_for('linkedin_feeds') }}">LinkedIn</option>
                <option value="{{ url_for('uptime_monitors_page') }}">Uptime Monitors</option>
                <option value="{{ url_for('status_page') }}">Status</option>
                {% if session.get("is_admin") %}
                <option value="{{ url_for('users') }}">Users</option>
                <option value="{{ url_for('guild_access') }}">Guild Access</option>
                <option value="{{ url_for('settings') }}">Settings (Global)</option>
                <option value="{{ url_for('observability') }}">Observability (Global)</option>
                <option value="{{ url_for('logs') }}">Logs (Global)</option>
                <option value="{{ url_for('documentation') }}">Documentation (Global)</option>
                {% endif %}
                <option value="{{ url_for('logout') }}">Logout</option>
              </select>
            </div>
            <div class="mobile-panel-section">
              <p class="mobile-panel-title">Primary Actions</p>
              <div class="mobile-link-grid">
                <a class="btn secondary" href="{{ url_for('guilds_page') }}">Servers</a>
                <a class="btn secondary" href="{{ url_for('account') }}">My Account</a>
                <a class="btn secondary" href="{{ url_for('member_activity_page') }}">Member Activity</a>
                <a class="btn secondary" href="{{ url_for('dashboard') }}">Dashboard</a>
                <a class="btn secondary" href="{{ url_for('command_permissions') }}">Permissions</a>
                <a class="btn secondary" href="{{ url_for('guild_settings') }}">Settings</a>
                <a class="btn secondary" href="{{ url_for('logs') }}">Logs</a>
                <a class="btn secondary" href="{{ url_for('logout') }}">Logout</a>
              </div>
            </div>
            <div class="mobile-panel-section">
              <p class="mobile-panel-title">Theme</p>
              <div class="theme-switch" aria-label="Theme selector">
                <button type="button" class="theme-btn" data-theme-choice="light">Light</button>
                <button type="button" class="theme-btn" data-theme-choice="black">Black</button>
                <button type="button" class="theme-btn" data-theme-choice="forest">Forest</button>
                <button type="button" class="theme-btn" data-theme-choice="ember">Ember</button>
                <button type="button" class="theme-btn" data-theme-choice="ice">Ice</button>
              </div>
            </div>
          </div>
        </details>
        {% endif %}
        <div class="theme-switch" aria-label="Theme selector">
          <button type="button" class="theme-btn" data-theme-choice="light">Light</button>
          <button type="button" class="theme-btn" data-theme-choice="black">Black</button>
          <button type="button" class="theme-btn" data-theme-choice="forest">Forest</button>
          <button type="button" class="theme-btn" data-theme-choice="ember">Ember</button>
          <button type="button" class="theme-btn" data-theme-choice="ice">Ice</button>
        </div>
      </div>
    </div>
    {% if session.get("user") %}
    <div class="mobile-quickbar">
      <div class="header-chip">
        <strong>Server</strong>
        <span>{{ selected_guild_name or "No server selected" }}</span>
      </div>
      <div class="mobile-link-grid">
        <a class="btn secondary" href="{{ url_for('guilds_page') }}">Servers</a>
        <a class="btn secondary" href="{{ url_for('account') }}">My Account</a>
        <a class="btn secondary" href="{{ url_for('member_activity_page') }}">Member Activity</a>
        <a class="btn secondary" href="{{ url_for('logout') }}">Logout</a>
        <a class="btn secondary" href="{{ url_for('dashboard') }}">Dashboard</a>
      </div>
    </div>
    {% endif %}
    <div class="header-right desktop-nav">
      {% if session.get("user") %}
        <nav class="nav-controls">
          <span class="current-user">{{ session.get("display_name") or session.get("user") }}{% if session.get("is_admin") %} (Admin){% elif session.get("is_guild_admin") %} (Guild Admin){% else %} (Read Only){% endif %}</span>
          {% if selected_guild_name %}<span class="current-user">Server: {{ selected_guild_name }}</span>{% endif %}
          <a class="btn secondary" href="{{ url_for('guilds_page') }}">Servers</a>
          <a class="btn secondary" href="{{ url_for('dashboard') }}">Dashboard</a>
          <a class="btn secondary" href="{{ url_for('logout') }}">Logout</a>
          <label class="sr-only" for="desktop-nav-page-select">Open page</label>
          <select id="desktop-nav-page-select" class="nav-select nav-page-select">
            <option value="">Go to page...</option>
            <option value="{{ url_for('dashboard') }}">Dashboard (Home)</option>
            <option value="{{ url_for('account') }}">Account</option>
            <option value="{{ url_for('overview') }}">Overview</option>
            <option value="{{ url_for('guilds_page') }}">Servers</option>
            <option value="{{ url_for('guild_settings') }}">Guild Settings</option>
            <option value="{{ url_for('moderation') }}">Moderation</option>
            <option value="{{ url_for('command_permissions') }}">Command Permissions</option>
            <option value="{{ url_for('bot_profile') }}">Bot Profile</option>
            <option value="{{ url_for('random_user_page') }}">Random User</option>
            <option value="{{ url_for('member_activity_page') }}">Member Activity</option>
            <option value="{{ url_for('actions') }}">Actions</option>
            <option value="{{ url_for('tag_responses') }}">Tag Responses</option>
            <option value="{{ url_for('spicy_prompts') }}">Spicy Prompts</option>
            <option value="{{ url_for('youtube_subscriptions') }}">YouTube</option>
            <option value="{{ url_for('reddit_feeds') }}">Reddit</option>
            <option value="{{ url_for('wordpress_feeds') }}">WordPress</option>
            <option value="{{ url_for('linkedin_feeds') }}">LinkedIn</option>
            <option value="{{ url_for('uptime_monitors_page') }}">Uptime Monitors</option>
            <option value="{{ url_for('status_page') }}">Status</option>
            {% if session.get("is_admin") %}
            <option value="{{ url_for('users') }}">Users</option>
            <option value="{{ url_for('guild_access') }}">Guild Access</option>
            <option value="{{ url_for('settings') }}">Settings (Global)</option>
            <option value="{{ url_for('observability') }}">Observability (Global)</option>
            <option value="{{ url_for('logs') }}">Logs (Global)</option>
            <option value="{{ url_for('documentation') }}">Documentation (Global)</option>
            {% endif %}
            <option value="{{ url_for('logout') }}">Logout</option>
          </select>
          {% if guild_options %}
          <form method="post" action="{{ url_for('select_guild') }}" class="inline-form">
            <input type="hidden" name="next_endpoint" value="{{ 'documentation' if request.endpoint == 'documentation_page' else (request.endpoint or 'home') }}">
            <select class="nav-select" name="guild_id" onchange="this.form.submit()">
              {% for guild in guild_options %}
              <option value="{{ guild.id }}" {% if selected_guild_id == guild.id %}selected{% endif %}>{{ guild.name }}</option>
              {% endfor %}
            </select>
          </form>
          {% endif %}
        </nav>
      {% endif %}
    </div>
  </header>

  <main class="container wrap">
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        {% for category, message in messages %}
          <div class="alert alert-{{ category }} alert-dismissible fade show" role="alert">
            {{ message }}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
          </div>
        {% endfor %}
      {% endif %}
    {% endwith %}

    {% if session.get("user") and selected_guild_name %}
    <p class="small text-secondary mb-3">Managing guild: <strong>{{ selected_guild_name }}</strong> ({{ selected_guild_id }})</p>
    {% endif %}
    {% if session.get("user") and not session.get("is_admin") and not session.get("is_guild_admin") %}
    <div class="alert alert-info">Read-only account: you can view pages, but admin changes are restricted.</div>
    {% endif %}

    {% if page == "login" %}
      <div class="row justify-content-center mt-4">
        <div class="col-12 col-sm-10 col-md-7 col-lg-5">
          <div class="card card-soft p-4">
            <h1 class="h4 mb-3">Admin Login</h1>
            <form method="post">
              <div class="mb-3">
                <label class="form-label" for="username">Email</label>
                <input class="form-control" id="username" name="username" required autocomplete="username" autocapitalize="none" spellcheck="false">
              </div>
              <div class="mb-3">
                <label class="form-label" for="password">Password</label>
                <input class="form-control" id="password" name="password" type="password" required autocomplete="current-password">
              </div>
              <div class="form-check mb-3">
                <input class="form-check-input" type="checkbox" id="remember_login" name="remember_login" value="1">
                <label class="form-check-label" for="remember_login">Keep me signed in for 5 days on this device</label>
              </div>
              <button class="btn btn-primary w-100" type="submit">Sign in</button>
            </form>
          </div>
        </div>
      </div>
    {% elif page == "status_public" %}
      <div class="row g-3 mb-3">
        <div class="col-12 col-md-3">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">Bot</p>
            <p class="mb-0 fw-semibold">{{ snapshot.bot_name }}</p>
          </div>
        </div>
        <div class="col-6 col-md-3">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">Guilds</p>
            <p class="mb-0 fs-5 fw-bold">{{ snapshot.guild_count or 1 }}</p>
          </div>
        </div>
        <div class="col-6 col-md-3">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">Commands Synced</p>
            <p class="mb-0 fs-5 fw-bold">{{ snapshot.commands_synced }}</p>
          </div>
        </div>
        <div class="col-12 col-md-3">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">Latency</p>
            <p class="mb-0 fs-5 fw-bold">{{ snapshot.latency_ms }} ms</p>
          </div>
        </div>
      </div>
      <div class="row g-3 mb-3">
        <div class="col-4">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">Total Actions</p>
            <p class="mb-0 fs-5 fw-bold">{{ counts.total }}</p>
          </div>
        </div>
        <div class="col-4">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">Success</p>
            <p class="mb-0 fs-5 fw-bold text-success">{{ counts.success }}</p>
          </div>
        </div>
        <div class="col-4">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">Failed</p>
            <p class="mb-0 fs-5 fw-bold text-danger">{{ counts.failed }}</p>
          </div>
        </div>
      </div>
      <div class="card card-soft p-3">
        <div class="d-flex justify-content-between align-items-center mb-2">
          <h2 class="h6 mb-0">Recent Activity</h2>
          <div class="d-flex align-items-center gap-2">
            <form method="get" class="d-flex align-items-center gap-2">
              <label class="small text-secondary mb-0" for="status_refresh">Auto refresh</label>
              <select class="form-select form-select-sm" id="status_refresh" name="refresh" onchange="this.form.submit()">
                {% for option in refresh_options %}
                <option value="{{ option }}" {% if option == status_refresh_seconds %}selected{% endif %}>
                  {% if option == 0 %}Off{% else %}{{ option }}s{% endif %}
                </option>
                {% endfor %}
              </select>
            </form>
            <span class="small text-secondary">UTC</span>
          </div>
        </div>
        <div class="table-wrap">
          <table class="table table-sm align-middle">
            <thead><tr><th>Time</th><th>Action</th><th>Status</th><th>Moderator</th><th>Target</th></tr></thead>
            <tbody>
              {% for row in actions %}
              <tr>
                <td class="small">{{ row.created_at }}</td>
                <td>{{ row.action }}</td>
                <td><span class="badge text-bg-{{ 'success' if row.status == 'success' else 'danger' }} status-pill">{{ row.status }}</span></td>
                <td class="small">{{ row.moderator or '-' }}</td>
                <td class="small">{{ row.target or '-' }}</td>
              </tr>
              {% else %}
              <tr><td colspan="5" class="text-secondary">No actions logged yet.</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </div>
    {% elif page == "home" %}
      <div class="card card-soft p-3 mb-3">
        <h1 class="h5 mb-2">Control Center</h1>
        <p class="text-secondary mb-0">Use the Menu in the top-right corner to navigate. This landing page stays minimal for mobile.</p>
      </div>
      <div class="row g-3">
        <div class="col-12 col-md-4">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">Bot</p>
            <p class="mb-0 fw-semibold">{{ snapshot.bot_name }}</p>
          </div>
        </div>
        <div class="col-12 col-md-4">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">Selected Guild</p>
            <p class="mb-0 fw-semibold">{{ selected_guild_name or snapshot.guild_id }}</p>
          </div>
        </div>
        <div class="col-12 col-md-4">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">Latency</p>
            <p class="mb-0 fw-semibold">{{ snapshot.latency_ms }} ms</p>
          </div>
        </div>
      </div>
    {% elif page == "overview" %}
      <div class="dashboard-shell">
        <section class="dashboard-hero">
          <div class="card card-soft dashboard-hero-main">
            <div>
              <h2>Dashboard</h2>
              <p class="dashboard-hero-lead">Operational control for <strong>{{ selected_guild_name or snapshot.guild_id }}</strong>. Use the sections below to manage core configuration, community tools, and notification feeds.</p>
            </div>
            <div class="dashboard-pill-row">
              <div class="dashboard-pill">
                <strong>Server</strong>
                <span>{{ selected_guild_name or snapshot.guild_id }}</span>
              </div>
              <div class="dashboard-pill">
                <strong>Access</strong>
                <span>{{ "Admin" if session.get("is_admin") else ("Guild Admin" if session.get("is_guild_admin") else "Read-only") }}</span>
              </div>
              <div class="dashboard-pill">
                <strong>Commands Enabled</strong>
                <span>{{ command_statuses | selectattr("enabled") | list | length }}/{{ command_statuses | length }}</span>
              </div>
              <div class="dashboard-pill">
                <strong>Spicy Prompts</strong>
                <span>
                  {% if spicy_status and spicy_status.ok %}
                  {{ "Enabled" if spicy_status.enabled else "Disabled" }}
                  {% else %}
                  Unknown
                  {% endif %}
                </span>
              </div>
            </div>
            <p class="dashboard-note">Latency: {{ snapshot.latency_ms }} ms | Actions: {{ counts.total }} total ({{ counts.success }} success, {{ counts.failed }} failed)</p>
          </div>
          <div class="card card-soft dashboard-hero-side">
            <div>
              <h3>Quick Notes</h3>
              <p class="text-secondary">Key status details for the selected guild.</p>
            </div>
            <div class="dashboard-list">
              <div class="dashboard-list-item">
                <strong>Bot</strong>
                <div class="text-secondary">{{ snapshot.bot_name }}</div>
              </div>
              <div class="dashboard-list-item">
                <strong>Spicy Channel</strong>
                <div class="text-secondary">
                  {% if spicy_status and spicy_status.ok and spicy_status.channel_id %}
                  Channel ID: {{ spicy_status.channel_id }}
                  {% else %}
                  Not configured
                  {% endif %}
                </div>
              </div>
              <div class="dashboard-list-item">
                <strong>Log Channel</strong>
                <div class="text-secondary">Set per guild in Guild Settings.</div>
              </div>
            </div>
          </div>
        </section>

        <section class="card card-soft dashboard-section">
          <div class="dashboard-section-head">
            <div>
              <h3>Core Controls</h3>
              <p>Primary configuration pages for this guild.</p>
            </div>
          </div>
          <div class="dashboard-section-grid">
            <div class="card dash-card primary">
              <h3>Guild Settings</h3>
              <p class="text-secondary">Configure bot log channels and guild-specific settings.</p>
              <div class="dash-actions">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('guild_settings') }}">Open Guild Settings</a>
              </div>
            </div>
            <div class="card dash-card">
              <h3>Command Permissions</h3>
              <p class="text-secondary">Enable, disable, and restrict commands by role.</p>
              <div class="dash-actions">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('command_permissions') }}">Open Permissions</a>
              </div>
            </div>
            <div class="card dash-card">
              <h3>Bot Profile</h3>
              <p class="text-secondary">Update bot display name and avatar.</p>
              <div class="dash-actions">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('bot_profile') }}">Open Bot Profile</a>
              </div>
            </div>
            <div class="card dash-card">
              <h3>Settings</h3>
              <p class="text-secondary">Runtime env values and system configuration.</p>
              <div class="dash-actions">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('settings') }}">Open Settings</a>
              </div>
            </div>
          </div>
        </section>

        <section class="card card-soft dashboard-section">
          <div class="dashboard-section-head">
            <div>
              <h3>Community Tools</h3>
              <p>Member activity, moderation history, and tag responses.</p>
            </div>
          </div>
          <div class="dashboard-section-grid">
            <div class="card dash-card">
              <h3>Member Activity</h3>
              <p class="text-secondary">Top 20 members across rolling time windows.</p>
              <div class="dash-actions">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('member_activity_page') }}">Open Activity</a>
              </div>
            </div>
            <div class="card dash-card">
              <h3>Moderation Actions</h3>
              <p class="text-secondary">Recent moderation events and audits.</p>
              <div class="dash-actions">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('actions') }}">View Actions</a>
              </div>
            </div>
            <div class="card dash-card">
              <h3>Moderation</h3>
              <p class="text-secondary">Bad word filters, warnings, and auto-timeout rules.</p>
              <div class="dash-actions">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('moderation') }}">Open Moderation</a>
              </div>
            </div>
            <div class="card dash-card">
              <h3>Tag Responses</h3>
              <p class="text-secondary">Maintain command shortcut responses.</p>
              <div class="dash-actions">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('tag_responses') }}">Manage Tags</a>
              </div>
            </div>
            <div class="card dash-card">
              <h3>Users</h3>
              <p class="text-secondary">Manage web GUI users and roles.</p>
              <div class="dash-actions">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('users') }}">Manage Users</a>
              </div>
            </div>
          </div>
        </section>

        <section class="card card-soft dashboard-section">
          <div class="dashboard-section-head">
            <div>
              <h3>Notification Feeds</h3>
              <p>External monitors and feed routing.</p>
            </div>
          </div>
          <div class="dashboard-section-grid">
            <div class="card dash-card">
              <h3>YouTube</h3>
              <p class="text-secondary">Video and community post alerts.</p>
              <div class="dash-actions">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('youtube_subscriptions') }}">Open YouTube</a>
              </div>
            </div>
            <div class="card dash-card">
              <h3>Reddit</h3>
              <p class="text-secondary">Scheduled subreddit updates.</p>
              <div class="dash-actions">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('reddit_feeds') }}">Open Reddit</a>
              </div>
            </div>
            <div class="card dash-card">
              <h3>WordPress</h3>
              <p class="text-secondary">New blog post alerts.</p>
              <div class="dash-actions">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('wordpress_feeds') }}">Open WordPress</a>
              </div>
            </div>
            <div class="card dash-card">
              <h3>LinkedIn</h3>
              <p class="text-secondary">Profile post notifications.</p>
              <div class="dash-actions">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('linkedin_feeds') }}">Open LinkedIn</a>
              </div>
            </div>
            <div class="card dash-card">
              <h3>Spicy Prompts</h3>
              <p class="text-secondary">Repo refresh and status.</p>
              <div class="dash-actions">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('spicy_prompts') }}">Open Spicy Prompts</a>
              </div>
            </div>
          </div>
        </section>

        <section class="card card-soft dashboard-section">
          <div class="dashboard-section-head">
            <div>
              <h3>Runtime and Admin</h3>
              <p>Logs, observability, and docs.</p>
            </div>
          </div>
          <div class="dashboard-section-grid">
            <div class="card dash-card">
              <h3>Logs</h3>
              <p class="text-secondary">Container and bot logs.</p>
              <div class="dash-actions">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('logs') }}">Open Logs</a>
              </div>
            </div>
            <div class="card dash-card">
              <h3>Observability</h3>
              <p class="text-secondary">Status summaries and metrics.</p>
              <div class="dash-actions">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('observability') }}">Open Observability</a>
              </div>
            </div>
            <div class="card dash-card">
              <h3>Status</h3>
              <p class="text-secondary">Internal status view.</p>
              <div class="dash-actions">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('status_page') }}">Open Status</a>
              </div>
            </div>
            <div class="card dash-card">
              <h3>Documentation</h3>
              <p class="text-secondary">Bot help and wiki pages.</p>
              <div class="dash-actions">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('documentation') }}">Open Docs</a>
              </div>
            </div>
          </div>
        </section>

        <section class="card card-soft dashboard-section">
          <div class="dashboard-section-head">
            <div>
              <h3>Latest Actions</h3>
              <p>Most recent moderation events.</p>
            </div>
            <a href="{{ url_for('actions') }}" class="btn btn-sm btn-outline-primary">View all</a>
          </div>
          <div class="table-wrap">
            <table class="table table-sm align-middle">
              <thead><tr><th>Time (UTC)</th><th>Action</th><th>Status</th><th>Moderator</th><th>Target</th></tr></thead>
              <tbody>
                {% for row in actions %}
                <tr>
                  <td class="small">{{ row.created_at }}</td>
                  <td>{{ row.action }}</td>
                  <td><span class="badge text-bg-{{ 'success' if row.status == 'success' else 'danger' }} status-pill">{{ row.status }}</span></td>
                  <td class="small">{{ row.moderator or '-' }}</td>
                  <td class="small">{{ row.target or '-' }}</td>
                </tr>
                {% else %}
                <tr><td colspan="5" class="text-secondary">No actions logged yet.</td></tr>
                {% endfor %}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    {% elif page == "dashboard" %}
      <div class="card card-soft p-3">
        <h1 class="h5 mb-2">Dashboard</h1>
        <p class="text-secondary mb-3">Every category is listed here for quick access.</p>
        <div class="row g-3">
          <div class="col-12 col-lg-4">
            <div class="card card-soft p-3 h-100">
              <h3 class="h6 mb-2">Core</h3>
              <div class="d-grid gap-2">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('home') }}">Landing Page</a>
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('overview') }}">Overview</a>
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('guilds_page') }}">Servers</a>
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('guild_settings') }}">Guild Settings</a>
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('command_permissions') }}">Command Permissions</a>
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('bot_profile') }}">Bot Profile</a>
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('random_user_page') }}">Random User</a>
              </div>
            </div>
          </div>
          <div class="col-12 col-lg-4">
            <div class="card card-soft p-3 h-100">
              <h3 class="h6 mb-2">Community</h3>
              <div class="d-grid gap-2">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('member_activity_page') }}">Member Activity</a>
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('actions') }}">Moderation Actions</a>
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('tag_responses') }}">Tag Responses</a>
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('spicy_prompts') }}">Spicy Prompts</a>
              </div>
            </div>
          </div>
          <div class="col-12 col-lg-4">
            <div class="card card-soft p-3 h-100">
              <h3 class="h6 mb-2">Feeds</h3>
              <div class="d-grid gap-2">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('youtube_subscriptions') }}">YouTube</a>
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('reddit_feeds') }}">Reddit</a>
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('wordpress_feeds') }}">WordPress</a>
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('linkedin_feeds') }}">LinkedIn</a>
              </div>
            </div>
          </div>
          <div class="col-12 col-lg-4">
            <div class="card card-soft p-3 h-100">
              <h3 class="h6 mb-2">Uptime</h3>
              <div class="d-grid gap-2">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('uptime_monitors_page') }}">Uptime Monitors</a>
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('status_page') }}">Status</a>
              </div>
            </div>
          </div>
          <div class="col-12 col-lg-4">
            <div class="card card-soft p-3 h-100">
              <h3 class="h6 mb-2">Admin</h3>
              <div class="d-grid gap-2">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('users') }}">Users</a>
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('guild_access') }}">Guild Access</a>
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('settings') }}">Settings (Global)</a>
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('observability') }}">Observability (Global)</a>
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('logs') }}">Logs (Global)</a>
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('documentation') }}">Documentation (Global)</a>
              </div>
            </div>
          </div>
          <div class="col-12 col-lg-4">
            <div class="card card-soft p-3 h-100">
              <h3 class="h6 mb-2">Account</h3>
              <div class="d-grid gap-2">
                <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('account') }}">My Account</a>
              </div>
            </div>
          </div>
        </div>
        <div class="mt-4">
          <h3 class="h6 mb-2">Latest Actions</h3>
          <div class="table-wrap">
            <table class="table table-sm align-middle">
              <thead><tr><th>Time (UTC)</th><th>Action</th><th>Status</th></tr></thead>
              <tbody>
                {% for row in actions %}
                <tr>
                  <td class="small">{{ row.created_at }}</td>
                  <td>{{ row.action }}</td>
                  <td><span class="badge text-bg-{{ 'success' if row.status == 'success' else 'danger' }} status-pill">{{ row.status }}</span></td>
                </tr>
                {% else %}
                <tr><td colspan="3" class="text-secondary">No actions logged yet.</td></tr>
                {% endfor %}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    {% elif page == "uptime_monitors" %}
      <div class="card card-soft p-3 mb-3">
        <h1 class="h5 mb-3">Uptime Monitors</h1>
        <form method="post" action="{{ url_for('uptime_monitor_add') }}">
          <div class="row g-2">
            <div class="col-12 col-xl-3">
              <label class="form-label" for="monitor_name">Name</label>
              <input class="form-control" id="monitor_name" name="monitor_name" placeholder="API - prod" required {% if not can_manage_guild %}disabled{% endif %}>
            </div>
            <div class="col-12 col-md-6 col-xl-2">
              <label class="form-label" for="monitor_type">Type</label>
              <select class="form-select" id="monitor_type" name="monitor_type" {% if not can_manage_guild %}disabled{% endif %}>
                <option value="http">HTTP (Website/API)</option>
                <option value="statuspage">Status Page</option>
                <option value="tcp">TCP</option>
              </select>
            </div>
            <div class="col-12 col-xl-4">
              <label class="form-label" for="monitor_target">Target</label>
              <input class="form-control" id="monitor_target" name="monitor_target" placeholder="https://example.com or host:port" required {% if not can_manage_guild %}disabled{% endif %}>
            </div>
            <div class="col-12 col-xl-3">
              <label class="form-label" for="monitor_preset">Preset</label>
              <select class="form-select" id="monitor_preset" {% if not can_manage_guild %}disabled{% endif %}>
                <option value="">Choose a preset...</option>
                <option value="discord">Discord Status</option>
                <option value="tailscale">Tailscale Status</option>
              </select>
              <div class="form-text">Presets use Statuspage endpoints.</div>
            </div>
            <div class="col-6 col-md-3 col-xl-1">
              <label class="form-label" for="monitor_interval">Interval</label>
              <select class="form-select" id="monitor_interval" name="interval_seconds" {% if not can_manage_guild %}disabled{% endif %}>
                {% for option in monitor_interval_options %}
                <option value="{{ option.value }}">{{ option.label }}</option>
                {% endfor %}
              </select>
            </div>
            <div class="col-6 col-md-3 col-xl-1">
              <label class="form-label" for="monitor_timeout">Timeout</label>
              <select class="form-select" id="monitor_timeout" name="timeout_seconds" {% if not can_manage_guild %}disabled{% endif %}>
                {% for option in monitor_timeout_options %}
                <option value="{{ option }}">{{ option }}s</option>
                {% endfor %}
              </select>
            </div>
            <div class="col-12 col-md-6 col-xl-4">
              <label class="form-label" for="monitor_channel">Alert Channel</label>
              <select class="form-select" id="monitor_channel" name="alert_channel_id" {% if not can_manage_guild %}disabled{% endif %}>
                <option value="">Default (Bot Log / Guild Setting)</option>
                {% for channel in notification_channels %}
                <option value="{{ channel.id }}">{{ channel.name }} ({{ channel.id }})</option>
                {% endfor %}
              </select>
            </div>
            <div class="col-12 col-xl-1 d-flex align-items-end">
              <button class="btn btn-primary w-100" type="submit" {% if not can_manage_guild %}disabled{% endif %}>Add</button>
            </div>
          </div>
        </form>
        <script>
          (function () {
            const preset = document.getElementById("monitor_preset");
            const type = document.getElementById("monitor_type");
            const target = document.getElementById("monitor_target");
            if (!preset || !type || !target) return;
            preset.addEventListener("change", () => {
              if (preset.value === "discord") {
                type.value = "statuspage";
                target.value = "https://discordstatus.com";
              } else if (preset.value === "tailscale") {
                type.value = "statuspage";
                target.value = "https://status.tailscale.com";
              }
            });
          })();
        </script>
        {% if not notification_channels %}
        <p class="small text-danger mt-2 mb-0">No text channels found. Verify bot guild/channel permissions and refresh.</p>
        {% endif %}
      </div>
      <div class="card card-soft p-3">
        <h2 class="h6 mb-3">Configured Monitors</h2>
        <div class="table-wrap">
          <table class="table table-sm align-middle">
            <thead><tr><th>Name</th><th>Target</th><th>Status</th><th>Interval</th><th>Last Check</th><th>Alert Channel</th><th>Action</th></tr></thead>
            <tbody>
              {% for row in uptime_monitors %}
              <tr>
                <td class="small">
                  <div class="fw-semibold">{{ row.name }}</div>
                  <div class="text-secondary small">{{ row.monitor_type|upper }}</div>
                </td>
                <td class="small">{{ row.target }}</td>
                <td class="small">
                  {% set status = (row.last_status or 'unknown') %}
                  <span class="badge text-bg-{{ 'success' if status == 'up' else ('danger' if status == 'down' else 'secondary') }}">{{ status }}</span>
                  {% if row.last_error %}
                  <div class="text-secondary small">{{ row.last_error }}</div>
                  {% endif %}
                </td>
                <td class="small">{{ row.interval_label }}</td>
                <td class="small">{{ row.last_checked_at or '-' }}</td>
                <td class="small">
                  {% if row.alert_channel_name %}
                  {{ row.alert_channel_name }} ({{ row.alert_channel_id }})
                  {% else %}
                  Default
                  {% endif %}
                </td>
                <td class="small d-flex gap-2">
                  <form method="post" action="{{ url_for('uptime_monitor_toggle', monitor_id=row.id) }}">
                    <input type="hidden" name="enabled" value="{{ 0 if row.enabled else 1 }}">
                    <button class="btn btn-sm btn-outline-secondary" type="submit" {% if not can_manage_guild %}disabled{% endif %}>
                      {{ "Disable" if row.enabled else "Enable" }}
                    </button>
                  </form>
                  <form method="post" action="{{ url_for('uptime_monitor_delete', monitor_id=row.id) }}">
                    <button class="btn btn-sm btn-outline-danger" type="submit" {% if not can_manage_guild %}disabled{% endif %}>Delete</button>
                  </form>
                </td>
              </tr>
              {% else %}
              <tr><td colspan="7" class="text-secondary">No monitors configured yet.</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </div>
    {% elif page == "status_admin" %}
      <div class="card card-soft p-3 mb-3">
        <h1 class="h5 mb-2">Service Status</h1>
        <p class="text-secondary mb-0">Focused service health view for the selected guild, separate from dashboard analytics.</p>
      </div>
      <div class="row g-3 mb-3">
        {% for check in status_checks %}
        <div class="col-12 col-md-4">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">{{ check.component }}</p>
            <p class="mb-1 fw-semibold">{{ check.state }}</p>
            <p class="small mb-0 text-secondary">{{ check.detail }}</p>
          </div>
        </div>
        {% endfor %}
      </div>
      <div class="card card-soft p-3 mb-3">
        <div class="d-flex justify-content-between align-items-center mb-2">
          <h2 class="h6 mb-0">Latest Action Events</h2>
          <a href="{{ url_for('actions') }}" class="btn btn-sm btn-outline-primary">View all</a>
        </div>
        <div class="table-wrap">
          <table class="table table-sm align-middle">
            <thead><tr><th>Time (UTC)</th><th>Action</th><th>Status</th><th>Moderator</th><th>Target</th></tr></thead>
            <tbody>
              {% for row in actions %}
              <tr>
                <td class="small">{{ row.created_at }}</td>
                <td>{{ row.action }}</td>
                <td><span class="badge text-bg-{{ 'success' if row.status == 'success' else 'danger' }} status-pill">{{ row.status }}</span></td>
                <td class="small">{{ row.moderator or '-' }}</td>
                <td class="small">{{ row.target or '-' }}</td>
              </tr>
              {% else %}
              <tr><td colspan="5" class="text-secondary">No actions logged yet.</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </div>
      <div class="card card-soft p-3">
        <h2 class="h6 mb-2">Status Log Tail ({{ status_log_name }})</h2>
        <p class="small text-secondary mb-2">Source directory: {{ status_log_dir }}</p>
        <pre class="small mb-0" style="white-space: pre-wrap; max-height: 35vh; overflow-y: auto;">{{ status_log_tail }}</pre>
      </div>
    {% elif page == "actions" %}
      <div class="card card-soft p-3">
        <h1 class="h5 mb-3">Moderation Actions</h1>
        <div class="table-wrap">
          <table class="table table-sm align-middle">
            <thead><tr><th>Time (UTC)</th><th>Action</th><th>Status</th><th>Moderator</th><th>Target</th><th>Reason</th><th>Guild</th></tr></thead>
            <tbody>
              {% for row in actions %}
              <tr>
                <td class="small">{{ row.created_at }}</td>
                <td>{{ row.action }}</td>
                <td><span class="badge text-bg-{{ 'success' if row.status == 'success' else 'danger' }} status-pill">{{ row.status }}</span></td>
                <td class="small">{{ row.moderator or '-' }}</td>
                <td class="small">{{ row.target or '-' }}</td>
                <td class="small">{{ row.reason or '-' }}</td>
                <td class="small">{{ row.guild or '-' }}</td>
              </tr>
              {% else %}
              <tr><td colspan="7" class="text-secondary">No actions logged yet.</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </div>
    {% elif page == "member_activity" %}
      <div class="card card-soft p-3 mb-3">
        <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3">
          <div>
            <h1 class="h5 mb-2">Member Activity</h1>
            <p class="text-secondary mb-0">Top {{ member_activity.top_limit }} eligible members by message activity for the selected guild across rolling time windows.</p>
          </div>
          <div class="d-flex flex-column flex-sm-row gap-2">
            <form method="get" action="{{ url_for('member_activity_page') }}" class="d-flex flex-column flex-sm-row gap-2">
              <select class="form-select" name="role_id" onchange="this.form.submit()">
                {% for option in member_activity_role_options %}
                <option value="{{ option.value }}" {% if option.value == member_activity.selected_role_id %}selected{% endif %}>{{ option.label }}</option>
                {% endfor %}
              </select>
            </form>
            {% if member_activity_export_enabled %}
            <a class="btn btn-outline-primary" href="{{ url_for('member_activity_export', role_id=member_activity.selected_role_id) if member_activity.selected_role_id else url_for('member_activity_export') }}">Download ZIP Export</a>
            {% endif %}
          </div>
        </div>
        {% if member_activity.error %}
        <p class="small text-danger mt-3 mb-0">{{ member_activity.error }}</p>
        {% else %}
        <p class="small text-secondary mt-3 mb-0">Current filter: <strong>{{ member_activity.selected_role_label }}</strong>. Moderator-style accounts are excluded from rankings.</p>
        {% endif %}
            <div class="card card-soft p-3 mb-3">
        <div class="d-flex align-items-center justify-content-between mb-2">
          <h2 class="h6 mb-0">Command Status</h2>
          <a class="small" href="{{ url_for('command_permissions') }}">Manage</a>
        </div>
        {% if command_statuses %}
        <div class="table-wrap">
          <table class="table table-sm align-middle">
            <thead>
              <tr>
                <th>Command</th>
                <th>Access</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {% for command in command_statuses %}
              <tr>
                <td>
                  <div class="fw-semibold">{{ command.label }}</div>
                  {% if command.description %}
                  <div class="text-secondary small">{{ command.description }}</div>
                  {% endif %}
                </td>
                <td class="small">{{ command.access }}</td>
                <td>
                  {% if command.enabled %}
                  <span class="badge text-bg-success">Enabled</span>
                  {% else %}
                  <span class="badge text-bg-secondary">Disabled</span>
                  {% endif %}
                </td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
        {% else %}
        <p class="text-secondary small mb-0">Command status is unavailable.</p>
        {% endif %}
      </div>
</div>
      <div class="row g-3">
        {% for window in member_activity.windows %}
        <div class="col-12 col-xl-6">
          <div class="card card-soft p-3 h-100">
            <h2 class="h6 mb-3">{{ window.label }}</h2>
            <div class="table-wrap">
              <table class="table table-sm align-middle">
                <thead><tr><th>Rank</th><th>Member</th><th>Messages</th><th>Active Days</th><th>Last Seen</th></tr></thead>
                <tbody>
                  {% for member in window.members %}
                  <tr>
                    <td>{{ member.rank }}</td>
                    <td class="small">
                      <div class="fw-semibold">{{ member.display_name or member.username or member.user_id }}</div>
                      {% if member.username and member.username != member.display_name %}
                      <div class="text-secondary">{{ member.username }}</div>
                      {% endif %}
                    </td>
                    <td>{{ member.message_count }}</td>
                    <td>{{ member.active_days }}</td>
                    <td class="small">{{ member.last_message_at or "n/a" }}</td>
                  </tr>
                  {% else %}
                  <tr><td colspan="5" class="text-secondary">No member activity recorded in this window yet.</td></tr>
                  {% endfor %}
                </tbody>
              </table>
            </div>
          </div>
        </div>
        {% endfor %}
      </div>
    {% elif page == "random_user" %}
      <div class="card card-soft p-3">
        <div class="d-flex flex-column flex-lg-row justify-content-between align-items-start gap-3 mb-3">
          <div>
            <h1 class="h5 mb-2">Random User Picker</h1>
            <p class="text-secondary mb-0">Select a random member. Users picked in the last 30 days are excluded.</p>
          </div>
        </div>
        <form method="post" action="{{ url_for('random_user_page') }}" class="d-flex flex-column flex-lg-row gap-2 align-items-end mb-3">
          <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
          <div class="flex-grow-1">
            <label class="form-label" for="random_role_id">Filter by role</label>
            <select class="form-select" id="random_role_id" name="role_id">
              {% for option in random_user_role_options %}
              <option value="{{ option.value }}" {% if option.value == random_user_selected_role_id %}selected{% endif %}>{{ option.label }}</option>
              {% endfor %}
            </select>
          </div>
          <div>
            <button class="btn btn-primary" type="submit" {% if not can_manage_guild %}disabled{% endif %}>Pick Random User</button>
          </div>
        </form>
        {% if random_user_result %}
          {% if random_user_result.ok %}
            <div class="alert alert-success">
              Selected: <strong>{{ random_user_result.display_name }}</strong>
            </div>
            <p class="text-secondary mb-0">Eligible: {{ random_user_result.eligible_count }} | Excluded last 30 days: {{ random_user_result.recent_count }}</p>
          {% else %}
            <div class="alert alert-danger">{{ random_user_result.error }}</div>
          {% endif %}
        {% endif %}
      </div>
    {% elif page == "youtube" %}
      <div class="card card-soft p-3 mb-3">
        <h1 class="h5 mb-3">YouTube Notifications</h1>
        <form method="post" action="{{ url_for('youtube_add') }}">
          <div class="row g-2">
            <div class="col-12 col-xl-4">
              <label class="form-label" for="youtube_url">YouTube Channel URL</label>
              <input class="form-control" id="youtube_url" name="youtube_url" placeholder="https://www.youtube.com/@channelname" required {% if not can_manage_guild %}disabled{% endif %}>
            </div>
            <div class="col-12 col-md-6 col-xl-3">
              <label class="form-label" for="notify_channel_id">Discord Notify Channel</label>
              <select class="form-select" id="notify_channel_id" name="notify_channel_id" required {% if not can_manage_guild %}disabled{% endif %}>
                <option value="">Select channel...</option>
                {% for channel in notification_channels %}
                <option value="{{ channel.id }}">{{ channel.name }} ({{ channel.id }})</option>
                {% endfor %}
              </select>
            </div>
            <div class="col-12 col-md-6 col-xl-2">
              <label class="form-label" for="youtube_interval">Schedule</label>
              <select class="form-select" id="youtube_interval" name="poll_interval_seconds" {% if not can_manage_guild %}disabled{% endif %}>
                {% for option in feed_interval_options %}
                <option value="{{ option.value }}">{{ option.label }}</option>
                {% endfor %}
              </select>
            </div>
            <div class="col-12 col-xl-2">
              <label class="form-label d-block">Notify On</label>
              <div class="form-check">
                <input class="form-check-input" type="checkbox" id="youtube_include_uploads" name="include_uploads" value="1" checked {% if not can_manage_guild %}disabled{% endif %}>
                <label class="form-check-label" for="youtube_include_uploads">Uploads / Shorts</label>
              </div>
              <div class="form-check">
                <input class="form-check-input" type="checkbox" id="youtube_include_posts" name="include_community_posts" value="1" {% if not can_manage_guild %}disabled{% endif %}>
                <label class="form-check-label" for="youtube_include_posts">Community Posts</label>
              </div>
            </div>
            <div class="col-12 col-xl-1 d-flex align-items-end">
              <button class="btn btn-primary w-100" type="submit" {% if not can_manage_guild %}disabled{% endif %}>Add</button>
            </div>
          </div>
        </form>
        {% if not notification_channels %}
        <p class="small text-danger mt-2 mb-0">No text channels found. Verify bot guild/channel permissions and refresh.</p>
        {% endif %}
      </div>
      <div class="card card-soft p-3">
        <h2 class="h6 mb-3">Current Subscriptions</h2>
        <div class="table-wrap">
          <table class="table table-sm align-middle">
            <thead><tr><th>Created (UTC)</th><th>YouTube Channel</th><th>Notify Channel</th><th>Schedule</th><th>Notify On</th><th>Last Update</th><th>Action</th></tr></thead>
            <tbody>
              {% for row in subscriptions %}
              <tr>
                <td class="small">{{ row.created_at }}</td>
                <td class="small">
                  <div class="fw-semibold">{{ row.channel_title }}</div>
                  <div><a href="{{ row.source_url }}" target="_blank" rel="noreferrer">{{ row.source_url }}</a></div>
                </td>
                <td class="small">{{ row.target_channel_name }} ({{ row.target_channel_id }})</td>
                <td class="small">
                  {{ row.interval_label }}
                </td>
                <td class="small">
                  {% if row.include_uploads %}Uploads{% endif %}{% if row.include_uploads and row.include_community_posts %} + {% endif %}{% if row.include_community_posts %}Posts{% endif %}
                </td>
                <td class="small">
                  {% if row.last_video_id %}
                    {{ row.last_video_title or row.last_video_id }}<br>
                    <span class="text-secondary">{{ row.last_published_at or '-' }}</span>
                  {% elif row.last_community_post_id %}
                    {{ row.last_community_post_title or row.last_community_post_id }}<br>
                    <span class="text-secondary">{{ row.last_community_published_at or '-' }}</span>
                  {% else %}
                    -
                  {% endif %}
                </td>
                <td>
                  <form method="post" action="{{ url_for('youtube_delete', subscription_id=row.id) }}">
                    <button class="btn btn-sm btn-outline-danger" type="submit" {% if not can_manage_guild %}disabled{% endif %}>Delete</button>
                  </form>
                </td>
              </tr>
              {% else %}
              <tr><td colspan="7" class="text-secondary">No YouTube subscriptions yet.</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </div>
    {% elif page == "reddit" %}
      <div class="card card-soft p-3 mb-3">
        <h1 class="h5 mb-3">Reddit Feeds</h1>
        <form method="post" action="{{ url_for('reddit_add') }}">
          <div class="row g-2">
            <div class="col-12 col-xl-4">
              <label class="form-label" for="reddit_source">Reddit Forum</label>
              <input class="form-control" id="reddit_source" name="reddit_source" placeholder="r/python or https://www.reddit.com/r/python" required {% if not can_manage_guild %}disabled{% endif %}>
            </div>
            <div class="col-12 col-md-6 col-xl-4">
              <label class="form-label" for="reddit_channel_id">Discord Notify Channel</label>
              <select class="form-select" id="reddit_channel_id" name="notify_channel_id" required {% if not can_manage_guild %}disabled{% endif %}>
                <option value="">Select channel...</option>
                {% for channel in notification_channels %}
                <option value="{{ channel.id }}">{{ channel.name }} ({{ channel.id }})</option>
                {% endfor %}
              </select>
            </div>
            <div class="col-12 col-md-6 col-xl-3">
              <label class="form-label" for="reddit_interval">Schedule</label>
              <select class="form-select" id="reddit_interval" name="poll_interval_seconds" {% if not can_manage_guild %}disabled{% endif %}>
                {% for option in feed_interval_options %}
                <option value="{{ option.value }}">{{ option.label }}</option>
                {% endfor %}
              </select>
            </div>
            <div class="col-12 col-xl-1 d-flex align-items-end">
              <button class="btn btn-primary w-100" type="submit" {% if not can_manage_guild %}disabled{% endif %}>Add</button>
            </div>
          </div>
        </form>
        {% if not notification_channels %}
        <p class="small text-danger mt-2 mb-0">No text channels found. Verify bot guild/channel permissions and refresh.</p>
        {% endif %}
      </div>
      <div class="card card-soft p-3">
        <h2 class="h6 mb-3">Current Reddit Feeds</h2>
        <div class="table-wrap">
          <table class="table table-sm align-middle">
            <thead><tr><th>Created (UTC)</th><th>Subreddit</th><th>Notify Channel</th><th>Schedule</th><th>Last Post</th><th>Action</th></tr></thead>
            <tbody>
              {% for row in reddit_feeds %}
              <tr>
                <td class="small">{{ row.created_at }}</td>
                <td class="small">
                  <div class="fw-semibold">r/{{ row.subreddit_name }}</div>
                  <div><a href="{{ row.source_url }}" target="_blank" rel="noreferrer">{{ row.source_url }}</a></div>
                </td>
                <td class="small">{{ row.target_channel_name }} ({{ row.target_channel_id }})</td>
                <td class="small">{{ row.interval_label }}</td>
                <td class="small">
                  {% if row.last_post_id %}
                    <a href="{{ row.last_post_url }}" target="_blank" rel="noreferrer">{{ row.last_post_title or row.last_post_id }}</a><br>
                    <span class="text-secondary">{{ row.last_published_at or '-' }}</span>
                  {% else %}
                    -
                  {% endif %}
                </td>
                <td>
                  <form method="post" action="{{ url_for('reddit_delete', feed_id=row.id) }}">
                    <button class="btn btn-sm btn-outline-danger" type="submit" {% if not can_manage_guild %}disabled{% endif %}>Delete</button>
                  </form>
                </td>
              </tr>
              {% else %}
              <tr><td colspan="6" class="text-secondary">No Reddit feeds yet.</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </div>
    {% elif page == "wordpress" %}
      <div class="card card-soft p-3 mb-3">
        <h1 class="h5 mb-3">WordPress Notifications</h1>
        <form method="post" action="{{ url_for('wordpress_add') }}">
          <div class="row g-2">
            <div class="col-12 col-xl-4">
              <label class="form-label" for="wordpress_site_url">WordPress Site URL</label>
              <input class="form-control" id="wordpress_site_url" name="wordpress_site_url" placeholder="https://wickedyoda.com" required {% if not can_manage_guild %}disabled{% endif %}>
            </div>
            <div class="col-12 col-md-6 col-xl-4">
              <label class="form-label" for="wordpress_channel_id">Discord Notify Channel</label>
              <select class="form-select" id="wordpress_channel_id" name="notify_channel_id" required {% if not can_manage_guild %}disabled{% endif %}>
                <option value="">Select channel...</option>
                {% for channel in notification_channels %}
                <option value="{{ channel.id }}">{{ channel.name }} ({{ channel.id }})</option>
                {% endfor %}
              </select>
            </div>
            <div class="col-12 col-md-6 col-xl-3">
              <label class="form-label" for="wordpress_interval">Schedule</label>
              <select class="form-select" id="wordpress_interval" name="poll_interval_seconds" {% if not can_manage_guild %}disabled{% endif %}>
                {% for option in feed_interval_options %}
                <option value="{{ option.value }}">{{ option.label }}</option>
                {% endfor %}
              </select>
            </div>
            <div class="col-12 col-xl-1 d-flex align-items-end">
              <button class="btn btn-primary w-100" type="submit" {% if not can_manage_guild %}disabled{% endif %}>Add</button>
            </div>
          </div>
        </form>
        {% if not notification_channels %}
        <p class="small text-danger mt-2 mb-0">No text channels found. Verify bot guild/channel permissions and refresh.</p>
        {% endif %}
      </div>
      <div class="card card-soft p-3">
        <h2 class="h6 mb-3">Current WordPress Feeds</h2>
        <div class="table-wrap">
          <table class="table table-sm align-middle">
            <thead><tr><th>Created (UTC)</th><th>Site</th><th>Notify Channel</th><th>Schedule</th><th>Last Post</th><th>Action</th></tr></thead>
            <tbody>
              {% for row in wordpress_feeds %}
              <tr>
                <td class="small">{{ row.created_at }}</td>
                <td class="small">
                  <div class="fw-semibold">{{ row.site_title }}</div>
                  <div><a href="{{ row.site_url }}" target="_blank" rel="noreferrer">{{ row.site_url }}</a></div>
                  <div class="text-secondary">{{ row.feed_url }}</div>
                </td>
                <td class="small">{{ row.target_channel_name }} ({{ row.target_channel_id }})</td>
                <td class="small">{{ row.interval_label }}</td>
                <td class="small">
                  {% if row.last_post_id %}
                    <a href="{{ row.last_post_url }}" target="_blank" rel="noreferrer">{{ row.last_post_title or row.last_post_id }}</a><br>
                    <span class="text-secondary">{{ row.last_published_at or '-' }}</span>
                  {% else %}
                    -
                  {% endif %}
                </td>
                <td>
                  <form method="post" action="{{ url_for('wordpress_delete', feed_id=row.id) }}">
                    <button class="btn btn-sm btn-outline-danger" type="submit" {% if not can_manage_guild %}disabled{% endif %}>Delete</button>
                  </form>
                </td>
              </tr>
              {% else %}
              <tr><td colspan="6" class="text-secondary">No WordPress feeds yet.</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </div>
    {% elif page == "linkedin" %}
      <div class="card card-soft p-3 mb-3">
        <h1 class="h5 mb-2">LinkedIn Notifications</h1>
        <p class="small text-secondary mb-3">Experimental. Works only for public LinkedIn profiles/pages where recent activity is accessible without login.</p>
        <form method="post" action="{{ url_for('linkedin_add') }}">
          <div class="row g-2">
            <div class="col-12 col-xl-4">
              <label class="form-label" for="linkedin_profile_url">LinkedIn Profile/Page URL</label>
              <input class="form-control" id="linkedin_profile_url" name="linkedin_profile_url" placeholder="https://www.linkedin.com/in/example" required {% if not can_manage_guild %}disabled{% endif %}>
            </div>
            <div class="col-12 col-md-6 col-xl-4">
              <label class="form-label" for="linkedin_channel_id">Discord Notify Channel</label>
              <select class="form-select" id="linkedin_channel_id" name="notify_channel_id" required {% if not can_manage_guild %}disabled{% endif %}>
                <option value="">Select channel...</option>
                {% for channel in notification_channels %}
                <option value="{{ channel.id }}">{{ channel.name }} ({{ channel.id }})</option>
                {% endfor %}
              </select>
            </div>
            <div class="col-12 col-md-6 col-xl-3">
              <label class="form-label" for="linkedin_interval">Schedule</label>
              <select class="form-select" id="linkedin_interval" name="poll_interval_seconds" {% if not can_manage_guild %}disabled{% endif %}>
                {% for option in feed_interval_options %}
                <option value="{{ option.value }}">{{ option.label }}</option>
                {% endfor %}
              </select>
            </div>
            <div class="col-12 col-xl-1 d-flex align-items-end">
              <button class="btn btn-primary w-100" type="submit" {% if not can_manage_guild %}disabled{% endif %}>Add</button>
            </div>
          </div>
        </form>
        {% if not notification_channels %}
        <p class="small text-danger mt-2 mb-0">No text channels found. Verify bot guild/channel permissions and refresh.</p>
        {% endif %}
      </div>
      <div class="card card-soft p-3">
        <h2 class="h6 mb-3">Current LinkedIn Feeds</h2>
        <div class="table-wrap">
          <table class="table table-sm align-middle">
            <thead><tr><th>Created (UTC)</th><th>Profile</th><th>Notify Channel</th><th>Schedule</th><th>Last Post</th><th>Action</th></tr></thead>
            <tbody>
              {% for row in linkedin_feeds %}
              <tr>
                <td class="small">{{ row.created_at }}</td>
                <td class="small">
                  <div class="fw-semibold">{{ row.profile_label }}</div>
                  <div><a href="{{ row.profile_url }}" target="_blank" rel="noreferrer">{{ row.profile_url }}</a></div>
                  <div class="text-secondary">{{ row.activity_url }}</div>
                </td>
                <td class="small">{{ row.target_channel_name }} ({{ row.target_channel_id }})</td>
                <td class="small">{{ row.interval_label }}</td>
                <td class="small">
                  {% if row.last_post_id %}
                    <a href="{{ row.last_post_url }}" target="_blank" rel="noreferrer">{{ row.last_post_title or row.last_post_id }}</a><br>
                    <span class="text-secondary">{{ row.last_published_at or '-' }}</span>
                  {% else %}
                    -
                  {% endif %}
                </td>
                <td>
                  <form method="post" action="{{ url_for('linkedin_delete', feed_id=row.id) }}">
                    <button class="btn btn-sm btn-outline-danger" type="submit" {% if not can_manage_guild %}disabled{% endif %}>Delete</button>
                  </form>
                </td>
              </tr>
              {% else %}
              <tr><td colspan="6" class="text-secondary">No LinkedIn feeds yet.</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </div>
    {% elif page == "spicy_prompts" %}
      <div class="card card-soft p-3 mb-3">
        <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-center gap-3">
          <div>
            <h1 class="h5 mb-1">Spicy Prompts</h1>
            <p class="small text-secondary mb-0">Refresh prompt packs from the configured GitHub repo without restarting the bot. This only updates cached prompt data.</p>
          </div>
          <form method="post" action="{{ url_for('spicy_prompts_refresh') }}">
            <button class="btn btn-primary" type="submit" {% if not session.get("is_admin") %}disabled{% endif %}>Refresh From Repo</button>
          </form>
        </div>
      </div>
      <div class="card card-soft p-3 mb-3">
        <h2 class="h6 mb-3">Guild Access Control</h2>
        <form method="post" action="{{ url_for('spicy_prompts_settings_save') }}">
          <div class="row g-3">
            <div class="col-12 col-lg-4">
              <div class="form-check mt-4">
                <input class="form-check-input" type="checkbox" id="spicy_prompts_enabled" name="spicy_prompts_enabled" value="1" {% if spicy_settings.spicy_prompts_enabled %}checked{% endif %} {% if not can_manage_guild %}disabled{% endif %}>
                <label class="form-check-label" for="spicy_prompts_enabled">Enable `/spicy` for this guild</label>
              </div>
            </div>
            <div class="col-12 col-lg-8">
              <label class="form-label" for="spicy_prompts_channel_id">Allowed Channel</label>
              <select class="form-select" id="spicy_prompts_channel_id" name="spicy_prompts_channel_id" {% if not can_manage_guild %}disabled{% endif %}>
                <option value="">Select age-restricted channel...</option>
                {% for channel in notification_channels %}
                <option value="{{ channel.id }}" {% if selected_spicy_channel_id == channel.id|string %}selected{% endif %}>
                  {{ channel.name }}{% if channel.nsfw %} [18+]{% endif %} ({{ channel.id }})
                </option>
                {% endfor %}
              </select>
              <div class="form-text">`/spicy` only works in the configured age-restricted channel. Non-NSFW channels are rejected.</div>
            </div>
            <div class="col-12">
              <button class="btn btn-primary" type="submit" {% if not can_manage_guild %}disabled{% endif %}>Save Spicy Prompt Settings</button>
            </div>
          </div>
        </form>
      </div>
      <div class="row g-3 mb-3">
        <div class="col-12 col-md-6 col-xl-3">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">Feature Enabled</p>
            <p class="mb-0 fw-semibold">{{ "Yes" if spicy_prompts.enabled else "No" }}</p>
          </div>
        </div>
        <div class="col-12 col-md-6 col-xl-3">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">Cached Packs</p>
            <p class="mb-0 fw-semibold">{{ spicy_prompts.pack_count }}</p>
          </div>
        </div>
        <div class="col-12 col-md-6 col-xl-3">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">Cached Prompts</p>
            <p class="mb-0 fw-semibold">{{ spicy_prompts.prompt_count }}</p>
          </div>
        </div>
        <div class="col-12 col-md-6 col-xl-3">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">Last Success</p>
            <p class="mb-0 fw-semibold">{{ spicy_prompts.last_success_at or "-" }}</p>
          </div>
        </div>
      </div>
      <div class="card card-soft p-3 mb-3">
        <h2 class="h6 mb-3">Repository</h2>
        <div class="row g-2">
          <div class="col-12">
            <div class="small text-secondary">Repo URL</div>
            <div class="fw-semibold">{{ spicy_prompts.repo_url or "-" }}</div>
          </div>
          <div class="col-12 col-lg-4">
            <div class="small text-secondary">Branch</div>
            <div class="fw-semibold">{{ spicy_prompts.repo_branch or "-" }}</div>
          </div>
          <div class="col-12 col-lg-8">
            <div class="small text-secondary">Manifest Path</div>
            <div class="fw-semibold">{{ spicy_prompts.manifest_path or "-" }}</div>
          </div>
          <div class="col-12">
            <div class="small text-secondary">Resolved Manifest URL</div>
            <div class="small">{{ spicy_prompts.manifest_url or "-" }}</div>
          </div>
          {% if spicy_prompts.last_error %}
          <div class="col-12">
            <div class="alert alert-warning mb-0">
              <strong>Last refresh error:</strong> {{ spicy_prompts.last_error }}
            </div>
          </div>
          {% endif %}
        </div>
      </div>
      <div class="card card-soft p-3 mb-3">
        <h2 class="h6 mb-3">Prompt Packs</h2>
        <div class="table-wrap">
          <table class="table table-sm align-middle">
            <thead><tr><th>Pack</th><th>Source Path</th><th>Prompts</th><th>Updated</th></tr></thead>
            <tbody>
              {% for row in spicy_prompts.packs %}
              <tr>
                <td class="small">
                  <div class="fw-semibold">{{ row.pack_name }}</div>
                  <div class="text-secondary">{{ row.pack_id }}</div>
                </td>
                <td class="small">{{ row.source_path }}</td>
                <td class="small">{{ row.prompt_count }}</td>
                <td class="small">{{ row.updated_at or "-" }}</td>
              </tr>
              {% else %}
              <tr><td colspan="4" class="text-secondary">No cached prompt packs yet. Use Refresh From Repo after populating the content repo.</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </div>
      <div class="card card-soft p-3">
        <h2 class="h6 mb-3">Prompt Preview</h2>
        <div class="table-wrap">
          <table class="table table-sm align-middle">
            <thead><tr><th>Pack</th><th>Type</th><th>Category</th><th>Prompt</th><th>Tags</th></tr></thead>
            <tbody>
              {% for row in spicy_prompts.preview %}
              <tr>
                <td class="small">{{ row.pack_id }}</td>
                <td class="small">{{ row.prompt_type }}</td>
                <td class="small">{{ row.category }}</td>
                <td class="small">{{ row.text }}</td>
                <td class="small">{{ row.tags|join(", ") if row.tags else "-" }}</td>
              </tr>
              {% else %}
              <tr><td colspan="5" class="text-secondary">No cached prompts yet.</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </div>
    {% elif page == "logs" %}
      <div class="card card-soft p-3 mb-3">
        <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-2 mb-3">
          <div>
            <h1 class="h5 mb-1">Logs</h1>
            <p class="text-secondary small mb-0">Download or preview the latest log files.</p>
          </div>
          <a class="btn btn-outline-primary btn-sm" href="{{ url_for('logs_download') }}">Export all logs (ZIP)</a>
        </div>
        <form method="get" class="row g-2">
          <input type="hidden" name="_" value="1">
          <div class="col-12 col-lg-4">
            <label class="form-label" for="log">Log File</label>
            <select class="form-select" id="log" name="log" onchange="this.form.submit()">
              {% for option in log_options %}
              <option value="{{ option }}" {% if option == selected_log %}selected{% endif %}>{{ option }}</option>
              {% endfor %}
            </select>
          </div>
          <div class="col-12 col-lg-3">
            <label class="form-label" for="refresh_interval">Auto Refresh</label>
            <select class="form-select" id="refresh_interval" name="refresh" onchange="this.form.submit()">
              {% for interval in refresh_interval_options %}
              <option value="{{ interval }}" {% if interval == selected_refresh_interval %}selected{% endif %}>
                {% if interval == 0 %}Off{% else %}{{ interval }}s{% endif %}
              </option>
              {% endfor %}
            </select>
          </div>
        </form>
      </div>
      <div class="card card-soft p-3">
        <pre class="small mb-0 mobile-pre">{{ log_preview }}</pre>
      </div>
    {% elif page == "guilds" %}
      <div class="card card-soft p-3 mb-3">
        <h1 class="h5 mb-2">Discord Servers</h1>
        <p class="text-secondary mb-0">Choose which server the web GUI is currently managing. Guild-scoped pages use the selected server context.</p>
            <div class="card card-soft p-3 mb-3">
        <div class="d-flex align-items-center justify-content-between mb-2">
          <h2 class="h6 mb-0">Command Status</h2>
          <a class="small" href="{{ url_for('command_permissions') }}">Manage</a>
        </div>
        {% if command_statuses %}
        <div class="table-wrap">
          <table class="table table-sm align-middle">
            <thead>
              <tr>
                <th>Command</th>
                <th>Access</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {% for command in command_statuses %}
              <tr>
                <td>
                  <div class="fw-semibold">{{ command.label }}</div>
                  {% if command.description %}
                  <div class="text-secondary small">{{ command.description }}</div>
                  {% endif %}
                </td>
                <td class="small">{{ command.access }}</td>
                <td>
                  {% if command.enabled %}
                  <span class="badge text-bg-success">Enabled</span>
                  {% else %}
                  <span class="badge text-bg-secondary">Disabled</span>
                  {% endif %}
                </td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
        {% else %}
        <p class="text-secondary small mb-0">Command status is unavailable.</p>
        {% endif %}
      </div>
</div>
      <div class="row g-3">
        {% for guild in guild_cards %}
        <div class="col-12 col-lg-6">
          <div class="card card-soft p-3 h-100">
            <div class="d-flex justify-content-between align-items-start gap-3 mb-2">
              <div>
                <h2 class="h6 mb-1">{{ guild.name }}</h2>
                <p class="small text-secondary mb-1">{{ guild.id }}</p>
                {% if guild.member_count is not none %}
                <p class="small text-secondary mb-0">Members: {{ guild.member_count }}</p>
                {% endif %}
              </div>
              {% if guild.selected %}
              <span class="badge text-bg-primary">Selected</span>
              {% endif %}
            </div>
            <form method="post" action="{{ url_for('select_guild') }}">
              <input type="hidden" name="guild_id" value="{{ guild.id }}">
              <input type="hidden" name="next_endpoint" value="dashboard">
              <button class="btn btn-primary btn-sm guild-card-action" type="submit" {% if guild.selected %}disabled{% endif %}>
                {% if guild.selected %}Currently Selected{% else %}Manage This Server{% endif %}
              </button>
            </form>
            {% if session.get("is_admin") %}
            <form method="post" action="{{ url_for('leave_guild_route') }}" class="mt-2" onsubmit="return confirm('Leave {{ guild.name|escape }}? The bot will immediately leave this server.');">
              <input type="hidden" name="guild_id" value="{{ guild.id }}">
              <button class="btn btn-outline-danger btn-sm guild-card-action" type="submit">Leave Guild</button>
            </form>
            {% endif %}
          </div>
        </div>
        {% else %}
        <div class="col-12">
          <div class="card card-soft p-3">
            <p class="text-secondary mb-0">No Discord servers are currently available to this bot.</p>
          </div>
        </div>
        {% endfor %}
      </div>
    {% elif page == "documentation" %}
      <div class="card card-soft p-3 mb-3">
        <div class="d-flex justify-content-between align-items-center gap-2">
          <div>
            <h1 class="h5 mb-1">Documentation</h1>
            <p class="text-secondary mb-0">Browse wiki pages packaged with this bot image.</p>
          </div>
          {% if github_wiki_url %}
          <a class="btn btn-outline-primary btn-sm" href="{{ github_wiki_url }}" target="_blank" rel="noreferrer">Open GitHub Wiki</a>
          {% endif %}
        </div>
            <div class="card card-soft p-3 mb-3">
        <div class="d-flex align-items-center justify-content-between mb-2">
          <h2 class="h6 mb-0">Command Status</h2>
          <a class="small" href="{{ url_for('command_permissions') }}">Manage</a>
        </div>
        {% if command_statuses %}
        <div class="table-wrap">
          <table class="table table-sm align-middle">
            <thead>
              <tr>
                <th>Command</th>
                <th>Access</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {% for command in command_statuses %}
              <tr>
                <td>
                  <div class="fw-semibold">{{ command.label }}</div>
                  {% if command.description %}
                  <div class="text-secondary small">{{ command.description }}</div>
                  {% endif %}
                </td>
                <td class="small">{{ command.access }}</td>
                <td>
                  {% if command.enabled %}
                  <span class="badge text-bg-success">Enabled</span>
                  {% else %}
                  <span class="badge text-bg-secondary">Disabled</span>
                  {% endif %}
                </td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
        {% else %}
        <p class="text-secondary small mb-0">Command status is unavailable.</p>
        {% endif %}
      </div>
</div>
      <div class="row g-3">
        <div class="col-12 col-lg-4">
          <div class="card card-soft p-3 h-100">
            <h2 class="h6 mb-3">Pages</h2>
            <div class="list-group list-group-flush documentation-sidebar">
              {% for item in documentation_pages %}
              <a class="list-group-item list-group-item-action documentation-link {% if item.slug == selected_doc_slug %}active{% endif %}" href="{{ url_for('documentation_page', page_slug=item.slug) }}">
                <div class="fw-semibold">{{ item.label }}</div>
                <div class="small {% if item.slug == selected_doc_slug %}text-white-50{% else %}text-secondary{% endif %}">{{ item.filename }}</div>
              </a>
              {% endfor %}
            </div>
          </div>
        </div>
        <div class="col-12 col-lg-8">
          <div class="card card-soft p-3">
            <h2 class="h6 mb-3">{{ documentation_title }}</h2>
            <pre class="small mb-0 mobile-pre">{{ documentation_content }}</pre>
          </div>
        </div>
      </div>
    {% elif page == "wiki" %}
      <div class="card card-soft p-3 mb-3">
        <h1 class="h5 mb-3">Wiki</h1>
        <form method="get" class="row g-2">
          <div class="col-12 col-lg-5">
            <label class="form-label" for="doc">Document</label>
            <select class="form-select" id="doc" name="doc" onchange="this.form.submit()">
              {% for option in wiki_files %}
              <option value="{{ option }}" {% if option == selected_wiki %}selected{% endif %}>{{ option }}</option>
              {% endfor %}
            </select>
          </div>
          <div class="col-12 col-lg-7 d-flex align-items-end">
            {% if github_wiki_url %}
            <a class="btn btn-outline-primary ms-lg-auto" href="{{ github_wiki_url }}" target="_blank" rel="noreferrer">Open GitHub Wiki</a>
            {% endif %}
          </div>
        </form>
      </div>
      <div class="card card-soft p-3">
        <pre class="small mb-0" style="white-space: pre-wrap;">{{ wiki_content }}</pre>
      </div>
    {% elif page == "command_permissions" %}
      <div class="card card-soft p-3">
        <h1 class="h5 mb-3">Command Permissions</h1>
        <p class="small text-secondary">Set command access mode, disable commands, and optionally restrict access to selected roles.</p>
        <form method="post" action="{{ url_for('command_permissions') }}">
          <div class="table-wrap">
            <table class="table table-sm align-middle">
              <thead><tr><th>Command</th><th>Default</th><th>Mode</th><th>Custom Role IDs</th></tr></thead>
              <tbody>
                {% for item in command_permissions.commands %}
                <tr data-command-row="{{ item.key }}">
                  <td class="small">
                    <div class="fw-semibold">{{ item.label }}</div>
                    <div class="text-secondary">{{ item.description }}</div>
                    <input type="hidden" name="command_key" value="{{ item.key }}">
                  </td>
                  <td class="small">{{ item.default_policy_label }}</td>
                  <td>
                    <select class="form-select" name="mode__{{ item.key }}" data-mode-select="{{ item.key }}" {% if not can_manage_guild %}disabled{% endif %}>
                      <option value="default" {% if item.mode == "default" %}selected{% endif %}>Default</option>
                      <option value="disabled" {% if item.mode == "disabled" %}selected{% endif %}>Disabled</option>
                      <option value="public" {% if item.mode == "public" %}selected{% endif %}>Public</option>
                      <option value="custom_roles" {% if item.mode == "custom_roles" %}selected{% endif %}>Custom roles</option>
                    </select>
                  </td>
                  <td>
                    <div class="command-roles" data-role-container="{{ item.key }}">
                      {% if role_options %}
                      <select class="form-select mb-2" name="role_ids__{{ item.key }}" multiple size="5" {% if not can_manage_guild %}disabled{% endif %}>
                        {% for role in role_options %}
                        <option value="{{ role.id }}" {% if role.id|string in item.role_id_strings %}selected{% endif %}>{{ role.name }} ({{ role.id }})</option>
                        {% endfor %}
                      </select>
                      {% endif %}
                      <input class="form-control" name="role_ids_text__{{ item.key }}" value="{{ item.role_ids_csv }}" placeholder="Comma-separated role IDs" {% if not can_manage_guild %}disabled{% endif %}>
                    </div>
                  </td>
                </tr>
                {% endfor %}
              </tbody>
            </table>
          </div>
                    <script>
            function toggleRoleInputs() {
              document.querySelectorAll('[data-mode-select]').forEach((select) => {
                const key = select.getAttribute('data-mode-select');
                const container = document.querySelector(`[data-role-container="${key}"]`);
                if (!container) {
                  return;
                }
                const isCustom = select.value === 'custom_roles';
                container.style.display = isCustom ? '' : 'none';
                container.querySelectorAll('select, input').forEach((el) => {
                  if (select.disabled) {
                    el.disabled = true;
                  } else {
                    el.disabled = !isCustom;
                  }
                });
              });
            }
            document.addEventListener('DOMContentLoaded', toggleRoleInputs);
            document.addEventListener('change', (event) => {
              if (event.target && event.target.matches('[data-mode-select]')) {
                toggleRoleInputs();
              }
            });
          </script>
          <button class="btn btn-primary" type="submit" {% if not can_manage_guild %}disabled{% endif %}>Save Command Permissions</button>
        </form>
      </div>
    {% elif page == "tag_responses" %}
      <div class="card card-soft p-3">
        <h1 class="h5 mb-3">Tag Responses</h1>
        <p class="small text-secondary">Edit JSON mapping used by `/tag`, `/tags`, and `!tag` message shortcuts.</p>
        <form method="post" action="{{ url_for('tag_responses') }}">
          <div class="mb-3">
            <textarea class="form-control font-monospace" rows="18" name="tag_json" {% if not can_manage_guild %}disabled{% endif %}>{{ tag_json }}</textarea>
          </div>
          <button class="btn btn-primary" type="submit" {% if not can_manage_guild %}disabled{% endif %}>Save Tag Responses</button>
        </form>
      </div>
    {% elif page == "users" %}
      <div class="card card-soft p-3 mb-3">
        <h1 class="h5 mb-3">Users</h1>
        <form method="post" action="{{ url_for('users_add') }}">
          <div class="row g-2">
            <div class="col-12 col-lg-2">
              <label class="form-label" for="new_display_name">Display Name</label>
              <input class="form-control" id="new_display_name" name="display_name" {% if not session.get("is_admin") %}disabled{% endif %}>
            </div>
            <div class="col-12 col-lg-2">
              <label class="form-label" for="new_first_name">First Name</label>
              <input class="form-control" id="new_first_name" name="first_name" {% if not session.get("is_admin") %}disabled{% endif %}>
            </div>
            <div class="col-12 col-lg-2">
              <label class="form-label" for="new_last_name">Last Name</label>
              <input class="form-control" id="new_last_name" name="last_name" {% if not session.get("is_admin") %}disabled{% endif %}>
            </div>
            <div class="col-12 col-lg-3">
              <label class="form-label" for="new_email">Email</label>
              <input class="form-control" id="new_email" name="email" type="email" required {% if not session.get("is_admin") %}disabled{% endif %}>
            </div>
            <div class="col-12 col-lg-3">
              <label class="form-label" for="new_password">Password</label>
              <input class="form-control" id="new_password" name="password" type="password" required {% if not session.get("is_admin") %}disabled{% endif %}>
            </div>
            <div class="col-12 col-lg-2">
              <label class="form-label" for="new_role">Role</label>
              <select class="form-select" id="new_role" name="role" {% if not session.get("is_admin") %}disabled{% endif %}>
                <option value="read-only">Read-only</option>
                <option value="guild-admin">Guild Admin</option>
                <option value="admin">Admin</option>
              </select>
            </div>
            <div class="col-12 col-lg-1 d-flex align-items-end">
              <button class="btn btn-primary w-100" type="submit" {% if not session.get("is_admin") %}disabled{% endif %}>Add User</button>
            </div>
          </div>
        </form>
      </div>
      <div class="card card-soft p-3">
        <div class="table-wrap">
          <table class="table table-sm align-middle">
            <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Created</th><th>Manage</th></tr></thead>
            <tbody>
              {% for row in users %}
              <tr>
                <td>
                  <form method="post" action="{{ url_for('users_update') }}" class="row g-2">
                    <input type="hidden" name="current_email" value="{{ row.email }}">
                    <div class="col-12">
                      <input class="form-control form-control-sm" name="display_name" value="{{ row.display_name or '' }}" placeholder="Display name" {% if not session.get("is_admin") %}disabled{% endif %}>
                    </div>
                    <div class="col-12 col-md-6">
                      <input class="form-control form-control-sm" name="first_name" value="{{ row.first_name or '' }}" placeholder="First name" {% if not session.get("is_admin") %}disabled{% endif %}>
                    </div>
                    <div class="col-12 col-md-6">
                      <input class="form-control form-control-sm" name="last_name" value="{{ row.last_name or '' }}" placeholder="Last name" {% if not session.get("is_admin") %}disabled{% endif %}>
                    </div>
                    <div class="col-12">
                      <input class="form-control form-control-sm" name="email" type="email" value="{{ row.email }}" {% if not session.get("is_admin") %}disabled{% endif %}>
                    </div>
                </td>
                <td class="small">{{ row.email }}</td>
                <td>
                    <select class="form-select form-select-sm" name="role" {% if not session.get("is_admin") %}disabled{% endif %}>
                      <option value="read-only" {% if not row.is_admin and not row.is_guild_admin %}selected{% endif %}>Read-only</option>
                      <option value="guild-admin" {% if row.is_guild_admin %}selected{% endif %}>Guild Admin</option>
                      <option value="admin" {% if row.is_admin %}selected{% endif %}>Admin</option>
                    </select>
                </td>
                <td class="small">{{ row.created_at }}</td>
                <td>
                    <input class="form-control form-control-sm mb-2" name="new_password" type="password" placeholder="Reset password" {% if not session.get("is_admin") %}disabled{% endif %}>
                    <button class="btn btn-sm btn-primary me-2" type="submit" {% if not session.get("is_admin") %}disabled{% endif %}>Save</button>
                  </form>
                  {% if row.email != session.get("user") %}
                  <form method="post" action="{{ url_for('users_delete') }}" class="mt-2">
                    <input type="hidden" name="email" value="{{ row.email }}">
                    <button class="btn btn-sm btn-outline-danger" type="submit" {% if not session.get("is_admin") %}disabled{% endif %}>Delete</button>
                  </form>
                  {% else %}
                  <span class="small text-secondary">Current user</span>
                  {% endif %}
                </td>
              </tr>
              {% else %}
              <tr><td colspan="5" class="text-secondary">No users available.</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </div>
    {% elif page == "guild_access" %}
      <div class="card card-soft p-3 mb-3">
        <h1 class="h5 mb-3">Guild Access</h1>
        <p class="text-secondary small mb-3">Create groups of guilds and assign users who can manage them.</p>
        <form method="post" action="{{ url_for('guild_access_create') }}">
          <div class="row g-2 align-items-end">
            <div class="col-12 col-lg-6">
              <label class="form-label" for="group_name">Group Name</label>
              <input class="form-control" id="group_name" name="group_name" placeholder="Community Moderators" required>
            </div>
            <div class="col-12 col-lg-2">
              <button class="btn btn-primary w-100" type="submit">Create Group</button>
            </div>
          </div>
        </form>
      </div>
      <div class="card card-soft p-3">
        <div class="table-wrap">
          <table class="table table-sm align-middle">
            <thead><tr><th>Group</th><th>Guilds</th><th>Users</th><th>Actions</th></tr></thead>
            <tbody>
              {% for group in guild_access_groups %}
              <tr>
                <td class="fw-semibold">{{ group.name }}</td>
                <td>
                  <form method="post" action="{{ url_for('guild_access_update') }}" class="d-grid gap-2">
                    <input type="hidden" name="group_id" value="{{ group.id }}">
                    <select class="form-select" name="guild_ids" multiple size="6">
                      {% for guild in guild_access_guilds %}
                      <option value="{{ guild.id }}" {% if guild.id in group.guild_ids %}selected{% endif %}>{{ guild.name }}</option>
                      {% endfor %}
                    </select>
                </td>
                <td>
                    <select class="form-select" name="user_emails" multiple size="6">
                      {% for user in guild_access_users %}
                      <option value="{{ user.email }}" {% if user.email in group.user_emails %}selected{% endif %}>{{ user.display_name or user.email }}</option>
                      {% endfor %}
                    </select>
                </td>
                <td>
                    <button class="btn btn-sm btn-primary w-100" type="submit">Save</button>
                  </form>
                  <form method="post" action="{{ url_for('guild_access_delete') }}" class="mt-2" onsubmit="return confirm('Delete this guild access group?');">
                    <input type="hidden" name="group_id" value="{{ group.id }}">
                    <button class="btn btn-sm btn-outline-danger w-100" type="submit">Delete</button>
                  </form>
                </td>
              </tr>
              {% else %}
              <tr><td colspan="4" class="text-secondary">No guild access groups defined.</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </div>
    {% elif page == "observability" %}
      <div class="row g-3 mb-3">
        <div class="col-12 col-md-4">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">Process Uptime</p>
            <p class="mb-0 fs-5 fw-bold">{{ observability.uptime }}</p>
          </div>
        </div>
        <div class="col-12 col-md-4">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">Process CPU</p>
            <p class="mb-0 fs-5 fw-bold">{{ observability.process_cpu }}</p>
          </div>
        </div>
        <div class="col-12 col-md-4">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">RSS Memory</p>
            <p class="mb-0 fs-5 fw-bold">{{ observability.rss }}</p>
          </div>
        </div>
      </div>
      <div class="row g-3 mb-3">
        <div class="col-12 col-md-6">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">Read I/O Rate</p>
            <p class="mb-0 fs-5 fw-bold">{{ observability.io_read }}</p>
          </div>
        </div>
        <div class="col-12 col-md-6">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">Write I/O Rate</p>
            <p class="mb-0 fs-5 fw-bold">{{ observability.io_write }}</p>
          </div>
        </div>
      </div>
      <div class="card card-soft p-3">
        <h1 class="h5 mb-3">Observability</h1>
        <p class="small text-secondary mb-2">Sampled at {{ observability.sampled_at }} UTC.</p>
        <div class="table-wrap">
          <table class="table table-sm align-middle">
            <thead><tr><th>Metric</th><th>Current</th><th>Min</th><th>Avg</th><th>Max</th></tr></thead>
            <tbody>
              {% for row in observability_rows %}
              <tr>
                <td>{{ row.label }}</td>
                <td>{{ row.current }}</td>
                <td>{{ row.min }}</td>
                <td>{{ row.avg }}</td>
                <td>{{ row.max }}</td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </div>
    {% elif page == "bot_profile" %}
      <div class="card card-soft p-3 mb-3">
        <h1 class="h5 mb-3">Bot Profile</h1>
        {% if bot_profile.ok %}
        <div class="row g-3">
          <div class="col-12 col-lg-4">
            {% if bot_profile.avatar_url %}
            <img src="{{ bot_profile.avatar_url }}" alt="Bot Avatar" class="img-fluid rounded border">
            {% else %}
            <div class="small text-secondary">No avatar available.</div>
            {% endif %}
          </div>
          <div class="col-12 col-lg-8">
            <p class="mb-1"><strong>Username:</strong> {{ bot_profile.name }}</p>
            <p class="mb-1"><strong>Global Name:</strong> {{ bot_profile.global_name or "-" }}</p>
            <p class="mb-1"><strong>Server Nickname:</strong> {{ bot_profile.server_nickname or "-" }}</p>
            <p class="mb-1"><strong>Guild:</strong> {{ bot_profile.guild_name or "-" }}</p>
            <p class="mb-0"><strong>Bot ID:</strong> {{ bot_profile.id }}</p>
          </div>
        </div>
        {% else %}
        <p class="text-danger mb-0">{{ bot_profile.error or "Bot profile is unavailable." }}</p>
        {% endif %}
            <div class="card card-soft p-3 mb-3">
        <div class="d-flex align-items-center justify-content-between mb-2">
          <h2 class="h6 mb-0">Command Status</h2>
          <a class="small" href="{{ url_for('command_permissions') }}">Manage</a>
        </div>
        {% if command_statuses %}
        <div class="table-wrap">
          <table class="table table-sm align-middle">
            <thead>
              <tr>
                <th>Command</th>
                <th>Access</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {% for command in command_statuses %}
              <tr>
                <td>
                  <div class="fw-semibold">{{ command.label }}</div>
                  {% if command.description %}
                  <div class="text-secondary small">{{ command.description }}</div>
                  {% endif %}
                </td>
                <td class="small">{{ command.access }}</td>
                <td>
                  {% if command.enabled %}
                  <span class="badge text-bg-success">Enabled</span>
                  {% else %}
                  <span class="badge text-bg-secondary">Disabled</span>
                  {% endif %}
                </td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
        {% else %}
        <p class="text-secondary small mb-0">Command status is unavailable.</p>
        {% endif %}
      </div>
</div>
      <div class="row g-3">
        <div class="col-12 col-lg-6">
          <div class="card card-soft p-3 h-100">
            <h2 class="h6 mb-3">Update Identity</h2>
            <form method="post" action="{{ url_for('bot_profile') }}">
              <input type="hidden" name="action" value="identity">
              <div class="mb-3">
                <label class="form-label" for="bot_name">Bot Username (optional)</label>
                <input class="form-control" id="bot_name" name="bot_name" placeholder="WickedYodaBot" {% if not can_manage_guild %}disabled{% endif %}>
                <div class="form-text">Leave blank to keep current username.</div>
              </div>
              <div class="mb-3">
                <label class="form-label" for="server_nickname">Server Nickname (optional)</label>
                <input class="form-control" id="server_nickname" name="server_nickname" placeholder="Wicked Yoda's Little Helper" {% if not can_manage_guild %}disabled{% endif %}>
                <div class="form-text">Nickname applies only to selected guild.</div>
              </div>
              <div class="form-check mb-3">
                <input class="form-check-input" type="checkbox" id="clear_server_nickname" name="clear_server_nickname" value="1" {% if not can_manage_guild %}disabled{% endif %}>
                <label class="form-check-label" for="clear_server_nickname">Clear server nickname</label>
              </div>
              <button class="btn btn-primary" type="submit" {% if not can_manage_guild %}disabled{% endif %}>Update Bot Profile</button>
            </form>
          </div>
        </div>
        <div class="col-12 col-lg-6">
          <div class="card card-soft p-3 h-100">
            <h2 class="h6 mb-3">Update Avatar</h2>
            <p class="small text-secondary">Upload PNG/JPG/JPEG/WEBP/GIF image (max {{ max_avatar_upload_bytes }} bytes).</p>
            <form method="post" action="{{ url_for('bot_profile') }}" enctype="multipart/form-data">
              <input type="hidden" name="action" value="avatar">
              <div class="mb-3">
                <label class="form-label" for="avatar_file">Avatar Image</label>
                <input class="form-control" id="avatar_file" name="avatar_file" type="file" accept=".png,.jpg,.jpeg,.webp,.gif,image/*" required {% if not can_manage_guild %}disabled{% endif %}>
              </div>
              <button class="btn btn-primary" type="submit" {% if not can_manage_guild %}disabled{% endif %}>Upload Avatar</button>
            </form>
          </div>
        </div>
      </div>
    {% elif page == "account" %}
      <div class="card card-soft p-3">
        <h1 class="h5 mb-3">Account</h1>
        {% if session.get("password_rotation_required") %}
        <div class="alert alert-warning">Password rotation is required. Update your password before continuing.</div>
        {% endif %}
        <div class="row g-3">
          <div class="col-12 col-xl-7">
            <form method="post" action="{{ url_for('account') }}">
              <input type="hidden" name="action" value="profile">
              <div class="row g-2">
                <div class="col-12">
                  <label class="form-label" for="account_display_name">Display Name</label>
                  <input class="form-control" id="account_display_name" name="display_name" value="{{ account_user.display_name or '' }}">
                </div>
                <div class="col-12 col-md-6">
                  <label class="form-label" for="account_first_name">First Name</label>
                  <input class="form-control" id="account_first_name" name="first_name" value="{{ account_user.first_name or '' }}">
                </div>
                <div class="col-12 col-md-6">
                  <label class="form-label" for="account_last_name">Last Name</label>
                  <input class="form-control" id="account_last_name" name="last_name" value="{{ account_user.last_name or '' }}">
                </div>
              </div>
              <div class="mt-3">
                <label class="form-label" for="account_email">Email</label>
                <input class="form-control" id="account_email" name="email" type="email" value="{{ account_user.email or '' }}" required>
              </div>
              <div class="mt-3">
                <label class="form-label" for="account_profile_password">Current Password</label>
                <input class="form-control" id="account_profile_password" name="current_password" type="password" required>
                <div class="form-text">Required to change your email or name.</div>
              </div>
              <button class="btn btn-primary mt-3" type="submit">Update Profile</button>
            </form>
          </div>
          <div class="col-12 col-xl-5">
            <form method="post" action="{{ url_for('account') }}">
              <input type="hidden" name="action" value="password">
              <div class="mb-3">
                <label class="form-label" for="current_password">Current Password</label>
                <input class="form-control" id="current_password" name="current_password" type="password" required>
              </div>
              <div class="mb-3">
                <label class="form-label" for="new_password">New Password</label>
                <input class="form-control" id="new_password" name="new_password" type="password" {% if session.get("password_rotation_required") %}required{% endif %}>
              </div>
              <div class="mb-3">
                <label class="form-label" for="confirm_new_password">Confirm New Password</label>
                <input class="form-control" id="confirm_new_password" name="confirm_new_password" type="password" {% if session.get("password_rotation_required") %}required{% endif %}>
              </div>
              <button class="btn btn-primary" type="submit">Update Password</button>
            </form>
          </div>
        </div>
      </div>
    {% elif page == "guild_settings" %}
      <div class="card card-soft p-3">
        <h1 class="h5 mb-3">Guild Settings</h1>
        <form method="post" action="{{ url_for('guild_settings') }}">
          <div class="mb-3">
            <label class="form-label" for="bot_log_channel_id">Bot Log Channel</label>
            <select class="form-select" id="bot_log_channel_id" name="bot_log_channel_id" {% if not can_manage_guild %}disabled{% endif %}>
              <option value="">Use global default (env Bot_Log_Channel)</option>
              {% for channel in notification_channels %}
              <option value="{{ channel.id }}" {% if selected_log_channel_id == channel.id|string %}selected{% endif %}>
                {{ channel.name }} ({{ channel.id }})
              </option>
              {% endfor %}
            </select>
            <div class="form-text">This guild-specific channel receives bot action logs and overrides the global env value.</div>
          </div>
          <div class="mb-3">
            <label class="form-label" for="uptime_alert_channel_id">Uptime Alert Channel</label>
            <select class="form-select" id="uptime_alert_channel_id" name="uptime_alert_channel_id" {% if not can_manage_guild %}disabled{% endif %}>
              <option value="">Use bot log channel</option>
              {% for channel in notification_channels %}
              <option value="{{ channel.id }}" {% if selected_uptime_channel_id == channel.id|string %}selected{% endif %}>
                {{ channel.name }} ({{ channel.id }})
              </option>
              {% endfor %}
            </select>
            <div class="form-text">Optional override for uptime monitor alerts; falls back to the bot log channel when unset.</div>
          </div>
          <button class="btn btn-primary" type="submit" {% if not can_manage_guild %}disabled{% endif %}>Save Guild Settings</button>
        </form>
      </div>
    {% elif page == "moderation" %}
      <div class="card card-soft p-3">
        <h1 class="h5 mb-3">Moderation</h1>
        <p class="text-secondary small mb-3">Configure per-guild bad word filters, warning limits, and automated actions.</p>
        <form method="post" action="{{ url_for('moderation') }}">
          <div class="mb-3">
            <label class="form-label" for="moderation_enabled">Moderation Filter</label>
            <select class="form-select" id="moderation_enabled" name="moderation_enabled" {% if not can_manage_guild %}disabled{% endif %}>
              <option value="0" {% if not moderation_settings.moderation_enabled %}selected{% endif %}>Disabled</option>
              <option value="1" {% if moderation_settings.moderation_enabled %}selected{% endif %}>Enabled</option>
            </select>
            <div class="form-text">When enabled, messages containing banned words trigger warnings.</div>
          </div>
          <div class="mb-3">
            <label class="form-label" for="moderation_words">Banned Words (one per line)</label>
            <textarea class="form-control" id="moderation_words" name="moderation_words" rows="6" {% if not can_manage_guild %}disabled{% endif %}>{{ moderation_words_text }}</textarea>
            <div class="form-text">Use single words or short phrases. Matching is case-insensitive.</div>
          </div>
          <div class="row g-3">
            <div class="col-12 col-md-4">
              <label class="form-label" for="moderation_warning_window_hours">Warning Window</label>
              <select class="form-select" id="moderation_warning_window_hours" name="moderation_warning_window_hours" {% if not can_manage_guild %}disabled{% endif %}>
                {% for value in moderation_window_options %}
                <option value="{{ value }}" {% if moderation_settings.moderation_warning_window_hours == value %}selected{% endif %}>{{ value }} hours</option>
                {% endfor %}
              </select>
            </div>
            <div class="col-12 col-md-4">
              <label class="form-label" for="moderation_warning_threshold">Max Warnings</label>
              <select class="form-select" id="moderation_warning_threshold" name="moderation_warning_threshold" {% if not can_manage_guild %}disabled{% endif %}>
                {% for value in moderation_threshold_options %}
                <option value="{{ value }}" {% if moderation_settings.moderation_warning_threshold == value %}selected{% endif %}>{{ value }} warnings</option>
                {% endfor %}
              </select>
            </div>
            <div class="col-12 col-md-4">
              <label class="form-label" for="moderation_action">Action</label>
              <select class="form-select" id="moderation_action" name="moderation_action" {% if not can_manage_guild %}disabled{% endif %}>
                <option value="timeout" {% if moderation_settings.moderation_action == "timeout" %}selected{% endif %}>Timeout / Mute</option>
                <option value="warn_only" {% if moderation_settings.moderation_action == "warn_only" %}selected{% endif %}>Warn Only</option>
              </select>
            </div>
          </div>
          <div class="row g-3 mt-1">
            <div class="col-12 col-md-4">
              <label class="form-label" for="moderation_timeout_minutes">Timeout Duration</label>
              <select class="form-select" id="moderation_timeout_minutes" name="moderation_timeout_minutes" {% if not can_manage_guild %}disabled{% endif %}>
                {% for value in moderation_timeout_options %}
                <option value="{{ value }}" {% if moderation_settings.moderation_timeout_minutes == value %}selected{% endif %}>{{ value }} minutes</option>
                {% endfor %}
              </select>
              <div class="form-text">Only used when action is Timeout.</div>
            </div>
          </div>
          <button class="btn btn-primary mt-3" type="submit" {% if not can_manage_guild %}disabled{% endif %}>Save Moderation Settings</button>
        </form>
      </div>
    {% elif page == "settings" %}
      <div class="card card-soft p-3">
        <h1 class="h5 mb-3">Runtime Settings</h1>
        <p class="text-secondary small mb-3">These settings apply globally to the bot runtime, not a single guild.</p>
        <form method="post" action="{{ url_for('settings_save') }}">
          <div class="row g-3">
            {% for item in settings %}
            <div class="col-12 col-lg-6">
              <label class="form-label" for="field_{{ item.key }}"><code>{{ item.key }}</code></label>
              {% if item.pending_restart %}
              <div class="badge bg-warning text-dark ms-2">Pending restart</div>
              {% endif %}
              {% if item.options %}
              <select class="form-select" id="field_{{ item.key }}" name="{{ item.key }}" {% if not session.get("is_admin") %}disabled{% endif %}>
                {% for option in item.options %}
                {% if option is mapping %}
                <option value="{{ option.value }}" {% if option.value == item.value %}selected{% endif %}>{{ option.label }}</option>
                {% else %}
                <option value="{{ option }}" {% if option == item.value %}selected{% endif %}>{{ option }}</option>
                {% endif %}
                {% endfor %}
              </select>
              {% elif item.is_sensitive %}
              <input class="form-control" id="field_{{ item.key }}" name="{{ item.key }}" value="{{ item.masked_value }}" autocomplete="off" {% if not session.get("is_admin") %}disabled{% endif %}>
              <div class="form-text">Leave as `********` to keep existing value.</div>
              {% else %}
              <input class="form-control" id="field_{{ item.key }}" name="{{ item.key }}" value="{{ item.value }}" {% if not session.get("is_admin") %}disabled{% endif %}>
              {% endif %}
            </div>
            {% endfor %}
          </div>
          <div class="mt-3 d-flex gap-2">
            <button class="btn btn-primary" type="submit" {% if not session.get("is_admin") %}disabled{% endif %}>Save Settings</button>
            <span class="small text-secondary align-self-center">Changes are written to env file; restart container to apply bot runtime changes.</span>
          </div>
        </form>
      </div>
    {% endif %}
  </main>
  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
  <script>
    (function () {
      const storageKey = "web_theme_choice";
      const fallbackTheme = "black";
      const allowed = { light: true, black: true, forest: true, ember: true, ice: true };

      function setTheme(theme) {
        const selected = allowed[theme] ? theme : fallbackTheme;
        document.body.setAttribute("data-theme", selected);
        try { window.localStorage.setItem(storageKey, selected); } catch (error) {}
        document.querySelectorAll("[data-theme-choice]").forEach((btn) => {
          btn.classList.toggle("active", btn.getAttribute("data-theme-choice") === selected);
        });
      }

      let storedTheme = fallbackTheme;
      try { storedTheme = window.localStorage.getItem(storageKey) || fallbackTheme; } catch (error) {}
      setTheme(storedTheme);

      document.querySelectorAll("[data-theme-choice]").forEach((btn) => {
        btn.addEventListener("click", function () { setTheme(btn.getAttribute("data-theme-choice")); });
      });

      document.querySelectorAll(".nav-page-select").forEach((navSelect) => {
        navSelect.addEventListener("change", function () {
          const target = navSelect.value || "";
          if (!target) { return; }
          const selectedOption = navSelect.options[navSelect.selectedIndex];
          const isExternal = selectedOption && selectedOption.dataset && selectedOption.dataset.external === "1";
          if (isExternal) {
            window.open(target, "_blank", "noopener");
          } else {
            window.location.href = target;
          }
          navSelect.value = "";
        });
      });

      const refreshValue = Number("{{ selected_refresh_interval|default(0) }}");
      if (refreshValue && refreshValue > 0) {
        window.setTimeout(() => {
          const url = new URL(window.location.href);
          url.searchParams.set("refresh", String(refreshValue));
          window.location.href = url.toString();
        }, refreshValue * 1000);
      }

      const csrfToken = "{{ csrf_token }}";
      if (csrfToken) {
        document.querySelectorAll("form[method='post'], form[method='POST']").forEach((form) => {
          if (form.querySelector("input[name='csrf_token']")) { return; }
          const input = document.createElement("input");
          input.type = "hidden";
          input.name = "csrf_token";
          input.value = csrfToken;
          form.appendChild(input);
        });
      }
    })();
  </script>
</body>
</html>
"""


def create_app(
    db_path: str,
    get_bot_snapshot: Callable[[], dict],
    get_managed_guilds: Callable[[], list[dict]] | None = None,
    get_notification_channels: Callable[[int], list[dict]] | Callable[[], list[dict]] | None = None,
    get_discord_catalog: Callable[[int], dict] | Callable[[], dict] | None = None,
    get_command_permissions: Callable[[int], dict] | Callable[[], dict] | None = None,
    save_command_permissions: Callable[[dict, str, int], dict] | Callable[[dict, str], dict] | None = None,
    get_tag_responses: Callable[[int], dict] | Callable[[], dict] | None = None,
    save_tag_responses: Callable[[dict, str, int], dict] | Callable[[dict, str], dict] | None = None,
    get_guild_settings: Callable[[int], dict] | None = None,
    save_guild_settings: Callable[[dict, str, int], dict] | None = None,
    get_bot_profile: Callable[[int], dict] | Callable[[], dict] | None = None,
    update_bot_profile: Callable[[dict, str, int], dict] | Callable[[dict, str], dict] | None = None,
    update_bot_avatar: Callable[[bytes, str, str, int], dict] | Callable[[bytes, str, str], dict] | None = None,
    get_member_activity: Callable[[int, int | None], dict] | Callable[[int], dict] | None = None,
    get_spicy_prompt_status: Callable[[int], dict] | Callable[[int | None], dict] | None = None,
    export_member_activity: Callable[[int, int | None], dict] | Callable[[int], dict] | None = None,
    pick_random_user: Callable[[int, int | None], dict] | Callable[[int], dict] | None = None,
    get_spicy_prompts_status: Callable[[], dict] | None = None,
    refresh_spicy_prompts: Callable[[str], dict] | None = None,
    leave_guild: Callable[[str, int], dict] | None = None,
    request_restart: Callable[[str], dict] | None = None,
    resolve_youtube_subscription: Callable[[str], dict] | None = None,
    resolve_youtube_community_seed: Callable[[str], dict] | None = None,
    resolve_wordpress_feed: Callable[[str], dict] | None = None,
    resolve_linkedin_feed: Callable[[str], dict] | None = None,
) -> Flask:
    app = Flask(__name__)
    _ensure_users_table(db_path)
    _ensure_guild_access_tables(db_path)
    configured_secret = os.getenv("WEB_ADMIN_SESSION_SECRET")
    if configured_secret:
        app.secret_key = configured_secret
    else:
        app.secret_key = secrets.token_urlsafe(48)
        app.logger.warning("WEB_ADMIN_SESSION_SECRET not set. Generated ephemeral secret for this runtime.")

    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = os.getenv("WEB_SESSION_COOKIE_SAMESITE", "Lax")
    app.config["SESSION_COOKIE_SECURE"] = _env_bool("WEB_SESSION_COOKIE_SECURE", False)
    app.config["MAX_CONTENT_LENGTH"] = max(1024 * 1024, _env_int("WEB_AVATAR_MAX_UPLOAD_BYTES", 2 * 1024 * 1024) + (64 * 1024))
    app.permanent_session_lifetime = timedelta(days=REMEMBER_LOGIN_DAYS)
    web_session_timeout_minutes = max(5, _env_int("WEB_SESSION_TIMEOUT_MINUTES", 60))
    enforce_csrf = _env_bool("WEB_ENFORCE_CSRF", True)
    enforce_same_origin_posts = _env_bool("WEB_ENFORCE_SAME_ORIGIN_POSTS", True)
    login_window_seconds = 15 * 60
    login_max_attempts = 6
    login_attempts: dict[str, list[float]] = {}
    max_avatar_upload_bytes = max(1024, _env_int("WEB_AVATAR_MAX_UPLOAD_BYTES", 2 * 1024 * 1024))
    restart_enabled = _env_bool("WEB_RESTART_ENABLED", False)
    observability_started_monotonic = time.monotonic()
    observability_state: dict[str, float | dict[str, int | None]] = {}
    observability_history: deque[dict] = deque(maxlen=240)

    try:
        audit_log_path = _resolve_log_directory(db_path) / "web_audit.log"
        audit_logger = logging.getLogger("wickedyoda-helper.web-audit")
        audit_logger.setLevel(logging.INFO)
        already_attached = any(
            isinstance(handler, logging.FileHandler) and Path(getattr(handler, "baseFilename", "")).resolve() == audit_log_path.resolve()
            for handler in audit_logger.handlers
        )
        if not already_attached:
            handler = logging.FileHandler(audit_log_path, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
            audit_logger.addHandler(handler)
    except Exception:
        audit_logger = app.logger

    admin_user = os.getenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com").strip().lower()
    admin_password: str | None = os.getenv("WEB_ADMIN_DEFAULT_PASSWORD", "")
    admin_password_hash = os.getenv("WEB_ADMIN_DEFAULT_PASSWORD_HASH", "")
    generated_one_time_admin_password = False
    existing_admin_user = _get_user(db_path, admin_user)

    if not admin_password_hash:
        if not admin_password:
            admin_password = secrets.token_urlsafe(16)
            generated_one_time_admin_password = True
            app.logger.warning("WEB_ADMIN_DEFAULT_PASSWORD not set. Generated one-time random admin password for this run.")
            admin_password_hash = generate_password_hash(admin_password)
        else:
            password_policy_error = _password_policy_error(admin_password)
            if password_policy_error:
                if existing_admin_user is None:
                    raise RuntimeError(f"WEB_ADMIN_DEFAULT_PASSWORD does not meet policy: {password_policy_error}")
                app.logger.warning(
                    "WEB_ADMIN_DEFAULT_PASSWORD is set but does not meet policy; ignoring it for existing admin user %s.",
                    admin_user,
                )
                admin_password = None
            else:
                admin_password_hash = generate_password_hash(admin_password)
    elif admin_password_hash.startswith(("pbkdf2:", "scrypt:")):
        pass
    else:
        admin_password_hash = generate_password_hash(admin_password_hash)

    if existing_admin_user is None:
        _upsert_user(
            db_path,
            admin_user,
            admin_password_hash,
            is_admin=True,
            display_name="Admin",
            password_changed_at=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        )
    elif (
        admin_password
        and not generated_one_time_admin_password
        and not check_password_hash(str(existing_admin_user.get("password_hash", "")), admin_password)
    ):
        _upsert_user(
            db_path,
            admin_user,
            generate_password_hash(admin_password),
            is_admin=True,
            password_changed_at=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        )
    elif admin_password_hash and str(existing_admin_user.get("password_hash", "")).strip() != admin_password_hash:
        _upsert_user(
            db_path,
            admin_user,
            admin_password_hash,
            is_admin=True,
            password_changed_at=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        )

    def _managed_guild_options() -> list[dict]:
        raw_options: list[dict] = []
        if callable(get_managed_guilds):
            try:
                raw = get_managed_guilds()
                if isinstance(raw, list):
                    raw_options = raw
            except Exception:
                raw_options = []

        options: list[dict] = []
        allowed_ids = _allowed_guild_ids_for_user(db_path, _current_user())
        for item in raw_options:
            if not isinstance(item, dict):
                continue
            raw_id = item.get("id")
            raw_name = item.get("name")
            if not isinstance(raw_name, str):
                continue
            if isinstance(raw_id, int):
                guild_id = raw_id
            elif isinstance(raw_id, str) and raw_id.strip().isdigit():
                guild_id = int(raw_id.strip())
            else:
                continue
            member_count = item.get("member_count")
            if not isinstance(member_count, int):
                member_count = None
            if allowed_ids is not None and guild_id not in allowed_ids:
                continue
            options.append(
                {
                    "id": guild_id,
                    "name": raw_name.strip() or str(guild_id),
                    "member_count": member_count,
                    "icon_url": str(item.get("icon_url", "")).strip(),
                    "is_primary": bool(item.get("is_primary", False)),
                }
            )

        if allowed_ids is not None:
            return sorted(options, key=lambda item: item["name"].lower())
        if options:
            return sorted(options, key=lambda item: item["name"].lower())

        snapshot = get_bot_snapshot()
        fallback_id = snapshot.get("guild_id")
        if isinstance(fallback_id, int):
            return [{"id": fallback_id, "name": str(fallback_id)}]
        if isinstance(fallback_id, str) and fallback_id.isdigit():
            return [{"id": int(fallback_id), "name": fallback_id}]
        return []

    def _resolve_selected_guild_id() -> int | None:
        options = _managed_guild_options()
        if not options:
            session.pop("selected_guild_id", None)
            return None
        valid_ids = {int(item["id"]) for item in options}

        selected_id: int | None = None
        requested = request.values.get("guild_id", "").strip()
        if requested.isdigit():
            selected_id = int(requested)
        if selected_id is None:
            stored = session.get("selected_guild_id")
            if isinstance(stored, int):
                selected_id = stored
            elif isinstance(stored, str) and stored.isdigit():
                selected_id = int(stored)
        if selected_id not in valid_ids:
            selected_id = int(options[0]["id"])
        session["selected_guild_id"] = selected_id
        return selected_id

    def _selected_guild_context() -> tuple[int | None, list[dict], str]:
        options = _managed_guild_options()
        selected_id = _resolve_selected_guild_id()
        selected_name = ""
        if selected_id is not None:
            for option in options:
                if int(option["id"]) == selected_id:
                    selected_name = str(option["name"])
                    break
        return selected_id, options, selected_name

    def _render_page(page: str, title: str, **kwargs):
        selected_guild_id, guild_options, selected_guild_name = _selected_guild_context()
        if "snapshot" not in kwargs:
            kwargs["snapshot"] = get_bot_snapshot() if callable(get_bot_snapshot) else {}
        return render_template_string(
            PAGE_TEMPLATE,
            page=page,
            title=title,
            csrf_token=_ensure_csrf_token(),
            selected_guild_id=selected_guild_id,
            selected_guild_name=selected_guild_name,
            guild_options=guild_options,
            restart_enabled=restart_enabled,
            feed_interval_options=[{"value": value, "label": label} for value, label in FEED_INTERVAL_OPTIONS],
            can_manage_guild=_current_user_is_admin() or _current_user_is_guild_admin(),
            **kwargs,
        )

    def _call_get_notification_channels(guild_id: int | None) -> list[dict]:
        if not callable(get_notification_channels):
            return []
        if guild_id is not None:
            try:
                return get_notification_channels(guild_id)  # type: ignore[misc]
            except TypeError:
                pass
        try:
            return get_notification_channels()  # type: ignore[misc]
        except TypeError:
            return []

    def _call_get_discord_catalog(guild_id: int | None) -> dict:
        if not callable(get_discord_catalog):
            return {}
        if guild_id is not None:
            try:
                return get_discord_catalog(guild_id)  # type: ignore[misc]
            except TypeError:
                pass
        try:
            return get_discord_catalog()  # type: ignore[misc]
        except TypeError:
            return {}

    def _call_get_command_permissions(guild_id: int | None) -> dict:
        if not callable(get_command_permissions):
            return {"ok": False, "error": "Command permissions callback not configured."}
        if guild_id is not None:
            try:
                return get_command_permissions(guild_id)  # type: ignore[misc]
            except TypeError:
                pass
        try:
            return get_command_permissions()  # type: ignore[misc]
        except TypeError:
            return {"ok": False, "error": "Command permissions callback could not be called."}

    def _call_save_command_permissions(payload: dict, actor: str, guild_id: int | None) -> dict:
        if not callable(save_command_permissions):
            return {"ok": False, "error": "Command permissions save callback is not configured."}
        if guild_id is not None:
            try:
                return save_command_permissions(payload, actor, guild_id)  # type: ignore[misc]
            except TypeError:
                pass
        try:
            return save_command_permissions(payload, actor)  # type: ignore[misc]
        except TypeError:
            return {"ok": False, "error": "Command permissions save callback could not be called."}

    def _call_get_tag_responses(guild_id: int | None) -> dict:
        if not callable(get_tag_responses):
            return {"ok": False, "error": "Tag response callback is not configured."}
        if guild_id is not None:
            try:
                return get_tag_responses(guild_id)  # type: ignore[misc]
            except TypeError:
                pass
        try:
            return get_tag_responses()  # type: ignore[misc]
        except TypeError:
            return {"ok": False, "error": "Tag response callback could not be called."}

    def _call_save_tag_responses(payload: dict, actor: str, guild_id: int | None) -> dict:
        if not callable(save_tag_responses):
            return {"ok": False, "error": "Tag response save callback is not configured."}
        if guild_id is not None:
            try:
                return save_tag_responses(payload, actor, guild_id)  # type: ignore[misc]
            except TypeError:
                pass
        try:
            return save_tag_responses(payload, actor)  # type: ignore[misc]
        except TypeError:
            return {"ok": False, "error": "Tag response save callback could not be called."}

    def _call_get_guild_settings(guild_id: int | None) -> dict:
        if guild_id is None or not callable(get_guild_settings):
            return {"ok": True, "bot_log_channel_id": ""}
        return get_guild_settings(guild_id)

    def _call_save_guild_settings(payload: dict, actor: str, guild_id: int | None) -> dict:
        if guild_id is None or not callable(save_guild_settings):
            return {"ok": False, "error": "Guild settings save callback is not configured."}
        return save_guild_settings(payload, actor, guild_id)

    def _call_get_bot_profile(guild_id: int | None) -> dict:
        if not callable(get_bot_profile):
            return {"ok": False, "error": "Bot profile callback is not configured."}
        if guild_id is not None:
            try:
                return get_bot_profile(guild_id)  # type: ignore[misc]
            except TypeError:
                pass
        try:
            return get_bot_profile()  # type: ignore[misc]
        except TypeError:
            return {"ok": False, "error": "Bot profile callback could not be called."}

    def _call_update_bot_profile(payload: dict, actor: str, guild_id: int | None) -> dict:
        if not callable(update_bot_profile):
            return {"ok": False, "error": "Bot profile update callback is not configured."}
        if guild_id is not None:
            try:
                return update_bot_profile(payload, actor, guild_id)  # type: ignore[misc]
            except TypeError:
                pass
        try:
            return update_bot_profile(payload, actor)  # type: ignore[misc]
        except TypeError:
            return {"ok": False, "error": "Bot profile update callback could not be called."}

    def _call_update_bot_avatar(payload: bytes, filename: str, actor: str, guild_id: int | None) -> dict:
        if not callable(update_bot_avatar):
            return {"ok": False, "error": "Bot avatar update callback is not configured."}
        if guild_id is not None:
            try:
                return update_bot_avatar(payload, filename, actor, guild_id)  # type: ignore[misc]
            except TypeError:
                pass
        try:
            return update_bot_avatar(payload, filename, actor)  # type: ignore[misc]
        except TypeError:
            return {"ok": False, "error": "Bot avatar update callback could not be called."}

    def _call_get_spicy_prompt_status(guild_id: int | None) -> dict:
        if not callable(get_spicy_prompt_status):
            return {"ok": False}
        try:
            if guild_id is not None:
                return get_spicy_prompt_status(guild_id)  # type: ignore[misc]
            return get_spicy_prompt_status()  # type: ignore[misc]
        except TypeError:
            return get_spicy_prompt_status()  # type: ignore[misc]

    def _call_get_member_activity(guild_id: int | None, role_id: int | None = None) -> dict:
        if guild_id is None or not callable(get_member_activity):
            return {"ok": False, "error": "Member activity callback is not configured."}
        try:
            return get_member_activity(guild_id, role_id)  # type: ignore[misc]
        except TypeError:
            try:
                return get_member_activity(guild_id)  # type: ignore[misc]
            except TypeError:
                return {"ok": False, "error": "Member activity callback could not be called."}

    def _call_export_member_activity(guild_id: int | None, role_id: int | None = None) -> dict:
        if guild_id is None or not callable(export_member_activity):
            return {"ok": False, "error": "Member activity export callback is not configured."}
        try:
            return export_member_activity(guild_id, role_id)  # type: ignore[misc]
        except TypeError:
            try:
                return export_member_activity(guild_id)  # type: ignore[misc]
            except TypeError:
                return {"ok": False, "error": "Member activity export callback could not be called."}

    def _call_pick_random_user(guild_id: int | None, role_id: int | None = None) -> dict:
        if guild_id is None or not callable(pick_random_user):
            return {"ok": False, "error": "Random user picker is not configured."}
        try:
            return pick_random_user(guild_id, role_id)  # type: ignore[misc]
        except TypeError:
            try:
                return pick_random_user(guild_id)  # type: ignore[misc]
            except TypeError:
                return {"ok": False, "error": "Random user picker callback could not be called."}

    def _call_get_spicy_prompts_status() -> dict:
        if callable(get_spicy_prompts_status):
            try:
                return get_spicy_prompts_status()
            except TypeError:
                return {"ok": False, "error": "Spicy Prompts status callback could not be called."}
        return {"ok": True, **_fetch_spicy_prompt_status(db_path)}

    def _call_refresh_spicy_prompts(actor: str) -> dict:
        if not callable(refresh_spicy_prompts):
            return {"ok": False, "error": "Spicy Prompts refresh callback is not configured."}
        return refresh_spicy_prompts(actor)

    def _call_request_restart(actor: str) -> dict:
        if not callable(request_restart):
            return {"ok": False, "error": "Restart callback is not configured."}
        return request_restart(actor)

    def _call_leave_guild(actor: str, guild_id: int | None) -> dict:
        if guild_id is None or not callable(leave_guild):
            return {"ok": False, "error": "Leave guild callback is not configured."}
        return leave_guild(actor, guild_id)

    def _collect_observability_snapshot() -> dict:
        now_mono = time.monotonic()
        process_cpu_total = time.process_time()
        rss_bytes = _read_rss_bytes()
        io_bytes = _read_process_io_bytes()

        prev_wall = observability_state.get("wall")
        prev_proc_cpu = observability_state.get("process_cpu_total")
        prev_io = observability_state.get("io") if isinstance(observability_state.get("io"), dict) else {}
        delta_wall = (now_mono - prev_wall) if isinstance(prev_wall, float) and now_mono > prev_wall else None

        process_cpu_percent: float | None = None
        if delta_wall and isinstance(prev_proc_cpu, float):
            process_cpu_percent = max(0.0, ((process_cpu_total - prev_proc_cpu) / delta_wall) * 100.0)

        io_read_rate_bps: float | None = None
        io_write_rate_bps: float | None = None
        if delta_wall and isinstance(prev_io, dict):
            prev_read = prev_io.get("read_bytes")
            prev_write = prev_io.get("write_bytes")
            current_read = io_bytes.get("read_bytes")
            current_write = io_bytes.get("write_bytes")
            if isinstance(prev_read, int) and isinstance(current_read, int):
                io_read_rate_bps = max(0.0, (current_read - prev_read) / delta_wall)
            if isinstance(prev_write, int) and isinstance(current_write, int):
                io_write_rate_bps = max(0.0, (current_write - prev_write) / delta_wall)

        observability_state["wall"] = now_mono
        observability_state["process_cpu_total"] = process_cpu_total
        observability_state["io"] = io_bytes

        sampled_at = datetime.now(UTC)
        snapshot = {
            "sampled_at": sampled_at.isoformat(),
            "uptime_seconds": now_mono - observability_started_monotonic,
            "process_cpu_percent": process_cpu_percent,
            "rss_bytes": rss_bytes,
            "io_read_rate_bps": io_read_rate_bps,
            "io_write_rate_bps": io_write_rate_bps,
        }
        observability_history.append(snapshot)
        return snapshot

    def _build_observability_rows(snapshot: dict) -> list[dict]:
        history_items = list(observability_history)
        specs = [
            ("Process CPU", "process_cpu_percent", "percent"),
            ("RSS Memory", "rss_bytes", "bytes"),
            ("I/O Read Rate", "io_read_rate_bps", "bytes_per_sec"),
            ("I/O Write Rate", "io_write_rate_bps", "bytes_per_sec"),
        ]

        def _fmt(value: float | int | None, value_type: str) -> str:
            if not isinstance(value, (int, float)):
                return "n/a"
            if value_type == "percent":
                return f"{float(value):.2f}%"
            if value_type == "bytes":
                return _format_bytes(value)
            return f"{_format_bytes(value)}/s"

        rows: list[dict] = []
        for label, key, value_type in specs:
            values = [float(item[key]) for item in history_items if isinstance(item.get(key), (int, float))]
            rows.append(
                {
                    "label": label,
                    "current": _fmt(snapshot.get(key), value_type),
                    "min": _fmt(min(values) if values else None, value_type),
                    "avg": _fmt((sum(values) / len(values)) if values else None, value_type),
                    "max": _fmt(max(values) if values else None, value_type),
                }
            )
        return rows

    def _extract_hostname(value: str) -> str:
        parsed = urlparse(value if "://" in value else f"//{value}")
        return str(parsed.hostname or "").strip().lower()

    def _request_hostnames() -> set[str]:
        hosts: set[str] = set()
        direct_host = _extract_hostname(str(request.host or ""))
        if direct_host:
            hosts.add(direct_host)

        for header_name in ("X-Forwarded-Host", "X-Original-Host"):
            raw_value = str(request.headers.get(header_name, "")).strip()
            if not raw_value:
                continue
            for candidate in raw_value.split(","):
                candidate_host = _extract_hostname(candidate.strip())
                if candidate_host:
                    hosts.add(candidate_host)
        return hosts

    def _is_secure_request() -> bool:
        if request.is_secure:
            return True
        forwarded_proto = str(request.headers.get("X-Forwarded-Proto", "")).strip()
        if forwarded_proto:
            first_proto = forwarded_proto.split(",", 1)[0].strip().lower()
            if first_proto == "https":
                return True
        return False

    def _is_potentially_trustworthy_origin() -> bool:
        if _is_secure_request():
            return True
        local_hosts = {"localhost", "127.0.0.1", "::1"}
        for host in _request_hostnames():
            if host in local_hosts or host.endswith(".localhost"):
                return True
        return False

    def _client_ip() -> str:
        forwarded = str(request.headers.get("X-Forwarded-For", "")).strip()
        if forwarded:
            first = forwarded.split(",", 1)[0].strip()
            if first:
                return first
        return str(request.remote_addr or "unknown")

    def _prune_login_attempts(client_ip: str) -> list[float]:
        now_ts = time.time()
        entries = login_attempts.get(client_ip, [])
        fresh_entries = [ts for ts in entries if (now_ts - ts) < login_window_seconds]
        if fresh_entries:
            login_attempts[client_ip] = fresh_entries
        else:
            login_attempts.pop(client_ip, None)
        return fresh_entries

    def _ensure_csrf_token() -> str:
        token = str(session.get("csrf_token", "")).strip()
        if token:
            return token
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
        return token

    def _clear_auth_session() -> None:
        session.pop("user", None)
        session.pop("is_admin", None)
        session.pop("is_guild_admin", None)
        session.pop("auth_mode", None)
        session.pop("auth_issued_at", None)
        session.pop("auth_last_seen", None)
        session.pop("auth_remember_until", None)
        session.pop("password_rotation_required", None)

    def _set_auth_session(user: dict, remember_login: bool) -> None:
        now_dt = datetime.now(UTC)
        session["user"] = str(user.get("email", "")).strip().lower()
        session["is_admin"] = bool(user.get("is_admin"))
        session["is_guild_admin"] = bool(user.get("is_guild_admin"))
        session["auth_mode"] = AUTH_MODE_REMEMBER if remember_login else AUTH_MODE_STANDARD
        session["auth_issued_at"] = now_dt.isoformat()
        session["auth_last_seen"] = now_dt.isoformat()
        if remember_login:
            session["auth_remember_until"] = (now_dt + timedelta(days=REMEMBER_LOGIN_DAYS)).isoformat()
        else:
            session.pop("auth_remember_until", None)
        session["password_rotation_required"] = _password_rotation_required(user)
        session.permanent = True
        _ensure_csrf_token()

    def _is_active_auth_session() -> bool:
        email = str(session.get("user", "")).strip().lower()
        if not email:
            return False

        now_dt = datetime.now(UTC)
        mode = str(session.get("auth_mode", AUTH_MODE_STANDARD)).strip().lower()
        if mode not in {AUTH_MODE_STANDARD, AUTH_MODE_REMEMBER}:
            mode = AUTH_MODE_STANDARD
        issued_raw = str(session.get("auth_issued_at", "")).strip()
        last_seen_raw = str(session.get("auth_last_seen", "")).strip()
        remember_until_raw = str(session.get("auth_remember_until", "")).strip()

        try:
            issued_dt = datetime.fromisoformat(issued_raw) if issued_raw else None
            last_seen_dt = datetime.fromisoformat(last_seen_raw) if last_seen_raw else None
            remember_until_dt = datetime.fromisoformat(remember_until_raw) if remember_until_raw else None
        except ValueError:
            issued_dt = None
            last_seen_dt = None
            remember_until_dt = None

        if issued_dt is None and last_seen_dt is None:
            _clear_auth_session()
            return False
        if issued_dt is None:
            issued_dt = last_seen_dt
            session["auth_issued_at"] = issued_dt.isoformat() if issued_dt else ""
        if last_seen_dt is None:
            last_seen_dt = issued_dt

        if mode == AUTH_MODE_REMEMBER:
            if remember_until_dt is None and issued_dt is not None:
                remember_until_dt = issued_dt + timedelta(days=REMEMBER_LOGIN_DAYS)
                session["auth_remember_until"] = remember_until_dt.isoformat()
            if remember_until_dt and now_dt > remember_until_dt:
                _clear_auth_session()
                flash("Your saved login expired. Please log in again.", "warning")
                return False

        if last_seen_dt and (now_dt - last_seen_dt) > timedelta(minutes=web_session_timeout_minutes):
            _clear_auth_session()
            flash("You were logged out due to inactivity.", "warning")
            return False

        session["auth_mode"] = mode
        session["auth_last_seen"] = now_dt.isoformat()
        session.permanent = True
        return True

    def _current_user() -> dict | None:
        if not _is_active_auth_session():
            return None
        email = str(session.get("user", "")).strip().lower()
        if not email:
            return None
        user = _get_user(db_path, email)
        if not user:
            _clear_auth_session()
            return None
        session["is_admin"] = bool(user.get("is_admin"))
        session["is_guild_admin"] = bool(user.get("is_guild_admin"))
        session["password_rotation_required"] = _password_rotation_required(user)
        return user

    def _is_same_origin_request() -> bool:
        allowed_hosts = _request_hostnames()
        if not allowed_hosts:
            return True
        for header_name in ("Origin", "Referer"):
            header_value = str(request.headers.get(header_name, "")).strip()
            if not header_value:
                continue
            source = _extract_hostname(header_value)
            if source and source not in allowed_hosts:
                return False
        return True

    def is_valid_login(username: str, password: str) -> dict | None:
        user = _get_user(db_path, username)
        if not user:
            return None
        if not check_password_hash(str(user["password_hash"]), password):
            return None
        if _password_hash_needs_upgrade(str(user["password_hash"])):
            upgraded_hash = generate_password_hash(password)
            _update_user_password_hash_only(db_path, str(user["email"]), upgraded_hash)
            user = _get_user(db_path, username) or (user | {"password_hash": upgraded_hash})
        return user

    def login_required(handler):
        @wraps(handler)
        def wrapped(*args, **kwargs):
            if _current_user() is None:
                return redirect(url_for("login"))
            return handler(*args, **kwargs)

        return wrapped

    def admin_required(handler):
        @wraps(handler)
        def wrapped(*args, **kwargs):
            user = _current_user()
            if user is None:
                return redirect(url_for("login"))
            if not bool(user.get("is_admin")):
                flash("Admin access required.", "danger")
                return redirect(url_for("dashboard"))
            return handler(*args, **kwargs)

        return wrapped

    def _current_user_is_admin() -> bool:
        return bool(session.get("is_admin"))

    def _current_user_is_guild_admin() -> bool:
        return bool(session.get("is_guild_admin"))

    def _current_user_can_manage_guild() -> bool:
        return _current_user_is_admin() or _current_user_is_guild_admin()

    def _reject_read_only_write(redirect_endpoint: str):
        flash("Read-only accounts can view this page but cannot make changes.", "warning")
        return redirect(url_for(redirect_endpoint))

    @app.before_request
    def mark_request_start():
        request.environ["wickedyoda_request_start"] = time.perf_counter()
        return None

    @app.before_request
    def enforce_post_security():
        if request.method != "POST":
            return None
        if request.endpoint in {"healthz", "health"}:
            return None

        if enforce_csrf and request.endpoint not in {"login"}:
            expected = str(session.get("csrf_token", "")).strip()
            submitted = str(request.form.get("csrf_token", "")).strip() or str(request.headers.get("X-CSRF-Token", "")).strip()
            if not expected:
                expected = _ensure_csrf_token()
            if not submitted or submitted != expected:
                app.logger.warning("Blocked POST request with invalid CSRF token: endpoint=%s ip=%s", request.endpoint, _client_ip())
                return ("Invalid CSRF token.", 403)

        if enforce_same_origin_posts and not _is_same_origin_request():
            if request.endpoint in {"login"}:
                app.logger.warning(
                    "Origin mismatch for login POST, accepted for reverse-proxy compatibility: ip=%s",
                    _client_ip(),
                )
                return None
            # Proxy layers can rewrite host/origin headers; for authenticated forms we trust CSRF validation.
            if enforce_csrf:
                app.logger.warning(
                    "Origin mismatch for POST, accepted because CSRF token was valid: endpoint=%s ip=%s",
                    request.endpoint,
                    _client_ip(),
                )
                return None
            app.logger.warning("Blocked cross-origin POST request: path=%s ip=%s", request.path, _client_ip())
            return ("Blocked request due to origin policy.", 403)
        return None

    @app.before_request
    def enforce_password_rotation():
        endpoint = str(request.endpoint or "").strip()
        if not endpoint or endpoint.startswith("static"):
            return None
        if endpoint in {"login", "logout", "account", "healthz", "health", "public_status", "public_status_everything"}:
            return None
        user = _current_user()
        if user is None or not bool(session.get("password_rotation_required")):
            return None
        flash(f"Your password is older than {PASSWORD_ROTATION_DAYS} days. Update it before continuing.", "warning")
        return redirect(url_for("account"))

    @app.get("/healthz")
    def healthz():
        return {"status": "ok", "timestamp": datetime.now(UTC).isoformat()}

    @app.get("/health")
    def health():
        snapshot = get_bot_snapshot() if callable(get_bot_snapshot) else {}
        ready = bool(snapshot.get("bot_ready"))
        status = "ok" if ready else "starting"
        payload = {
            "status": status,
            "bot_ready": ready,
            "bot_name": snapshot.get("bot_name"),
            "guild_count": snapshot.get("guild_count"),
            "commands_synced": snapshot.get("commands_synced"),
            "latency_ms": snapshot.get("latency_ms"),
            "timestamp": datetime.now(UTC).isoformat(),
        }
        return payload, 200 if ready else 503

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        if _is_potentially_trustworthy_origin():
            response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
            response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        else:
            response.headers.pop("Cross-Origin-Resource-Policy", None)
            response.headers.pop("Cross-Origin-Opener-Policy", None)
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault("Pragma", "no-cache")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self' https://cdn.jsdelivr.net; img-src 'self' https: data:; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
        )
        if _is_secure_request():
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains; preload")
        started = request.environ.get("wickedyoda_request_start")
        duration_ms = int(max(0.0, (time.perf_counter() - float(started)) * 1000.0)) if isinstance(started, float) else -1
        if request.endpoint not in {"healthz", "health"}:
            audit_logger.info(
                "WEB_AUDIT method=%s path=%s endpoint=%s status=%s ip=%s user=%s duration_ms=%s",
                request.method,
                request.path,
                request.endpoint or "unknown",
                int(getattr(response, "status_code", 0) or 0),
                _client_ip(),
                str(session.get("user", "")).strip().lower() or "anonymous",
                duration_ms,
            )
        return response

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            client_ip = _client_ip()
            attempts = _prune_login_attempts(client_ip)
            if len(attempts) >= login_max_attempts:
                flash("Too many login attempts. Try again in 15 minutes.", "danger")
                return redirect(url_for("login"))
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            remember_login = bool(request.form.get("remember_login"))
            user = is_valid_login(username, password)
            if user:
                login_attempts.pop(client_ip, None)
                _set_auth_session(user, remember_login=remember_login)
                _resolve_selected_guild_id()
                if bool(session.get("password_rotation_required")):
                    flash(f"Your password is older than {PASSWORD_ROTATION_DAYS} days. Update it now.", "warning")
                    return redirect(url_for("account"))
                flash("Logged in.", "success")
                return redirect(url_for("home"))
            attempts.append(time.time())
            login_attempts[client_ip] = attempts[-login_max_attempts:]
            flash("Invalid credentials.", "danger")
        return _render_page("login", "Web Admin Login")

    @app.get("/logout")
    def logout():
        _clear_auth_session()
        session.pop("csrf_token", None)
        return redirect(url_for("login"))

    @app.get("/")
    def index():
        if _current_user() is not None:
            return redirect(url_for("home"))
        return redirect(url_for("login"))

    @app.get("/status")
    def public_status():
        return redirect(url_for("public_status_everything"))

    @app.get("/status/everything")
    def public_status_everything():
        refresh_options = [0, 15, 30, 60, 120, 300]
        raw_refresh = request.args.get("refresh", "0").strip()
        status_refresh_seconds = int(raw_refresh) if raw_refresh.isdigit() else 0
        if status_refresh_seconds not in refresh_options:
            status_refresh_seconds = 0
        selected_guild_id, _, _ = _selected_guild_context()
        counts = _fetch_counts(db_path, guild_id=selected_guild_id)
        actions = _fetch_actions(db_path, limit=25, guild_id=selected_guild_id)
        snapshot = get_bot_snapshot()
        spicy_status = _call_get_spicy_prompt_status(selected_guild_id)
        command_payload = _call_get_command_permissions(selected_guild_id)
        command_statuses = []
        if isinstance(command_payload, dict) and command_payload.get("ok"):
            for item in command_payload.get("commands", []) or []:
                mode = str(item.get("mode") or "default")
                default_label = str(item.get("default_policy_label") or "")
                if mode == "disabled":
                    access_label = "Disabled"
                    enabled = False
                elif mode == "public":
                    access_label = "Public"
                    enabled = True
                elif mode == "custom_roles":
                    access_label = "Custom roles"
                    enabled = True
                else:
                    access_label = default_label or "Default"
                    enabled = True
                command_statuses.append(
                    {
                        "label": str(item.get("label") or item.get("key") or ""),
                        "description": str(item.get("description") or ""),
                        "access": access_label,
                        "enabled": enabled,
                    }
                )
        return _render_page(
            "status_public",
            "Bot Status",
            counts=counts,
            actions=actions,
            snapshot=snapshot,
            spicy_status=spicy_status,
            command_statuses=command_statuses,
            status_refresh_seconds=status_refresh_seconds,
            refresh_options=refresh_options,
        )

    @app.get("/admin/home")
    @login_required
    def home():
        selected_guild_id, _, _ = _selected_guild_context()
        counts = _fetch_counts(db_path, guild_id=selected_guild_id)
        actions = _fetch_actions(db_path, limit=15, guild_id=selected_guild_id)
        snapshot = get_bot_snapshot()
        spicy_status = _call_get_spicy_prompt_status(selected_guild_id)
        command_payload = _call_get_command_permissions(selected_guild_id)
        command_statuses = []
        if isinstance(command_payload, dict) and command_payload.get("ok"):
            for item in command_payload.get("commands", []) or []:
                mode = str(item.get("mode") or "default")
                default_label = str(item.get("default_policy_label") or "")
                if mode == "disabled":
                    access_label = "Disabled"
                    enabled = False
                elif mode == "public":
                    access_label = "Public"
                    enabled = True
                elif mode == "custom_roles":
                    access_label = "Custom roles"
                    enabled = True
                else:
                    access_label = default_label or "Default"
                    enabled = True
                command_statuses.append(
                    {
                        "label": str(item.get("label") or item.get("key") or ""),
                        "description": str(item.get("description") or ""),
                        "access": access_label,
                        "enabled": enabled,
                    }
                )
        return _render_page(
            "home",
            "Web Admin Home",
            counts=counts,
            actions=actions,
            snapshot=snapshot,
            spicy_status=spicy_status,
            command_statuses=command_statuses,
        )

    @app.get("/admin/guilds")
    @login_required
    def guilds_page():
        selected_guild_id, guild_options, _ = _selected_guild_context()
        guild_cards = []
        for guild in guild_options:
            guild_cards.append(
                {
                    "id": guild["id"],
                    "name": guild["name"],
                    "selected": selected_guild_id == guild["id"],
                    "member_count": guild.get("member_count"),
                }
            )
        return _render_page(
            "guilds",
            "Discord Servers",
            guild_cards=guild_cards,
        )

    @app.post("/admin/guilds/leave")
    @admin_required
    def leave_guild_route():
        raw_guild_id = request.form.get("guild_id", "").strip()
        if not raw_guild_id.isdigit():
            flash("Invalid guild selection.", "danger")
            return redirect(url_for("guilds_page"))
        guild_id = int(raw_guild_id)
        result = _call_leave_guild(str(session.get("user", "")), guild_id)
        if isinstance(result, dict) and result.get("ok"):
            if session.get("selected_guild_id") == guild_id:
                session.pop("selected_guild_id", None)
            flash(str(result.get("message", "Left guild.")), "success")
        else:
            flash(
                str(result.get("error", "Failed to leave guild.")) if isinstance(result, dict) else "Failed to leave guild.",
                "danger",
            )
        return redirect(url_for("guilds_page"))

    @app.get("/admin/status")
    @login_required
    def status_page():
        selected_guild_id, _, _ = _selected_guild_context()
        counts = _fetch_counts(db_path, guild_id=selected_guild_id)
        actions = _fetch_actions(db_path, limit=15, guild_id=selected_guild_id)
        snapshot = get_bot_snapshot()
        log_dir = _resolve_log_directory(db_path)
        status_log_path = _resolve_log_path(log_dir, "container_errors.log")
        if status_log_path is None or not status_log_path.exists():
            status_log_path = _resolve_log_path(log_dir, "bot.log")
        status_checks = [
            {
                "component": "Discord Session",
                "state": "Connected" if snapshot.get("bot_name") else "Unknown",
                "detail": f"Latency: {snapshot.get('latency_ms', 'n/a')} ms",
            },
            {
                "component": "Moderation Store",
                "state": "Healthy" if counts.get("failed", 0) <= counts.get("total", 0) else "Degraded",
                "detail": f"Actions logged: {counts.get('total', 0)}",
            },
            {
                "component": "Web Runtime",
                "state": "Healthy",
                "detail": f"Log directory: {log_dir}",
            },
        ]
        return _render_page(
            "status_admin",
            "Service Status",
            actions=actions,
            status_checks=status_checks,
            status_log_name=status_log_path.name if status_log_path is not None else "n/a",
            status_log_dir=str(log_dir),
            status_log_tail=_tail_file(status_log_path, line_limit=120)
            if status_log_path is not None
            else "No status log file configured.",
        )

    @app.get("/admin/uptime-monitors")
    @login_required
    def uptime_monitors_page():
        selected_guild_id, _, _ = _selected_guild_context()
        catalog_payload = _call_get_discord_catalog(selected_guild_id)
        channels: list[dict] = []
        if isinstance(catalog_payload, dict) and catalog_payload.get("ok"):
            raw_channels = catalog_payload.get("channels", [])
            if isinstance(raw_channels, list):
                channels = [item for item in raw_channels if isinstance(item, dict)]
        if not channels:
            channels = _call_get_notification_channels(selected_guild_id)
        channel_map = {int(item["id"]): item for item in channels if str(item.get("id", "")).isdigit()}

        monitors = _fetch_uptime_monitors(db_path, guild_id=selected_guild_id, limit=300)
        for row in monitors:
            row["interval_label"] = _monitor_interval_label(row.get("interval_seconds"))
            channel_id = int(row.get("alert_channel_id", 0) or 0)
            row["alert_channel_name"] = channel_map.get(channel_id, {}).get("name") if channel_id else None

        return _render_page(
            "uptime_monitors",
            "Uptime Monitors",
            notification_channels=channels,
            uptime_monitors=monitors,
            monitor_interval_options=[{"value": value, "label": label} for value, label in UPTIME_MONITOR_INTERVAL_OPTIONS],
            monitor_timeout_options=list(UPTIME_MONITOR_TIMEOUT_OPTIONS),
        )

    @app.post("/admin/uptime-monitors/add")
    @login_required
    def uptime_monitor_add():
        if not _current_user_can_manage_guild():
            return _reject_read_only_write("uptime_monitors_page")
        selected_guild_id, _, _ = _selected_guild_context()
        name = request.form.get("monitor_name", "").strip()
        monitor_type = request.form.get("monitor_type", "http").strip().lower()
        target = request.form.get("monitor_target", "").strip()
        interval_seconds = _normalize_monitor_interval(request.form.get("interval_seconds", "60"))
        timeout_seconds = _normalize_monitor_timeout(request.form.get("timeout_seconds", "8"))
        raw_alert_channel_id = request.form.get("alert_channel_id", "").strip()
        alert_channel_id = int(raw_alert_channel_id) if raw_alert_channel_id.isdigit() else None

        try:
            if not name:
                raise ValueError("Monitor name is required.")
            normalized_target = _normalize_monitor_target(target, monitor_type)
            _insert_uptime_monitor(
                db_path,
                guild_id=selected_guild_id,
                name=name,
                monitor_type=monitor_type,
                target=normalized_target,
                interval_seconds=interval_seconds,
                timeout_seconds=timeout_seconds,
                alert_channel_id=alert_channel_id,
            )
        except Exception as exc:
            flash(f"Failed to add monitor: {exc}", "danger")
            return redirect(url_for("uptime_monitors_page"))

        flash("Monitor added.", "success")
        return redirect(url_for("uptime_monitors_page"))

    @app.post("/admin/uptime-monitors/<int:monitor_id>/toggle")
    @login_required
    def uptime_monitor_toggle(monitor_id: int):
        if not _current_user_can_manage_guild():
            return _reject_read_only_write("uptime_monitors_page")
        enabled = str(request.form.get("enabled", "")).strip()
        updated = _set_uptime_monitor_enabled(db_path, monitor_id, enabled == "1")
        if updated:
            flash("Monitor updated.", "success")
        else:
            flash("Monitor not found.", "warning")
        return redirect(url_for("uptime_monitors_page"))

    @app.post("/admin/uptime-monitors/<int:monitor_id>/delete")
    @login_required
    def uptime_monitor_delete(monitor_id: int):
        if not _current_user_can_manage_guild():
            return _reject_read_only_write("uptime_monitors_page")
        deleted = _delete_uptime_monitor(db_path, monitor_id)
        if deleted:
            flash("Monitor removed.", "success")
        else:
            flash("Monitor not found.", "warning")
        return redirect(url_for("uptime_monitors_page"))

    @app.get("/admin/observability")
    @admin_required
    def observability():
        snapshot = _collect_observability_snapshot()
        observability_payload = {
            "sampled_at": str(snapshot.get("sampled_at", "")).replace("T", " ").replace("+00:00", ""),
            "uptime": _format_uptime(snapshot.get("uptime_seconds", 0)),
            "process_cpu": f"{float(snapshot['process_cpu_percent']):.2f}%"
            if isinstance(snapshot.get("process_cpu_percent"), (int, float))
            else "n/a",
            "rss": _format_bytes(snapshot.get("rss_bytes")),
            "io_read": f"{_format_bytes(snapshot.get('io_read_rate_bps'))}/s"
            if isinstance(snapshot.get("io_read_rate_bps"), (int, float))
            else "n/a",
            "io_write": f"{_format_bytes(snapshot.get('io_write_rate_bps'))}/s"
            if isinstance(snapshot.get("io_write_rate_bps"), (int, float))
            else "n/a",
        }
        rows = _build_observability_rows(snapshot)
        return _render_page(
            "observability",
            "Observability",
            observability=observability_payload,
            observability_rows=rows,
        )

    @app.route("/admin/bot-profile", methods=["GET", "POST"])
    @login_required
    def bot_profile():
        selected_guild_id, _, _ = _selected_guild_context()
        profile_payload = _call_get_bot_profile(selected_guild_id)

        if request.method == "POST":
            if not _current_user_can_manage_guild():
                return _reject_read_only_write("bot_profile")
            action = str(request.form.get("action", "identity")).strip().lower()
            if action == "identity":
                payload = {
                    "bot_name": request.form.get("bot_name", "").strip(),
                    "server_nickname": request.form.get("server_nickname", "").strip(),
                    "clear_server_nickname": request.form.get("clear_server_nickname", "").strip().lower() in {"1", "true", "yes", "on"},
                }
                result = _call_update_bot_profile(payload, str(session.get("user", "")), selected_guild_id)
                if isinstance(result, dict) and result.get("ok"):
                    profile_payload = result
                    flash(str(result.get("message", "Bot profile updated.")), "success")
                else:
                    flash(
                        str(result.get("error", "Failed to update bot profile."))
                        if isinstance(result, dict)
                        else "Failed to update bot profile.",
                        "danger",
                    )
            elif action == "avatar":
                uploaded_file = request.files.get("avatar_file")
                if uploaded_file is None or not uploaded_file.filename:
                    flash("Avatar image file is required.", "danger")
                else:
                    payload_bytes = uploaded_file.read()
                    lowered_name = uploaded_file.filename.lower()
                    allowed_extensions = (".png", ".jpg", ".jpeg", ".webp", ".gif")
                    if not payload_bytes:
                        flash("Uploaded avatar file is empty.", "danger")
                    elif len(payload_bytes) > max_avatar_upload_bytes:
                        flash(
                            f"Avatar file is too large ({len(payload_bytes)} bytes). Max allowed is {max_avatar_upload_bytes} bytes.",
                            "danger",
                        )
                    elif not lowered_name.endswith(allowed_extensions):
                        flash("Avatar must be PNG, JPG, JPEG, WEBP, or GIF.", "danger")
                    else:
                        result = _call_update_bot_avatar(
                            payload_bytes,
                            uploaded_file.filename,
                            str(session.get("user", "")),
                            selected_guild_id,
                        )
                        if isinstance(result, dict) and result.get("ok"):
                            profile_payload = result
                            flash(str(result.get("message", "Bot avatar updated.")), "success")
                        else:
                            flash(
                                str(result.get("error", "Failed to update bot avatar."))
                                if isinstance(result, dict)
                                else "Failed to update bot avatar.",
                                "danger",
                            )
            else:
                flash("Invalid bot profile action.", "danger")

        if not isinstance(profile_payload, dict):
            profile_payload = {"ok": False, "error": "Bot profile callback returned an invalid payload."}
        return _render_page(
            "bot_profile",
            "Bot Profile",
            bot_profile=profile_payload,
            max_avatar_upload_bytes=max_avatar_upload_bytes,
        )

    @app.post("/admin/restart")
    @admin_required
    def restart_service():
        if not restart_enabled:
            flash("Container restart is disabled in this deployment.", "warning")
            return redirect(url_for("dashboard"))
        result = _call_request_restart(str(session.get("user", "")))
        if isinstance(result, dict) and result.get("ok"):
            flash(str(result.get("message", "Restart requested.")), "success")
        else:
            flash(
                str(result.get("error", "Failed to request restart.")) if isinstance(result, dict) else "Failed to request restart.",
                "danger",
            )
        return redirect(url_for("dashboard"))

    @app.post("/admin/select-guild")
    @login_required
    def select_guild():
        selected_guild_id = _resolve_selected_guild_id()
        if selected_guild_id is None:
            flash("No managed guilds available.", "warning")
        else:
            flash("Guild context updated.", "success")

        next_endpoint = request.form.get("next_endpoint", "").strip()
        allowed_endpoints = {
            "home",
            "guilds_page",
            "dashboard",
            "overview",
            "status_page",
            "actions",
            "member_activity_page",
            "reddit_feeds",
            "wordpress_feeds",
            "linkedin_feeds",
            "youtube_subscriptions",
            "spicy_prompts",
            "logs",
            "uptime_monitors_page",
            "wiki",
            "documentation",
            "account",
            "observability",
            "public_status_everything",
            "users",
            "guild_access",
            "command_permissions",
            "tag_responses",
            "guild_settings",
            "settings",
            "bot_profile",
        }
        if next_endpoint in allowed_endpoints:
            return redirect(url_for(next_endpoint))
        return redirect(url_for("home"))

    @app.get("/admin")
    @login_required
    def dashboard():
        selected_guild_id, _, _ = _selected_guild_context()
        snapshot = get_bot_snapshot()
        actions = _fetch_actions(db_path, limit=15, guild_id=selected_guild_id)
        return _render_page(
            "dashboard",
            "Web Admin Dashboard",
            snapshot=snapshot,
            actions=actions,
        )

    @app.get("/admin/overview")
    @login_required
    def overview():
        selected_guild_id, _, _ = _selected_guild_context()
        counts = _fetch_counts(db_path, guild_id=selected_guild_id)
        actions = _fetch_actions(db_path, limit=15, guild_id=selected_guild_id)
        snapshot = get_bot_snapshot()
        spicy_status = _call_get_spicy_prompt_status(selected_guild_id)
        command_payload = _call_get_command_permissions(selected_guild_id)
        command_statuses = []
        if isinstance(command_payload, dict) and command_payload.get("ok"):
            for item in command_payload.get("commands", []) or []:
                mode = str(item.get("mode") or "default")
                default_label = str(item.get("default_policy_label") or "")
                if mode == "disabled":
                    access_label = "Disabled"
                    enabled = False
                elif mode == "public":
                    access_label = "Public"
                    enabled = True
                elif mode == "custom_roles":
                    access_label = "Custom roles"
                    enabled = True
                else:
                    access_label = default_label or "Default"
                    enabled = True
                command_statuses.append(
                    {
                        "label": str(item.get("label") or item.get("key") or ""),
                        "description": str(item.get("description") or ""),
                        "access": access_label,
                        "enabled": enabled,
                    }
                )
        return _render_page(
            "overview",
            "Web Admin Overview",
            counts=counts,
            actions=actions,
            snapshot=snapshot,
            spicy_status=spicy_status,
            command_statuses=command_statuses,
        )

    @app.get("/admin/actions")
    @login_required
    def actions():
        selected_guild_id, _, _ = _selected_guild_context()
        return _render_page(
            "actions",
            "Moderation Action History",
            actions=_fetch_actions(db_path, limit=300, guild_id=selected_guild_id),
        )

    @app.route("/admin/random-user", methods=["GET", "POST"])
    @login_required
    def random_user_page():
        selected_guild_id, _, _ = _selected_guild_context()
        catalog_payload = _call_get_discord_catalog(selected_guild_id)
        role_options = [{"value": "", "label": "All members"}]
        if isinstance(catalog_payload, dict) and catalog_payload.get("ok"):
            for role in catalog_payload.get("roles", []) or []:
                role_id_value = str(role.get("id") or "").strip()
                role_name = str(role.get("name") or "").strip()
                if not role_id_value or not role_name:
                    continue
                role_options.append({"value": role_id_value, "label": role_name})

        selected_role_id = ""
        result: dict | None = None
        if request.method == "POST":
            if not _current_user_can_manage_guild():
                return _reject_read_only_write("random_user_page")
            raw_role_id = str(request.form.get("role_id", "")).strip()
            selected_role_id = raw_role_id if raw_role_id.isdigit() else ""
            role_id_value = int(selected_role_id) if selected_role_id else None
            result = _call_pick_random_user(selected_guild_id, role_id_value)
            if not isinstance(result, dict) or not result.get("ok"):
                flash(
                    str(result.get("error") or "Failed to pick a random user.")
                    if isinstance(result, dict)
                    else "Failed to pick a random user.",
                    "danger",
                )
        return _render_page(
            "random_user",
            "Random User Picker",
            random_user_role_options=role_options,
            random_user_selected_role_id=selected_role_id,
            random_user_result=result,
        )

    @app.get("/admin/member-activity")
    @login_required
    def member_activity_page():
        selected_guild_id, _, selected_guild_name = _selected_guild_context()
        raw_role_id = str(request.args.get("role_id", "")).strip()
        selected_role_id = int(raw_role_id) if raw_role_id.isdigit() and int(raw_role_id) > 0 else None
        payload = _call_get_member_activity(selected_guild_id, selected_role_id)
        catalog_payload = _call_get_discord_catalog(selected_guild_id)
        role_options = [{"value": "", "label": "All eligible members"}]
        if isinstance(catalog_payload, dict) and catalog_payload.get("ok"):
            for role in catalog_payload.get("roles", []) or []:
                role_id_value = str(role.get("id") or "").strip()
                role_name = str(role.get("name") or "").strip()
                if not role_id_value or not role_name:
                    continue
                role_options.append({"value": role_id_value, "label": role_name})
        selected_role_label = "All eligible members"
        for option in role_options:
            if option["value"] == (str(selected_role_id) if selected_role_id else ""):
                selected_role_label = option["label"]
                break
        member_activity_payload = {
            "windows": payload.get("windows", []) if isinstance(payload, dict) else [],
            "error": str(payload.get("error") or "") if isinstance(payload, dict) and not payload.get("ok") else "",
            "top_limit": int(payload.get("top_limit") or 20) if isinstance(payload, dict) else 20,
            "selected_role_id": str(selected_role_id or ""),
            "selected_role_label": selected_role_label,
            "guild_name": selected_guild_name,
        }
        return _render_page(
            "member_activity",
            "Member Activity",
            member_activity=member_activity_payload,
            member_activity_role_options=role_options,
            member_activity_export_enabled=callable(export_member_activity),
        )

    @app.get("/admin/member-activity/export")
    @login_required
    def member_activity_export():
        selected_guild_id, _, _ = _selected_guild_context()
        raw_role_id = str(request.args.get("role_id", "")).strip()
        selected_role_id = int(raw_role_id) if raw_role_id.isdigit() and int(raw_role_id) > 0 else None
        payload = _call_export_member_activity(selected_guild_id, selected_role_id)
        if not isinstance(payload, dict) or not payload.get("ok"):
            flash(
                str(payload.get("error") or "Failed to export member activity.")
                if isinstance(payload, dict)
                else "Failed to export member activity.",
                "danger",
            )
            return redirect(url_for("member_activity_page"))
        file_name = str(payload.get("filename") or "member_activity.zip")
        content_type = str(payload.get("content_type") or "application/octet-stream")
        data = payload.get("data") or b""
        return send_file(io.BytesIO(data), mimetype=content_type, as_attachment=True, download_name=file_name)

    @app.get("/admin/youtube")
    @login_required
    def youtube_subscriptions():
        selected_guild_id, _, _ = _selected_guild_context()
        catalog_payload = _call_get_discord_catalog(selected_guild_id)
        channels: list[dict] = []
        if isinstance(catalog_payload, dict) and catalog_payload.get("ok"):
            raw_channels = catalog_payload.get("channels", [])
            if isinstance(raw_channels, list):
                channels = [item for item in raw_channels if isinstance(item, dict)]
        if not channels:
            channels = _call_get_notification_channels(selected_guild_id)
        channel_ids = [int(item["id"]) for item in channels if str(item.get("id", "")).isdigit()]
        subscriptions = _fetch_youtube_subscriptions(db_path, limit=300, channel_ids=channel_ids)
        for row in subscriptions:
            row["interval_label"] = _feed_interval_label(row.get("poll_interval_seconds"))
        return _render_page(
            "youtube",
            "YouTube Notifications",
            notification_channels=channels,
            subscriptions=subscriptions,
        )

    @app.post("/admin/youtube/add")
    @login_required
    def youtube_add():
        if not _current_user_can_manage_guild():
            return _reject_read_only_write("youtube_subscriptions")
        selected_guild_id, _, _ = _selected_guild_context()
        source_url = request.form.get("youtube_url", "").strip()
        selected_channel_id = request.form.get("notify_channel_id", "").strip()
        poll_interval_seconds = _normalize_feed_interval(request.form.get("poll_interval_seconds", "300"))
        include_uploads = request.form.get("include_uploads", "").strip().lower() in {"1", "true", "yes", "on"}
        include_community_posts = request.form.get("include_community_posts", "").strip().lower() in {"1", "true", "yes", "on"}
        catalog_payload = _call_get_discord_catalog(selected_guild_id)
        channels: list[dict] = []
        if isinstance(catalog_payload, dict) and catalog_payload.get("ok"):
            raw_channels = catalog_payload.get("channels", [])
            if isinstance(raw_channels, list):
                channels = [item for item in raw_channels if isinstance(item, dict)]
        if not channels:
            channels = _call_get_notification_channels(selected_guild_id)
        channel_map = {str(item.get("id", "")): item for item in channels}
        selected_channel = channel_map.get(selected_channel_id)
        if not source_url:
            flash("YouTube URL is required.", "danger")
            return redirect(url_for("youtube_subscriptions"))
        if selected_channel is None:
            flash("Please select a valid Discord channel.", "danger")
            return redirect(url_for("youtube_subscriptions"))
        if not include_uploads and not include_community_posts:
            flash("Select at least one YouTube notification type.", "danger")
            return redirect(url_for("youtube_subscriptions"))
        if not callable(resolve_youtube_subscription):
            flash("YouTube resolver is not configured in the bot runtime.", "danger")
            return redirect(url_for("youtube_subscriptions"))

        try:
            details = resolve_youtube_subscription(source_url)
            channel_id = str(details.get("channel_id", "")).strip()
            if not channel_id:
                raise ValueError("Resolved channel ID is empty.")
            community_seed: dict = {}
            if include_community_posts and callable(resolve_youtube_community_seed):
                community_seed = resolve_youtube_community_seed(source_url)
            _upsert_youtube_subscription(
                db_path,
                source_url=str(details.get("source_url", source_url)),
                channel_id=channel_id,
                channel_title=str(details.get("channel_title", "Unknown Channel")),
                target_channel_id=int(selected_channel["id"]),
                target_channel_name=str(selected_channel["name"]),
                poll_interval_seconds=poll_interval_seconds,
                include_uploads=include_uploads,
                include_community_posts=include_community_posts,
                last_video_id=str(details.get("last_video_id", "")),
                last_video_title=str(details.get("last_video_title", "")),
                last_published_at=str(details.get("last_published_at", "")),
                last_community_post_id=str(community_seed.get("last_community_post_id", "")),
                last_community_post_title=str(community_seed.get("last_community_post_title", "")),
                last_community_published_at=str(community_seed.get("last_community_published_at", "")),
            )
        except Exception as exc:
            flash(f"Failed to add YouTube subscription: {exc}", "danger")
            return redirect(url_for("youtube_subscriptions"))

        flash("YouTube subscription saved.", "success")
        return redirect(url_for("youtube_subscriptions"))

    @app.post("/admin/youtube/<int:subscription_id>/delete")
    @login_required
    def youtube_delete(subscription_id: int):
        if not _current_user_can_manage_guild():
            return _reject_read_only_write("youtube_subscriptions")
        selected_guild_id, _, _ = _selected_guild_context()
        catalog_payload = _call_get_discord_catalog(selected_guild_id)
        channel_ids: list[int] = []
        if isinstance(catalog_payload, dict) and catalog_payload.get("ok"):
            raw_channels = catalog_payload.get("channels", [])
            if isinstance(raw_channels, list):
                channel_ids = [int(item["id"]) for item in raw_channels if isinstance(item, dict) and str(item.get("id", "")).isdigit()]
        if channel_ids:
            visible_ids = {int(item["id"]) for item in _fetch_youtube_subscriptions(db_path, limit=1000, channel_ids=channel_ids)}
            if subscription_id not in visible_ids:
                flash("YouTube subscription was not found for the selected guild.", "warning")
                return redirect(url_for("youtube_subscriptions"))
        deleted = _delete_youtube_subscription(db_path, subscription_id)
        if deleted:
            flash("YouTube subscription removed.", "success")
        else:
            flash("YouTube subscription not found.", "warning")
        return redirect(url_for("youtube_subscriptions"))

    @app.get("/admin/reddit")
    @login_required
    def reddit_feeds():
        selected_guild_id, _, _ = _selected_guild_context()
        catalog_payload = _call_get_discord_catalog(selected_guild_id)
        channels: list[dict] = []
        if isinstance(catalog_payload, dict) and catalog_payload.get("ok"):
            raw_channels = catalog_payload.get("channels", [])
            if isinstance(raw_channels, list):
                channels = [item for item in raw_channels if isinstance(item, dict)]
        if not channels:
            channels = _call_get_notification_channels(selected_guild_id)
        channel_ids = [int(item["id"]) for item in channels if str(item.get("id", "")).isdigit()]
        feeds = _fetch_reddit_feeds(db_path, limit=300, channel_ids=channel_ids)
        for row in feeds:
            row["interval_label"] = _feed_interval_label(row.get("poll_interval_seconds"))
        return _render_page(
            "reddit",
            "Reddit Feeds",
            notification_channels=channels,
            reddit_feeds=feeds,
        )

    @app.post("/admin/reddit/add")
    @login_required
    def reddit_add():
        if not _current_user_can_manage_guild():
            return _reject_read_only_write("reddit_feeds")
        selected_guild_id, _, _ = _selected_guild_context()
        reddit_source = request.form.get("reddit_source", "").strip()
        selected_channel_id = request.form.get("notify_channel_id", "").strip()
        poll_interval_seconds = _normalize_feed_interval(request.form.get("poll_interval_seconds", "300"))
        catalog_payload = _call_get_discord_catalog(selected_guild_id)
        channels: list[dict] = []
        if isinstance(catalog_payload, dict) and catalog_payload.get("ok"):
            raw_channels = catalog_payload.get("channels", [])
            if isinstance(raw_channels, list):
                channels = [item for item in raw_channels if isinstance(item, dict)]
        if not channels:
            channels = _call_get_notification_channels(selected_guild_id)
        channel_map = {str(item.get("id", "")): item for item in channels}
        selected_channel = channel_map.get(selected_channel_id)
        if selected_channel is None:
            flash("Please select a valid Discord channel.", "danger")
            return redirect(url_for("reddit_feeds"))
        try:
            subreddit_name, source_url = _normalize_reddit_source(reddit_source)
            _upsert_reddit_feed(
                db_path,
                subreddit_name=subreddit_name,
                source_url=source_url,
                target_channel_id=int(selected_channel["id"]),
                target_channel_name=str(selected_channel["name"]),
                poll_interval_seconds=poll_interval_seconds,
            )
        except Exception as exc:
            flash(f"Failed to add Reddit feed: {exc}", "danger")
            return redirect(url_for("reddit_feeds"))

        flash("Reddit feed saved.", "success")
        return redirect(url_for("reddit_feeds"))

    @app.post("/admin/reddit/<int:feed_id>/delete")
    @login_required
    def reddit_delete(feed_id: int):
        if not _current_user_can_manage_guild():
            return _reject_read_only_write("reddit_feeds")
        selected_guild_id, _, _ = _selected_guild_context()
        catalog_payload = _call_get_discord_catalog(selected_guild_id)
        channel_ids: list[int] = []
        if isinstance(catalog_payload, dict) and catalog_payload.get("ok"):
            raw_channels = catalog_payload.get("channels", [])
            if isinstance(raw_channels, list):
                channel_ids = [int(item["id"]) for item in raw_channels if isinstance(item, dict) and str(item.get("id", "")).isdigit()]
        if channel_ids:
            visible_ids = {int(item["id"]) for item in _fetch_reddit_feeds(db_path, limit=1000, channel_ids=channel_ids)}
            if feed_id not in visible_ids:
                flash("Reddit feed was not found for the selected guild.", "warning")
                return redirect(url_for("reddit_feeds"))
        deleted = _delete_reddit_feed(db_path, feed_id)
        if deleted:
            flash("Reddit feed removed.", "success")
        else:
            flash("Reddit feed not found.", "warning")
        return redirect(url_for("reddit_feeds"))

    @app.get("/admin/wordpress")
    @login_required
    def wordpress_feeds():
        selected_guild_id, _, _ = _selected_guild_context()
        catalog_payload = _call_get_discord_catalog(selected_guild_id)
        channels: list[dict] = []
        if isinstance(catalog_payload, dict) and catalog_payload.get("ok"):
            raw_channels = catalog_payload.get("channels", [])
            if isinstance(raw_channels, list):
                channels = [item for item in raw_channels if isinstance(item, dict)]
        if not channels:
            channels = _call_get_notification_channels(selected_guild_id)
        channel_ids = [int(item["id"]) for item in channels if str(item.get("id", "")).isdigit()]
        feeds = _fetch_wordpress_feeds(db_path, limit=300, channel_ids=channel_ids)
        for row in feeds:
            row["interval_label"] = _feed_interval_label(row.get("poll_interval_seconds"))
        return _render_page(
            "wordpress",
            "WordPress Notifications",
            notification_channels=channels,
            wordpress_feeds=feeds,
        )

    @app.post("/admin/wordpress/add")
    @login_required
    def wordpress_add():
        if not _current_user_can_manage_guild():
            return _reject_read_only_write("wordpress_feeds")
        selected_guild_id, _, _ = _selected_guild_context()
        wordpress_site_url = request.form.get("wordpress_site_url", "").strip()
        selected_channel_id = request.form.get("notify_channel_id", "").strip()
        poll_interval_seconds = _normalize_feed_interval(request.form.get("poll_interval_seconds", "300"))
        catalog_payload = _call_get_discord_catalog(selected_guild_id)
        channels: list[dict] = []
        if isinstance(catalog_payload, dict) and catalog_payload.get("ok"):
            raw_channels = catalog_payload.get("channels", [])
            if isinstance(raw_channels, list):
                channels = [item for item in raw_channels if isinstance(item, dict)]
        if not channels:
            channels = _call_get_notification_channels(selected_guild_id)
        channel_map = {str(item.get("id", "")): item for item in channels}
        selected_channel = channel_map.get(selected_channel_id)
        if selected_channel is None:
            flash("Please select a valid Discord channel.", "danger")
            return redirect(url_for("wordpress_feeds"))
        if not callable(resolve_wordpress_feed):
            flash("WordPress resolver is not configured in the bot runtime.", "danger")
            return redirect(url_for("wordpress_feeds"))
        try:
            normalized_site_url = _normalize_wordpress_source(wordpress_site_url)
            details = resolve_wordpress_feed(normalized_site_url)
            _upsert_wordpress_feed(
                db_path,
                site_url=str(details.get("site_url", normalized_site_url)),
                feed_url=str(details.get("feed_url", "")),
                site_title=str(details.get("site_title", "WordPress Site")),
                target_channel_id=int(selected_channel["id"]),
                target_channel_name=str(selected_channel["name"]),
                poll_interval_seconds=poll_interval_seconds,
                last_post_id=str(details.get("last_post_id", "")),
                last_post_title=str(details.get("last_post_title", "")),
                last_post_url=str(details.get("last_post_url", "")),
                last_published_at=str(details.get("last_published_at", "")),
            )
        except Exception as exc:
            flash(f"Failed to add WordPress feed: {exc}", "danger")
            return redirect(url_for("wordpress_feeds"))

        flash("WordPress feed saved.", "success")
        return redirect(url_for("wordpress_feeds"))

    @app.post("/admin/wordpress/<int:feed_id>/delete")
    @login_required
    def wordpress_delete(feed_id: int):
        if not _current_user_can_manage_guild():
            return _reject_read_only_write("wordpress_feeds")
        selected_guild_id, _, _ = _selected_guild_context()
        catalog_payload = _call_get_discord_catalog(selected_guild_id)
        channel_ids: list[int] = []
        if isinstance(catalog_payload, dict) and catalog_payload.get("ok"):
            raw_channels = catalog_payload.get("channels", [])
            if isinstance(raw_channels, list):
                channel_ids = [int(item["id"]) for item in raw_channels if isinstance(item, dict) and str(item.get("id", "")).isdigit()]
        if channel_ids:
            visible_ids = {int(item["id"]) for item in _fetch_wordpress_feeds(db_path, limit=1000, channel_ids=channel_ids)}
            if feed_id not in visible_ids:
                flash("WordPress feed was not found for the selected guild.", "warning")
                return redirect(url_for("wordpress_feeds"))
        deleted = _delete_wordpress_feed(db_path, feed_id)
        if deleted:
            flash("WordPress feed removed.", "success")
        else:
            flash("WordPress feed not found.", "warning")
        return redirect(url_for("wordpress_feeds"))

    @app.get("/admin/linkedin")
    @login_required
    def linkedin_feeds():
        selected_guild_id, _, _ = _selected_guild_context()
        catalog_payload = _call_get_discord_catalog(selected_guild_id)
        channels: list[dict] = []
        if isinstance(catalog_payload, dict) and catalog_payload.get("ok"):
            raw_channels = catalog_payload.get("channels", [])
            if isinstance(raw_channels, list):
                channels = [item for item in raw_channels if isinstance(item, dict)]
        if not channels:
            channels = _call_get_notification_channels(selected_guild_id)
        channel_ids = [int(item["id"]) for item in channels if str(item.get("id", "")).isdigit()]
        feeds = _fetch_linkedin_feeds(db_path, limit=300, channel_ids=channel_ids)
        for row in feeds:
            row["interval_label"] = _feed_interval_label(row.get("poll_interval_seconds"))
        return _render_page(
            "linkedin",
            "LinkedIn Notifications",
            notification_channels=channels,
            linkedin_feeds=feeds,
        )

    @app.post("/admin/linkedin/add")
    @login_required
    def linkedin_add():
        if not _current_user_can_manage_guild():
            return _reject_read_only_write("linkedin_feeds")
        selected_guild_id, _, _ = _selected_guild_context()
        linkedin_profile_url = request.form.get("linkedin_profile_url", "").strip()
        selected_channel_id = request.form.get("notify_channel_id", "").strip()
        poll_interval_seconds = _normalize_feed_interval(request.form.get("poll_interval_seconds", "300"))
        catalog_payload = _call_get_discord_catalog(selected_guild_id)
        channels: list[dict] = []
        if isinstance(catalog_payload, dict) and catalog_payload.get("ok"):
            raw_channels = catalog_payload.get("channels", [])
            if isinstance(raw_channels, list):
                channels = [item for item in raw_channels if isinstance(item, dict)]
        if not channels:
            channels = _call_get_notification_channels(selected_guild_id)
        channel_map = {str(item.get("id", "")): item for item in channels}
        selected_channel = channel_map.get(selected_channel_id)
        if selected_channel is None:
            flash("Please select a valid Discord channel.", "danger")
            return redirect(url_for("linkedin_feeds"))
        if not callable(resolve_linkedin_feed):
            flash("LinkedIn resolver is not configured in the bot runtime.", "danger")
            return redirect(url_for("linkedin_feeds"))
        try:
            normalized_profile_url = _normalize_linkedin_source(linkedin_profile_url)
            details = resolve_linkedin_feed(normalized_profile_url)
            _upsert_linkedin_feed(
                db_path,
                profile_url=str(details.get("profile_url", normalized_profile_url)),
                activity_url=str(details.get("activity_url", "")),
                profile_label=str(details.get("profile_label", "LinkedIn Profile")),
                target_channel_id=int(selected_channel["id"]),
                target_channel_name=str(selected_channel["name"]),
                poll_interval_seconds=poll_interval_seconds,
                last_post_id=str(details.get("last_post_id", "")),
                last_post_title=str(details.get("last_post_title", "")),
                last_post_url=str(details.get("last_post_url", "")),
                last_published_at=str(details.get("last_published_at", "")),
            )
        except Exception as exc:
            flash(f"Failed to add LinkedIn feed: {exc}", "danger")
            return redirect(url_for("linkedin_feeds"))

        flash("LinkedIn feed saved.", "success")
        return redirect(url_for("linkedin_feeds"))

    @app.post("/admin/linkedin/<int:feed_id>/delete")
    @login_required
    def linkedin_delete(feed_id: int):
        if not _current_user_can_manage_guild():
            return _reject_read_only_write("linkedin_feeds")
        selected_guild_id, _, _ = _selected_guild_context()
        catalog_payload = _call_get_discord_catalog(selected_guild_id)
        channel_ids: list[int] = []
        if isinstance(catalog_payload, dict) and catalog_payload.get("ok"):
            raw_channels = catalog_payload.get("channels", [])
            if isinstance(raw_channels, list):
                channel_ids = [int(item["id"]) for item in raw_channels if isinstance(item, dict) and str(item.get("id", "")).isdigit()]
        if channel_ids:
            visible_ids = {int(item["id"]) for item in _fetch_linkedin_feeds(db_path, limit=1000, channel_ids=channel_ids)}
            if feed_id not in visible_ids:
                flash("LinkedIn feed was not found for the selected guild.", "warning")
                return redirect(url_for("linkedin_feeds"))
        deleted = _delete_linkedin_feed(db_path, feed_id)
        if deleted:
            flash("LinkedIn feed removed.", "success")
        else:
            flash("LinkedIn feed not found.", "warning")
        return redirect(url_for("linkedin_feeds"))

    @app.get("/admin/spicy-prompts")
    @login_required
    def spicy_prompts():
        selected_guild_id, _, _ = _selected_guild_context()
        catalog_payload = _call_get_discord_catalog(selected_guild_id)
        channels: list[dict] = []
        if isinstance(catalog_payload, dict) and catalog_payload.get("ok"):
            raw_channels = catalog_payload.get("channels", [])
            if isinstance(raw_channels, list):
                channels = [item for item in raw_channels if isinstance(item, dict)]
        if not channels:
            channels = _call_get_notification_channels(selected_guild_id)
        settings_payload = _call_get_guild_settings(selected_guild_id)
        selected_spicy_channel_id = ""
        if isinstance(settings_payload, dict):
            raw_channel_id = settings_payload.get("spicy_prompts_channel_id", "")
            selected_spicy_channel_id = str(raw_channel_id).strip() if raw_channel_id is not None else ""
        return _render_page(
            "spicy_prompts",
            "Spicy Prompts",
            spicy_prompts=_call_get_spicy_prompts_status(),
            spicy_settings=settings_payload if isinstance(settings_payload, dict) else {"ok": False},
            notification_channels=channels,
            selected_spicy_channel_id=selected_spicy_channel_id,
        )

    @app.post("/admin/spicy-prompts/refresh")
    @admin_required
    def spicy_prompts_refresh():
        result = _call_refresh_spicy_prompts(str(session.get("user", "")).strip().lower())
        if result.get("ok"):
            flash(str(result.get("message", "Spicy Prompts refreshed.")), "success")
        else:
            flash(str(result.get("error", "Failed to refresh Spicy Prompts.")), "danger")
        return redirect(url_for("spicy_prompts"))

    @app.post("/admin/spicy-prompts/settings")
    @login_required
    def spicy_prompts_settings_save():
        if not _current_user_can_manage_guild():
            return _reject_read_only_write("spicy_prompts")
        selected_guild_id, _, _ = _selected_guild_context()
        catalog_payload = _call_get_discord_catalog(selected_guild_id)
        channels: list[dict] = []
        if isinstance(catalog_payload, dict) and catalog_payload.get("ok"):
            raw_channels = catalog_payload.get("channels", [])
            if isinstance(raw_channels, list):
                channels = [item for item in raw_channels if isinstance(item, dict)]
        if not channels:
            channels = _call_get_notification_channels(selected_guild_id)
        channel_map = {str(item.get("id", "")): item for item in channels}
        raw_channel_id = request.form.get("spicy_prompts_channel_id", "").strip()
        spicy_prompts_enabled = bool(request.form.get("spicy_prompts_enabled"))
        if spicy_prompts_enabled:
            selected_channel = channel_map.get(raw_channel_id)
            if selected_channel is None:
                flash("Please select a valid Discord channel for Spicy Prompts.", "danger")
                return redirect(url_for("spicy_prompts"))
            if not bool(selected_channel.get("nsfw")):
                flash("Spicy Prompts must use an age-restricted Discord channel.", "danger")
                return redirect(url_for("spicy_prompts"))
        payload = {
            "bot_log_channel_id": str(_call_get_guild_settings(selected_guild_id).get("bot_log_channel_id", "") or ""),
            "spicy_prompts_enabled": "1" if spicy_prompts_enabled else "0",
            "spicy_prompts_channel_id": raw_channel_id,
        }
        result = _call_save_guild_settings(payload, str(session.get("user", "")), selected_guild_id)
        if isinstance(result, dict) and result.get("ok"):
            flash(str(result.get("message", "Spicy Prompts settings updated.")), "success")
        else:
            flash(
                str(result.get("error", "Failed to update Spicy Prompts settings."))
                if isinstance(result, dict)
                else "Failed to update Spicy Prompts settings.",
                "danger",
            )
        return redirect(url_for("spicy_prompts"))

    @app.get("/admin/logs")
    @admin_required
    def logs():
        log_dir = _resolve_log_directory(db_path)
        log_options = list(LOG_FILE_OPTIONS)
        resolved_paths = {option: _resolve_log_path(log_dir, option) for option in log_options}
        existing_logs = [option for option, path in resolved_paths.items() if path is not None and path.exists() and path.is_file()]
        default_log = existing_logs[0] if existing_logs else log_options[0]
        selected_log = Path(request.args.get("log", default_log).strip()).name
        if selected_log not in log_options:
            selected_log = default_log
        raw_refresh = request.args.get("refresh", "0").strip()
        selected_refresh_interval = int(raw_refresh) if raw_refresh.isdigit() else 0
        if selected_refresh_interval not in AUTO_REFRESH_INTERVAL_OPTIONS:
            selected_refresh_interval = 0
        selected_path = resolved_paths.get(selected_log)
        if selected_path is None:
            log_preview = "Invalid log file selection."
        elif existing_logs:
            log_preview = _tail_file(selected_path)
        else:
            expected = ", ".join(log_options)
            log_preview = f"No logs found in {log_dir}. Expected files: {expected}"
        return _render_page(
            "logs",
            "Web Admin Logs",
            selected_log=selected_log,
            log_options=log_options,
            log_preview=log_preview,
            selected_refresh_interval=selected_refresh_interval,
            refresh_interval_options=list(AUTO_REFRESH_INTERVAL_OPTIONS),
        )

    @app.get("/admin/logs/download")
    @admin_required
    def logs_download():
        log_dir = _resolve_log_directory(db_path)
        log_options = list(LOG_FILE_OPTIONS)
        resolved_paths = {option: _resolve_log_path(log_dir, option) for option in log_options}
        existing_paths = [path for path in resolved_paths.values() if path is not None and path.exists() and path.is_file()]
        if not existing_paths:
            flash("No log files found to download.", "danger")
            return redirect(url_for("logs"))
        payload_bytes, _ = _build_logs_export_payload(log_dir, existing_paths)
        return send_file(
            io.BytesIO(payload_bytes),
            mimetype="application/zip",
            as_attachment=True,
            download_name="wickedyoda-logs.zip",
        )

    @app.get("/admin/logs/export")
    @admin_required
    def logs_export():
        return logs_download()

    @app.get("/admin/wiki")
    @login_required
    def wiki():
        return redirect(url_for("documentation"))

    @app.get("/admin/documentation")
    @login_required
    def documentation():
        page_map = _get_wiki_page_map()
        entries = [
            {
                "slug": path.stem,
                "label": _wiki_label_from_filename(path.name),
                "filename": path.name,
            }
            for path in sorted(
                page_map.values(),
                key=lambda value: (0 if value.stem.casefold() == "home" else 1, value.stem.casefold()),
            )
        ]
        if not entries:
            return _render_page(
                "documentation",
                "Documentation",
                documentation_pages=[],
                selected_doc_slug="",
                documentation_title="Documentation",
                documentation_content="No wiki markdown files found in ./wiki.",
                github_wiki_url=os.getenv("WEB_GITHUB_WIKI_URL", "").strip(),
            )

        first_entry = entries[0]
        return redirect(url_for("documentation_page", page_slug=first_entry["slug"]))

    @app.get("/admin/documentation/<page_slug>")
    @login_required
    def documentation_page(page_slug: str):
        if not page_slug or not page_slug.replace("-", "").replace("_", "").isalnum():
            return {"ok": False, "error": "Invalid documentation page."}, 404
        page_map = _get_wiki_page_map()
        entries = [
            {
                "slug": path.stem,
                "label": _wiki_label_from_filename(path.name),
                "filename": path.name,
                "path": path,
            }
            for path in sorted(
                page_map.values(),
                key=lambda value: (0 if value.stem.casefold() == "home" else 1, value.stem.casefold()),
            )
        ]
        selected_entry = next((item for item in entries if item["slug"].casefold() == page_slug.casefold()), None)
        if selected_entry is None:
            return {"ok": False, "error": "Documentation page not found."}, 404
        selected_path = selected_entry["path"]
        if not isinstance(selected_path, Path) or not _is_within_wiki_dir(selected_path):
            return {"ok": False, "error": "Documentation page not found."}, 404
        content = selected_path.read_text(encoding="utf-8", errors="replace")
        title = selected_entry["label"]
        first_line = content.splitlines()[0].strip() if content else ""
        if first_line.startswith("#"):
            title = first_line.lstrip("#").strip() or title
        wiki_files = _list_wiki_files()
        return _render_page(
            "documentation",
            title,
            documentation_pages=[{key: value for key, value in item.items() if key != "path"} for item in entries],
            selected_doc_slug=selected_entry["slug"],
            documentation_title=title,
            documentation_content=content if wiki_files else "No wiki markdown files found in ./wiki.",
            github_wiki_url=os.getenv("WEB_GITHUB_WIKI_URL", "").strip(),
        )

    @app.route("/admin/command-permissions", methods=["GET", "POST"])
    @login_required
    def command_permissions():
        selected_guild_id, _, _ = _selected_guild_context()
        permissions_payload = _call_get_command_permissions(selected_guild_id)
        catalog_payload = _call_get_discord_catalog(selected_guild_id)
        role_options = []
        if isinstance(catalog_payload, dict) and catalog_payload.get("ok"):
            role_options = catalog_payload.get("roles", []) or []

        if request.method == "POST":
            if not _current_user_can_manage_guild():
                return _reject_read_only_write("command_permissions")
            command_updates: dict[str, dict] = {}
            for command_key in request.form.getlist("command_key"):
                command_updates[command_key] = {
                    "mode": request.form.get(f"mode__{command_key}", "default"),
                    "role_ids": request.form.getlist(f"role_ids__{command_key}") or request.form.get(f"role_ids_text__{command_key}", ""),
                }
            save_result = _call_save_command_permissions(
                command_updates and {"commands": command_updates},
                str(session.get("user", "")),
                selected_guild_id,
            )
            if not isinstance(save_result, dict):
                flash("Invalid response from command permission save handler.", "danger")
            elif not save_result.get("ok"):
                flash(str(save_result.get("error", "Failed to update command permissions.")), "danger")
            else:
                permissions_payload = save_result
                flash(str(save_result.get("message", "Command permissions updated.")), "success")

        if not isinstance(permissions_payload, dict) or not permissions_payload.get("ok"):
            flash(
                str(permissions_payload.get("error", "Could not load command permissions."))
                if isinstance(permissions_payload, dict)
                else "Could not load command permissions.",
                "danger",
            )
            permissions_payload = {"ok": True, "commands": []}

        commands = permissions_payload.get("commands", []) or []
        for item in commands:
            role_ids = item.get("role_ids", []) or []
            role_id_strings = [str(value) for value in role_ids]
            item["role_id_strings"] = role_id_strings
            item["role_ids_csv"] = ",".join(role_id_strings)

        return _render_page(
            "command_permissions",
            "Web Admin Command Permissions",
            command_permissions=permissions_payload,
            role_options=role_options,
        )

    @app.route("/admin/tag-responses", methods=["GET", "POST"])
    @login_required
    def tag_responses():
        selected_guild_id, _, _ = _selected_guild_context()
        if request.method == "POST":
            if not _current_user_can_manage_guild():
                return _reject_read_only_write("tag_responses")
            raw_json = request.form.get("tag_json", "")
            try:
                payload = json.loads(raw_json)
                if not isinstance(payload, dict):
                    raise ValueError("Tag response JSON must be an object.")
                result = _call_save_tag_responses(payload, str(session.get("user", "")), selected_guild_id)
                if not isinstance(result, dict) or not result.get("ok"):
                    raise ValueError(
                        str(result.get("error", "Failed to save tag responses.")) if isinstance(result, dict) else "Invalid save response."
                    )
                flash(str(result.get("message", "Tag responses updated.")), "success")
            except Exception as exc:
                flash(f"Invalid tag JSON: {exc}", "danger")

        mapping: dict[str, str] = {}
        response = _call_get_tag_responses(selected_guild_id)
        if isinstance(response, dict) and response.get("ok"):
            mapping = response.get("mapping", {}) or {}
        else:
            flash(
                str(response.get("error", "Failed to load tag responses."))
                if isinstance(response, dict)
                else "Failed to load tag responses.",
                "danger",
            )
        tag_json = json.dumps(mapping, indent=2, sort_keys=True)
        return _render_page(
            "tag_responses",
            "Web Admin Tag Responses",
            tag_json=tag_json,
        )

    @app.route("/admin/guild-settings", methods=["GET", "POST"])
    @login_required
    def guild_settings():
        selected_guild_id, _, _ = _selected_guild_context()
        catalog_payload = _call_get_discord_catalog(selected_guild_id)
        channel_options: list[dict] = []
        if isinstance(catalog_payload, dict) and catalog_payload.get("ok"):
            raw_channels = catalog_payload.get("channels", [])
            if isinstance(raw_channels, list):
                channel_options = [item for item in raw_channels if isinstance(item, dict)]

        if request.method == "POST":
            if not _current_user_can_manage_guild():
                return _reject_read_only_write("guild_settings")
            payload = {
                "bot_log_channel_id": request.form.get("bot_log_channel_id", "").strip(),
                "uptime_alert_channel_id": request.form.get("uptime_alert_channel_id", "").strip(),
            }
            result = _call_save_guild_settings(payload, str(session.get("user", "")), selected_guild_id)
            if isinstance(result, dict) and result.get("ok"):
                flash(str(result.get("message", "Guild settings updated.")), "success")
            else:
                flash(
                    str(result.get("error", "Failed to update guild settings."))
                    if isinstance(result, dict)
                    else "Failed to update guild settings.",
                    "danger",
                )

        settings_payload = _call_get_guild_settings(selected_guild_id)
        selected_log_channel_id = ""
        selected_uptime_channel_id = ""
        if isinstance(settings_payload, dict):
            raw_channel_id = settings_payload.get("bot_log_channel_id", "")
            selected_log_channel_id = str(raw_channel_id).strip() if raw_channel_id is not None else ""
            raw_uptime_channel_id = settings_payload.get("uptime_alert_channel_id", "")
            selected_uptime_channel_id = str(raw_uptime_channel_id).strip() if raw_uptime_channel_id is not None else ""
        return _render_page(
            "guild_settings",
            "Guild Settings",
            guild_settings=settings_payload if isinstance(settings_payload, dict) else {"ok": False},
            notification_channels=channel_options,
            selected_log_channel_id=selected_log_channel_id,
            selected_uptime_channel_id=selected_uptime_channel_id,
        )

    @app.route("/admin/moderation", methods=["GET", "POST"])
    @login_required
    def moderation():
        selected_guild_id, _, _ = _selected_guild_context()
        if request.method == "POST":
            if not _current_user_can_manage_guild():
                return _reject_read_only_write("moderation")
            payload = {
                "moderation_enabled": request.form.get("moderation_enabled", "").strip(),
                "moderation_words": request.form.get("moderation_words", ""),
                "moderation_warning_window_hours": request.form.get("moderation_warning_window_hours", "").strip(),
                "moderation_warning_threshold": request.form.get("moderation_warning_threshold", "").strip(),
                "moderation_action": request.form.get("moderation_action", "").strip(),
                "moderation_timeout_minutes": request.form.get("moderation_timeout_minutes", "").strip(),
            }
            result = _call_save_guild_settings(payload, str(session.get("user", "")), selected_guild_id)
            if isinstance(result, dict) and result.get("ok"):
                flash("Moderation settings updated.", "success")
            else:
                flash(
                    str(result.get("error", "Failed to update moderation settings."))
                    if isinstance(result, dict)
                    else "Failed to update moderation settings.",
                    "danger",
                )

        settings_payload = _call_get_guild_settings(selected_guild_id)
        moderation_settings = settings_payload if isinstance(settings_payload, dict) else {}
        moderation_settings = {
            "moderation_enabled": bool(int(moderation_settings.get("moderation_enabled", 0) or 0)),
            "moderation_words": moderation_settings.get("moderation_words") or [],
            "moderation_warning_window_hours": int(moderation_settings.get("moderation_warning_window_hours", 72) or 72),
            "moderation_warning_threshold": int(moderation_settings.get("moderation_warning_threshold", 3) or 3),
            "moderation_action": str(moderation_settings.get("moderation_action") or "timeout"),
            "moderation_timeout_minutes": int(moderation_settings.get("moderation_timeout_minutes", 10) or 10),
        }
        moderation_words_text = "\n".join([str(word) for word in moderation_settings["moderation_words"] if str(word).strip()])
        return _render_page(
            "moderation",
            "Moderation",
            moderation_settings=moderation_settings,
            moderation_words_text=moderation_words_text,
            moderation_window_options=[24, 48, 72, 96, 168],
            moderation_threshold_options=[1, 2, 3, 4, 5],
            moderation_timeout_options=[5, 10, 30, 60, 120, 1440],
        )

    @app.get("/admin/users")
    @login_required
    def users():
        return _render_page(
            "users",
            "Web Admin Users",
            users=_list_users(db_path),
        )

    @app.get("/admin/guild-access")
    @admin_required
    def guild_access():
        groups = _list_guild_groups(db_path)
        group_payload = []
        for group in groups:
            group_id = int(group.get("id", 0))
            group_payload.append(
                {
                    **group,
                    "guild_ids": _list_group_guild_ids(db_path, group_id),
                    "user_emails": _list_group_user_emails(db_path, group_id),
                }
            )
        guild_options = _managed_guild_options()
        users_payload = _list_users(db_path)
        return _render_page(
            "guild_access",
            "Guild Access",
            guild_access_groups=group_payload,
            guild_access_guilds=guild_options,
            guild_access_users=users_payload,
        )

    @app.post("/admin/guild-access/create")
    @admin_required
    def guild_access_create():
        group_name = request.form.get("group_name", "").strip()
        if not group_name:
            flash("Group name is required.", "danger")
            return redirect(url_for("guild_access"))
        _create_guild_group(db_path, group_name)
        flash("Guild access group created.", "success")
        return redirect(url_for("guild_access"))

    @app.post("/admin/guild-access/update")
    @admin_required
    def guild_access_update():
        group_id_raw = request.form.get("group_id", "").strip()
        if not group_id_raw.isdigit():
            flash("Invalid group selection.", "danger")
            return redirect(url_for("guild_access"))
        group_id = int(group_id_raw)
        guild_ids = [int(value) for value in request.form.getlist("guild_ids") if str(value).isdigit()]
        allowed_users = {str(user.get("email", "")).strip().lower() for user in _list_users(db_path)}
        user_emails = [
            email.strip().lower()
            for email in request.form.getlist("user_emails")
            if _is_valid_email(email) and email.strip().lower() in allowed_users
        ]
        _set_guild_group_guilds(db_path, group_id, guild_ids)
        _set_guild_group_users(db_path, group_id, user_emails)
        flash("Guild access group updated.", "success")
        return redirect(url_for("guild_access"))

    @app.post("/admin/guild-access/delete")
    @admin_required
    def guild_access_delete():
        group_id_raw = request.form.get("group_id", "").strip()
        if not group_id_raw.isdigit():
            flash("Invalid group selection.", "danger")
            return redirect(url_for("guild_access"))
        _delete_guild_group(db_path, int(group_id_raw))
        flash("Guild access group deleted.", "success")
        return redirect(url_for("guild_access"))

    @app.post("/admin/users/add")
    @admin_required
    def users_add():
        email = request.form.get("email", "").strip().lower()
        display_name = request.form.get("display_name", "").strip()
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "read-only").strip().lower()
        is_admin = role == "admin"
        is_guild_admin = role == "guild-admin"

        if not _is_valid_email(email):
            flash("Please provide a valid email address.", "danger")
            return redirect(url_for("users"))
        password_policy_error = _password_policy_error(password)
        if password_policy_error:
            flash(password_policy_error, "danger")
            return redirect(url_for("users"))

        _upsert_user(
            db_path,
            email,
            generate_password_hash(password),
            is_admin=is_admin,
            is_guild_admin=is_guild_admin,
            display_name=display_name,
            first_name=first_name,
            last_name=last_name,
            password_changed_at=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        )
        flash("User saved.", "success")
        return redirect(url_for("users"))

    @app.post("/admin/users/update")
    @admin_required
    def users_update():
        current_email = request.form.get("current_email", "").strip().lower()
        new_email = request.form.get("email", "").strip().lower()
        display_name = request.form.get("display_name", "").strip()
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        new_password = request.form.get("new_password", "")
        role = request.form.get("role", "read-only").strip().lower()
        is_admin = role == "admin"
        is_guild_admin = role == "guild-admin"
        current_user = str(session.get("user", "")).strip().lower()

        if not current_email:
            flash("Current email is required.", "danger")
            return redirect(url_for("users"))
        user = _get_user(db_path, current_email)
        if not user:
            flash("User not found.", "warning")
            return redirect(url_for("users"))
        if current_email == current_user and role == "read-only":
            flash("You cannot make your own account read-only.", "danger")
            return redirect(url_for("users"))
        if bool(user.get("is_admin")) and not is_admin:
            admin_count = sum(1 for item in _list_users(db_path) if bool(item.get("is_admin")))
            if admin_count <= 1:
                flash("At least one admin user must remain.", "danger")
                return redirect(url_for("users"))
        password_hash = None
        if new_password:
            password_policy_error = _password_policy_error(new_password)
            if password_policy_error:
                flash(password_policy_error, "danger")
                return redirect(url_for("users"))
            password_hash = generate_password_hash(new_password)

        ok, message = _update_user_record(
            db_path,
            current_email,
            new_email=new_email or current_email,
            display_name=display_name if display_name else ("" if (first_name or last_name) else str(user.get("display_name", ""))),
            first_name=first_name,
            last_name=last_name,
            is_admin=is_admin,
            is_guild_admin=is_guild_admin,
            password_hash=password_hash,
        )
        if not ok:
            flash(message, "danger")
            return redirect(url_for("users"))
        if current_email == current_user:
            session["user"] = (new_email or current_email).lower()
            session["is_admin"] = is_admin
            session["is_guild_admin"] = is_guild_admin
        flash(message, "success")
        return redirect(url_for("users"))

    @app.post("/admin/users/delete")
    @admin_required
    def users_delete():
        email = request.form.get("email", "").strip().lower()
        current_user = str(session.get("user", "")).strip().lower()
        if not email:
            flash("Email is required.", "danger")
            return redirect(url_for("users"))
        if email == current_user:
            flash("You cannot delete your own account.", "warning")
            return redirect(url_for("users"))

        user = _get_user(db_path, email)
        if not user:
            flash("User not found.", "warning")
            return redirect(url_for("users"))

        if bool(user.get("is_admin")):
            admin_count = sum(1 for item in _list_users(db_path) if bool(item.get("is_admin")))
            if admin_count <= 1:
                flash("At least one admin user must remain.", "danger")
                return redirect(url_for("users"))

        _delete_user(db_path, email)
        flash("User deleted.", "success")
        return redirect(url_for("users"))

    @app.route("/admin/account", methods=["GET", "POST"])
    @login_required
    def account():
        current_user = str(session.get("user", "")).strip().lower()
        user = _get_user(db_path, current_user)
        if not user:
            _clear_auth_session()
            flash("Session expired. Please log in again.", "warning")
            return redirect(url_for("login"))
        if request.method == "POST":
            action = request.form.get("action", "").strip().lower()
            current_password = request.form.get("current_password", "")
            new_password = request.form.get("new_password", "")
            confirm_new_password = request.form.get("confirm_new_password", "")
            updated_email = request.form.get("email", "").strip().lower()
            display_name = request.form.get("display_name", "").strip()
            first_name = request.form.get("first_name", "").strip()
            last_name = request.form.get("last_name", "").strip()
            password_rotation_required = bool(session.get("password_rotation_required"))
            if not check_password_hash(str(user["password_hash"]), current_password):
                flash("Current password is incorrect.", "danger")
                return redirect(url_for("account"))
            if not action:
                if password_rotation_required and not new_password:
                    flash(f"Password rotation is required every {PASSWORD_ROTATION_DAYS} days. Set a new password now.", "danger")
                    return redirect(url_for("account"))
                if new_password and new_password == current_password:
                    flash("New password must be different from the current password.", "danger")
                    return redirect(url_for("account"))
                password_policy_error = _password_policy_error(new_password) if new_password else None
                if password_policy_error:
                    flash(password_policy_error, "danger")
                    return redirect(url_for("account"))
                if confirm_new_password and new_password != confirm_new_password:
                    flash("New password confirmation does not match.", "danger")
                    return redirect(url_for("account"))
                ok, message = _update_user_record(
                    db_path,
                    current_user,
                    new_email=updated_email or current_user,
                    display_name=display_name if display_name else ("" if (first_name or last_name) else str(user.get("display_name", ""))),
                    first_name=first_name,
                    last_name=last_name,
                    is_admin=bool(user.get("is_admin")),
                    is_guild_admin=bool(user.get("is_guild_admin")),
                    password_hash=generate_password_hash(new_password) if new_password else None,
                )
                if not ok:
                    flash(message, "danger")
                    return redirect(url_for("account"))
                session["user"] = (updated_email or current_user).lower()
                if new_password:
                    session["password_rotation_required"] = False
                flash("Account updated.", "success")
                return redirect(url_for("account"))
            if action == "profile":
                ok, message = _update_user_record(
                    db_path,
                    current_user,
                    new_email=updated_email or current_user,
                    display_name=display_name if display_name else ("" if (first_name or last_name) else str(user.get("display_name", ""))),
                    first_name=first_name,
                    last_name=last_name,
                    is_admin=bool(user.get("is_admin")),
                    is_guild_admin=bool(user.get("is_guild_admin")),
                    password_hash=None,
                )
                if not ok:
                    flash(message, "danger")
                    return redirect(url_for("account"))
                session["user"] = (updated_email or current_user).lower()
                flash("Profile updated.", "success")
                return redirect(url_for("account"))

            if action != "password":
                flash("Invalid account action.", "danger")
                return redirect(url_for("account"))
            if password_rotation_required and not new_password:
                flash(f"Password rotation is required every {PASSWORD_ROTATION_DAYS} days. Set a new password now.", "danger")
                return redirect(url_for("account"))
            if not new_password:
                flash("New password is required.", "danger")
                return redirect(url_for("account"))
            if new_password == current_password:
                flash("New password must be different from the current password.", "danger")
                return redirect(url_for("account"))
            password_policy_error = _password_policy_error(new_password)
            if password_policy_error:
                flash(password_policy_error, "danger")
                return redirect(url_for("account"))
            if confirm_new_password and new_password != confirm_new_password:
                flash("New password confirmation does not match.", "danger")
                return redirect(url_for("account"))
            ok, message = _update_user_record(
                db_path,
                current_user,
                new_email=current_user,
                display_name=str(user.get("display_name", "")),
                first_name=str(user.get("first_name", "")),
                last_name=str(user.get("last_name", "")),
                is_admin=bool(user.get("is_admin")),
                is_guild_admin=bool(user.get("is_guild_admin")),
                password_hash=generate_password_hash(new_password),
            )
            if not ok:
                flash(message, "danger")
                return redirect(url_for("account"))
            session["password_rotation_required"] = False
            flash("Password updated.", "success")
            return redirect(url_for("account"))

        return _render_page("account", "Web Admin Account", account_user=user)

    @app.get("/admin/settings")
    @login_required
    def settings():
        selected_guild_id, _, _ = _selected_guild_context()
        catalog_payload = _call_get_discord_catalog(selected_guild_id)
        channel_options: list[dict] = []
        if isinstance(catalog_payload, dict) and catalog_payload.get("ok"):
            raw_channels = catalog_payload.get("channels", [])
            if isinstance(raw_channels, list):
                channel_options = [item for item in raw_channels if isinstance(item, dict)]
        settings_view = _build_settings_fields(channel_options=channel_options)
        return _render_page(
            "settings",
            "Web Admin Settings",
            settings=settings_view,
        )

    @app.post("/admin/settings/save")
    @login_required
    def settings_save():
        if not _current_user_is_admin():
            return _reject_read_only_write("settings")
        selected_guild_id, _, _ = _selected_guild_context()
        catalog_payload = _call_get_discord_catalog(selected_guild_id)
        channel_options: list[dict] = []
        if isinstance(catalog_payload, dict) and catalog_payload.get("ok"):
            raw_channels = catalog_payload.get("channels", [])
            if isinstance(raw_channels, list):
                channel_options = [item for item in raw_channels if isinstance(item, dict)]
        settings_fields = _build_settings_fields(channel_options=channel_options)
        allowed_keys = [item["key"] for item in settings_fields]
        current_values = {item["key"]: item["value"] for item in settings_fields}
        options_lookup = {item["key"]: item.get("options") for item in settings_fields}

        payload = {key: request.form.get(key, current_values.get(key, "")) for key in allowed_keys}
        for key in allowed_keys:
            if _is_sensitive_key(key):
                raw_value = payload[key].strip()
                if raw_value == "********":
                    payload[key] = current_values.get(key, "")

        validated, errors = _validate_settings_payload(payload, allowed_keys, options_lookup=options_lookup)
        if errors:
            for error in errors:
                flash(error, "danger")
            return redirect(url_for("settings"))

        try:
            _write_env_file(_resolve_env_file_path(), validated)
        except OSError as exc:
            flash(f"Unable to write env file: {exc}", "danger")
            return redirect(url_for("settings"))

        flash("Settings saved to env file. Restart container to apply runtime changes.", "success")
        return redirect(url_for("settings"))

    return app


def start_web_admin(
    db_path: str,
    get_bot_snapshot: Callable[[], dict],
    get_managed_guilds: Callable[[], list[dict]] | None = None,
    get_notification_channels: Callable[[int], list[dict]] | Callable[[], list[dict]] | None = None,
    get_discord_catalog: Callable[[int], dict] | Callable[[], dict] | None = None,
    get_command_permissions: Callable[[int], dict] | Callable[[], dict] | None = None,
    save_command_permissions: Callable[[dict, str, int], dict] | Callable[[dict, str], dict] | None = None,
    get_tag_responses: Callable[[int], dict] | Callable[[], dict] | None = None,
    save_tag_responses: Callable[[dict, str, int], dict] | Callable[[dict, str], dict] | None = None,
    get_guild_settings: Callable[[int], dict] | None = None,
    save_guild_settings: Callable[[dict, str, int], dict] | None = None,
    get_bot_profile: Callable[[int], dict] | Callable[[], dict] | None = None,
    update_bot_profile: Callable[[dict, str, int], dict] | Callable[[dict, str], dict] | None = None,
    update_bot_avatar: Callable[[bytes, str, str, int], dict] | Callable[[bytes, str, str], dict] | None = None,
    get_member_activity: Callable[[int, int | None], dict] | Callable[[int], dict] | None = None,
    get_spicy_prompt_status: Callable[[int], dict] | Callable[[int | None], dict] | None = None,
    export_member_activity: Callable[[int, int | None], dict] | Callable[[int], dict] | None = None,
    pick_random_user: Callable[[int, int | None], dict] | Callable[[int], dict] | None = None,
    get_spicy_prompts_status: Callable[[], dict] | None = None,
    refresh_spicy_prompts: Callable[[str], dict] | None = None,
    leave_guild: Callable[[str, int], dict] | None = None,
    request_restart: Callable[[str], dict] | None = None,
    resolve_youtube_subscription: Callable[[str], dict] | None = None,
    resolve_youtube_community_seed: Callable[[str], dict] | None = None,
    resolve_wordpress_feed: Callable[[str], dict] | None = None,
    resolve_linkedin_feed: Callable[[str], dict] | None = None,
    host: str = "127.0.0.1",
    port: int = 8081,
    ssl_context: str | tuple[str, str] | None = None,
) -> threading.Thread:
    app = create_app(
        db_path,
        get_bot_snapshot,
        get_managed_guilds=get_managed_guilds,
        get_notification_channels=get_notification_channels,
        get_discord_catalog=get_discord_catalog,
        get_command_permissions=get_command_permissions,
        save_command_permissions=save_command_permissions,
        get_tag_responses=get_tag_responses,
        save_tag_responses=save_tag_responses,
        get_guild_settings=get_guild_settings,
        save_guild_settings=save_guild_settings,
        get_bot_profile=get_bot_profile,
        update_bot_profile=update_bot_profile,
        update_bot_avatar=update_bot_avatar,
        get_member_activity=get_member_activity,
        get_spicy_prompt_status=get_spicy_prompt_status,
        export_member_activity=export_member_activity,
        pick_random_user=pick_random_user,
        get_spicy_prompts_status=get_spicy_prompts_status,
        refresh_spicy_prompts=refresh_spicy_prompts,
        leave_guild=leave_guild,
        request_restart=request_restart,
        resolve_youtube_subscription=resolve_youtube_subscription,
        resolve_youtube_community_seed=resolve_youtube_community_seed,
        resolve_wordpress_feed=resolve_wordpress_feed,
        resolve_linkedin_feed=resolve_linkedin_feed,
    )

    def run() -> None:
        try:
            app.run(host=host, port=port, debug=False, use_reloader=False, ssl_context=ssl_context)
        except Exception:
            logging.getLogger("wickedyoda-helper").exception("Web admin listener failed to start on %s:%s", host, port)

    thread = threading.Thread(target=run, daemon=True, name="web-admin")
    thread.start()
    return thread
