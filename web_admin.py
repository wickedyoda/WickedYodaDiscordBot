import json
import logging
import os
import secrets
import sqlite3
import threading
import time
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, flash, redirect, render_template_string, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

SENSITIVE_ENV_KEYS = {
    "DISCORD_TOKEN",
    "WEB_ADMIN_DEFAULT_PASSWORD",
    "WEB_ADMIN_DEFAULT_PASSWORD_HASH",
    "WEB_ADMIN_SESSION_SECRET",
}
SESSION_SAMESITE_OPTIONS = ("Lax", "Strict", "None")
BOOL_SELECT_OPTIONS = ("false", "true")
LOG_FILE_OPTIONS = ("bot.log", "bot_log.log", "container_errors.log", "web_gui_audit.log")
AUTH_MODE_STANDARD = "standard"
AUTH_MODE_REMEMBER = "remember"
REMEMBER_LOGIN_DAYS = 5
SETTINGS_FIELD_ORDER = [
    "DISCORD_TOKEN",
    "GUILD_ID",
    "Bot_Log_Channel",
    "WEB_ENABLED",
    "WEB_BIND_HOST",
    "WEB_PORT",
    "WEB_TLS_ENABLED",
    "WEB_TLS_PORT",
    "WEB_TLS_CERT_FILE",
    "WEB_TLS_KEY_FILE",
    "ENABLE_MEMBERS_INTENT",
    "COMMAND_RESPONSES_EPHEMERAL",
    "PUPPY_IMAGE_API_URL",
    "PUPPY_IMAGE_TIMEOUT_SECONDS",
    "SHORTENER_ENABLED",
    "SHORTENER_BASE_URL",
    "SHORTENER_TIMEOUT_SECONDS",
    "YOUTUBE_NOTIFY_ENABLED",
    "YOUTUBE_POLL_INTERVAL_SECONDS",
    "YOUTUBE_REQUEST_TIMEOUT_SECONDS",
    "UPTIME_STATUS_ENABLED",
    "UPTIME_STATUS_PAGE_URL",
    "UPTIME_STATUS_TIMEOUT_SECONDS",
    "WEB_ADMIN_DEFAULT_USERNAME",
    "WEB_ADMIN_DEFAULT_PASSWORD",
    "WEB_ADMIN_SESSION_SECRET",
    "WEB_SESSION_COOKIE_SECURE",
    "WEB_SESSION_COOKIE_SAMESITE",
    "WEB_SESSION_TIMEOUT_MINUTES",
    "WEB_AVATAR_MAX_UPLOAD_BYTES",
    "WEB_ENFORCE_CSRF",
    "WEB_ENFORCE_SAME_ORIGIN_POSTS",
    "WEB_RESTART_ENABLED",
    "DATA_DIR",
    "LOG_DIR",
    "ACTION_DB_PATH",
    "WEB_ENV_FILE",
    "WEB_GITHUB_WIKI_URL",
]
SETTINGS_DROPDOWN_OPTIONS: dict[str, tuple[str, ...]] = {
    "WEB_ENABLED": BOOL_SELECT_OPTIONS,
    "WEB_TLS_ENABLED": BOOL_SELECT_OPTIONS,
    "ENABLE_MEMBERS_INTENT": BOOL_SELECT_OPTIONS,
    "COMMAND_RESPONSES_EPHEMERAL": BOOL_SELECT_OPTIONS,
    "SHORTENER_ENABLED": BOOL_SELECT_OPTIONS,
    "YOUTUBE_NOTIFY_ENABLED": BOOL_SELECT_OPTIONS,
    "UPTIME_STATUS_ENABLED": BOOL_SELECT_OPTIONS,
    "WEB_SESSION_COOKIE_SECURE": BOOL_SELECT_OPTIONS,
    "WEB_ENFORCE_CSRF": BOOL_SELECT_OPTIONS,
    "WEB_ENFORCE_SAME_ORIGIN_POSTS": BOOL_SELECT_OPTIONS,
    "WEB_RESTART_ENABLED": BOOL_SELECT_OPTIONS,
    "WEB_SESSION_COOKIE_SAMESITE": SESSION_SAMESITE_OPTIONS,
    "WEB_SESSION_TIMEOUT_MINUTES": ("30", "60", "120", "240"),
    "WEB_AVATAR_MAX_UPLOAD_BYTES": ("262144", "524288", "1048576", "2097152", "3145728", "4194304"),
    "WEB_PORT": ("8080", "8000", "5000"),
    "WEB_TLS_PORT": ("8081", "8443", "4443"),
    "PUPPY_IMAGE_TIMEOUT_SECONDS": ("5", "8", "10", "15", "30"),
    "SHORTENER_TIMEOUT_SECONDS": ("5", "8", "10", "15", "30"),
    "YOUTUBE_POLL_INTERVAL_SECONDS": ("60", "120", "300", "600", "900"),
    "YOUTUBE_REQUEST_TIMEOUT_SECONDS": ("8", "10", "12", "15", "30"),
    "UPTIME_STATUS_TIMEOUT_SECONDS": ("5", "8", "10", "15", "30"),
}


def _is_sensitive_key(key: str) -> bool:
    if key in SENSITIVE_ENV_KEYS:
        return True
    upper_key = key.upper()
    return "TOKEN" in upper_key or "PASSWORD" in upper_key or "SECRET" in upper_key


def _ensure_actions_table(db_path: str) -> None:
    directory = os.path.dirname(db_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
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
    with sqlite3.connect(db_path) as conn:
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
                last_video_id TEXT,
                last_video_title TEXT,
                last_published_at TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                UNIQUE(channel_id, target_channel_id)
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
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, tuple(params)).fetchall()
    return [dict(row) for row in rows]


