"""Extended moderation: cases, notes, warnings, reports, appeals, automod, raids.

This module is deliberately free of Discord imports so the pure detection
helpers and the SQLite store can be unit-tested without a gateway connection.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from typing import Any

DEFAULT_BLOCKED_EXTENSIONS = (
    "exe",
    "bat",
    "cmd",
    "com",
    "scr",
    "msi",
    "ps1",
    "vbs",
    "js",
    "jar",
    "sh",
    "app",
    "dll",
)

INVITE_PATTERN = re.compile(r"(?:discord\.(?:gg|com/invite|me)/[A-Za-z0-9\-_]+)", re.IGNORECASE)
URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
EMOJI_PATTERN = re.compile("[\U0001f300-\U0001faff\u2600-\u27bf]")
CUSTOM_EMOJI_PATTERN = re.compile(r"<a?:[A-Za-z0-9_]+:\d+>")
ZALGO_PATTERN = re.compile(r"[\u0300-\u036f\u0489\u1ab0-\u1aff\u1dc0-\u1dff\u20d0-\u20ff\ufe20-\ufe2f]")

CASE_ACTIONS = (
    "warn",
    "timeout",
    "kick",
    "ban",
    "softban",
    "unban",
    "note",
    "automod",
    "report",
    "quarantine",
    "lockdown",
    "sharedban",
)

_STORE_CACHE: dict[str, ModerationStore] = {}
_STORE_LOCK = threading.Lock()


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_now() -> str:
    return utc_now().strftime("%Y-%m-%d %H:%M:%S")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None


def _json_list(raw: Any) -> list:
    if isinstance(raw, list):
        return raw
    text = str(raw or "").strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _int_list(raw: Any) -> list[int]:
    values: list[int] = []
    for item in _json_list(raw):
        try:
            values.append(int(item))
        except (TypeError, ValueError):
            continue
    return values


def normalize_content(content: str) -> str:
    return " ".join(str(content or "").lower().split())


def count_emoji(content: str) -> int:
    """Count Unicode emoji plus Discord custom/animated emoji syntax."""
    text = str(content or "")
    return len(EMOJI_PATTERN.findall(text)) + len(CUSTOM_EMOJI_PATTERN.findall(text))


def chunk_text(text: str, limit: int = 1900) -> list[str]:
    """Split text into chunks that fit inside a Discord message."""
    value = str(text or "")
    if len(value) <= limit:
        return [value] if value else []
    chunks: list[str] = []
    current = ""
    for line in value.splitlines():
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        while len(line) > limit:
            chunks.append(line[:limit])
            line = line[limit:]
        current = line
    if current:
        chunks.append(current)
    return chunks


def neutralize_csv_cell(value: Any) -> Any:
    """Prevent spreadsheet formula injection in exported CSV cells."""
    if value is None:
        return ""
    text = str(value)
    if text[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


def contains_invite(content: str) -> bool:
    return bool(INVITE_PATTERN.search(str(content or "")))


def extract_urls(content: str) -> list[str]:
    return URL_PATTERN.findall(str(content or ""))


def url_allowed(url: str, allowlist: list[str]) -> bool:
    """Return True when the URL host matches an allowlist entry exactly or as a subdomain."""
    from urllib.parse import urlparse

    try:
        host = (urlparse(url).hostname or "").lower().strip(".")
    except ValueError:
        return False
    if not host:
        return False
    for entry in allowlist:
        allowed = str(entry or "").lower().strip().strip(".")
        if not allowed:
            continue
        if host == allowed or host.endswith("." + allowed):
            return True
    return False


def match_regex_rules(content: str, rules: list[dict]) -> str | None:
    text = str(content or "")
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        pattern = str(rule.get("pattern") or "").strip()
        if not pattern:
            continue
        try:
            if re.search(pattern, text, re.IGNORECASE):
                return str(rule.get("reason") or pattern)
        except re.error:
            continue
    return None


def attachment_violation(attachments: list[dict], blocked_extensions: list[str], max_mb: int) -> str | None:
    blocked = {str(ext).lower().lstrip(".") for ext in blocked_extensions}
    max_bytes = max(0, int(max_mb)) * 1024 * 1024
    for item in attachments:
        filename = str(item.get("filename") or "")
        size = int(item.get("size") or 0)
        extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if extension and extension in blocked:
            return f"blocked attachment type .{extension}"
        if max_bytes and size > max_bytes:
            return f"attachment exceeds {max_mb} MB"
    return None


def detect_spam(
    *,
    content: str,
    recent_contents: list[str],
    mention_count: int,
    emoji_count: int,
    settings: dict,
) -> str | None:
    """Return a human-readable reason when the message trips an anti-spam rule."""
    text = str(content or "")
    normalized = normalize_content(text)

    duplicate_threshold = settings.get("duplicate_threshold")
    duplicate_threshold = 3 if duplicate_threshold is None else int(duplicate_threshold)
    if duplicate_threshold > 0 and normalized:
        duplicates = sum(1 for item in recent_contents if normalize_content(item) == normalized)
        if duplicates + 1 >= duplicate_threshold:
            return "repeated message"

    mention_limit = settings.get("mention_limit")
    mention_limit = 5 if mention_limit is None else int(mention_limit)
    if mention_limit > 0 and mention_count > mention_limit:
        return f"mention spam ({mention_count} mentions)"

    emoji_limit = settings.get("emoji_limit")
    emoji_limit = 10 if emoji_limit is None else int(emoji_limit)
    if emoji_limit > 0 and emoji_count > emoji_limit:
        return f"emoji spam ({emoji_count} emoji)"

    caps_ratio = float(settings.get("caps_ratio") or 0.7)
    letters = [char for char in text if char.isalpha()]
    if caps_ratio > 0 and len(letters) >= 12:
        uppercase = sum(1 for char in letters if char.isupper())
        if uppercase / len(letters) >= caps_ratio:
            return "excessive capitalisation"

    if len(ZALGO_PATTERN.findall(text)) > 10:
        return "zalgo text"

    return None


def escalation_action(count: int, ladder: list[dict]) -> dict | None:
    """Pick the highest ladder rung whose threshold is met."""
    chosen: dict | None = None
    for rung in ladder:
        if not isinstance(rung, dict):
            continue
        try:
            threshold = int(rung.get("threshold") or 0)
        except (TypeError, ValueError):
            continue
        if threshold > 0 and count >= threshold:
            if chosen is None or threshold >= int(chosen.get("threshold") or 0):
                chosen = rung
    return chosen


def in_quiet_hours(now: datetime, start_hour: int, end_hour: int) -> bool:
    start = int(start_hour) % 24
    end = int(end_hour) % 24
    hour = now.hour
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


class ModerationStore:
    """SQLite-backed store for the extended moderation suite."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._lock = threading.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS mod_cases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    case_number INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    action TEXT NOT NULL,
                    target_id INTEGER,
                    target_name TEXT,
                    moderator_id INTEGER,
                    moderator_name TEXT,
                    reason TEXT,
                    duration_minutes INTEGER,
                    channel_id INTEGER,
                    message_id INTEGER,
                    source TEXT NOT NULL DEFAULT 'command',
                    status TEXT NOT NULL DEFAULT 'active',
                    metadata_json TEXT,
                    UNIQUE(guild_id, case_number)
                );
                CREATE INDEX IF NOT EXISTS idx_mod_cases_target
                    ON mod_cases (guild_id, target_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_mod_cases_action
                    ON mod_cases (guild_id, action, created_at);

                CREATE TABLE IF NOT EXISTS mod_notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    target_id INTEGER NOT NULL,
                    author_id INTEGER,
                    author_name TEXT,
                    note TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_mod_notes_target
                    ON mod_notes (guild_id, target_id, created_at);

                CREATE TABLE IF NOT EXISTS mod_warnings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    moderator_id INTEGER,
                    moderator_name TEXT,
                    reason TEXT NOT NULL,
                    case_number INTEGER,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_mod_warnings_user
                    ON mod_warnings (guild_id, user_id, created_at);

                CREATE TABLE IF NOT EXISTS mod_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    reporter_id INTEGER NOT NULL,
                    reporter_name TEXT,
                    target_id INTEGER NOT NULL,
                    target_name TEXT,
                    channel_id INTEGER,
                    message_id INTEGER,
                    message_excerpt TEXT,
                    reason TEXT,
                    status TEXT NOT NULL DEFAULT 'open',
                    created_at TEXT NOT NULL,
                    resolved_at TEXT,
                    resolved_by TEXT,
                    resolution TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_mod_reports_status
                    ON mod_reports (guild_id, status, created_at);

                CREATE TABLE IF NOT EXISTS mod_appeals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    user_name TEXT,
                    case_number INTEGER,
                    message TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    created_at TEXT NOT NULL,
                    resolved_at TEXT,
                    resolved_by TEXT,
                    response TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_mod_appeals_status
                    ON mod_appeals (guild_id, status, created_at);

                CREATE TABLE IF NOT EXISTS mod_shared_bans (
                    user_id INTEGER PRIMARY KEY,
                    reason TEXT,
                    added_by TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS mod_automod_settings (
                    guild_id INTEGER PRIMARY KEY,
                    enabled INTEGER NOT NULL DEFAULT 0,
                    spam_enabled INTEGER NOT NULL DEFAULT 1,
                    spam_max_messages INTEGER NOT NULL DEFAULT 5,
                    spam_window_seconds INTEGER NOT NULL DEFAULT 10,
                    duplicate_enabled INTEGER NOT NULL DEFAULT 1,
                    duplicate_threshold INTEGER NOT NULL DEFAULT 3,
                    mention_limit INTEGER NOT NULL DEFAULT 5,
                    emoji_limit INTEGER NOT NULL DEFAULT 10,
                    caps_ratio REAL NOT NULL DEFAULT 0.7,
                    invite_block INTEGER NOT NULL DEFAULT 1,
                    link_block INTEGER NOT NULL DEFAULT 0,
                    link_allowlist_json TEXT NOT NULL DEFAULT '[]',
                    regex_rules_json TEXT NOT NULL DEFAULT '[]',
                    exempt_role_ids_json TEXT NOT NULL DEFAULT '[]',
                    exempt_channel_ids_json TEXT NOT NULL DEFAULT '[]',
                    attachment_block INTEGER NOT NULL DEFAULT 1,
                    blocked_extensions_json TEXT NOT NULL DEFAULT '[]',
                    max_attachment_mb INTEGER NOT NULL DEFAULT 25,
                    escalation_json TEXT NOT NULL DEFAULT '[]',
                    quiet_hours_enabled INTEGER NOT NULL DEFAULT 0,
                    quiet_start_hour INTEGER NOT NULL DEFAULT 22,
                    quiet_end_hour INTEGER NOT NULL DEFAULT 7,
                    raid_enabled INTEGER NOT NULL DEFAULT 1,
                    raid_join_threshold INTEGER NOT NULL DEFAULT 10,
                    raid_window_seconds INTEGER NOT NULL DEFAULT 60,
                    raid_min_account_age_hours INTEGER NOT NULL DEFAULT 24,
                    quarantine_role_id INTEGER,
                    updated_at TEXT
                );

                CREATE TABLE IF NOT EXISTS mod_raid_joins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    joined_at TEXT NOT NULL,
                    account_age_hours REAL
                );
                CREATE INDEX IF NOT EXISTS idx_mod_raid_joins
                    ON mod_raid_joins (guild_id, joined_at);

                CREATE TABLE IF NOT EXISTS mod_lockdowns (
                    guild_id INTEGER PRIMARY KEY,
                    active INTEGER NOT NULL DEFAULT 0,
                    reason TEXT,
                    started_at TEXT,
                    ends_at TEXT,
                    started_by TEXT
                );
                """
            )

    # ------------------------------------------------------------------ cases
    def create_case(
        self,
        *,
        guild_id: int,
        action: str,
        target_id: int | None = None,
        target_name: str = "",
        moderator_id: int | None = None,
        moderator_name: str = "",
        reason: str = "",
        duration_minutes: int | None = None,
        channel_id: int | None = None,
        message_id: int | None = None,
        source: str = "command",
        metadata: dict | None = None,
    ) -> int:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(case_number), 0) + 1 AS next FROM mod_cases WHERE guild_id = ?",
                (int(guild_id),),
            ).fetchone()
            case_number = int(row["next"] if row else 1)
            conn.execute(
                """
                INSERT INTO mod_cases (
                    guild_id, case_number, created_at, action, target_id, target_name,
                    moderator_id, moderator_name, reason, duration_minutes, channel_id,
                    message_id, source, status, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)
                """,
                (
                    int(guild_id),
                    case_number,
                    iso_now(),
                    str(action),
                    int(target_id) if target_id else None,
                    str(target_name or ""),
                    int(moderator_id) if moderator_id else None,
                    str(moderator_name or ""),
                    str(reason or ""),
                    int(duration_minutes) if duration_minutes else None,
                    int(channel_id) if channel_id else None,
                    int(message_id) if message_id else None,
                    str(source or "command"),
                    json.dumps(metadata or {}, ensure_ascii=True),
                ),
            )
            return case_number

    def get_case(self, guild_id: int, case_number: int) -> dict | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM mod_cases WHERE guild_id = ? AND case_number = ?",
                (int(guild_id), int(case_number)),
            ).fetchone()
        return dict(row) if row else None

    def list_cases(
        self,
        guild_id: int,
        *,
        target_id: int | None = None,
        action: str | None = None,
        since: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        clauses = ["guild_id = ?"]
        params: list[Any] = [int(guild_id)]
        if target_id:
            clauses.append("target_id = ?")
            params.append(int(target_id))
        if action:
            clauses.append("action = ?")
            params.append(str(action))
        if since:
            clauses.append("created_at >= ?")
            params.append(str(since))
        params.extend([max(1, int(limit)), max(0, int(offset))])
        query = "SELECT * FROM mod_cases WHERE " + " AND ".join(clauses) + " ORDER BY case_number DESC LIMIT ? OFFSET ?"
        with self._lock, self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def update_case_reason(self, guild_id: int, case_number: int, reason: str, actor: str) -> bool:
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "UPDATE mod_cases SET reason = ?, metadata_json = ? WHERE guild_id = ? AND case_number = ?",
                (
                    str(reason or ""),
                    json.dumps({"reason_updated_by": str(actor or ""), "reason_updated_at": iso_now()}),
                    int(guild_id),
                    int(case_number),
                ),
            )
            return cursor.rowcount > 0

    def count_cases(self, guild_id: int, target_id: int, action: str, since: str | None = None) -> int:
        clauses = ["guild_id = ?", "target_id = ?", "action = ?"]
        params: list[Any] = [int(guild_id), int(target_id), str(action)]
        if since:
            clauses.append("created_at >= ?")
            params.append(str(since))
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS total FROM mod_cases WHERE " + " AND ".join(clauses), params).fetchone()
        return int(row["total"] if row else 0)

    # ------------------------------------------------------------------ notes
    def add_note(
        self,
        *,
        guild_id: int,
        target_id: int,
        author_id: int | None,
        author_name: str,
        note: str,
    ) -> int:
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO mod_notes (guild_id, target_id, author_id, author_name, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    int(guild_id),
                    int(target_id),
                    int(author_id) if author_id else None,
                    str(author_name or ""),
                    str(note or ""),
                    iso_now(),
                ),
            )
            return int(cursor.lastrowid or 0)

    def list_notes(self, guild_id: int, target_id: int, limit: int = 50) -> list[dict]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM mod_notes WHERE guild_id = ? AND target_id = ? ORDER BY id DESC LIMIT ?",
                (int(guild_id), int(target_id), max(1, int(limit))),
            ).fetchall()
        return [dict(row) for row in rows]

    # --------------------------------------------------------------- warnings
    def add_warning(
        self,
        *,
        guild_id: int,
        user_id: int,
        moderator_id: int | None,
        moderator_name: str,
        reason: str,
        case_number: int | None = None,
    ) -> int:
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO mod_warnings (
                    guild_id, user_id, moderator_id, moderator_name, reason, case_number, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(guild_id),
                    int(user_id),
                    int(moderator_id) if moderator_id else None,
                    str(moderator_name or ""),
                    str(reason or ""),
                    int(case_number) if case_number else None,
                    iso_now(),
                ),
            )
            return int(cursor.lastrowid or 0)

    def list_warnings(self, guild_id: int, user_id: int, limit: int = 50) -> list[dict]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM mod_warnings WHERE guild_id = ? AND user_id = ? ORDER BY id DESC LIMIT ?",
                (int(guild_id), int(user_id), max(1, int(limit))),
            ).fetchall()
        return [dict(row) for row in rows]

    def count_warnings(self, guild_id: int, user_id: int, since: str | None = None) -> int:
        clauses = ["guild_id = ?", "user_id = ?"]
        params: list[Any] = [int(guild_id), int(user_id)]
        if since:
            clauses.append("created_at >= ?")
            params.append(str(since))
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS total FROM mod_warnings WHERE " + " AND ".join(clauses), params).fetchone()
        return int(row["total"] if row else 0)

    def clear_warnings(self, guild_id: int, user_id: int) -> int:
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM mod_warnings WHERE guild_id = ? AND user_id = ?",
                (int(guild_id), int(user_id)),
            )
            return int(cursor.rowcount or 0)

    # ---------------------------------------------------------------- reports
    def create_report(
        self,
        *,
        guild_id: int,
        reporter_id: int,
        reporter_name: str,
        target_id: int,
        target_name: str,
        channel_id: int | None,
        message_id: int | None,
        message_excerpt: str,
        reason: str,
    ) -> int:
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO mod_reports (
                    guild_id, reporter_id, reporter_name, target_id, target_name,
                    channel_id, message_id, message_excerpt, reason, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)
                """,
                (
                    int(guild_id),
                    int(reporter_id),
                    str(reporter_name or ""),
                    int(target_id),
                    str(target_name or ""),
                    int(channel_id) if channel_id else None,
                    int(message_id) if message_id else None,
                    str(message_excerpt or "")[:500],
                    str(reason or ""),
                    iso_now(),
                ),
            )
            return int(cursor.lastrowid or 0)

    def list_reports(self, guild_id: int, status: str = "open", limit: int = 50) -> list[dict]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM mod_reports WHERE guild_id = ? AND status = ? ORDER BY id DESC LIMIT ?",
                (int(guild_id), str(status), max(1, int(limit))),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_report(self, guild_id: int, report_id: int) -> dict | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM mod_reports WHERE guild_id = ? AND id = ?",
                (int(guild_id), int(report_id)),
            ).fetchone()
        return dict(row) if row else None

    def resolve_report(self, guild_id: int, report_id: int, *, actor: str, resolution: str) -> bool:
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE mod_reports
                SET status = 'resolved', resolved_at = ?, resolved_by = ?, resolution = ?
                WHERE guild_id = ? AND id = ?
                """,
                (iso_now(), str(actor or ""), str(resolution or ""), int(guild_id), int(report_id)),
            )
            return cursor.rowcount > 0

    # ---------------------------------------------------------------- appeals
    def create_appeal(
        self,
        *,
        guild_id: int,
        user_id: int,
        user_name: str,
        case_number: int | None,
        message: str,
    ) -> int:
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO mod_appeals (
                    guild_id, user_id, user_name, case_number, message, status, created_at
                ) VALUES (?, ?, ?, ?, ?, 'open', ?)
                """,
                (
                    int(guild_id),
                    int(user_id),
                    str(user_name or ""),
                    int(case_number) if case_number else None,
                    str(message or ""),
                    iso_now(),
                ),
            )
            return int(cursor.lastrowid or 0)

    def list_appeals(self, guild_id: int, status: str = "open", limit: int = 50) -> list[dict]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM mod_appeals WHERE guild_id = ? AND status = ? ORDER BY id DESC LIMIT ?",
                (int(guild_id), str(status), max(1, int(limit))),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_appeal(self, guild_id: int, appeal_id: int) -> dict | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM mod_appeals WHERE guild_id = ? AND id = ?",
                (int(guild_id), int(appeal_id)),
            ).fetchone()
        return dict(row) if row else None

    def resolve_appeal(self, guild_id: int, appeal_id: int, *, actor: str, response: str, status: str = "resolved") -> bool:
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE mod_appeals
                SET status = ?, resolved_at = ?, resolved_by = ?, response = ?
                WHERE guild_id = ? AND id = ?
                """,
                (str(status), iso_now(), str(actor or ""), str(response or ""), int(guild_id), int(appeal_id)),
            )
            return cursor.rowcount > 0

    # ------------------------------------------------------------ shared bans
    def add_shared_ban(self, user_id: int, *, reason: str, added_by: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO mod_shared_bans (user_id, reason, added_by, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    reason = excluded.reason,
                    added_by = excluded.added_by,
                    created_at = excluded.created_at
                """,
                (int(user_id), str(reason or ""), str(added_by or ""), iso_now()),
            )

    def remove_shared_ban(self, user_id: int) -> bool:
        with self._lock, self._connect() as conn:
            cursor = conn.execute("DELETE FROM mod_shared_bans WHERE user_id = ?", (int(user_id),))
            return cursor.rowcount > 0

    def get_shared_ban(self, user_id: int) -> dict | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM mod_shared_bans WHERE user_id = ?", (int(user_id),)).fetchone()
        return dict(row) if row else None

    def list_shared_bans(self, limit: int = 200) -> list[dict]:
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT * FROM mod_shared_bans ORDER BY created_at DESC LIMIT ?", (max(1, int(limit)),)).fetchall()
        return [dict(row) for row in rows]

    # ----------------------------------------------------------- automod cfg
    def get_automod_settings(self, guild_id: int) -> dict:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM mod_automod_settings WHERE guild_id = ?", (int(guild_id),)).fetchone()
        if row is None:
            return {
                "guild_id": int(guild_id),
                "enabled": 0,
                "spam_enabled": 1,
                "spam_max_messages": 5,
                "spam_window_seconds": 10,
                "duplicate_enabled": 1,
                "duplicate_threshold": 3,
                "mention_limit": 5,
                "emoji_limit": 10,
                "caps_ratio": 0.7,
                "invite_block": 1,
                "link_block": 0,
                "link_allowlist": [],
                "regex_rules": [],
                "exempt_role_ids": [],
                "exempt_channel_ids": [],
                "attachment_block": 1,
                "blocked_extensions": list(DEFAULT_BLOCKED_EXTENSIONS),
                "max_attachment_mb": 25,
                "escalation": [],
                "quiet_hours_enabled": 0,
                "quiet_start_hour": 22,
                "quiet_end_hour": 7,
                "raid_enabled": 1,
                "raid_join_threshold": 10,
                "raid_window_seconds": 60,
                "raid_min_account_age_hours": 24,
                "quarantine_role_id": None,
            }
        data = dict(row)
        data["link_allowlist"] = _json_list(data.pop("link_allowlist_json", "[]"))
        data["regex_rules"] = _json_list(data.pop("regex_rules_json", "[]"))
        data["exempt_role_ids"] = _int_list(data.pop("exempt_role_ids_json", "[]"))
        data["exempt_channel_ids"] = _int_list(data.pop("exempt_channel_ids_json", "[]"))
        data["blocked_extensions"] = _json_list(data.pop("blocked_extensions_json", "[]")) or list(DEFAULT_BLOCKED_EXTENSIONS)
        data["escalation"] = _json_list(data.pop("escalation_json", "[]"))
        return data

    def save_automod_settings(self, guild_id: int, **values: Any) -> dict:
        current = self.get_automod_settings(guild_id)
        merged = {**current, **{key: value for key, value in values.items() if value is not None}}

        def int_setting(key: str, default: int) -> int:
            value = merged.get(key)
            return default if value is None else int(value)

        def float_setting(key: str, default: float) -> float:
            value = merged.get(key)
            return default if value is None else float(value)

        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO mod_automod_settings (
                    guild_id, enabled, spam_enabled, spam_max_messages, spam_window_seconds,
                    duplicate_enabled, duplicate_threshold, mention_limit, emoji_limit, caps_ratio,
                    invite_block, link_block, link_allowlist_json, regex_rules_json,
                    exempt_role_ids_json, exempt_channel_ids_json, attachment_block,
                    blocked_extensions_json, max_attachment_mb, escalation_json,
                    quiet_hours_enabled, quiet_start_hour, quiet_end_hour, raid_enabled,
                    raid_join_threshold, raid_window_seconds, raid_min_account_age_hours,
                    quarantine_role_id, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    enabled = excluded.enabled,
                    spam_enabled = excluded.spam_enabled,
                    spam_max_messages = excluded.spam_max_messages,
                    spam_window_seconds = excluded.spam_window_seconds,
                    duplicate_enabled = excluded.duplicate_enabled,
                    duplicate_threshold = excluded.duplicate_threshold,
                    mention_limit = excluded.mention_limit,
                    emoji_limit = excluded.emoji_limit,
                    caps_ratio = excluded.caps_ratio,
                    invite_block = excluded.invite_block,
                    link_block = excluded.link_block,
                    link_allowlist_json = excluded.link_allowlist_json,
                    regex_rules_json = excluded.regex_rules_json,
                    exempt_role_ids_json = excluded.exempt_role_ids_json,
                    exempt_channel_ids_json = excluded.exempt_channel_ids_json,
                    attachment_block = excluded.attachment_block,
                    blocked_extensions_json = excluded.blocked_extensions_json,
                    max_attachment_mb = excluded.max_attachment_mb,
                    escalation_json = excluded.escalation_json,
                    quiet_hours_enabled = excluded.quiet_hours_enabled,
                    quiet_start_hour = excluded.quiet_start_hour,
                    quiet_end_hour = excluded.quiet_end_hour,
                    raid_enabled = excluded.raid_enabled,
                    raid_join_threshold = excluded.raid_join_threshold,
                    raid_window_seconds = excluded.raid_window_seconds,
                    raid_min_account_age_hours = excluded.raid_min_account_age_hours,
                    quarantine_role_id = excluded.quarantine_role_id,
                    updated_at = excluded.updated_at
                """,
                (
                    int(guild_id),
                    int(merged.get("enabled") or 0),
                    int(merged.get("spam_enabled") or 0),
                    int(merged.get("spam_max_messages") or 5),
                    int(merged.get("spam_window_seconds") or 10),
                    int(merged.get("duplicate_enabled") or 0),
                    int_setting("duplicate_threshold", 3),
                    int_setting("mention_limit", 5),
                    int_setting("emoji_limit", 10),
                    float_setting("caps_ratio", 0.7),
                    int(merged.get("invite_block") or 0),
                    int(merged.get("link_block") or 0),
                    json.dumps(merged.get("link_allowlist") or [], ensure_ascii=True),
                    json.dumps(merged.get("regex_rules") or [], ensure_ascii=True),
                    json.dumps(merged.get("exempt_role_ids") or [], ensure_ascii=True),
                    json.dumps(merged.get("exempt_channel_ids") or [], ensure_ascii=True),
                    int(merged.get("attachment_block") or 0),
                    json.dumps(merged.get("blocked_extensions") or [], ensure_ascii=True),
                    int_setting("max_attachment_mb", 25),
                    json.dumps(merged.get("escalation") or [], ensure_ascii=True),
                    int(merged.get("quiet_hours_enabled") or 0),
                    int(merged.get("quiet_start_hour") or 22),
                    int(merged.get("quiet_end_hour") or 7),
                    int(merged.get("raid_enabled") or 0),
                    int(merged.get("raid_join_threshold") or 10),
                    int(merged.get("raid_window_seconds") or 60),
                    int(merged.get("raid_min_account_age_hours") or 24),
                    int(merged["quarantine_role_id"]) if merged.get("quarantine_role_id") else None,
                    iso_now(),
                ),
            )
        return self.get_automod_settings(guild_id)

    # ------------------------------------------------------------ raid state
    def record_join(self, guild_id: int, user_id: int, account_age_hours: float | None) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO mod_raid_joins (guild_id, user_id, joined_at, account_age_hours) VALUES (?, ?, ?, ?)",
                (int(guild_id), int(user_id), iso_now(), float(account_age_hours) if account_age_hours is not None else None),
            )

    def recent_join_count(self, guild_id: int, window_seconds: int) -> int:
        since = (utc_now() - timedelta(seconds=max(1, int(window_seconds)))).strftime("%Y-%m-%d %H:%M:%S")
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS total FROM mod_raid_joins WHERE guild_id = ? AND joined_at >= ?",
                (int(guild_id), since),
            ).fetchone()
        return int(row["total"] if row else 0)

    def prune_raid_joins(self, guild_id: int, older_than_seconds: int = 86400) -> None:
        cutoff = (utc_now() - timedelta(seconds=max(60, int(older_than_seconds)))).strftime("%Y-%m-%d %H:%M:%S")
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM mod_raid_joins WHERE guild_id = ? AND joined_at < ?", (int(guild_id), cutoff))

    def set_lockdown(self, guild_id: int, *, active: bool, reason: str, actor: str, minutes: int | None = None) -> None:
        ends_at = None
        if active and minutes:
            ends_at = (utc_now() + timedelta(minutes=int(minutes))).strftime("%Y-%m-%d %H:%M:%S")
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO mod_lockdowns (guild_id, active, reason, started_at, ends_at, started_by)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    active = excluded.active,
                    reason = excluded.reason,
                    started_at = excluded.started_at,
                    ends_at = excluded.ends_at,
                    started_by = excluded.started_by
                """,
                (int(guild_id), 1 if active else 0, str(reason or ""), iso_now(), ends_at, str(actor or "")),
            )

    def get_lockdown(self, guild_id: int) -> dict:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM mod_lockdowns WHERE guild_id = ?", (int(guild_id),)).fetchone()
        if row is None:
            return {"guild_id": int(guild_id), "active": 0, "reason": "", "started_at": None, "ends_at": None, "started_by": ""}
        data = dict(row)
        ends_at = parse_iso(data.get("ends_at"))
        if data.get("active") and ends_at and ends_at <= utc_now():
            data["active"] = 0
        return data


def get_store(db_path: str) -> ModerationStore:
    """Return a cached store for a database path (safe for web request handlers)."""
    key = str(db_path)
    with _STORE_LOCK:
        store = _STORE_CACHE.get(key)
        if store is None:
            store = ModerationStore(key)
            _STORE_CACHE[key] = store
        return store
