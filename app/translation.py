"""Translation store, flag emoji mappings, and data structures for WickedYoda bot."""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from datetime import UTC, datetime
from typing import Any

# Comprehensive flag emoji to ISO language code mapping
FLAG_TO_LANG: dict[str, str] = {
    # English
    "🇬🇧": "en",
    "🇺🇸": "en",
    "🇦🇺": "en",
    "🇨🇦": "en",
    "🇳🇿": "en",
    # Spanish
    "🇪🇸": "es",
    "🇲🇽": "es",
    "🇦🇷": "es",
    "🇨🇴": "es",
    # French
    "🇫🇷": "fr",
    # German
    "🇩🇪": "de",
    "🇦🇹": "de",
    "🇨🇭": "de",
    # Italian
    "🇮🇹": "it",
    # Portuguese
    "🇵🇹": "pt",
    "🇧🇷": "pt",
    # Russian
    "🇷🇺": "ru",
    # Chinese
    "🇨🇳": "zh",
    "🇹🇼": "zh",
    "🇭🇰": "zh",
    # Japanese
    "🇯🇵": "ja",
    # Korean
    "🇰🇷": "ko",
    # Arabic
    "🇸🇦": "ar",
    "🇪🇬": "ar",
    "🇦🇪": "ar",
    # Hindi
    "🇮🇳": "hi",
    # Indonesian
    "🇮🇩": "id",
    # Dutch
    "🇳🇱": "nl",
    "🇧🇪": "nl",
    # Polish
    "🇵🇱": "pl",
    # Turkish
    "🇹🇷": "tr",
    # Ukrainian
    "🇺🇦": "uk",
    # Vietnamese
    "🇻🇳": "vi",
}

DEFAULT_TRANSLATION_SETTINGS: dict[str, int | str | list[int]] = {
    "flag_translation_enabled": 0,
    "flag_translation_mode": "reply",  # "reply" or "ephemeral"
    "context_menu_enabled": 1,
    "channel_auto_translate_enabled": 0,
    "channel_auto_translate_channel_ids": [],
    "channel_auto_translate_target_lang": "en",
}


def get_lang_for_flag(emoji_str: str) -> str | None:
    """Return language code for a flag emoji string or None if unmapped."""
    if not emoji_str:
        return None
    emoji_clean = emoji_str.strip()
    return FLAG_TO_LANG.get(emoji_clean)


def parse_channel_ids_list(raw_value: str | list | None) -> list[int]:
    """Parse string or list of channel IDs into unique list of positive ints."""
    if not raw_value:
        return []
    if isinstance(raw_value, list):
        result: list[int] = []
        for item in raw_value:
            try:
                val = int(item)
                if val > 0 and val not in result:
                    result.append(val)
            except (ValueError, TypeError):
                continue
        return result
    if isinstance(raw_value, str):
        found = re.findall(r"\d+", raw_value)
        result = []
        for s in found:
            try:
                val = int(s)
                if val > 0 and val not in result:
                    result.append(val)
            except (ValueError, TypeError):
                continue
        return result
    return []