def _fetch_youtube_subscriptions(db_path: str, limit: int = 300, channel_ids: list[int] | None = None) -> list[dict]:
    _ensure_youtube_subscriptions_table(db_path)
    query = """
        SELECT id, created_at, source_url, channel_id, channel_title, target_channel_id,
               target_channel_name, last_video_id, last_video_title, last_published_at, enabled
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
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, tuple(params)).fetchall()
    return [dict(row) for row in rows]


def _upsert_youtube_subscription(
    db_path: str,
    *,
    source_url: str,
    channel_id: str,
    channel_title: str,
    target_channel_id: int,
    target_channel_name: str,
    last_video_id: str,
    last_video_title: str,
    last_published_at: str,
) -> None:
    _ensure_youtube_subscriptions_table(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO youtube_subscriptions (
                created_at, source_url, channel_id, channel_title, target_channel_id,
                target_channel_name, last_video_id, last_video_title, last_published_at, enabled
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(channel_id, target_channel_id) DO UPDATE SET
                source_url=excluded.source_url,
                channel_title=excluded.channel_title,
                target_channel_name=excluded.target_channel_name,
                last_video_id=excluded.last_video_id,
                last_video_title=excluded.last_video_title,
                last_published_at=excluded.last_published_at,
                enabled=1
            """,
            (
                datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
                source_url,
                channel_id,
                channel_title,
                target_channel_id,
                target_channel_name,
                last_video_id,
                last_video_title,
                last_published_at,
            ),
        )
        conn.commit()


def _delete_youtube_subscription(db_path: str, subscription_id: int) -> bool:
    _ensure_youtube_subscriptions_table(db_path)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute("DELETE FROM youtube_subscriptions WHERE id = ?", (subscription_id,))
        conn.commit()
    return cursor.rowcount > 0


def _fetch_counts(db_path: str, guild_id: int | None = None) -> dict:
    _ensure_actions_table(db_path)
    with sqlite3.connect(db_path) as conn:
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
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{key}={existing[key]}" for key in SETTINGS_FIELD_ORDER if key in existing]
    extra_keys = sorted(key for key in existing if key not in SETTINGS_FIELD_ORDER)
    lines.extend(f"{key}={existing[key]}" for key in extra_keys)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _build_settings_fields() -> list[dict]:
    env_file_values = _read_env_file(_resolve_env_file_path())
    ordered_keys = list(SETTINGS_FIELD_ORDER)
    for key in sorted(env_file_values):
        if key not in ordered_keys:
            ordered_keys.append(key)
    for key in sorted(os.environ):
        if key.startswith("WEB_") and key not in ordered_keys:
            ordered_keys.append(key)

    fields: list[dict] = []
    for key in ordered_keys:
        raw = os.getenv(key)
        value = env_file_values.get(key, raw or "")
        is_sensitive = _is_sensitive_key(key)
        fields.append(
            {
                "key": key,
                "value": value,
                "masked_value": "********" if is_sensitive and value else value,
                "is_sensitive": is_sensitive,
                "options": SETTINGS_DROPDOWN_OPTIONS.get(key, ()),
            }
        )
    return fields


def _validate_settings_payload(payload: dict[str, str], allowed_keys: list[str]) -> tuple[dict[str, str], list[str]]:
    validated: dict[str, str] = {}
    errors: list[str] = []
    for key in allowed_keys:
        raw_value = payload.get(key, "").strip()
        options = SETTINGS_DROPDOWN_OPTIONS.get(key)
        if options and raw_value and raw_value not in options:
            errors.append(f"{key} has an invalid option.")
            continue
        if key in {"GUILD_ID", "Bot_Log_Channel", "WEB_PORT", "WEB_TLS_PORT", "WEB_AVATAR_MAX_UPLOAD_BYTES"} and raw_value:
            if not raw_value.isdigit():
                errors.append(f"{key} must be numeric.")
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
    return validated, errors


def _resolve_log_directory(db_path: str) -> Path:
    configured = os.getenv("LOG_DIR", "").strip()
    fallback = Path(db_path).resolve().parent
    preferred = Path(configured).expanduser() if configured else fallback
    candidates = [preferred]
    if fallback != preferred:
        candidates.append(fallback)

    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
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
    if selected_log == "web_gui_audit.log":
        return (log_dir / "web_gui_audit.log").resolve()
    return None


def _tail_file(safe_path: Path, line_limit: int = 400) -> str:
    if safe_path.suffix.lower() != ".log":
        return "Invalid log file selection."
    if not safe_path.exists() or not safe_path.is_file():
        return f"Log file not found: {safe_path.name}"
    with safe_path.open("r", encoding="utf-8", errors="replace") as handle:
        lines = handle.readlines()
    if not lines:
        return "(empty log file)"
    return "".join(lines[-line_limit:])


def _list_wiki_files() -> list[str]:
    wiki_root = Path.cwd() / "wiki"
    if not wiki_root.exists():
        return []
    files = sorted(path.name for path in wiki_root.glob("*.md") if path.is_file())
    return files


def _read_wiki_file(filename: str) -> str:
    wiki_root = Path.cwd() / "wiki"
    candidate = (wiki_root / filename).resolve()
    try:
        candidate.relative_to(wiki_root.resolve())
    except ValueError:
        return "Invalid wiki file path."
    if not candidate.exists() or not candidate.is_file():
        return "Wiki file not found."
    return candidate.read_text(encoding="utf-8", errors="replace")


