import json
import os
import secrets
import sqlite3
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from functools import wraps
from pathlib import Path

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
SETTINGS_FIELD_ORDER = [
    "DISCORD_TOKEN",
    "GUILD_ID",
    "Bot_Log_Channel",
    "WEB_ENABLED",
    "WEB_BIND_HOST",
    "WEB_PORT",
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
    "DATA_DIR",
    "LOG_DIR",
    "ACTION_DB_PATH",
    "WEB_ENV_FILE",
    "WEB_GITHUB_WIKI_URL",
]
SETTINGS_DROPDOWN_OPTIONS: dict[str, tuple[str, ...]] = {
    "WEB_ENABLED": BOOL_SELECT_OPTIONS,
    "ENABLE_MEMBERS_INTENT": BOOL_SELECT_OPTIONS,
    "COMMAND_RESPONSES_EPHEMERAL": BOOL_SELECT_OPTIONS,
    "SHORTENER_ENABLED": BOOL_SELECT_OPTIONS,
    "YOUTUBE_NOTIFY_ENABLED": BOOL_SELECT_OPTIONS,
    "UPTIME_STATUS_ENABLED": BOOL_SELECT_OPTIONS,
    "WEB_SESSION_COOKIE_SECURE": BOOL_SELECT_OPTIONS,
    "WEB_SESSION_COOKIE_SAMESITE": SESSION_SAMESITE_OPTIONS,
    "WEB_SESSION_TIMEOUT_MINUTES": ("30", "60", "120", "240"),
    "WEB_PORT": ("8080", "8000", "5000"),
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


def _fetch_actions(db_path: str, limit: int = 200) -> list[dict]:
    _ensure_actions_table(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT created_at, action, status, moderator, target, reason, guild
            FROM actions
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def _fetch_youtube_subscriptions(db_path: str, limit: int = 300) -> list[dict]:
    _ensure_youtube_subscriptions_table(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, created_at, source_url, channel_id, channel_title, target_channel_id,
                   target_channel_name, last_video_id, last_video_title, last_published_at, enabled
            FROM youtube_subscriptions
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
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


def _fetch_counts(db_path: str) -> dict:
    _ensure_actions_table(db_path)
    with sqlite3.connect(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM actions").fetchone()[0]
        success = conn.execute("SELECT COUNT(*) FROM actions WHERE status='success'").fetchone()[0]
        failed = conn.execute("SELECT COUNT(*) FROM actions WHERE status='failed'").fetchone()[0]
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
        if key in {"GUILD_ID", "Bot_Log_Channel", "WEB_PORT"} and raw_value:
            if not raw_value.isdigit():
                errors.append(f"{key} must be numeric.")
                continue
        validated[key] = raw_value
    return validated, errors


def _resolve_log_directory(db_path: str) -> Path:
    configured = os.getenv("LOG_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path(db_path).resolve().parent


def _tail_file(path: Path, line_limit: int = 400) -> str:
    if not path.exists() or not path.is_file():
        return f"Log file not found: {path}"
    with path.open("r", encoding="utf-8", errors="replace") as handle:
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


PAGE_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ title }}</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body { background: linear-gradient(180deg, #f3f6fa 0%, #ffffff 55%); min-height: 100vh; }
    .card-soft { border: 0; border-radius: 14px; box-shadow: 0 8px 24px rgba(0,0,0,0.08); }
    .brand { font-weight: 700; letter-spacing: .2px; }
    .table-wrap { overflow-x: auto; }
    .status-pill { text-transform: capitalize; }
  </style>
</head>
<body>
  <nav class="navbar navbar-expand-lg bg-white border-bottom sticky-top">
    <div class="container-fluid px-3 px-lg-4">
      <a class="navbar-brand brand" href="{{ url_for('dashboard') }}">WickedYoda's Little Helper</a>
      <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#topNav">
        <span class="navbar-toggler-icon"></span>
      </button>
      <div class="collapse navbar-collapse" id="topNav">
        {% if session.get("user") %}
        <ul class="navbar-nav me-auto mb-2 mb-lg-0">
          <li class="nav-item"><a class="nav-link" href="{{ url_for('dashboard') }}">Dashboard</a></li>
          <li class="nav-item"><a class="nav-link" href="{{ url_for('actions') }}">Actions</a></li>
          <li class="nav-item"><a class="nav-link" href="{{ url_for('youtube_subscriptions') }}">YouTube</a></li>
          <li class="nav-item"><a class="nav-link" href="{{ url_for('logs') }}">Logs</a></li>
          <li class="nav-item"><a class="nav-link" href="{{ url_for('wiki') }}">Wiki</a></li>
          {% if session.get("is_admin") %}
          <li class="nav-item"><a class="nav-link" href="{{ url_for('users') }}">Users</a></li>
          <li class="nav-item"><a class="nav-link" href="{{ url_for('command_permissions') }}">Command Permissions</a></li>
          <li class="nav-item"><a class="nav-link" href="{{ url_for('tag_responses') }}">Tag Responses</a></li>
          <li class="nav-item"><a class="nav-link" href="{{ url_for('settings') }}">Settings</a></li>
          {% endif %}
          <li class="nav-item"><a class="nav-link" href="{{ url_for('account') }}">Account</a></li>
        </ul>
        <div class="d-flex">
          <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('logout') }}">Logout</a>
        </div>
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

    {% if page == "login" %}
      <div class="row justify-content-center mt-4">
        <div class="col-12 col-sm-10 col-md-7 col-lg-5">
          <div class="card card-soft p-4">
            <h1 class="h4 mb-3">Admin Login</h1>
            <form method="post">
              <div class="mb-3">
                <label class="form-label" for="username">Username</label>
                <input class="form-control" id="username" name="username" required autocomplete="username">
              </div>
              <div class="mb-3">
                <label class="form-label" for="password">Password</label>
                <input class="form-control" id="password" name="password" type="password" required autocomplete="current-password">
              </div>
              <button class="btn btn-primary w-100" type="submit">Sign in</button>
            </form>
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
            <p class="mb-0 fw-semibold">{{ snapshot.guild_id }}</p>
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
</body>
</html>
"""


def create_app(
    db_path: str,
    get_bot_snapshot: Callable[[], dict],
    get_notification_channels: Callable[[], list[dict]] | None = None,
    get_discord_catalog: Callable[[], dict] | None = None,
    get_command_permissions: Callable[[], dict] | None = None,
    save_command_permissions: Callable[[dict, str], dict] | None = None,
    get_tag_responses: Callable[[], dict] | None = None,
    save_tag_responses: Callable[[dict, str], dict] | None = None,
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
    app.permanent_session_lifetime = timedelta(minutes=_env_int("WEB_SESSION_TIMEOUT_MINUTES", 60))

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
            if not session.get("user"):
                return redirect(url_for("login"))
            return handler(*args, **kwargs)

        return wrapped

    def admin_required(handler):
        @wraps(handler)
        def wrapped(*args, **kwargs):
            if not session.get("user"):
                return redirect(url_for("login"))
            if not session.get("is_admin"):
                flash("Admin access required.", "danger")
                return redirect(url_for("dashboard"))
            return handler(*args, **kwargs)

        return wrapped

    @app.get("/healthz")
    def healthz():
        return {"status": "ok", "timestamp": datetime.now(UTC).isoformat()}

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault(
            "Content-Security-Policy", "default-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data:;"
        )
        return response

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            user = is_valid_login(username, password)
            if user:
                session.permanent = True
                session["user"] = str(user["email"]).lower()
                session["is_admin"] = bool(user["is_admin"])
                flash("Logged in.", "success")
                return redirect(url_for("dashboard"))
            flash("Invalid credentials.", "danger")
        return render_template_string(PAGE_TEMPLATE, page="login", title="Web Admin Login")

    @app.get("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.get("/")
    def index():
        if session.get("user"):
            return redirect(url_for("dashboard"))
        return redirect(url_for("login"))

    @app.get("/admin")
    @login_required
    def dashboard():
        counts = _fetch_counts(db_path)
        actions = _fetch_actions(db_path, limit=15)
        snapshot = get_bot_snapshot()
        return render_template_string(
            PAGE_TEMPLATE,
            page="dashboard",
            title="Web Admin Dashboard",
            counts=counts,
            actions=actions,
            snapshot=snapshot,
        )

    @app.get("/admin/actions")
    @login_required
    def actions():
        return render_template_string(
            PAGE_TEMPLATE,
            page="actions",
            title="Moderation Action History",
            actions=_fetch_actions(db_path, limit=300),
        )

    @app.get("/admin/youtube")
    @login_required
    def youtube_subscriptions():
        channels = get_notification_channels() if callable(get_notification_channels) else []
        return render_template_string(
            PAGE_TEMPLATE,
            page="youtube",
            title="YouTube Notifications",
            notification_channels=channels,
            subscriptions=_fetch_youtube_subscriptions(db_path, limit=300),
        )

    @app.post("/admin/youtube/add")
    @login_required
    def youtube_add():
        source_url = request.form.get("youtube_url", "").strip()
        selected_channel_id = request.form.get("notify_channel_id", "").strip()
        channels = get_notification_channels() if callable(get_notification_channels) else []
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
        discovered_logs = sorted(path.name for path in log_dir.glob("*.log") if path.is_file())
        log_options = list(dict.fromkeys([*LOG_FILE_OPTIONS, *discovered_logs]))
        if not log_options:
            log_options = list(LOG_FILE_OPTIONS)
        selected_log = request.args.get("log", log_options[0]).strip()
        if selected_log not in log_options:
            selected_log = log_options[0]
        log_preview = _tail_file(log_dir / selected_log)
        return render_template_string(
            PAGE_TEMPLATE,
            page="logs",
            title="Web Admin Logs",
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
        return render_template_string(
            PAGE_TEMPLATE,
            page="wiki",
            title="Web Admin Wiki",
            wiki_files=wiki_files,
            selected_wiki=selected_wiki,
            wiki_content=wiki_content,
            github_wiki_url=os.getenv("WEB_GITHUB_WIKI_URL", "").strip(),
        )

    @app.route("/admin/command-permissions", methods=["GET", "POST"])
    @admin_required
    def command_permissions():
        permissions_payload = (
            get_command_permissions()
            if callable(get_command_permissions)
            else {"ok": False, "error": "Command permissions callback not configured."}
        )
        catalog_payload = get_discord_catalog() if callable(get_discord_catalog) else {}
        role_options = []
        if isinstance(catalog_payload, dict) and catalog_payload.get("ok"):
            role_options = catalog_payload.get("roles", []) or []

        if request.method == "POST":
            if not callable(save_command_permissions):
                flash("Command permissions save callback is not configured.", "danger")
            else:
                command_updates: dict[str, dict] = {}
                for command_key in request.form.getlist("command_key"):
                    command_updates[command_key] = {
                        "mode": request.form.get(f"mode__{command_key}", "default"),
                        "role_ids": request.form.getlist(f"role_ids__{command_key}")
                        or request.form.get(f"role_ids_text__{command_key}", ""),
                    }
                save_result = save_command_permissions(command_updates and {"commands": command_updates}, str(session.get("user", "")))
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

        return render_template_string(
            PAGE_TEMPLATE,
            page="command_permissions",
            title="Web Admin Command Permissions",
            command_permissions=permissions_payload,
            role_options=role_options,
        )

    @app.route("/admin/tag-responses", methods=["GET", "POST"])
    @admin_required
    def tag_responses():
        if request.method == "POST":
            raw_json = request.form.get("tag_json", "")
            try:
                payload = json.loads(raw_json)
                if not isinstance(payload, dict):
                    raise ValueError("Tag response JSON must be an object.")
                if not callable(save_tag_responses):
                    raise ValueError("Tag response save callback is not configured.")
                result = save_tag_responses(payload, str(session.get("user", "")))
                if not isinstance(result, dict) or not result.get("ok"):
                    raise ValueError(
                        str(result.get("error", "Failed to save tag responses.")) if isinstance(result, dict) else "Invalid save response."
                    )
                flash(str(result.get("message", "Tag responses updated.")), "success")
            except Exception as exc:
                flash(f"Invalid tag JSON: {exc}", "danger")

        mapping: dict[str, str] = {}
        if callable(get_tag_responses):
            response = get_tag_responses()
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
        return render_template_string(
            PAGE_TEMPLATE,
            page="tag_responses",
            title="Web Admin Tag Responses",
            tag_json=tag_json,
        )

    @app.get("/admin/users")
    @admin_required
    def users():
        return render_template_string(
            PAGE_TEMPLATE,
            page="users",
            title="Web Admin Users",
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
                session.clear()
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

        return render_template_string(
            PAGE_TEMPLATE,
            page="account",
            title="Web Admin Account",
        )

    @app.get("/admin/settings")
    @admin_required
    def settings():
        settings_view = _build_settings_fields()
        return render_template_string(
            PAGE_TEMPLATE,
            page="settings",
            title="Web Admin Settings",
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
    get_notification_channels: Callable[[], list[dict]] | None,
    get_discord_catalog: Callable[[], dict] | None,
    get_command_permissions: Callable[[], dict] | None,
    save_command_permissions: Callable[[dict, str], dict] | None,
    get_tag_responses: Callable[[], dict] | None,
    save_tag_responses: Callable[[dict, str], dict] | None,
    resolve_youtube_subscription: Callable[[str], dict] | None,
    host: str,
    port: int,
) -> threading.Thread:
    app = create_app(
        db_path,
        get_bot_snapshot,
        get_notification_channels=get_notification_channels,
        get_discord_catalog=get_discord_catalog,
        get_command_permissions=get_command_permissions,
        save_command_permissions=save_command_permissions,
        get_tag_responses=get_tag_responses,
        save_tag_responses=save_tag_responses,
        resolve_youtube_subscription=resolve_youtube_subscription,
    )

    def run() -> None:
        app.run(host=host, port=port, debug=False, use_reloader=False)

    thread = threading.Thread(target=run, daemon=True, name="web-admin")
    thread.start()
    return thread