class TranslationStore:
    """Manages SQLite storage for per-guild translation settings."""

    def __init__(self, db_path: str, lock: threading.Lock | None = None) -> None:
        self._db_path = db_path
        self._lock = lock or threading.Lock()
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _ensure_schema(self) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS guild_translation_settings (
                        guild_id INTEGER PRIMARY KEY,
                        flag_translation_enabled INTEGER NOT NULL DEFAULT 0,
                        flag_translation_mode TEXT NOT NULL DEFAULT 'reply',
                        context_menu_enabled INTEGER NOT NULL DEFAULT 1,
                        channel_auto_translate_enabled INTEGER NOT NULL DEFAULT 0,
                        channel_auto_translate_channel_ids_json TEXT NOT NULL DEFAULT '[]',
                        channel_auto_translate_target_lang TEXT NOT NULL DEFAULT 'en',
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                conn.commit()

    def _now(self) -> str:
        return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

    def get_settings(self, guild_id: int) -> dict[str, Any]:
        """Get translation settings for a guild."""
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT guild_id,
                           flag_translation_enabled,
                           flag_translation_mode,
                           context_menu_enabled,
                           channel_auto_translate_enabled,
                           channel_auto_translate_channel_ids_json,
                           channel_auto_translate_target_lang
                    FROM guild_translation_settings
                    WHERE guild_id = ?
                    """,
                    (int(guild_id),),
                ).fetchone()
        if row is None:
            return {
                "guild_id": int(guild_id),
                "flag_translation_enabled": 0,
                "flag_translation_mode": "reply",
                "context_menu_enabled": 1,
                "channel_auto_translate_enabled": 0,
                "channel_auto_translate_channel_ids": [],
                "channel_auto_translate_target_lang": "en",
            }
        raw_channels = row["channel_auto_translate_channel_ids_json"] or "[]"
        try:
            parsed_channels = json.loads(str(raw_channels)) if isinstance(raw_channels, str) else []
            if not isinstance(parsed_channels, list):
                parsed_channels = []
        except json.JSONDecodeError:
            parsed_channels = []

        return {
            "guild_id": int(row["guild_id"]),
            "flag_translation_enabled": int(row["flag_translation_enabled"] or 0),
            "flag_translation_mode": str(row["flag_translation_mode"] or "reply"),
            "context_menu_enabled": int(row["context_menu_enabled"] or 0),
            "channel_auto_translate_enabled": int(row["channel_auto_translate_enabled"] or 0),
            "channel_auto_translate_channel_ids": [int(x) for x in parsed_channels if str(x).isdigit()],
            "channel_auto_translate_target_lang": str(row["channel_auto_translate_target_lang"] or "en"),
        }

    def save_settings(
        self,
        guild_id: int,
        *,
        flag_translation_enabled: bool | int | None = None,
        flag_translation_mode: str | None = None,
        context_menu_enabled: bool | int | None = None,
        channel_auto_translate_enabled: bool | int | None = None,
        channel_auto_translate_channel_ids: list[int] | str | None = None,
        channel_auto_translate_target_lang: str | None = None,
    ) -> dict[str, Any]:
        """Save/update translation settings for a guild."""
        current = self.get_settings(guild_id)
        now = self._now()

        flag_val = current.get("flag_translation_enabled", 0)
        flag_enabled = 1 if (flag_translation_enabled if flag_translation_enabled is not None else flag_val) else 0

        raw_mode = flag_translation_mode if flag_translation_mode is not None else current.get("flag_translation_mode", "reply")
        flag_mode = str(raw_mode).strip().lower()
        if flag_mode not in {"reply", "ephemeral"}:
            flag_mode = "reply"

        ctx_val = current.get("context_menu_enabled", 1)
        ctx_enabled = 1 if (context_menu_enabled if context_menu_enabled is not None else ctx_val) else 0

        chan_val = current.get("channel_auto_translate_enabled", 0)
        chan_enabled = 1 if (channel_auto_translate_enabled if channel_auto_translate_enabled is not None else chan_val) else 0

        if channel_auto_translate_channel_ids is not None:
            chan_ids = parse_channel_ids_list(channel_auto_translate_channel_ids)
        else:
            chan_ids_val = current.get("channel_auto_translate_channel_ids")
            chan_ids = [int(x) for x in chan_ids_val] if isinstance(chan_ids_val, list) else []

        raw_target = (
            channel_auto_translate_target_lang
            if channel_auto_translate_target_lang is not None
            else current.get("channel_auto_translate_target_lang", "en")
        )
        target_lang = str(raw_target).strip().lower() or "en"

        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO guild_translation_settings (
                        guild_id,
                        flag_translation_enabled,
                        flag_translation_mode,
                        context_menu_enabled,
                        channel_auto_translate_enabled,
                        channel_auto_translate_channel_ids_json,
                        channel_auto_translate_target_lang,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(guild_id) DO UPDATE SET
                        flag_translation_enabled = excluded.flag_translation_enabled,
                        flag_translation_mode = excluded.flag_translation_mode,
                        context_menu_enabled = excluded.context_menu_enabled,
                        channel_auto_translate_enabled = excluded.channel_auto_translate_enabled,
                        channel_auto_translate_channel_ids_json = excluded.channel_auto_translate_channel_ids_json,
                        channel_auto_translate_target_lang = excluded.channel_auto_translate_target_lang,
                        updated_at = excluded.updated_at
                    """,
                    (
                        int(guild_id),
                        flag_enabled,
                        flag_mode,
                        ctx_enabled,
                        chan_enabled,
                        json.dumps(chan_ids),
                        target_lang,
                        now,
                    ),
                )
                conn.commit()

        return {
            "guild_id": int(guild_id),
            "flag_translation_enabled": flag_enabled,
            "flag_translation_mode": flag_mode,
            "context_menu_enabled": ctx_enabled,
            "channel_auto_translate_enabled": chan_enabled,
            "channel_auto_translate_channel_ids": chan_ids,
            "channel_auto_translate_target_lang": target_lang,
        }