def _ensure_users_table(db_path: str) -> None:
    directory = os.path.dirname(db_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS web_users (
                email TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                is_admin INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _upsert_user(db_path: str, email: str, password_hash: str, is_admin: bool) -> None:
    _ensure_users_table(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO web_users (email, password_hash, is_admin, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
                password_hash = excluded.password_hash,
                is_admin = excluded.is_admin
            """,
            (email.lower(), password_hash, int(is_admin), datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()


def _get_user(db_path: str, email: str) -> dict | None:
    _ensure_users_table(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT email, password_hash, is_admin, created_at FROM web_users WHERE email = ?", (email.lower(),)).fetchone()
    return dict(row) if row else None


def _list_users(db_path: str) -> list[dict]:
    _ensure_users_table(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT email, is_admin, created_at FROM web_users ORDER BY email ASC").fetchall()
    return [dict(row) for row in rows]


def _delete_user(db_path: str, email: str) -> bool:
    _ensure_users_table(db_path)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute("DELETE FROM web_users WHERE email = ?", (email.lower(),))
        conn.commit()
    return cursor.rowcount > 0


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
  {% if page == "status_public" and status_refresh_seconds and status_refresh_seconds > 0 %}
  <meta http-equiv="refresh" content="{{ status_refresh_seconds }}">
  {% endif %}
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    :root {
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
      --input-bg: #ffffff;
      --input-fg: #1e293b;
    }
    body[data-theme="black"] {
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
      --input-bg: #0f141d;
      --input-fg: #e7edf7;
    }
    body {
      background:
        radial-gradient(1100px 450px at 20% -20%, var(--bg-grad-b), transparent 55%),
        radial-gradient(900px 360px at 100% 0%, #10213d, transparent 50%),
        var(--bg);
      min-height: 100vh;
      color: var(--fg);
    }
    .card-soft {
      border: 1px solid var(--border);
      background: var(--card);
      border-radius: 14px;
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
    }
    .brand { font-weight: 700; letter-spacing: .2px; color: var(--fg); }
    a { color: var(--link); }
    .navbar { background: var(--header) !important; border-bottom-color: var(--border) !important; }
    .nav-link { color: var(--fg); }
    .nav-link:hover { color: var(--link); }
    .text-secondary, .small.text-secondary { color: var(--muted) !important; }
    .form-control, .form-select, textarea {
      background: var(--input-bg);
      color: var(--input-fg);
      border-color: var(--border);
    }
    .form-control:focus, .form-select:focus, textarea:focus {
      background: var(--input-bg);
      color: var(--input-fg);
      border-color: var(--btn-bg);
      box-shadow: 0 0 0 .25rem rgba(37, 99, 235, .2);
    }
    .btn-primary { background: var(--btn-bg); border-color: var(--btn-bg); }
    .btn-outline-secondary { border-color: var(--border); color: var(--fg); }
    .btn-outline-secondary:hover { background: var(--btn-secondary); border-color: var(--btn-secondary); color: #fff; }
    .theme-switch { display: inline-flex; border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }
    .theme-btn {
      border: 0;
      background: transparent;
      color: var(--fg);
      padding: 6px 10px;
      cursor: pointer;
      font-weight: 600;
    }
    .theme-btn.active { background: var(--btn-bg); color: #fff; }
    .table-wrap { overflow-x: auto; }
    .status-pill { text-transform: capitalize; }
    .go-page-select { min-width: 180px; max-width: 40vw; }
    @media (max-width: 900px) {
      .theme-switch, .go-page-select { width: 100%; max-width: 100%; }
      .theme-btn { flex: 1; min-height: 42px; }
    }
  </style>
</head>
<body data-theme="light">
  <nav class="navbar navbar-expand-lg border-bottom sticky-top">
    <div class="container-fluid px-3 px-lg-4">
      <a class="navbar-brand brand" href="{{ url_for('home') }}">WickedYoda's Little Helper</a>
      <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#topNav">
        <span class="navbar-toggler-icon"></span>
      </button>
      <div class="collapse navbar-collapse" id="topNav">
        <div class="theme-switch me-2 mb-2 mb-lg-0" aria-label="Theme selector">
          <button type="button" class="theme-btn" data-theme-choice="light">Light</button>
          <button type="button" class="theme-btn" data-theme-choice="black">Black</button>
        </div>
        {% if session.get("user") %}
        <ul class="navbar-nav me-auto mb-2 mb-lg-0">
          <li class="nav-item"><a class="nav-link" href="{{ url_for('home') }}">Home</a></li>
          <li class="nav-item"><a class="nav-link" href="{{ url_for('dashboard') }}">Dashboard</a></li>
          <li class="nav-item"><a class="nav-link" href="{{ url_for('actions') }}">Actions</a></li>
          <li class="nav-item"><a class="nav-link" href="{{ url_for('youtube_subscriptions') }}">YouTube</a></li>
          <li class="nav-item"><a class="nav-link" href="{{ url_for('status_page') }}">Status</a></li>
          <li class="nav-item"><a class="nav-link" href="{{ url_for('logs') }}">Logs</a></li>
          <li class="nav-item"><a class="nav-link" href="{{ url_for('wiki') }}">Wiki</a></li>
          {% if session.get("is_admin") %}
          <li class="nav-item"><a class="nav-link" href="{{ url_for('users') }}">Users</a></li>
          <li class="nav-item"><a class="nav-link" href="{{ url_for('observability') }}">Observability</a></li>
          <li class="nav-item"><a class="nav-link" href="{{ url_for('bot_profile') }}">Bot Profile</a></li>
          <li class="nav-item"><a class="nav-link" href="{{ url_for('guild_settings') }}">Guild Settings</a></li>
          <li class="nav-item"><a class="nav-link" href="{{ url_for('command_permissions') }}">Command Permissions</a></li>
          <li class="nav-item"><a class="nav-link" href="{{ url_for('tag_responses') }}">Tag Responses</a></li>
          <li class="nav-item"><a class="nav-link" href="{{ url_for('settings') }}">Settings</a></li>
          {% endif %}
          <li class="nav-item"><a class="nav-link" href="{{ url_for('account') }}">Account</a></li>
        </ul>
        <div class="d-flex align-items-center gap-2">
          <select id="nav-page-select" class="form-select form-select-sm go-page-select">
            <option value="">Go to page...</option>
            <option value="{{ url_for('home') }}">Home</option>
            <option value="{{ url_for('dashboard') }}">Dashboard</option>
            <option value="{{ url_for('actions') }}">Actions</option>
            <option value="{{ url_for('youtube_subscriptions') }}">YouTube</option>
            <option value="{{ url_for('status_page') }}">Status</option>
            <option value="{{ url_for('logs') }}">Logs</option>
            <option value="{{ url_for('wiki') }}">Wiki</option>
            <option value="{{ url_for('account') }}">Account</option>
            {% if session.get("is_admin") %}
            <option value="{{ url_for('users') }}">Users</option>
            <option value="{{ url_for('observability') }}">Observability</option>
            <option value="{{ url_for('bot_profile') }}">Bot Profile</option>
            <option value="{{ url_for('guild_settings') }}">Guild Settings</option>
            <option value="{{ url_for('command_permissions') }}">Command Permissions</option>
            <option value="{{ url_for('tag_responses') }}">Tag Responses</option>
            <option value="{{ url_for('settings') }}">Settings</option>
            {% endif %}
          </select>
          {% if guild_options %}
          <form method="post" action="{{ url_for('select_guild') }}" class="d-flex">
            <input type="hidden" name="next_endpoint" value="{{ request.endpoint or 'home' }}">
            <select class="form-select form-select-sm" name="guild_id" onchange="this.form.submit()">
              {% for guild in guild_options %}
              <option value="{{ guild.id }}" {% if selected_guild_id == guild.id %}selected{% endif %}>{{ guild.name }}</option>
              {% endfor %}
            </select>
          </form>
          {% endif %}
          {% if session.get("is_admin") and restart_enabled %}
          <form method="post" action="{{ url_for('restart_service') }}" onsubmit="return confirm('WARNING: This restarts the container process. Continue?');">
            <button class="btn btn-outline-danger btn-sm" type="submit">Restart</button>
          </form>
          {% endif %}
          <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('logout') }}">Logout</a>
        </div>
        {% else %}
        <ul class="navbar-nav me-auto mb-2 mb-lg-0">
          <li class="nav-item"><a class="nav-link" href="{{ url_for('public_status_everything') }}">Status</a></li>
        </ul>
        {% endif %}
      </div>
    </div>
  </nav>

  <main class="container px-3 px-lg-4 py-4">
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
    {% if session.get("user") and not session.get("is_admin") %}
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
        <p class="text-secondary mb-0">Manage moderation workflows, guild configuration, notifications, and runtime health from one place.</p>
      </div>
      <div class="row g-3 mb-3">
        <div class="col-6 col-lg-3">
          <a class="card card-soft p-3 h-100 text-decoration-none" href="{{ url_for('dashboard') }}">
            <p class="text-secondary small mb-1">Open</p>
            <p class="mb-0 fw-semibold">Dashboard</p>
          </a>
        </div>
        <div class="col-6 col-lg-3">
          <a class="card card-soft p-3 h-100 text-decoration-none" href="{{ url_for('status_page') }}">
            <p class="text-secondary small mb-1">Open</p>
            <p class="mb-0 fw-semibold">Status</p>
          </a>
        </div>
        <div class="col-6 col-lg-3">
          <a class="card card-soft p-3 h-100 text-decoration-none" href="{{ url_for('observability') }}">
            <p class="text-secondary small mb-1">Open</p>
            <p class="mb-0 fw-semibold">Observability</p>
          </a>
        </div>
        <div class="col-6 col-lg-3">
          <a class="card card-soft p-3 h-100 text-decoration-none" href="{{ url_for('logs') }}">
            <p class="text-secondary small mb-1">Open</p>
            <p class="mb-0 fw-semibold">Logs</p>
          </a>
        </div>
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
    {% elif page == "dashboard" %}
      <div class="row g-3 mb-3">
        <div class="col-12 col-md-4">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">Bot</p>
            <p class="mb-0 fw-semibold">{{ snapshot.bot_name }}</p>
          </div>
        </div>
        <div class="col-12 col-md-4">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">Guild</p>
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
      <div class="row g-3 mb-3">
        <div class="col-6 col-md-4">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">Total Actions</p>
            <p class="mb-0 fs-5 fw-bold">{{ counts.total }}</p>
          </div>
        </div>
        <div class="col-6 col-md-4">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">Success</p>
            <p class="mb-0 fs-5 fw-bold text-success">{{ counts.success }}</p>
          </div>
        </div>
        <div class="col-6 col-md-4">
          <div class="card card-soft p-3 h-100">
            <p class="text-secondary small mb-1">Failed</p>
            <p class="mb-0 fs-5 fw-bold text-danger">{{ counts.failed }}</p>
          </div>
        </div>
      </div>
      <div class="card card-soft p-3">
        <div class="d-flex justify-content-between align-items-center mb-2">
          <h2 class="h6 mb-0">Latest Actions</h2>
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
    {% elif page == "youtube" %}
      <div class="card card-soft p-3 mb-3">
        <h1 class="h5 mb-3">YouTube Notifications</h1>
        <form method="post" action="{{ url_for('youtube_add') }}">
          <div class="row g-2">
            <div class="col-12 col-lg-6">
              <label class="form-label" for="youtube_url">YouTube Channel URL</label>
              <input class="form-control" id="youtube_url" name="youtube_url" placeholder="https://www.youtube.com/@channelname" required>
            </div>
            <div class="col-12 col-lg-4">
              <label class="form-label" for="notify_channel_id">Discord Notify Channel</label>
              <select class="form-select" id="notify_channel_id" name="notify_channel_id" required>
                <option value="">Select channel...</option>
                {% for channel in notification_channels %}
                <option value="{{ channel.id }}">{{ channel.name }} ({{ channel.id }})</option>
                {% endfor %}
              </select>
            </div>
            <div class="col-12 col-lg-2 d-flex align-items-end">
              <button class="btn btn-primary w-100" type="submit">Add</button>
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
            <thead><tr><th>Created (UTC)</th><th>YouTube Channel</th><th>Notify Channel</th><th>Last Video</th><th>Action</th></tr></thead>
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
                  {% if row.last_video_id %}
                    {{ row.last_video_title or row.last_video_id }}<br>
                    <span class="text-secondary">{{ row.last_published_at or '-' }}</span>
                  {% else %}
                    -
                  {% endif %}
                </td>
                <td>
                  <form method="post" action="{{ url_for('youtube_delete', subscription_id=row.id) }}">
                    <button class="btn btn-sm btn-outline-danger" type="submit">Delete</button>
                  </form>
                </td>
              </tr>
              {% else %}
              <tr><td colspan="5" class="text-secondary">No YouTube subscriptions yet.</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </div>
    {% elif page == "logs" %}
      <div class="card card-soft p-3 mb-3">
        <h1 class="h5 mb-3">Logs</h1>
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
        </form>
      </div>
      <div class="card card-soft p-3">
        <pre class="small mb-0" style="white-space: pre-wrap; max-height: 60vh; overflow-y: auto;">{{ log_preview }}</pre>
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
        <p class="small text-secondary">Set command access mode. Use custom role IDs for granular control.</p>
        <form method="post" action="{{ url_for('command_permissions') }}">
          <div class="table-wrap">
            <table class="table table-sm align-middle">
              <thead><tr><th>Command</th><th>Default</th><th>Mode</th><th>Custom Role IDs</th></tr></thead>
              <tbody>
                {% for item in command_permissions.commands %}
                <tr>
                  <td class="small">
                    <div class="fw-semibold">{{ item.label }}</div>
                    <div class="text-secondary">{{ item.description }}</div>
                    <input type="hidden" name="command_key" value="{{ item.key }}">
                  </td>
                  <td class="small">{{ item.default_policy_label }}</td>
                  <td>
                    <select class="form-select" name="mode__{{ item.key }}">
                      <option value="default" {% if item.mode == "default" %}selected{% endif %}>Default</option>
                      <option value="public" {% if item.mode == "public" %}selected{% endif %}>Public</option>
                      <option value="custom_roles" {% if item.mode == "custom_roles" %}selected{% endif %}>Custom roles</option>
                    </select>
                  </td>
                  <td>
                    {% if role_options %}
                    <select class="form-select mb-2" name="role_ids__{{ item.key }}" multiple size="5">
                      {% for role in role_options %}
                      <option value="{{ role.id }}" {% if role.id|string in item.role_id_strings %}selected{% endif %}>{{ role.name }} ({{ role.id }})</option>
                      {% endfor %}
                    </select>
                    {% endif %}
                    <input class="form-control" name="role_ids_text__{{ item.key }}" value="{{ item.role_ids_csv }}" placeholder="Comma-separated role IDs">
                  </td>
                </tr>
                {% endfor %}
              </tbody>
            </table>
          </div>
          <button class="btn btn-primary" type="submit">Save Command Permissions</button>
        </form>
      </div>
    {% elif page == "tag_responses" %}
      <div class="card card-soft p-3">
        <h1 class="h5 mb-3">Tag Responses</h1>
        <p class="small text-secondary">Edit JSON mapping used by `/tag`, `/tags`, and `!tag` message shortcuts.</p>
        <form method="post" action="{{ url_for('tag_responses') }}">
          <div class="mb-3">
            <textarea class="form-control font-monospace" rows="18" name="tag_json">{{ tag_json }}</textarea>
          </div>
          <button class="btn btn-primary" type="submit">Save Tag Responses</button>
        </form>
      </div>
    {% elif page == "users" %}
      <div class="card card-soft p-3 mb-3">
        <h1 class="h5 mb-3">Users</h1>
        <form method="post" action="{{ url_for('users_add') }}">
          <div class="row g-2">
            <div class="col-12 col-lg-4">
              <label class="form-label" for="new_email">Email</label>
              <input class="form-control" id="new_email" name="email" type="email" required>
            </div>
            <div class="col-12 col-lg-4">
              <label class="form-label" for="new_password">Password</label>
              <input class="form-control" id="new_password" name="password" type="password" required>
            </div>
            <div class="col-12 col-lg-2">
              <label class="form-label" for="new_is_admin">Role</label>
              <select class="form-select" id="new_is_admin" name="is_admin">
                <option value="0">Read-only</option>
                <option value="1">Admin</option>
              </select>
            </div>
            <div class="col-12 col-lg-2 d-flex align-items-end">
              <button class="btn btn-primary w-100" type="submit">Add User</button>
            </div>
          </div>
        </form>
      </div>
      <div class="card card-soft p-3">
        <div class="table-wrap">
          <table class="table table-sm align-middle">
            <thead><tr><th>Email</th><th>Role</th><th>Created</th><th>Action</th></tr></thead>
            <tbody>
              {% for row in users %}
              <tr>
                <td class="small">{{ row.email }}</td>
                <td class="small">{{ "Admin" if row.is_admin else "Read-only" }}</td>
                <td class="small">{{ row.created_at }}</td>
                <td>
                  {% if row.email != session.get("user") %}
                  <form method="post" action="{{ url_for('users_delete') }}">
                    <input type="hidden" name="email" value="{{ row.email }}">
                    <button class="btn btn-sm btn-outline-danger" type="submit">Delete</button>
                  </form>
                  {% else %}
                  <span class="small text-secondary">Current user</span>
                  {% endif %}
                </td>
              </tr>
              {% else %}
              <tr><td colspan="4" class="text-secondary">No users available.</td></tr>
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
      </div>
      <div class="row g-3">
        <div class="col-12 col-lg-6">
          <div class="card card-soft p-3 h-100">
            <h2 class="h6 mb-3">Update Identity</h2>
            <form method="post" action="{{ url_for('bot_profile') }}">
              <input type="hidden" name="action" value="identity">
              <div class="mb-3">
                <label class="form-label" for="bot_name">Bot Username (optional)</label>
                <input class="form-control" id="bot_name" name="bot_name" placeholder="WickedYodaBot">
                <div class="form-text">Leave blank to keep current username.</div>
              </div>
              <div class="mb-3">
                <label class="form-label" for="server_nickname">Server Nickname (optional)</label>
                <input class="form-control" id="server_nickname" name="server_nickname" placeholder="WickedYoda's Little Helper">
                <div class="form-text">Nickname applies only to selected guild.</div>
              </div>
              <div class="form-check mb-3">
                <input class="form-check-input" type="checkbox" id="clear_server_nickname" name="clear_server_nickname" value="1">
                <label class="form-check-label" for="clear_server_nickname">Clear server nickname</label>
              </div>
              <button class="btn btn-primary" type="submit">Update Bot Profile</button>
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
                <input class="form-control" id="avatar_file" name="avatar_file" type="file" accept=".png,.jpg,.jpeg,.webp,.gif,image/*" required>
              </div>
              <button class="btn btn-primary" type="submit">Upload Avatar</button>
            </form>
          </div>
        </div>
      </div>
    {% elif page == "account" %}
      <div class="card card-soft p-3">
        <h1 class="h5 mb-3">Account</h1>
        <form method="post" action="{{ url_for('account') }}">
          <div class="mb-3">
            <label class="form-label" for="current_password">Current Password</label>
            <input class="form-control" id="current_password" name="current_password" type="password" required>
          </div>
          <div class="mb-3">
            <label class="form-label" for="new_password">New Password</label>
            <input class="form-control" id="new_password" name="new_password" type="password" required>
          </div>
          <button class="btn btn-primary" type="submit">Update Password</button>
        </form>
      </div>
    {% elif page == "guild_settings" %}
      <div class="card card-soft p-3">
        <h1 class="h5 mb-3">Guild Settings</h1>
        <form method="post" action="{{ url_for('guild_settings') }}">
          <div class="mb-3">
            <label class="form-label" for="bot_log_channel_id">Bot Log Channel</label>
            <select class="form-select" id="bot_log_channel_id" name="bot_log_channel_id">
              <option value="">Use global default (env Bot_Log_Channel)</option>
              {% for channel in notification_channels %}
              <option value="{{ channel.id }}" {% if selected_log_channel_id == channel.id|string %}selected{% endif %}>
                {{ channel.name }} ({{ channel.id }})
              </option>
              {% endfor %}
            </select>
            <div class="form-text">This guild-specific channel receives bot action logs and overrides the global env value.</div>
          </div>
          <button class="btn btn-primary" type="submit">Save Guild Settings</button>
        </form>
      </div>
    {% elif page == "settings" %}
      <div class="card card-soft p-3">
        <h1 class="h5 mb-3">Runtime Settings</h1>
        <form method="post" action="{{ url_for('settings_save') }}">
          <div class="row g-3">
            {% for item in settings %}
            <div class="col-12 col-lg-6">
              <label class="form-label" for="field_{{ item.key }}"><code>{{ item.key }}</code></label>
              {% if item.options %}
              <select class="form-select" id="field_{{ item.key }}" name="{{ item.key }}">
                {% for option in item.options %}
                <option value="{{ option }}" {% if option == item.value %}selected{% endif %}>{{ option }}</option>
                {% endfor %}
              </select>
              {% elif item.is_sensitive %}
              <input class="form-control" id="field_{{ item.key }}" name="{{ item.key }}" value="{{ item.masked_value }}" autocomplete="off">
              <div class="form-text">Leave as `********` to keep existing value.</div>
              {% else %}
              <input class="form-control" id="field_{{ item.key }}" name="{{ item.key }}" value="{{ item.value }}">
              {% endif %}
            </div>
            {% endfor %}
          </div>
          <div class="mt-3 d-flex gap-2">
            <button class="btn btn-primary" type="submit">Save Settings</button>
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
      const fallbackTheme = "light";
      const allowed = { light: true, black: true };

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

      const navSelect = document.getElementById("nav-page-select");
      if (navSelect) {
        navSelect.addEventListener("change", function () {
          const target = navSelect.value || "";
          if (!target) { return; }
          window.location.href = target;
          navSelect.value = "";
        });
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
    request_restart: Callable[[str], dict] | None = None,
    resolve_youtube_subscription: Callable[[str], dict] | None = None,
) -> Flask:
    app = Flask(__name__)
    configured_secret = os.getenv("WEB_ADMIN_SESSION_SECRET")
    if configured_secret:
        app.secret_key = configured_secret
    else:
        app.secret_key = secrets.token_urlsafe(48)
        app.logger.warning("WEB_ADMIN_SESSION_SECRET not set. Generated ephemeral secret for this runtime.")

    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = os.getenv("WEB_SESSION_COOKIE_SAMESITE", "Lax")
    app.config["SESSION_COOKIE_SECURE"] = _env_bool("WEB_SESSION_COOKIE_SECURE", False)
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
        audit_log_path = _resolve_log_directory(db_path) / "web_gui_audit.log"
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
    admin_password = os.getenv("WEB_ADMIN_DEFAULT_PASSWORD", "")
    admin_password_hash = os.getenv("WEB_ADMIN_DEFAULT_PASSWORD_HASH", "")

    if not admin_password_hash:
        if not admin_password:
            admin_password = secrets.token_urlsafe(16)
            app.logger.warning("WEB_ADMIN_DEFAULT_PASSWORD not set. Generated one-time random admin password for this run.")
        admin_password_hash = generate_password_hash(admin_password)
    elif admin_password_hash.startswith(("pbkdf2:", "scrypt:")):
        pass
    else:
        admin_password_hash = generate_password_hash(admin_password_hash)

    _upsert_user(db_path, admin_user, admin_password_hash, is_admin=True)

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
            options.append({"id": guild_id, "name": raw_name.strip() or str(guild_id)})

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
        return render_template_string(
            PAGE_TEMPLATE,
            page=page,
            title=title,
            csrf_token=_ensure_csrf_token(),
            selected_guild_id=selected_guild_id,
            selected_guild_name=selected_guild_name,
            guild_options=guild_options,
            restart_enabled=restart_enabled,
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

    def _call_request_restart(actor: str) -> dict:
        if not callable(request_restart):
            return {"ok": False, "error": "Restart callback is not configured."}
        return request_restart(actor)

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
        session.pop("auth_mode", None)
        session.pop("auth_issued_at", None)
        session.pop("auth_last_seen", None)
        session.pop("auth_remember_until", None)

    def _set_auth_session(user: dict, remember_login: bool) -> None:
        now_dt = datetime.now(UTC)
        session["user"] = str(user.get("email", "")).strip().lower()
        session["is_admin"] = bool(user.get("is_admin"))
        session["auth_mode"] = AUTH_MODE_REMEMBER if remember_login else AUTH_MODE_STANDARD
        session["auth_issued_at"] = now_dt.isoformat()
        session["auth_last_seen"] = now_dt.isoformat()
        if remember_login:
            session["auth_remember_until"] = (now_dt + timedelta(days=REMEMBER_LOGIN_DAYS)).isoformat()
        else:
            session.pop("auth_remember_until", None)
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

    @app.before_request
    def mark_request_start():
        request.environ["wickedyoda_request_start"] = time.perf_counter()
        return None

    @app.before_request
    def enforce_post_security():
        if request.method != "POST":
            return None
        if request.endpoint in {"healthz"}:
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

    @app.get("/healthz")
    def healthz():
        return {"status": "ok", "timestamp": datetime.now(UTC).isoformat()}

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
        if request.endpoint != "healthz":
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
        return _render_page(
            "status_public",
            "Bot Status",
            counts=counts,
            actions=actions,
            snapshot=snapshot,
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
        return _render_page(
            "home",
            "Web Admin Home",
            counts=counts,
            actions=actions,
            snapshot=snapshot,
        )

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

    @app.get("/admin/observability")
    @login_required
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
    @admin_required
    def bot_profile():
        selected_guild_id, _, _ = _selected_guild_context()
        profile_payload = _call_get_bot_profile(selected_guild_id)

        if request.method == "POST":
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
        login_allowed_endpoints = {
            "home",
            "dashboard",
            "status_page",
            "actions",
            "youtube_subscriptions",
            "logs",
            "wiki",
            "account",
            "observability",
            "public_status_everything",
        }
        admin_only_endpoints = {
            "users",
            "command_permissions",
            "tag_responses",
            "guild_settings",
            "settings",
            "bot_profile",
        }
        allowed_endpoints = login_allowed_endpoints | admin_only_endpoints
        if next_endpoint in allowed_endpoints:
            if next_endpoint in admin_only_endpoints and not bool(session.get("is_admin")):
                return redirect(url_for("home"))
            return redirect(url_for(next_endpoint))
        return redirect(url_for("home"))

    @app.get("/admin")
    @login_required
    def dashboard():
        selected_guild_id, _, _ = _selected_guild_context()
        counts = _fetch_counts(db_path, guild_id=selected_guild_id)
        actions = _fetch_actions(db_path, limit=15, guild_id=selected_guild_id)
        snapshot = get_bot_snapshot()
        return _render_page(
            "dashboard",
            "Web Admin Dashboard",
            counts=counts,
            actions=actions,
            snapshot=snapshot,
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
        return _render_page(
            "youtube",
            "YouTube Notifications",
            notification_channels=channels,
            subscriptions=_fetch_youtube_subscriptions(db_path, limit=300, channel_ids=channel_ids),
        )

    @app.post("/admin/youtube/add")
    @login_required
    def youtube_add():
        selected_guild_id, _, _ = _selected_guild_context()
        source_url = request.form.get("youtube_url", "").strip()
        selected_channel_id = request.form.get("notify_channel_id", "").strip()
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
        if not callable(resolve_youtube_subscription):
            flash("YouTube resolver is not configured in the bot runtime.", "danger")
            return redirect(url_for("youtube_subscriptions"))

        try:
            details = resolve_youtube_subscription(source_url)
            channel_id = str(details.get("channel_id", "")).strip()
            if not channel_id:
                raise ValueError("Resolved channel ID is empty.")
            _upsert_youtube_subscription(
                db_path,
                source_url=str(details.get("source_url", source_url)),
                channel_id=channel_id,
                channel_title=str(details.get("channel_title", "Unknown Channel")),
                target_channel_id=int(selected_channel["id"]),
                target_channel_name=str(selected_channel["name"]),
                last_video_id=str(details.get("last_video_id", "")),
                last_video_title=str(details.get("last_video_title", "")),
                last_published_at=str(details.get("last_published_at", "")),
            )
        except Exception as exc:
            flash(f"Failed to add YouTube subscription: {exc}", "danger")
            return redirect(url_for("youtube_subscriptions"))

        flash("YouTube subscription saved.", "success")
        return redirect(url_for("youtube_subscriptions"))

    @app.post("/admin/youtube/<int:subscription_id>/delete")
    @login_required
    def youtube_delete(subscription_id: int):
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

    @app.get("/admin/logs")
    @login_required
    def logs():
        log_dir = _resolve_log_directory(db_path)
        log_options = list(LOG_FILE_OPTIONS)
        resolved_paths = {option: _resolve_log_path(log_dir, option) for option in log_options}
        existing_logs = [option for option, path in resolved_paths.items() if path is not None and path.exists() and path.is_file()]
        default_log = existing_logs[0] if existing_logs else log_options[0]
        selected_log = Path(request.args.get("log", default_log).strip()).name
        if selected_log not in log_options:
            selected_log = default_log
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
        )

    @app.get("/admin/wiki")
    @login_required
    def wiki():
        wiki_files = _list_wiki_files()
        selected_wiki = request.args.get("doc", "").strip()
        if wiki_files:
            if selected_wiki not in wiki_files:
                selected_wiki = wiki_files[0]
            wiki_content = _read_wiki_file(selected_wiki)
        else:
            selected_wiki = ""
            wiki_content = "No wiki markdown files found in ./wiki."
        return _render_page(
            "wiki",
            "Web Admin Wiki",
            wiki_files=wiki_files,
            selected_wiki=selected_wiki,
            wiki_content=wiki_content,
            github_wiki_url=os.getenv("WEB_GITHUB_WIKI_URL", "").strip(),
        )

    @app.route("/admin/command-permissions", methods=["GET", "POST"])
    @admin_required
    def command_permissions():
        selected_guild_id, _, _ = _selected_guild_context()
        permissions_payload = _call_get_command_permissions(selected_guild_id)
        catalog_payload = _call_get_discord_catalog(selected_guild_id)
        role_options = []
        if isinstance(catalog_payload, dict) and catalog_payload.get("ok"):
            role_options = catalog_payload.get("roles", []) or []

        if request.method == "POST":
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
    @admin_required
    def tag_responses():
        selected_guild_id, _, _ = _selected_guild_context()
        if request.method == "POST":
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
    @admin_required
    def guild_settings():
        selected_guild_id, _, _ = _selected_guild_context()
        catalog_payload = _call_get_discord_catalog(selected_guild_id)
        channel_options: list[dict] = []
        if isinstance(catalog_payload, dict) and catalog_payload.get("ok"):
            raw_channels = catalog_payload.get("channels", [])
            if isinstance(raw_channels, list):
                channel_options = [item for item in raw_channels if isinstance(item, dict)]

        if request.method == "POST":
            payload = {"bot_log_channel_id": request.form.get("bot_log_channel_id", "").strip()}
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
        if isinstance(settings_payload, dict):
            raw_channel_id = settings_payload.get("bot_log_channel_id", "")
            selected_log_channel_id = str(raw_channel_id).strip() if raw_channel_id is not None else ""
        return _render_page(
            "guild_settings",
            "Guild Settings",
            guild_settings=settings_payload if isinstance(settings_payload, dict) else {"ok": False},
            notification_channels=channel_options,
            selected_log_channel_id=selected_log_channel_id,
        )

    @app.get("/admin/users")
    @admin_required
    def users():
        return _render_page(
            "users",
            "Web Admin Users",
            users=_list_users(db_path),
        )

    @app.post("/admin/users/add")
    @admin_required
    def users_add():
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        is_admin = request.form.get("is_admin", "0").strip() == "1"

        if not _is_valid_email(email):
            flash("Please provide a valid email address.", "danger")
            return redirect(url_for("users"))
        if len(password) < 8:
            flash("Password must be at least 8 characters.", "danger")
            return redirect(url_for("users"))

        _upsert_user(db_path, email, generate_password_hash(password), is_admin=is_admin)
        flash("User saved.", "success")
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
        if request.method == "POST":
            current_password = request.form.get("current_password", "")
            new_password = request.form.get("new_password", "")
            current_user = str(session.get("user", "")).strip().lower()
            user = _get_user(db_path, current_user)
            if not user:
                _clear_auth_session()
                flash("Session expired. Please log in again.", "warning")
                return redirect(url_for("login"))
            if not check_password_hash(str(user["password_hash"]), current_password):
                flash("Current password is incorrect.", "danger")
                return redirect(url_for("account"))
            if len(new_password) < 8:
                flash("New password must be at least 8 characters.", "danger")
                return redirect(url_for("account"))

            _upsert_user(
                db_path,
                current_user,
                generate_password_hash(new_password),
                is_admin=bool(user.get("is_admin")),
            )
            flash("Password updated.", "success")
            return redirect(url_for("account"))

        return _render_page("account", "Web Admin Account")

    @app.get("/admin/settings")
    @admin_required
    def settings():
        settings_view = _build_settings_fields()
        return _render_page(
            "settings",
            "Web Admin Settings",
            settings=settings_view,
        )

    @app.post("/admin/settings/save")
    @admin_required
    def settings_save():
        settings_fields = _build_settings_fields()
        allowed_keys = [item["key"] for item in settings_fields]
        current_values = {item["key"]: item["value"] for item in settings_fields}

        payload = {key: request.form.get(key, current_values.get(key, "")) for key in allowed_keys}
        for key in allowed_keys:
            if _is_sensitive_key(key):
                raw_value = payload[key].strip()
                if raw_value == "********":
                    payload[key] = current_values.get(key, "")

        validated, errors = _validate_settings_payload(payload, allowed_keys)
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
    request_restart: Callable[[str], dict] | None = None,
    resolve_youtube_subscription: Callable[[str], dict] | None = None,
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
        request_restart=request_restart,
        resolve_youtube_subscription=resolve_youtube_subscription,
    )

    def run() -> None:
        try:
            app.run(host=host, port=port, debug=False, use_reloader=False, ssl_context=ssl_context)
        except Exception:
            logging.getLogger("wickedyoda-helper").exception("Web admin listener failed to start on %s:%s", host, port)

    thread = threading.Thread(target=run, daemon=True, name="web-admin")
    thread.start()
    return thread
