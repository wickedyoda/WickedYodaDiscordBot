import asyncio
import concurrent.futures
import csv
import http.client
import importlib.util
import io
import json
import logging
import logging.handlers
import os
import re
import secrets
import socket
import sqlite3
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import discord
from defusedxml import ElementTree as DefusedET
from discord import app_commands
from discord.ext import commands

from core.bot_constants import (
    COMMAND_PERMISSION_DEFAULT_POLICY_MODERATOR,
    COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC,
    COMMAND_PERMISSION_METADATA,
    COMMAND_PERMISSION_MODE_CUSTOM_ROLES,
    COMMAND_PERMISSION_MODE_DEFAULT,
    COMMAND_PERMISSION_MODE_DISABLED,
    COMMAND_PERMISSION_MODE_PUBLIC,
    COMMAND_PERMISSION_POLICY_LABELS,
    DEFAULT_TAG_RESPONSES,
    LINKEDIN_ACTIVITY_URN_PATTERN,
    LINKEDIN_OG_TITLE_PATTERN,
    LINKEDIN_POST_URL_PATTERN,
    LINKEDIN_TEXT_PATTERN,
    SHORT_CODE_REGEX,
    SPICY_PROMPT_ALLOWED_TYPES,
    SPICY_PROMPT_BLOCKED_CATEGORIES,
    SPICY_PROMPT_BLOCKED_TAGS,
    STATUS_PAGE_PATH_REGEX,
    USER_ID_INPUT_PATTERN,
    YOUTUBE_CHANNEL_ID_META_PATTERNS,
    YOUTUBE_CHANNEL_ID_PATTERN,
    YOUTUBE_POST_ID_PATTERN,
    YOUTUBE_TEXT_PATTERN,
)
from core.moderation_filter import apply_moderation_filter
from core.runtime_env import PROTECTED_CONTAINER_ENV_KEYS, load_env_file
from core.web_moderation import (
    configure_web_moderation,
    run_web_ban_member,
    run_web_kick_member,
    run_web_leave_guild,
    run_web_timeout_member,
    run_web_untimeout_member,
    validate_manageable_role,
    validate_moderation_target,
)
from dnd.bot_integration import ensure_dnd_schema, register_dnd_commands
from webui import start_web_admin

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("wickedyoda-helper")
bot_channel_logger = logging.getLogger("wickedyoda-helper.channel-log")

# Load defaults first, then override with web GUI edits.
load_env_file(Path.cwd() / "env.env", override=False)
load_env_file(Path("/app/env.env"), override=True, protected_keys=PROTECTED_CONTAINER_ENV_KEYS)


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def optional_positive_int_env(name: str) -> int | None:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    if not value.isdigit():
        raise RuntimeError(f"Environment variable {name} must be a positive integer if provided.")
    parsed = int(value)
    if parsed <= 0:
        raise RuntimeError(f"Environment variable {name} must be a positive integer if provided.")
    return parsed


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"Environment variable {name} must be an integer.") from exc


def secure_randint(low: int, high: int) -> int:
    if high < low:
        raise ValueError("high must be >= low")
    return low + secrets.randbelow(high - low + 1)


def secure_choice(options):
    if isinstance(options, (list, tuple)):
        seq = options
    else:
        seq = tuple(options)
    if not seq:
        raise ValueError("options must not be empty")
    return secrets.choice(seq)


def apply_best_effort_permissions(path: str, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError:
        return


def ensure_private_directory(path: str) -> None:
    os.makedirs(path, exist_ok=True)
    apply_best_effort_permissions(path, 0o700)


def secure_sqlite_sidecars(path: str) -> None:
    for suffix in ("", "-wal", "-shm"):
        candidate = path if not suffix else f"{path}{suffix}"
        if os.path.exists(candidate):
            apply_best_effort_permissions(candidate, 0o600)


def connect_sqlite(path: str, timeout: int = 10) -> sqlite3.Connection:
    directory = os.path.dirname(path)
    if directory:
        ensure_private_directory(directory)
    conn = sqlite3.connect(path, timeout=timeout)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {max(1, timeout) * 1000}")
    secure_sqlite_sidecars(path)
    return conn


DISCORD_TOKEN = required_env("DISCORD_TOKEN")
MANAGED_GUILD_IDS_RAW = os.getenv("MANAGED_GUILD_IDS", "").strip()

DATA_DIR = os.getenv("DATA_DIR", "/app/data")
WEB_ENABLED = env_bool("WEB_ENABLED", True)
WEB_BIND_HOST = os.getenv("WEB_BIND_HOST", "127.0.0.1")
WEB_PORT = env_int("WEB_PORT", 8080)
WEB_TLS_ENABLED = env_bool("WEB_TLS_ENABLED", False)
WEB_TLS_PORT = env_int("WEB_TLS_PORT", WEB_PORT + 1)
WEB_TLS_CERT_FILE = os.getenv("WEB_TLS_CERT_FILE", "").strip()
WEB_TLS_KEY_FILE = os.getenv("WEB_TLS_KEY_FILE", "").strip()
ENABLE_MEMBERS_INTENT = env_bool("ENABLE_MEMBERS_INTENT", False)
ENABLE_MESSAGE_CONTENT_INTENT = env_bool("ENABLE_MESSAGE_CONTENT_INTENT", False)
COMMAND_RESPONSES_EPHEMERAL = env_bool("COMMAND_RESPONSES_EPHEMERAL", False)
SHORTENER_ENABLED = env_bool("SHORTENER_ENABLED", False)
SHORTENER_TIMEOUT_SECONDS = env_int("SHORTENER_TIMEOUT_SECONDS", 8)
PUPPY_IMAGE_API_URL = os.getenv("PUPPY_IMAGE_API_URL", "https://dog.ceo/api/breeds/image/random").strip()
PUPPY_IMAGE_TIMEOUT_SECONDS = env_int("PUPPY_IMAGE_TIMEOUT_SECONDS", 8)
FUN_API_TIMEOUT_SECONDS = env_int("FUN_API_TIMEOUT_SECONDS", 8)
CAT_IMAGE_API_URL = os.getenv("CAT_IMAGE_API_URL", "https://api.thecatapi.com/v1/images/search").strip()
MEME_API_URL = os.getenv("MEME_API_URL", "https://meme-api.com/gimme").strip()
DAD_JOKE_API_URL = os.getenv("DAD_JOKE_API_URL", "https://icanhazdadjoke.com/").strip()
YOUTUBE_NOTIFY_ENABLED = env_bool("YOUTUBE_NOTIFY_ENABLED", True)
YOUTUBE_POLL_INTERVAL_SECONDS = env_int("YOUTUBE_POLL_INTERVAL_SECONDS", 300)
YOUTUBE_REQUEST_TIMEOUT_SECONDS = env_int("YOUTUBE_REQUEST_TIMEOUT_SECONDS", 12)
WORDPRESS_REQUEST_TIMEOUT_SECONDS = env_int("WORDPRESS_REQUEST_TIMEOUT_SECONDS", 12)
LINKEDIN_REQUEST_TIMEOUT_SECONDS = env_int("LINKEDIN_REQUEST_TIMEOUT_SECONDS", 12)
TRANSLATE_API_URL = os.getenv("TRANSLATE_API_URL", "https://libretranslate.de/translate").strip()
TRANSLATE_API_KEY = os.getenv("TRANSLATE_API_KEY", "").strip()
TRANSLATE_TIMEOUT_SECONDS = env_int("TRANSLATE_TIMEOUT_SECONDS", 12)
WIKI_SEARCH_ENABLED = env_bool("WIKI_SEARCH_ENABLED", True)
WIKI_SEARCH_URL = os.getenv("WIKI_SEARCH_URL", "").strip()
WIKI_SEARCH_TIMEOUT_SECONDS = env_int("WIKI_SEARCH_TIMEOUT_SECONDS", 12)
OLLAMA_ENABLED = env_bool("OLLAMA_ENABLED", False)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "").strip().rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1").strip() or "llama3.1"
OLLAMA_TIMEOUT_SECONDS = env_int("OLLAMA_TIMEOUT_SECONDS", 30)
SPICY_PROMPTS_ENABLED = env_bool("SPICY_PROMPTS_ENABLED", True)
SPICY_PROMPTS_REPO_URL = os.getenv(
    "SPICY_PROMPTS_REPO_URL",
    "https://github.com/wickedyoda/SpicyGameAndBookTokQuiz",
).strip()
SPICY_PROMPTS_REPO_BRANCH = os.getenv("SPICY_PROMPTS_REPO_BRANCH", "main").strip() or "main"
SPICY_PROMPTS_MANIFEST_PATH = os.getenv("SPICY_PROMPTS_MANIFEST_PATH", "manifests/index.json").strip() or "manifests/index.json"
SPICY_PROMPTS_REQUEST_TIMEOUT_SECONDS = env_int("SPICY_PROMPTS_REQUEST_TIMEOUT_SECONDS", 12)
SPICY_PROMPTS_REFRESH_ON_BOOT = env_bool("SPICY_PROMPTS_REFRESH_ON_BOOT", True)
SPICY_PROMPTS_REFRESH_INTERVAL_HOURS = env_int("SPICY_PROMPTS_REFRESH_INTERVAL_HOURS", 24)
UPTIME_STATUS_ENABLED = env_bool("UPTIME_STATUS_ENABLED", True)
UPTIME_STATUS_TIMEOUT_SECONDS = env_int("UPTIME_STATUS_TIMEOUT_SECONDS", 8)
WEB_RESTART_ENABLED = env_bool("WEB_RESTART_ENABLED", False)
WEB_AVATAR_MAX_UPLOAD_BYTES = max(1024, env_int("WEB_AVATAR_MAX_UPLOAD_BYTES", 2 * 1024 * 1024))
FEED_INTERVAL_OPTIONS = {300, 600, 900, 1800, 3600, 10800, 21600}
UPTIME_MONITOR_INTERVAL_OPTIONS = {30, 60, 120, 300, 600, 900, 1800, 3600}
UPTIME_MONITOR_DEFAULT_INTERVAL_SECONDS = env_int("UPTIME_MONITOR_DEFAULT_INTERVAL_SECONDS", 60)
UPTIME_MONITOR_DEFAULT_TIMEOUT_SECONDS = env_int("UPTIME_MONITOR_DEFAULT_TIMEOUT_SECONDS", 8)
UPTIME_MONITOR_TIMEOUT_MIN_SECONDS = 3
UPTIME_MONITOR_TIMEOUT_MAX_SECONDS = 30
NOTIFICATION_LOOP_SECONDS = 60
MEMBER_ACTIVITY_RECENT_RETENTION_DAYS = 90
MEMBER_ACTIVITY_WEB_TOP_LIMIT = 20
MEMBER_ACTIVITY_BACKFILL_ENABLED = env_bool("MEMBER_ACTIVITY_BACKFILL_ENABLED", False)
MEMBER_ACTIVITY_BACKFILL_SINCE_RAW = os.getenv("MEMBER_ACTIVITY_BACKFILL_SINCE", "").strip()
MEMBER_ACTIVITY_BACKFILL_GUILD_ID = optional_positive_int_env("MEMBER_ACTIVITY_BACKFILL_GUILD_ID")
MEMBER_ACTIVITY_BACKFILL_PROGRESS_LOG_INTERVAL = env_int("MEMBER_ACTIVITY_BACKFILL_PROGRESS_LOG_INTERVAL", 500)
RANDOM_USER_COOLDOWN_DAYS = 30
LOG_RETENTION_DAYS = env_int("LOG_RETENTION_DAYS", 90)
LOG_ROTATION_INTERVAL_DAYS = env_int("LOG_ROTATION_INTERVAL_DAYS", 1)
LOG_HARDEN_FILE_PERMISSIONS = env_bool("LOG_HARDEN_FILE_PERMISSIONS", True)
POPULAR_COLOR_ROLES = {
    "Red": 0xE74C3C,
    "Orange": 0xE67E22,
    "Yellow": 0xF1C40F,
    "Green": 0x2ECC71,
    "Teal": 0x1ABC9C,
    "Blue": 0x3498DB,
    "Navy": 0x2C3E50,
    "Purple": 0x9B59B6,
    "Pink": 0xFF69B4,
    "White": 0xECF0F1,
}

MEMBER_ACTIVITY_WINDOW_SPECS = (
    ("90d", "Last 90 Days", timedelta(days=90)),
    ("30d", "Last 30 Days", timedelta(days=30)),
    ("7d", "Last 7 Days", timedelta(days=7)),
    ("1d", "Last 24 Hours", timedelta(days=1)),
)

if WEB_TLS_ENABLED and bool(WEB_TLS_CERT_FILE) != bool(WEB_TLS_KEY_FILE):
    raise RuntimeError("WEB_TLS_CERT_FILE and WEB_TLS_KEY_FILE must both be set when using custom TLS certificates.")
if WEB_TLS_ENABLED and WEB_TLS_PORT == WEB_PORT:
    raise RuntimeError("WEB_TLS_PORT must be different from WEB_PORT when WEB_TLS_ENABLED is true.")

if MANAGED_GUILD_IDS_RAW:
    parsed_guild_ids: set[int] = set()
    for part in re.split(r"[\s,]+", MANAGED_GUILD_IDS_RAW):
        if not part:
            continue
        if not part.isdigit():
            raise RuntimeError("MANAGED_GUILD_IDS must contain only numeric guild IDs.")
        guild_id_value = int(part)
        if guild_id_value <= 0:
            raise RuntimeError("MANAGED_GUILD_IDS must contain only positive guild IDs.")
        parsed_guild_ids.add(guild_id_value)
    MANAGED_GUILD_IDS: set[int] | None = parsed_guild_ids if parsed_guild_ids else None
else:
    MANAGED_GUILD_IDS = None

GUILD_ID_CONFIGURED = optional_positive_int_env("GUILD_ID")
if GUILD_ID_CONFIGURED is not None:
    GUILD_ID = GUILD_ID_CONFIGURED
elif MANAGED_GUILD_IDS:
    GUILD_ID = sorted(MANAGED_GUILD_IDS)[0]
else:
    GUILD_ID = 0
    logger.info("GUILD_ID is not set and MANAGED_GUILD_IDS is empty. Multi-guild mode will activate after guild discovery.")

BOT_LOG_CHANNEL_CONFIGURED = optional_positive_int_env("Bot_Log_Channel")
BOT_LOG_CHANNEL = BOT_LOG_CHANNEL_CONFIGURED or 0
if BOT_LOG_CHANNEL <= 0:
    logger.warning(
        "Bot_Log_Channel is not set. Configure per-guild bot log channels in /admin/guild-settings or set Bot_Log_Channel in env."
    )
INVALID_BOT_LOG_CHANNEL_CACHE: set[tuple[int | None, int]] = set()
WARNED_INVALID_BOT_LOG_CHANNEL_CACHE: set[tuple[int | None, int]] = set()
BOT_LOG_SEND_MAX_ATTEMPTS = 3
BOT_LOG_SEND_RETRY_DELAY_SECONDS = 2
COUNTDOWN_INPUT_FORMATS = (
    "%Y-%m-%d",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
)
ROLL_EXPRESSION_PATTERN = re.compile(r"^\s*(\d{1,2})d(\d{1,4})([+-]\d{1,4})?\s*$", re.IGNORECASE)
DICE_CHOICES = [
    app_commands.Choice(name="d4 (4-sided)", value="d4"),
    app_commands.Choice(name="d6 (6-sided)", value="d6"),
    app_commands.Choice(name="d8 (8-sided)", value="d8"),
    app_commands.Choice(name="d10 (10-sided)", value="d10"),
    app_commands.Choice(name="d00 / Percentile (10-sided)", value="d00"),
    app_commands.Choice(name="d12 (12-sided)", value="d12"),
    app_commands.Choice(name="d20 (20-sided)", value="d20"),
]
DICE_MEANING = {
    "d4": "Triangular die for light weapon damage and low-level spells like Healing Word or Magic Missile.",
    "d6": "Classic cube for standard weapon damage, character stats, and Fireball-style AoE.",
    "d8": "Diamond-shaped die for mid-tier weapons and moderate spell damage.",
    "d10": "Heavier weapon damage, fighter/paladin/ranger hit dice, and cantrips like Eldritch Blast.",
    "d00": "Percentile d10 marked in tens (00-90), paired with a d10 for a 1-100% result.",
    "d12": "Heavy weapon die for greataxe-style damage and Barbarian hit point rolls.",
    "d20": "Core d20 for attack rolls, ability checks, and saving throws.",
}
NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
RPS_BEATS = {"rock": "scissors", "paper": "rock", "scissors": "paper"}
FUN_GIF_LIBRARY: dict[str, list[dict[str, str]]] = {
    "celebrate": [
        {"title": "Celebrate", "url": "https://media.tenor.com/8Jf8u6H2n0QAAAAC/celebrate-happy.gif"},
        {"title": "Party Time", "url": "https://media.tenor.com/1g8z7QxgK5AAAAAC/party-celebration.gif"},
    ],
    "laugh": [
        {"title": "Laugh", "url": "https://media.tenor.com/FZ9Y8wSg1skAAAAC/laughing-lol.gif"},
        {"title": "That Was Funny", "url": "https://media.tenor.com/1B1x7jQ4W4kAAAAC/funny-laugh.gif"},
    ],
    "hype": [
        {"title": "Hype", "url": "https://media.tenor.com/6D8lL0z7oOAAAAAC/hype-excited.gif"},
        {"title": "Let's Go", "url": "https://media.tenor.com/U6v1kO8x0csAAAAC/lets-go-hype.gif"},
    ],
    "cute": [
        {"title": "Cute", "url": "https://media.tenor.com/Fqv8W8mKX1YAAAAC/cute-happy.gif"},
        {"title": "Adorable", "url": "https://media.tenor.com/2t8hS8mVQxMAAAAC/aww-cute.gif"},
    ],
}

TRANSLATE_LANGUAGE_CHOICES = [
    ("ar", "Arabic"),
    ("de", "German"),
    ("en", "English"),
    ("es", "Spanish"),
    ("fr", "French"),
    ("hi", "Hindi"),
    ("id", "Indonesian"),
    ("it", "Italian"),
    ("ja", "Japanese"),
    ("ko", "Korean"),
    ("nl", "Dutch"),
    ("pl", "Polish"),
    ("pt", "Portuguese"),
    ("ru", "Russian"),
    ("tr", "Turkish"),
    ("uk", "Ukrainian"),
    ("vi", "Vietnamese"),
    ("zh", "Chinese (Simplified)"),
]
TRANSLATE_LANGUAGE_BY_CODE = {code: label for code, label in TRANSLATE_LANGUAGE_CHOICES}
TRANSLATE_LANGUAGE_OPTIONS = [app_commands.Choice(name=label, value=code) for code, label in TRANSLATE_LANGUAGE_CHOICES]
EIGHTBALL_RESPONSES = (
    "Yes.",
    "No.",
    "Maybe.",
    "Absolutely.",
    "Ask again later.",
    "Signs point to yes.",
    "Very doubtful.",
    "Focus and ask once more.",
)
PLAYFUL_ROASTS = (
    "Your Wi-Fi probably disconnects just to get a break from you.",
    "If overthinking were a sport, you'd still somehow miss the playoffs.",
    "You bring strong 'forgot the semicolon' energy.",
    "You're proof that chaos can be a personality trait.",
    "Your browser tabs have started filing complaints.",
)
COMPLIMENTS = (
    "You make the server better just by being active in it.",
    "You have strong main-character energy, in a good way.",
    "Your timing is better than most deployment windows.",
    "You consistently bring good vibes and useful chaos.",
    "You seem like the person who actually reads the pinned messages.",
)
YODA_WISDOM_LINES = (
    "Patience you need; rushed commands, buggy results make.",
    "Helpful the small bot is, when configured well it remains.",
    "Do, or do not. There is no 'I forgot to check the logs.'",
    "Calm your mind. Then fix the root cause.",
    "Strong with the helper you are, when kindness and moderation balance.",
)
QUESTION_OF_THE_DAY_PROMPTS = (
    "What small thing made your day better this week?",
    "If you could master one skill instantly, what would it be?",
    "What is one app or tool you use more than anything else?",
    "What fictional world would you visit for a day?",
    "What is the most underrated comfort food?",
)
WOULD_YOU_RATHER_PROMPTS = (
    "Would you rather always be 10 minutes early or always have perfect Wi-Fi?",
    "Would you rather only communicate in GIFs or only in voice notes?",
    "Would you rather have unlimited snacks or unlimited battery life?",
    "Would you rather win every argument or never lose your keys again?",
    "Would you rather always know the best meme for the moment or the perfect song?",
)
TRIVIA_QUESTIONS = (
    {
        "question": "Which planet is known as the Red Planet?",
        "choices": ["Mars", "Venus", "Jupiter", "Mercury"],
        "answer": "Mars",
    },
    {
        "question": "What does CPU stand for?",
        "choices": ["Central Processing Unit", "Core Program Utility", "Central Program Upload", "Computer Power Unit"],
        "answer": "Central Processing Unit",
    },
    {
        "question": "Which ocean is the largest on Earth?",
        "choices": ["Atlantic", "Indian", "Pacific", "Arctic"],
        "answer": "Pacific",
    },
    {
        "question": "How many sides does a hexagon have?",
        "choices": ["5", "6", "7", "8"],
        "answer": "6",
    },
    {
        "question": "What year did the first iPhone launch?",
        "choices": ["2005", "2007", "2009", "2010"],
        "answer": "2007",
    },
)


def normalize_tag(raw_tag: str) -> str:
    value = (raw_tag or "").strip().lower()
    if not value:
        return ""
    if value.startswith("/"):
        value = value[1:]
    if not value.startswith("!"):
        value = f"!{value}"
    value = value.replace(" ", "")
    if not re.fullmatch(r"![a-z0-9_-]{1,40}", value):
        return ""
    return value


def normalize_permission_mode(value: str | None) -> str:
    candidate = (value or "").strip().lower()
    if candidate in {
        COMMAND_PERMISSION_MODE_DEFAULT,
        COMMAND_PERMISSION_MODE_PUBLIC,
        COMMAND_PERMISSION_MODE_CUSTOM_ROLES,
        COMMAND_PERMISSION_MODE_DISABLED,
    }:
        return candidate
    return COMMAND_PERMISSION_MODE_DEFAULT


def normalize_role_ids(values: list[str] | str | None) -> list[int]:
    normalized: list[int] = []
    seen: set[int] = set()
    source: list[str]
    if isinstance(values, str):
        source = re.split(r"[\s,]+", values.strip()) if values.strip() else []
    elif isinstance(values, list):
        source = [str(item) for item in values]
    else:
        source = []
    for raw in source:
        value = raw.strip()
        if value.startswith("<@&") and value.endswith(">"):
            value = value[3:-1]
        if not value.isdigit():
            continue
        role_id = int(value)
        if role_id <= 0 or role_id in seen:
            continue
        seen.add(role_id)
        normalized.append(role_id)
    return normalized


def normalize_feed_interval_seconds(value: str | int | None, default: int = 300) -> int:
    if isinstance(value, int):
        return value if value in FEED_INTERVAL_OPTIONS else default
    candidate = str(value or "").strip()
    if candidate.isdigit():
        parsed = int(candidate)
        if parsed in FEED_INTERVAL_OPTIONS:
            return parsed
    return default


def normalize_monitor_interval_seconds(value: str | int | None, default: int | None = None) -> int:
    resolved_default = UPTIME_MONITOR_DEFAULT_INTERVAL_SECONDS if default is None else default
    if isinstance(value, int):
        return value if value in UPTIME_MONITOR_INTERVAL_OPTIONS else resolved_default
    candidate = str(value or "").strip()
    if candidate.isdigit():
        parsed = int(candidate)
        if parsed in UPTIME_MONITOR_INTERVAL_OPTIONS:
            return parsed
    return resolved_default


def normalize_monitor_timeout_seconds(value: str | int | None, default: int | None = None) -> int:
    resolved_default = UPTIME_MONITOR_DEFAULT_TIMEOUT_SECONDS if default is None else default
    if isinstance(value, int):
        timeout_value = value
    else:
        candidate = str(value or "").strip()
        timeout_value = int(candidate) if candidate.isdigit() else resolved_default
    return max(UPTIME_MONITOR_TIMEOUT_MIN_SECONDS, min(timeout_value, UPTIME_MONITOR_TIMEOUT_MAX_SECONDS))


def normalize_command_permission_rule(raw_rule: dict | None) -> dict[str, str | list[int]]:
    if not isinstance(raw_rule, dict):
        return {"mode": COMMAND_PERMISSION_MODE_DEFAULT, "role_ids": []}
    mode = normalize_permission_mode(str(raw_rule.get("mode", COMMAND_PERMISSION_MODE_DEFAULT)))
    role_ids = normalize_role_ids(raw_rule.get("role_ids")) if mode == COMMAND_PERMISSION_MODE_CUSTOM_ROLES else []
    return {"mode": mode, "role_ids": role_ids}


def parse_user_id_input(raw_value: str) -> int | None:
    value = (raw_value or "").strip()
    if value.startswith("<@") and value.endswith(">"):
        value = value.strip("<@!>")
    if not USER_ID_INPUT_PATTERN.fullmatch(value):
        return None
    return int(value)


def is_moderator_member(member: discord.Member | discord.User) -> bool:
    if not isinstance(member, discord.Member):
        return False
    perms = member.guild_permissions
    return bool(
        perms.administrator
        or perms.kick_members
        or perms.ban_members
        or perms.manage_messages
        or perms.manage_roles
        or perms.moderate_members
    )


def normalize_activity_timestamp(raw_value: datetime | None = None) -> datetime:
    if isinstance(raw_value, datetime):
        if raw_value.tzinfo is None:
            return raw_value.replace(tzinfo=UTC)
        return raw_value.astimezone(UTC)
    return datetime.now(UTC)


def parse_iso_datetime_utc(raw_value: str | datetime | None) -> datetime | None:
    if isinstance(raw_value, datetime):
        return normalize_activity_timestamp(raw_value)
    candidate = str(raw_value or "").strip()
    if not candidate:
        return None
    if candidate.endswith("Z"):
        candidate = f"{candidate[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    return normalize_activity_timestamp(parsed)


def parse_member_activity_backfill_since(raw_value: str) -> datetime | None:
    candidate = str(raw_value or "").strip()
    if not candidate:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", candidate):
        candidate = f"{candidate}T00:00:00+00:00"
    parsed = parse_iso_datetime_utc(candidate)
    if parsed is None:
        return None
    return parsed.replace(minute=0, second=0, microsecond=0)


def merge_member_activity_backfill_ranges(ranges: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    normalized: list[tuple[datetime, datetime]] = []
    for start_dt, end_dt in ranges:
        safe_start = normalize_activity_timestamp(start_dt)
        safe_end = normalize_activity_timestamp(end_dt)
        if safe_end <= safe_start:
            continue
        normalized.append((safe_start, safe_end))
    if not normalized:
        return []
    normalized.sort(key=lambda item: item[0])
    merged = [normalized[0]]
    for start_dt, end_dt in normalized[1:]:
        last_start, last_end = merged[-1]
        if start_dt <= last_end:
            merged[-1] = (last_start, max(last_end, end_dt))
        else:
            merged.append((start_dt, end_dt))
    return merged


def compute_member_activity_backfill_missing_ranges(
    requested_since: datetime,
    requested_until: datetime,
    completed_ranges: list[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    safe_since = normalize_activity_timestamp(requested_since)
    safe_until = normalize_activity_timestamp(requested_until)
    if safe_until <= safe_since:
        return []
    merged_ranges = merge_member_activity_backfill_ranges(completed_ranges)
    missing: list[tuple[datetime, datetime]] = []
    cursor = safe_since
    for completed_start, completed_end in merged_ranges:
        if completed_end <= safe_since:
            continue
        if completed_start >= safe_until:
            break
        clipped_start = max(completed_start, safe_since)
        clipped_end = min(completed_end, safe_until)
        if clipped_end <= clipped_start:
            continue
        if clipped_start > cursor:
            missing.append((cursor, clipped_start))
        cursor = max(cursor, clipped_end)
        if cursor >= safe_until:
            break
    if cursor < safe_until:
        missing.append((cursor, safe_until))
    return missing


def require_managed_guild_id(guild_id: int | None, *, context: str) -> int:
    try:
        safe_guild_id = int(guild_id or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {context}.") from exc
    if safe_guild_id <= 0:
        raise ValueError(f"Invalid {context}.")
    if MANAGED_GUILD_IDS is not None and safe_guild_id not in MANAGED_GUILD_IDS:
        raise ValueError(f"Guild {safe_guild_id} is not managed by this bot.")
    return safe_guild_id


def is_managed_guild_id(guild_id: int | None) -> bool:
    try:
        safe_guild_id = int(guild_id or 0)
    except (TypeError, ValueError):
        return False
    if safe_guild_id <= 0:
        return False
    if MANAGED_GUILD_IDS is None:
        return True
    return safe_guild_id in MANAGED_GUILD_IDS


def build_member_activity_window_record(
    key: str,
    label: str,
    message_count: int,
    active_days: int,
    *,
    last_message_at: str = "",
) -> dict[str, str | int]:
    return {
        "key": key,
        "label": label,
        "message_count": int(message_count or 0),
        "active_days": int(active_days or 0),
        "last_message_at": str(last_message_at or ""),
    }


def format_member_activity_last_seen(raw_value: str) -> str:
    value = str(raw_value or "").strip()
    return value if value else "n/a"


def format_member_activity_window_summary(window: dict) -> str:
    label = str(window.get("label") or "Activity")
    return "\n".join(
        [
            f"**{label}**",
            f"- Messages: {int(window.get('message_count') or 0)}",
            f"- Active Days: {int(window.get('active_days') or 0)}",
            f"- Last Seen: {format_member_activity_last_seen(str(window.get('last_message_at') or ''))}",
        ]
    )


def member_has_any_role_id(member: discord.Member | discord.User, role_ids: list[int]) -> bool:
    if not isinstance(member, discord.Member) or not role_ids:
        return False
    member_role_ids = {role.id for role in member.roles}
    return any(role_id in member_role_ids for role_id in role_ids)


def normalize_shortener_base_url(raw_url: str) -> str:
    parsed = urllib.parse.urlparse(raw_url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise RuntimeError("SHORTENER_BASE_URL must start with http:// or https://")
    if not parsed.netloc:
        raise RuntimeError("SHORTENER_BASE_URL must include a domain.")
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def normalize_reddit_source(raw_value: str) -> tuple[str, str]:
    candidate = str(raw_value or "").strip()
    if not candidate:
        raise ValueError("Reddit forum is required.")
    if candidate.startswith("r/"):
        candidate = candidate[2:]
    if "://" in candidate:
        parsed = urllib.parse.urlparse(candidate)
        host = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        if host != "reddit.com":
            raise ValueError("Reddit URL must be on reddit.com.")
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) < 2 or parts[0].lower() != "r":
            raise ValueError("Reddit URL must point to a subreddit.")
        candidate = parts[1]
    subreddit_name = candidate.strip().lower()
    if not subreddit_name or not subreddit_name.replace("_", "").isalnum():
        raise ValueError("Reddit forum must be a valid subreddit name.")
    return subreddit_name, f"https://www.reddit.com/r/{subreddit_name}"


def normalize_status_page_url(raw_url: str) -> str:
    parsed = urllib.parse.urlparse(raw_url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise RuntimeError("UPTIME_STATUS_PAGE_URL must start with http:// or https://")
    if not parsed.netloc:
        raise RuntimeError("UPTIME_STATUS_PAGE_URL must include a domain.")
    path = parsed.path.rstrip("/")
    if not STATUS_PAGE_PATH_REGEX.match(path):
        raise RuntimeError("UPTIME_STATUS_PAGE_URL must match /status/<slug>.")
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


SHORTENER_BASE_URL = normalize_shortener_base_url(os.getenv("SHORTENER_BASE_URL", "https://l.twy4.us"))
SHORTENER_HOST = urllib.parse.urlparse(SHORTENER_BASE_URL).netloc.lower()
UPTIME_STATUS_PAGE_URL = normalize_status_page_url(os.getenv("UPTIME_STATUS_PAGE_URL", "https://randy.wickedyoda.com/status/everything"))
UPTIME_STATUS_PAGE_PARSED = urllib.parse.urlparse(UPTIME_STATUS_PAGE_URL)
uptime_slug_match = STATUS_PAGE_PATH_REGEX.match(UPTIME_STATUS_PAGE_PARSED.path)
if uptime_slug_match is None:
    raise RuntimeError("UPTIME_STATUS_PAGE_URL path could not be parsed.")
UPTIME_STATUS_SLUG = uptime_slug_match.group(1)
UPTIME_API_BASE = f"{UPTIME_STATUS_PAGE_PARSED.scheme}://{UPTIME_STATUS_PAGE_PARSED.netloc}"
UPTIME_API_CONFIG_URL = f"{UPTIME_API_BASE}/api/status-page/{UPTIME_STATUS_SLUG}"
UPTIME_API_HEARTBEAT_URL = f"{UPTIME_API_BASE}/api/status-page/heartbeat/{UPTIME_STATUS_SLUG}"

if SHORTENER_TIMEOUT_SECONDS <= 0:
    raise RuntimeError("SHORTENER_TIMEOUT_SECONDS must be a positive integer.")
if PUPPY_IMAGE_TIMEOUT_SECONDS <= 0:
    raise RuntimeError("PUPPY_IMAGE_TIMEOUT_SECONDS must be a positive integer.")
if FUN_API_TIMEOUT_SECONDS <= 0:
    raise RuntimeError("FUN_API_TIMEOUT_SECONDS must be a positive integer.")
if YOUTUBE_POLL_INTERVAL_SECONDS <= 0:
    raise RuntimeError("YOUTUBE_POLL_INTERVAL_SECONDS must be a positive integer.")
if YOUTUBE_REQUEST_TIMEOUT_SECONDS <= 0:
    raise RuntimeError("YOUTUBE_REQUEST_TIMEOUT_SECONDS must be a positive integer.")
if WORDPRESS_REQUEST_TIMEOUT_SECONDS <= 0:
    raise RuntimeError("WORDPRESS_REQUEST_TIMEOUT_SECONDS must be a positive integer.")
if LINKEDIN_REQUEST_TIMEOUT_SECONDS <= 0:
    raise RuntimeError("LINKEDIN_REQUEST_TIMEOUT_SECONDS must be a positive integer.")
if TRANSLATE_TIMEOUT_SECONDS <= 0:
    raise RuntimeError("TRANSLATE_TIMEOUT_SECONDS must be a positive integer.")
if WIKI_SEARCH_TIMEOUT_SECONDS <= 0:
    raise RuntimeError("WIKI_SEARCH_TIMEOUT_SECONDS must be a positive integer.")
if UPTIME_STATUS_TIMEOUT_SECONDS <= 0:
    raise RuntimeError("UPTIME_STATUS_TIMEOUT_SECONDS must be a positive integer.")
if UPTIME_MONITOR_DEFAULT_INTERVAL_SECONDS not in UPTIME_MONITOR_INTERVAL_OPTIONS:
    raise RuntimeError("UPTIME_MONITOR_DEFAULT_INTERVAL_SECONDS must be one of the allowed interval options.")
if not (UPTIME_MONITOR_TIMEOUT_MIN_SECONDS <= UPTIME_MONITOR_DEFAULT_TIMEOUT_SECONDS <= UPTIME_MONITOR_TIMEOUT_MAX_SECONDS):
    raise RuntimeError("UPTIME_MONITOR_DEFAULT_TIMEOUT_SECONDS must be within the allowed timeout range.")

intents = discord.Intents.default()
intents.guilds = True
intents.members = ENABLE_MEMBERS_INTENT
intents.messages = True
intents.message_content = ENABLE_MESSAGE_CONTENT_INTENT


def normalize_target_url(raw_url: str) -> str:
    value = raw_url.strip()
    if not value:
        raise ValueError("Please provide a URL.")
    if "://" not in value:
        value = f"https://{value}"
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Invalid URL. Use a valid http(s) URL.")
    return urllib.parse.urlunparse(parsed)


def normalize_statuspage_api_url(raw_url: str) -> str:
    value = raw_url.strip()
    if not value:
        raise ValueError("Status page URL is required.")
    if "://" not in value:
        value = f"https://{value}"
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Status page URL must be valid http(s).")
    path = parsed.path.rstrip("/")
    if not path.endswith("/api/v2/status.json"):
        path = f"{path}/api/v2/status.json" if path else "/api/v2/status.json"
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def parse_tcp_target(raw_value: str) -> tuple[str, int]:
    value = raw_value.strip()
    if value.startswith("tcp://"):
        value = value[6:]
    if "/" in value:
        value = value.split("/", 1)[0]
    if ":" not in value:
        raise ValueError("TCP targets must be in host:port format.")
    host, port_text = value.rsplit(":", 1)
    host = host.strip()
    port_text = port_text.strip()
    if not host:
        raise ValueError("TCP target must include a host.")
    if not port_text.isdigit():
        raise ValueError("TCP target port must be numeric.")
    port = int(port_text)
    if port <= 0 or port > 65535:
        raise ValueError("TCP target port must be between 1 and 65535.")
    return host, port


def require_http_url(raw_url: str) -> str:
    parsed = urllib.parse.urlparse(raw_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http/https URLs are allowed.")
    if not parsed.netloc:
        raise ValueError("URL must include a host.")
    return raw_url


def check_http_endpoint(url: str, timeout_seconds: int) -> tuple[bool, int, str]:
    url = require_http_url(url)
    start = time.monotonic()
    request = urllib.request.Request(url, method="GET", headers={"User-Agent": "WickedYodaBot/1.0"})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # nosec B310
        status = int(response.status)
    elapsed_ms = int((time.monotonic() - start) * 1000)
    return 200 <= status < 400, elapsed_ms, f"HTTP {status}"


def check_statuspage_endpoint(url: str, timeout_seconds: int) -> tuple[bool, int, str]:
    url = require_http_url(url)
    start = time.monotonic()
    request = urllib.request.Request(url, method="GET", headers={"User-Agent": "WickedYodaBot/1.0"})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # nosec B310
        status_code = int(response.status)
        body = response.read().decode("utf-8", errors="replace")
    elapsed_ms = int((time.monotonic() - start) * 1000)
    if status_code < 200 or status_code >= 400:
        return False, elapsed_ms, f"HTTP {status_code}"
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return False, elapsed_ms, "Invalid JSON response"
    status = payload.get("status", {}) if isinstance(payload, dict) else {}
    indicator = str(status.get("indicator", "")).lower()
    description = str(status.get("description", "")).strip()
    is_ok = indicator == "none"
    detail = description or f"Indicator: {indicator or 'unknown'}"
    return is_ok, elapsed_ms, detail


def check_tcp_endpoint(host: str, port: int, timeout_seconds: int) -> tuple[bool, int, str]:
    start = time.monotonic()
    with socket.create_connection((host, port), timeout=timeout_seconds):
        pass
    elapsed_ms = int((time.monotonic() - start) * 1000)
    return True, elapsed_ms, "Connected"


def normalize_wordpress_site_url(raw_url: str) -> str:
    value = raw_url.strip()
    if not value:
        raise ValueError("WordPress site URL is required.")
    if "://" not in value:
        value = f"https://{value}"
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Invalid WordPress site URL.")
    path = parsed.path.rstrip("/")
    normalized = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, path or "/", "", "", ""))
    return normalized.rstrip("/") if normalized != f"{parsed.scheme}://{parsed.netloc}/" else normalized


def normalize_linkedin_profile_url(raw_url: str) -> str:
    value = raw_url.strip()
    if not value:
        raise ValueError("LinkedIn profile URL is required.")
    if "://" not in value:
        value = f"https://{value}"
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Invalid LinkedIn URL.")
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if host != "linkedin.com":
        raise ValueError("LinkedIn URL must be on linkedin.com.")
    path = parsed.path.rstrip("/")
    valid_prefixes = ("/in/", "/company/", "/school/", "/showcase/")
    if not any(path.startswith(prefix) for prefix in valid_prefixes):
        raise ValueError("LinkedIn URL must point to a public profile or page.")
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def normalize_short_reference(raw_value: str) -> str:
    value = raw_value.strip()
    if not value:
        raise ValueError("Please provide a short code or short URL.")
    if value.isdigit():
        return f"{SHORTENER_BASE_URL}/{value}"
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Invalid short URL format.")
    if parsed.netloc.lower() != SHORTENER_HOST:
        raise ValueError(f"Short URL must use {SHORTENER_HOST}.")
    short_code = parsed.path.strip("/")
    if not short_code or "/" in short_code or not short_code.isdigit():
        raise ValueError("Short URL must point to a numeric short code.")
    return f"{SHORTENER_BASE_URL}/{short_code}"


def truncate_log_text(text: str, max_length: int = 300) -> str:
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 3]}..."


def validate_image_url(url: str) -> str:
    candidate = str(url or "").strip()
    parsed = urllib.parse.urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError("API returned an invalid image URL.")
    return candidate


def fetch_json_url(url: str, timeout_seconds: int, *, accept: str = "application/json") -> dict | list:
    status, _, body_text = fetch_text_url(url, timeout_seconds=timeout_seconds, accept=accept)
    if status >= 400:
        raise RuntimeError(f"API returned HTTP {status}.")
    try:
        payload = json.loads(body_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("API returned invalid JSON.") from exc
    if not isinstance(payload, dict | list):
        raise RuntimeError("API returned an unexpected response.")
    return payload


def post_json_url(url: str, timeout_seconds: int, payload: dict, *, accept: str = "application/json") -> dict | list:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError("Request URL is invalid.")
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"

    body = json.dumps(payload).encode("utf-8")
    headers = {
        "User-Agent": "WickedYodaLittleHelper/1.0",
        "Accept": accept,
        "Content-Type": "application/json",
    }
    connection_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    conn = connection_cls(parsed.netloc, timeout=timeout_seconds)
    try:
        conn.request("POST", path, body=body, headers=headers)
        response = conn.getresponse()
        body_text = response.read().decode("utf-8", errors="ignore")
    except OSError as exc:
        raise RuntimeError(f"Request failed: {exc}") from exc
    finally:
        conn.close()

    if response.status >= 400:
        raise RuntimeError(f"API returned HTTP {response.status}.")
    try:
        parsed_body = json.loads(body_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("API returned invalid JSON.") from exc
    if not isinstance(parsed_body, dict | list):
        raise RuntimeError("API returned an unexpected response.")
    return parsed_body


def build_github_raw_url(repo_url: str, branch: str, relative_path: str) -> str:
    normalized_repo_url = str(repo_url or "").strip()
    normalized_branch = str(branch or "").strip() or "main"
    normalized_path = str(relative_path or "").strip().lstrip("/")
    if not normalized_repo_url or not normalized_path:
        raise RuntimeError("Spicy Prompts repo URL and manifest path are required.")

    parsed = urllib.parse.urlparse(normalized_repo_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError("Spicy Prompts repo URL is invalid.")

    host = parsed.netloc.lower()
    path_parts = [part for part in parsed.path.split("/") if part]
    if host == "raw.githubusercontent.com":
        if len(path_parts) >= 2:
            owner, repo = path_parts[0], path_parts[1]
            return f"https://raw.githubusercontent.com/{owner}/{repo}/{normalized_branch}/{normalized_path}"
        raise RuntimeError("Spicy Prompts raw repo URL must include owner and repo.")
    if host.startswith("www."):
        host = host[4:]
    if host != "github.com" or len(path_parts) < 2:
        raise RuntimeError("Spicy Prompts repo URL must point to a GitHub repository.")

    owner, repo = path_parts[0], path_parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{normalized_branch}/{normalized_path}"


def normalize_spicy_prompt_entry(pack_id: str, entry: dict) -> dict | None:
    prompt_id = str(entry.get("id", "")).strip()
    prompt_type = str(entry.get("type", "prompt")).strip().lower() or "prompt"
    category = str(entry.get("category", "general")).strip().lower() or "general"
    rating = str(entry.get("rating", "18+")).strip() or "18+"
    text = str(entry.get("text", "")).strip()
    if not prompt_id or not text:
        return None
    if prompt_type not in SPICY_PROMPT_ALLOWED_TYPES:
        return None
    if category in SPICY_PROMPT_BLOCKED_CATEGORIES:
        return None

    raw_tags = entry.get("tags", [])
    tags = [str(item).strip().lower() for item in raw_tags if str(item).strip()] if isinstance(raw_tags, list) else []
    if any(tag in SPICY_PROMPT_BLOCKED_TAGS for tag in tags):
        return None

    if entry.get("enabled", True) is False:
        return None

    return {
        "pack_id": pack_id,
        "prompt_id": prompt_id,
        "prompt_type": prompt_type,
        "category": category,
        "rating": rating,
        "text": text,
        "tags": tags,
    }


def fetch_spicy_prompt_catalog() -> dict:
    manifest_url = build_github_raw_url(SPICY_PROMPTS_REPO_URL, SPICY_PROMPTS_REPO_BRANCH, SPICY_PROMPTS_MANIFEST_PATH)
    manifest_payload = fetch_json_url(manifest_url, SPICY_PROMPTS_REQUEST_TIMEOUT_SECONDS)
    if not isinstance(manifest_payload, dict):
        raise RuntimeError("Spicy Prompts manifest returned an unexpected payload.")

    raw_packs = manifest_payload.get("packs", [])
    if not isinstance(raw_packs, list):
        raise RuntimeError("Spicy Prompts manifest is missing a valid packs list.")

    prompt_rows: list[dict] = []
    pack_rows: list[dict] = []

    for raw_pack in raw_packs:
        if not isinstance(raw_pack, dict):
            continue
        if raw_pack.get("enabled", True) is False:
            continue
        pack_id = str(raw_pack.get("id", "")).strip()
        pack_name = str(raw_pack.get("name", pack_id)).strip() or pack_id
        pack_path = str(raw_pack.get("path", "")).strip()
        if not pack_id or not pack_path:
            continue

        pack_url = pack_path
        if not urllib.parse.urlparse(pack_path).scheme:
            pack_url = build_github_raw_url(SPICY_PROMPTS_REPO_URL, SPICY_PROMPTS_REPO_BRANCH, pack_path)

        pack_payload = fetch_json_url(pack_url, SPICY_PROMPTS_REQUEST_TIMEOUT_SECONDS)
        if not isinstance(pack_payload, dict):
            raise RuntimeError(f"Spicy Prompts pack {pack_id} returned an unexpected payload.")
        raw_prompts = pack_payload.get("prompts", [])
        if not isinstance(raw_prompts, list):
            raise RuntimeError(f"Spicy Prompts pack {pack_id} is missing a valid prompts list.")

        accepted_count = 0
        for raw_entry in raw_prompts:
            if not isinstance(raw_entry, dict):
                continue
            normalized = normalize_spicy_prompt_entry(pack_id, raw_entry)
            if normalized is None:
                continue
            prompt_rows.append(normalized)
            accepted_count += 1

        pack_rows.append(
            {
                "pack_id": pack_id,
                "pack_name": pack_name,
                "source_path": pack_path,
                "prompt_count": accepted_count,
            }
        )

    return {
        "repo_url": SPICY_PROMPTS_REPO_URL,
        "repo_branch": SPICY_PROMPTS_REPO_BRANCH,
        "manifest_path": SPICY_PROMPTS_MANIFEST_PATH,
        "manifest_url": manifest_url,
        "pack_count": len(pack_rows),
        "prompt_count": len(prompt_rows),
        "packs": pack_rows,
        "prompts": prompt_rows,
    }


def parse_db_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return None


def fetch_random_cat_image_url() -> str:
    payload = fetch_json_url(CAT_IMAGE_API_URL, FUN_API_TIMEOUT_SECONDS)
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
        raise RuntimeError("Cat API returned an unexpected payload.")
    return validate_image_url(str(payload[0].get("url", "")).strip())


def fetch_random_meme() -> dict[str, str]:
    payload = fetch_json_url(MEME_API_URL, FUN_API_TIMEOUT_SECONDS)
    if not isinstance(payload, dict):
        raise RuntimeError("Meme API returned an unexpected payload.")
    if bool(payload.get("nsfw")):
        raise RuntimeError("Meme API returned an NSFW meme.")
    image_url = validate_image_url(str(payload.get("url", "")).strip())
    return {
        "title": str(payload.get("title", "Random Meme")).strip() or "Random Meme",
        "image_url": image_url,
        "post_url": str(payload.get("postLink", "")).strip(),
        "subreddit": str(payload.get("subreddit", "")).strip(),
    }


def fetch_dad_joke() -> str:
    payload = fetch_json_url(DAD_JOKE_API_URL, FUN_API_TIMEOUT_SECONDS, accept="application/json")
    if not isinstance(payload, dict):
        raise RuntimeError("Dad joke API returned an unexpected payload.")
    joke = str(payload.get("joke", "")).strip()
    if not joke:
        raise RuntimeError("Dad joke API did not return a joke.")
    return joke


def translate_text(text: str, target_language: str) -> str:
    if not TRANSLATE_API_URL:
        raise RuntimeError("Translate API URL is not configured.")
    payload = {
        "q": text,
        "source": "auto",
        "target": target_language,
        "format": "text",
    }
    if TRANSLATE_API_KEY:
        payload["api_key"] = TRANSLATE_API_KEY
    response = post_json_url(TRANSLATE_API_URL, TRANSLATE_TIMEOUT_SECONDS, payload)
    if isinstance(response, dict):
        translated = str(response.get("translatedText", "")).strip()
        if translated:
            return translated
    raise RuntimeError("Translation API did not return translated text.")


def call_ollama(prompt: str) -> str:
    if not OLLAMA_BASE_URL:
        raise RuntimeError("OLLAMA_BASE_URL is not configured.")
    url = f"{OLLAMA_BASE_URL}/api/generate"
    payload = {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}
    status, _, body_text = post_json_url(
        url,
        payload,
        timeout_seconds=OLLAMA_TIMEOUT_SECONDS,
    )
    if status >= 400:
        raise RuntimeError(f"Ollama API returned HTTP {status}.")
    try:
        response = json.loads(body_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Ollama returned invalid JSON.") from exc
    output = str(response.get("response", "")).strip()
    if not output:
        raise RuntimeError("Ollama returned an empty response.")
    return output


def search_wiki_help(query: str) -> list[str]:
    if not WIKI_SEARCH_URL:
        raise RuntimeError("WIKI_SEARCH_URL is not configured.")
    status, headers, body_text = fetch_text_url(WIKI_SEARCH_URL, timeout_seconds=WIKI_SEARCH_TIMEOUT_SECONDS, accept="text/html")
    if status >= 400:
        raise RuntimeError(f"Wiki returned HTTP {status}.")
    content_type = str(headers.get("content-type", "")).lower()
    text = body_text
    if "html" in content_type:
        text = re.sub(r"<script[^>]*>.*?</script\b[^>]*>", " ", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style\b[^>]*>", " ", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []

    query_norm = query.strip().lower()
    matches: list[str] = []
    for line in body_text.splitlines():
        if query_norm in line.lower():
            snippet = re.sub(r"\s+", " ", line).strip()
            if snippet:
                matches.append(snippet)
        if len(matches) >= 5:
            break
    if matches:
        return matches

    index = text.lower().find(query_norm)
    if index == -1:
        return []
    start = max(0, index - 120)
    end = min(len(text), index + 200)
    return [text[start:end].strip()]


def split_option_values(raw_value: str, *, max_options: int = 10) -> list[str]:
    parts = [item.strip() for item in re.split(r"[,|\n]+", str(raw_value or "").strip())]
    options = [item for item in parts if item]
    deduped: list[str] = []
    seen: set[str] = set()
    for option in options:
        lowered = option.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(truncate_log_text(option, max_length=100))
        if len(deduped) >= max_options:
            break
    return deduped


def parse_roll_expression(raw_value: str) -> tuple[int, int, int]:
    match = ROLL_EXPRESSION_PATTERN.fullmatch(str(raw_value or "").strip())
    if match is None:
        raise ValueError("Dice format must look like `1d20`, `2d6+3`, or `4d8-1`.")
    count = int(match.group(1))
    sides = int(match.group(2))
    modifier = int(match.group(3) or 0)
    if count <= 0 or count > 20:
        raise ValueError("You can roll between 1 and 20 dice at a time.")
    if sides <= 1 or sides > 1000:
        raise ValueError("Dice sides must be between 2 and 1000.")
    return count, sides, modifier


def execute_roll_expression(raw_value: str) -> dict[str, int | list[int] | str]:
    count, sides, modifier = parse_roll_expression(raw_value)
    rolls = [secure_randint(1, sides) for _ in range(count)]
    subtotal = sum(rolls)
    total = subtotal + modifier
    return {
        "expression": f"{count}d{sides}{modifier:+d}" if modifier else f"{count}d{sides}",
        "count": count,
        "sides": sides,
        "modifier": modifier,
        "rolls": rolls,
        "subtotal": subtotal,
        "total": total,
    }


def parse_countdown_target(raw_value: str) -> datetime:
    candidate = str(raw_value or "").strip()
    if not candidate:
        raise ValueError("Provide a target date like `2026-12-31` or `2026-12-31 18:30`.")
    if candidate.endswith("Z"):
        candidate = f"{candidate[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        parsed = None
    if parsed is None:
        for fmt in COUNTDOWN_INPUT_FORMATS:
            try:
                parsed = datetime.strptime(candidate, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        raise ValueError("Unsupported date format. Use `YYYY-MM-DD` or `YYYY-MM-DD HH:MM`.")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def format_duration_until(target_dt: datetime, *, now_dt: datetime | None = None) -> str:
    safe_now = normalize_activity_timestamp(now_dt)
    safe_target = normalize_activity_timestamp(target_dt)
    delta = safe_target - safe_now
    total_seconds = int(delta.total_seconds())
    if total_seconds <= 0:
        return "already passed"
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes or not parts:
        parts.append(f"{minutes}m")
    return " ".join(parts[:3])


def parse_month_day_input(raw_value: str) -> tuple[int, int]:
    candidate = str(raw_value or "").strip()
    if not candidate:
        raise ValueError("Birthday is required. Use `MM-DD`, `MM/DD`, or `YYYY-MM-DD`.")
    year: int
    month: int
    day: int
    match = re.fullmatch(r"(\d{1,2})[-/](\d{1,2})", candidate)
    if match is not None:
        year = 2000
        month = int(match.group(1))
        day = int(match.group(2))
    else:
        match = re.fullmatch(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", candidate)
        if match is None:
            raise ValueError("Birthday format must be `MM-DD`, `MM/DD`, or `YYYY-MM-DD`.")
        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))
    try:
        datetime(year, month, day)
    except ValueError as exc:
        raise ValueError("Birthday is not a valid calendar date.") from exc
    return month, day


def birthday_label(month: int, day: int) -> str:
    return datetime(2000, month, day).strftime("%B %d")


def next_birthday_occurrence(month: int, day: int, *, now_dt: datetime | None = None) -> datetime:
    safe_now = normalize_activity_timestamp(now_dt)
    current_year = safe_now.year
    for offset in range(0, 9):
        year = current_year + offset
        try:
            candidate = datetime(year, month, day, tzinfo=UTC)
        except ValueError:
            continue
        if candidate.date() >= safe_now.date():
            return candidate
    raise ValueError("Unable to calculate the next birthday occurrence.")


def choose_random_gif(theme: str) -> dict[str, str]:
    selected_theme = str(theme or "celebrate").strip().lower()
    if selected_theme == "random" or selected_theme not in FUN_GIF_LIBRARY:
        selected_theme = secure_choice(sorted(FUN_GIF_LIBRARY))
    chosen = secure_choice(FUN_GIF_LIBRARY[selected_theme])
    return {"theme": selected_theme, "title": chosen["title"], "url": chosen["url"]}


def shortener_request(
    method: str,
    url: str,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], str]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError("Shortener request URL is invalid.")
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"

    connection_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    request_headers = {"User-Agent": "WickedYodaLittleHelper/1.0"}
    if headers:
        request_headers.update(headers)

    conn = connection_cls(parsed.netloc, timeout=SHORTENER_TIMEOUT_SECONDS)
    try:
        conn.request(method=method, url=path, body=body, headers=request_headers)
        response = conn.getresponse()
        response_headers = {name.lower(): value for name, value in response.getheaders()}
        response_body = response.read().decode("utf-8", errors="ignore")
        return response.status, response_headers, response_body
    except OSError as exc:
        raise RuntimeError(f"Shortener request failed: {exc}") from exc
    finally:
        conn.close()


def create_short_url(target_url: str) -> tuple[str, str]:
    payload = urllib.parse.urlencode({"short": target_url}).encode("utf-8")
    status, _, response_body = shortener_request(
        method="POST",
        url=f"{SHORTENER_BASE_URL}/",
        body=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if status >= 400:
        raise RuntimeError(f"Shortener returned HTTP {status}.")

    match = SHORT_CODE_REGEX.search(response_body)
    if not match:
        raise RuntimeError("Shortener did not return a short code.")

    short_code = match.group(1)
    short_url = f"{SHORTENER_BASE_URL}/{short_code}"
    return short_code, short_url


def expand_short_url(short_url: str) -> str:
    status, headers, _ = shortener_request(method="GET", url=short_url)
    if status in {301, 302, 303, 307, 308}:
        location = headers.get("location")
        if not location:
            raise RuntimeError("Shortener redirect did not include a Location header.")
        return urllib.parse.urljoin(short_url, location)
    if status == 404:
        raise RuntimeError("Short code not found.")
    if status >= 400:
        raise RuntimeError(f"Shortener returned HTTP {status}.")
    raise RuntimeError("Shortener did not return a redirect target.")


def fetch_random_puppy_image_url() -> str:
    parsed = urllib.parse.urlparse(PUPPY_IMAGE_API_URL)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError("PUPPY_IMAGE_API_URL is invalid.")
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"

    connection_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    conn = connection_cls(parsed.netloc, timeout=PUPPY_IMAGE_TIMEOUT_SECONDS)
    try:
        conn.request("GET", path, headers={"User-Agent": "WickedYodaLittleHelper/1.0", "Accept": "application/json"})
        response = conn.getresponse()
        body_text = response.read().decode("utf-8", errors="ignore")
    except OSError as exc:
        raise RuntimeError(f"Puppy API request failed: {exc}") from exc
    finally:
        conn.close()

    if response.status >= 400:
        raise RuntimeError(f"Puppy API returned HTTP {response.status}.")

    try:
        parsed_body = json.loads(body_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Puppy API returned invalid JSON.") from exc

    if not isinstance(parsed_body, dict):
        raise RuntimeError("Puppy API returned an unexpected payload.")

    image_url = parsed_body.get("message")
    if not isinstance(image_url, str):
        raise RuntimeError("Puppy API response did not include an image URL.")

    parsed_image_url = urllib.parse.urlparse(image_url)
    if parsed_image_url.scheme not in {"http", "https"} or not parsed_image_url.netloc:
        raise RuntimeError("Puppy API returned an invalid image URL.")

    return image_url


def fetch_text_url(url: str, timeout_seconds: int, accept: str) -> tuple[int, dict[str, str], str]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError("Request URL is invalid.")
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"

    connection_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    conn = connection_cls(parsed.netloc, timeout=timeout_seconds)
    try:
        conn.request("GET", path, headers={"User-Agent": "WickedYodaLittleHelper/1.0", "Accept": accept})
        response = conn.getresponse()
        response_headers = {name.lower(): value for name, value in response.getheaders()}
        body_text = response.read().decode("utf-8", errors="ignore")
    except OSError as exc:
        raise RuntimeError(f"Request failed: {exc}") from exc
    finally:
        conn.close()
    return response.status, response_headers, body_text


def normalize_youtube_channel_url(raw_url: str) -> str:
    value = raw_url.strip()
    if not value:
        raise ValueError("YouTube channel URL is required.")
    if "://" not in value:
        value = f"https://{value}"
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Invalid YouTube URL.")
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if host != "youtube.com":
        raise ValueError("YouTube URL must be on youtube.com.")
    if not parsed.path or parsed.path == "/":
        raise ValueError("YouTube URL must include a channel path.")
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", parsed.query, ""))


def resolve_youtube_channel_id(source_url: str) -> str:
    normalized_url = normalize_youtube_channel_url(source_url)
    parsed = urllib.parse.urlparse(normalized_url)
    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) >= 2 and path_parts[0] == "channel":
        direct_channel_id = path_parts[1]
        if YOUTUBE_CHANNEL_ID_PATTERN.fullmatch(direct_channel_id):
            return direct_channel_id

    if parsed.path == "/feeds/videos.xml":
        query_values = urllib.parse.parse_qs(parsed.query)
        channel_id = query_values.get("channel_id", [""])[0]
        if YOUTUBE_CHANNEL_ID_PATTERN.fullmatch(channel_id):
            return channel_id

    status, _, body_text = fetch_text_url(normalized_url, timeout_seconds=YOUTUBE_REQUEST_TIMEOUT_SECONDS, accept="text/html")
    if status >= 400:
        raise RuntimeError(f"YouTube channel page returned HTTP {status}.")
    for pattern in YOUTUBE_CHANNEL_ID_META_PATTERNS:
        match = pattern.search(body_text)
        if match:
            return match.group(1)
    raise RuntimeError("Unable to resolve YouTube channel ID from URL.")


def fetch_latest_youtube_video(channel_id: str) -> dict:
    entries = fetch_recent_youtube_uploads(channel_id, limit=1)
    if not entries:
        raise RuntimeError("YouTube feed has no entries.")
    latest = entries[0]
    return {
        "channel_id": channel_id,
        "channel_title": latest["channel_title"],
        "video_id": latest["video_id"],
        "video_title": latest["video_title"],
        "video_url": latest["video_url"],
        "published_at": latest["published_at"],
    }


def fetch_recent_youtube_uploads(channel_id: str, limit: int = 10) -> list[dict]:
    if not YOUTUBE_CHANNEL_ID_PATTERN.fullmatch(channel_id):
        raise RuntimeError("Invalid YouTube channel ID.")
    feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    status, _, body_text = fetch_text_url(feed_url, timeout_seconds=YOUTUBE_REQUEST_TIMEOUT_SECONDS, accept="application/atom+xml")
    if status >= 400:
        raise RuntimeError(f"YouTube feed returned HTTP {status}.")

    try:
        root = DefusedET.fromstring(body_text)
    except DefusedET.ParseError as exc:
        raise RuntimeError("YouTube feed returned invalid XML.") from exc

    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "yt": "http://www.youtube.com/xml/schemas/2015",
    }
    channel_title = root.findtext("atom:title", default="Unknown Channel", namespaces=ns).strip()
    entries: list[dict] = []
    for entry in root.findall("atom:entry", ns)[: max(1, limit)]:
        video_id = entry.findtext("yt:videoId", default="", namespaces=ns).strip()
        video_title = entry.findtext("atom:title", default="Untitled", namespaces=ns).strip()
        published_at = entry.findtext("atom:published", default="", namespaces=ns).strip()
        link_el = entry.find("atom:link[@rel='alternate']", ns)
        video_url = link_el.get("href", "").strip() if link_el is not None else ""
        if not video_url and video_id:
            video_url = f"https://www.youtube.com/watch?v={video_id}"
        if not video_id or not video_url:
            continue
        entries.append(
            {
                "channel_id": channel_id,
                "channel_title": channel_title,
                "video_id": video_id,
                "video_title": video_title,
                "video_url": video_url,
                "published_at": published_at,
            }
        )
    if not entries:
        raise RuntimeError("YouTube feed has no entries.")
    return entries


def resolve_youtube_subscription_seed(source_url: str) -> dict:
    normalized_url = normalize_youtube_channel_url(source_url)
    channel_id = resolve_youtube_channel_id(normalized_url)
    latest = fetch_latest_youtube_video(channel_id)
    return {
        "source_url": normalized_url,
        "channel_id": channel_id,
        "channel_title": latest["channel_title"],
        "last_video_id": latest["video_id"],
        "last_video_title": latest["video_title"],
        "last_published_at": latest["published_at"],
    }


def _youtube_community_url(source_url: str) -> str:
    normalized_url = normalize_youtube_channel_url(source_url)
    parsed = urllib.parse.urlparse(normalized_url)
    base_path = parsed.path.rstrip("/")
    if base_path.endswith("/community") or base_path.endswith("/posts"):
        path = base_path
    else:
        path = f"{base_path}/community"
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def _extract_youtube_text_window(body_text: str, anchor_index: int) -> str:
    window = body_text[anchor_index : anchor_index + 900]
    texts = [match.group(1) for match in YOUTUBE_TEXT_PATTERN.finditer(window)]
    cleaned = []
    for value in texts:
        candidate = value.replace("\\n", " ").replace("\\u0026", "&").replace('\\"', '"').strip()
        if candidate and candidate not in cleaned:
            cleaned.append(candidate)
        if len(cleaned) >= 3:
            break
    return " ".join(cleaned).strip() or "New community post"


def fetch_recent_youtube_community_posts(source_url: str, limit: int = 10) -> list[dict]:
    community_url = _youtube_community_url(source_url)
    status, _, body_text = fetch_text_url(community_url, timeout_seconds=YOUTUBE_REQUEST_TIMEOUT_SECONDS, accept="text/html")
    if status >= 400:
        raise RuntimeError(f"YouTube community page returned HTTP {status}.")
    posts: list[dict] = []
    seen: set[str] = set()
    for match in YOUTUBE_POST_ID_PATTERN.finditer(body_text):
        post_id = match.group(1).strip()
        if not post_id or post_id in seen:
            continue
        seen.add(post_id)
        posts.append(
            {
                "post_id": post_id,
                "post_title": truncate_log_text(_extract_youtube_text_window(body_text, match.start()), max_length=160),
                "post_url": f"https://www.youtube.com/post/{post_id}",
                "published_at": "",
            }
        )
        if len(posts) >= max(1, limit):
            break
    return posts


def resolve_youtube_community_seed(source_url: str) -> dict:
    posts = fetch_recent_youtube_community_posts(source_url, limit=1)
    if not posts:
        return {}
    latest = posts[0]
    return {
        "last_community_post_id": latest["post_id"],
        "last_community_post_title": latest["post_title"],
        "last_community_published_at": latest["published_at"],
    }


def fetch_recent_reddit_posts(subreddit_name: str, limit: int = 10) -> list[dict]:
    normalized_name, source_url = normalize_reddit_source(subreddit_name)
    api_url = f"https://www.reddit.com/r/{normalized_name}/new.json?limit={max(1, limit)}&raw_json=1"
    status, _, body_text = fetch_text_url(api_url, timeout_seconds=UPTIME_STATUS_TIMEOUT_SECONDS, accept="application/json")
    if status >= 400:
        raise RuntimeError(f"Reddit feed returned HTTP {status}.")
    try:
        payload = json.loads(body_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Reddit feed returned invalid JSON.") from exc
    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    children = data.get("children", []) if isinstance(data, dict) else []
    posts: list[dict] = []
    for child in children:
        child_data = child.get("data", {}) if isinstance(child, dict) else {}
        post_id = str(child_data.get("name", "")).strip()
        permalink = str(child_data.get("permalink", "")).strip()
        title = str(child_data.get("title", "Untitled")).strip()
        published_utc = child_data.get("created_utc")
        published_at = ""
        if isinstance(published_utc, (int, float)):
            published_at = datetime.fromtimestamp(float(published_utc), tz=UTC).isoformat()
        if not post_id:
            continue
        posts.append(
            {
                "post_id": post_id,
                "post_title": title,
                "post_url": urllib.parse.urljoin("https://www.reddit.com", permalink) if permalink else source_url,
                "published_at": published_at,
                "subreddit_name": normalized_name,
                "source_url": source_url,
            }
        )
    return posts


def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _find_xml_child_text(element: object, candidate_names: tuple[str, ...]) -> str:
    for child in list(element):
        if _xml_local_name(child.tag) in candidate_names:
            return (child.text or "").strip()
    return ""


def _find_xml_link(element: object) -> str:
    for child in list(element):
        if _xml_local_name(child.tag) != "link":
            continue
        href = str(child.attrib.get("href", "")).strip()
        if href:
            return href
        text = (child.text or "").strip()
        if text:
            return text
    return ""


def discover_wordpress_feed_url(source_url: str) -> str:
    normalized_url = normalize_wordpress_site_url(source_url)
    candidate_urls: list[str] = []
    lowered_path = urllib.parse.urlparse(normalized_url).path.lower()
    if lowered_path.endswith("/feed") or lowered_path.endswith("/feed/") or lowered_path.endswith(".xml"):
        candidate_urls.append(normalized_url)
    else:
        base = normalized_url.rstrip("/")
        candidate_urls.extend([f"{base}/feed/", f"{base}/feed", f"{base}/index.php/feed/"])
    seen: set[str] = set()
    for candidate in candidate_urls:
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            status, headers, body_text = fetch_text_url(
                candidate,
                timeout_seconds=WORDPRESS_REQUEST_TIMEOUT_SECONDS,
                accept="application/rss+xml, application/atom+xml, application/xml, text/xml, text/html",
            )
        except RuntimeError:
            continue
        content_type = headers.get("content-type", "").lower()
        if status < 400 and (
            "xml" in content_type or body_text.lstrip().startswith("<?xml") or "<rss" in body_text or "<feed" in body_text
        ):
            return candidate
    status, _, body_text = fetch_text_url(normalized_url, timeout_seconds=WORDPRESS_REQUEST_TIMEOUT_SECONDS, accept="text/html")
    if status >= 400:
        raise RuntimeError(f"WordPress site returned HTTP {status}.")
    link_patterns = (
        re.compile(r'<link[^>]+type=["\']application/rss\+xml["\'][^>]+href=["\']([^"\']+)["\']', re.IGNORECASE),
        re.compile(r'<link[^>]+href=["\']([^"\']+)["\'][^>]+type=["\']application/rss\+xml["\']', re.IGNORECASE),
        re.compile(r'<link[^>]+type=["\']application/atom\+xml["\'][^>]+href=["\']([^"\']+)["\']', re.IGNORECASE),
        re.compile(r'<link[^>]+href=["\']([^"\']+)["\'][^>]+type=["\']application/atom\+xml["\']', re.IGNORECASE),
    )
    for pattern in link_patterns:
        match = pattern.search(body_text)
        if match:
            return urllib.parse.urljoin(normalized_url, match.group(1))
    raise RuntimeError("Unable to discover a WordPress RSS/Atom feed from the site URL.")


def fetch_recent_wordpress_posts(source_url: str, limit: int = 10) -> dict:
    normalized_site_url = normalize_wordpress_site_url(source_url)
    feed_url = discover_wordpress_feed_url(normalized_site_url)
    status, _, body_text = fetch_text_url(
        feed_url,
        timeout_seconds=WORDPRESS_REQUEST_TIMEOUT_SECONDS,
        accept="application/rss+xml, application/atom+xml, application/xml, text/xml",
    )
    if status >= 400:
        raise RuntimeError(f"WordPress feed returned HTTP {status}.")
    try:
        root = DefusedET.fromstring(body_text)
    except DefusedET.ParseError as exc:
        raise RuntimeError("WordPress feed returned invalid XML.") from exc

    root_name = _xml_local_name(root.tag).lower()
    site_title = ""
    posts: list[dict] = []
    if root_name == "rss":
        channel = next((child for child in list(root) if _xml_local_name(child.tag) == "channel"), None)
        if channel is None:
            raise RuntimeError("WordPress RSS feed is missing a channel element.")
        site_title = _find_xml_child_text(channel, ("title",)) or urllib.parse.urlparse(normalized_site_url).netloc
        for item in [child for child in list(channel) if _xml_local_name(child.tag) == "item"][: max(1, limit)]:
            post_id = _find_xml_child_text(item, ("guid", "id", "link"))
            post_url = _find_xml_child_text(item, ("link",)) or post_id or normalized_site_url
            if not post_id:
                post_id = post_url
            posts.append(
                {
                    "post_id": post_id,
                    "post_title": _find_xml_child_text(item, ("title",)) or "Untitled Post",
                    "post_url": post_url,
                    "published_at": _find_xml_child_text(item, ("pubDate", "published", "updated", "dc:date")),
                }
            )
    elif root_name == "feed":
        site_title = _find_xml_child_text(root, ("title",)) or urllib.parse.urlparse(normalized_site_url).netloc
        entries = [child for child in list(root) if _xml_local_name(child.tag) == "entry"][: max(1, limit)]
        for entry in entries:
            post_id = _find_xml_child_text(entry, ("id",))
            post_url = _find_xml_link(entry) or normalized_site_url
            if not post_id:
                post_id = post_url
            posts.append(
                {
                    "post_id": post_id,
                    "post_title": _find_xml_child_text(entry, ("title",)) or "Untitled Post",
                    "post_url": post_url,
                    "published_at": _find_xml_child_text(entry, ("published", "updated")),
                }
            )
    else:
        raise RuntimeError("Unsupported WordPress feed format.")

    return {
        "site_url": normalized_site_url,
        "feed_url": feed_url,
        "site_title": site_title,
        "posts": posts,
    }


def resolve_wordpress_feed_seed(source_url: str) -> dict:
    feed_payload = fetch_recent_wordpress_posts(source_url, limit=1)
    latest = feed_payload["posts"][0] if feed_payload["posts"] else {}
    return {
        "site_url": feed_payload["site_url"],
        "feed_url": feed_payload["feed_url"],
        "site_title": feed_payload["site_title"],
        "last_post_id": str(latest.get("post_id", "")),
        "last_post_title": str(latest.get("post_title", "")),
        "last_post_url": str(latest.get("post_url", "")),
        "last_published_at": str(latest.get("published_at", "")),
    }


def linkedin_recent_activity_url(source_url: str) -> str:
    normalized_url = normalize_linkedin_profile_url(source_url)
    parsed = urllib.parse.urlparse(normalized_url)
    path = parsed.path.rstrip("/")
    if "/recent-activity/" in path:
        activity_path = path
    else:
        activity_path = f"{path}/recent-activity/all"
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, activity_path, "", "", ""))


def _extract_linkedin_text_window(body_text: str, anchor_index: int) -> str:
    window = body_text[anchor_index : anchor_index + 1400]
    texts = [match.group(1) for match in LINKEDIN_TEXT_PATTERN.finditer(window)]
    cleaned: list[str] = []
    for value in texts:
        candidate = (
            value.replace("\\n", " ").replace("\\u003C", "<").replace("\\u003E", ">").replace("\\u0026", "&").replace('\\"', '"').strip()
        )
        if candidate and candidate not in cleaned:
            cleaned.append(candidate)
        if len(cleaned) >= 3:
            break
    return truncate_log_text(" ".join(cleaned).strip() or "New LinkedIn post", max_length=160)


def fetch_recent_linkedin_posts(source_url: str, limit: int = 10) -> dict:
    profile_url = normalize_linkedin_profile_url(source_url)
    activity_url = linkedin_recent_activity_url(profile_url)
    status, _, body_text = fetch_text_url(activity_url, timeout_seconds=LINKEDIN_REQUEST_TIMEOUT_SECONDS, accept="text/html")
    if status >= 400:
        raise RuntimeError(f"LinkedIn activity page returned HTTP {status}.")
    if "linkedin.com/checkpoint/challenge" in body_text or "Sign in to LinkedIn" in body_text:
        raise RuntimeError("LinkedIn activity page requires authentication or blocked automated access.")

    decoded_body = body_text.replace("\\/", "/").replace("\\u002F", "/").replace("&amp;", "&")
    title_match = LINKEDIN_OG_TITLE_PATTERN.search(body_text)
    default_label = urllib.parse.urlparse(profile_url).path.strip("/").split("/")[-1]
    profile_label = title_match.group(1).strip() if title_match else default_label

    posts: list[dict] = []
    seen_ids: set[str] = set()
    for match in LINKEDIN_ACTIVITY_URN_PATTERN.finditer(decoded_body):
        activity_id = match.group(1).strip()
        if not activity_id or activity_id in seen_ids:
            continue
        seen_ids.add(activity_id)
        post_url_match = LINKEDIN_POST_URL_PATTERN.search(decoded_body, max(0, match.start() - 400), match.start() + 1400)
        post_url = post_url_match.group(0) if post_url_match else f"https://www.linkedin.com/feed/update/urn:li:activity:{activity_id}"
        posts.append(
            {
                "post_id": activity_id,
                "post_title": _extract_linkedin_text_window(decoded_body, match.start()),
                "post_url": post_url,
                "published_at": "",
            }
        )
        if len(posts) >= max(1, limit):
            break
    if not posts:
        raise RuntimeError("No public LinkedIn posts were found for this profile/page.")
    return {
        "profile_url": profile_url,
        "activity_url": activity_url,
        "profile_label": profile_label,
        "posts": posts,
    }


def resolve_linkedin_feed_seed(source_url: str) -> dict:
    payload = fetch_recent_linkedin_posts(source_url, limit=1)
    latest = payload["posts"][0] if payload["posts"] else {}
    return {
        "profile_url": payload["profile_url"],
        "activity_url": payload["activity_url"],
        "profile_label": payload["profile_label"],
        "last_post_id": str(latest.get("post_id", "")),
        "last_post_title": str(latest.get("post_title", "")),
        "last_post_url": str(latest.get("post_url", "")),
        "last_published_at": str(latest.get("published_at", "")),
    }


def uptime_request_json(url: str) -> dict:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError("Uptime API URL is invalid.")
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"

    connection_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    conn = connection_cls(parsed.netloc, timeout=UPTIME_STATUS_TIMEOUT_SECONDS)
    try:
        conn.request("GET", path, headers={"User-Agent": "WickedYodaLittleHelper/1.0", "Accept": "application/json"})
        response = conn.getresponse()
        body_text = response.read().decode("utf-8", errors="ignore")
    except OSError as exc:
        raise RuntimeError(f"Uptime request failed: {exc}") from exc
    finally:
        conn.close()

    if response.status >= 400:
        raise RuntimeError(f"Uptime endpoint returned HTTP {response.status}.")
    try:
        parsed_body = json.loads(body_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Uptime endpoint returned invalid JSON.") from exc
    if not isinstance(parsed_body, dict):
        raise RuntimeError("Uptime endpoint returned an unexpected response.")
    return parsed_body


def _status_label(status_code: int) -> str:
    return {
        0: "down",
        1: "up",
        2: "pending",
        3: "maintenance",
    }.get(status_code, "unknown")


def fetch_uptime_snapshot() -> dict:
    config_payload = uptime_request_json(UPTIME_API_CONFIG_URL)
    heartbeat_payload = uptime_request_json(UPTIME_API_HEARTBEAT_URL)

    group_list = config_payload.get("publicGroupList", [])
    heartbeat_list = heartbeat_payload.get("heartbeatList", {})
    uptime_list = heartbeat_payload.get("uptimeList", {})
    if not isinstance(group_list, list) or not isinstance(heartbeat_list, dict):
        raise RuntimeError("Uptime payload is missing expected fields.")

    monitor_names: dict[int, str] = {}
    for group in group_list:
        if not isinstance(group, dict):
            continue
        monitors = group.get("monitorList", [])
        if not isinstance(monitors, list):
            continue
        for monitor in monitors:
            if not isinstance(monitor, dict):
                continue
            monitor_id = monitor.get("id")
            monitor_name = monitor.get("name")
            if isinstance(monitor_id, int) and isinstance(monitor_name, str):
                monitor_names[monitor_id] = monitor_name.strip()

    status_counts = {"up": 0, "down": 0, "pending": 0, "maintenance": 0, "unknown": 0}
    down_monitors: list[str] = []
    latest_timestamp = ""

    monitor_ids = sorted(monitor_names.keys())
    if not monitor_ids:
        monitor_ids = sorted(int(key) for key in heartbeat_list.keys() if str(key).isdigit())

    for monitor_id in monitor_ids:
        entries = heartbeat_list.get(str(monitor_id), [])
        latest_entry = entries[-1] if isinstance(entries, list) and entries else None
        if not isinstance(latest_entry, dict):
            status_counts["unknown"] += 1
            continue

        status_code = latest_entry.get("status")
        status_label = _status_label(status_code) if isinstance(status_code, int) else "unknown"
        status_counts[status_label] += 1

        current_time = latest_entry.get("time")
        if isinstance(current_time, str) and current_time > latest_timestamp:
            latest_timestamp = current_time

        if status_label == "down":
            monitor_name = monitor_names.get(monitor_id, f"Monitor {monitor_id}")
            uptime_key = f"{monitor_id}_24"
            uptime_value = uptime_list.get(uptime_key) if isinstance(uptime_list, dict) else None
            if isinstance(uptime_value, int | float):
                down_monitors.append(f"{monitor_name} ({uptime_value * 100:.1f}% 24h)")
            else:
                down_monitors.append(monitor_name)

    return {
        "title": config_payload.get("config", {}).get("title", "Uptime Status"),
        "page_url": UPTIME_STATUS_PAGE_URL,
        "total": len(monitor_ids),
        "counts": status_counts,
        "down_monitors": down_monitors,
        "last_sample": latest_timestamp,
    }


def format_uptime_summary(snapshot: dict) -> str:
    counts = snapshot.get("counts", {})
    total = int(snapshot.get("total", 0))
    up = int(counts.get("up", 0))
    down = int(counts.get("down", 0))
    pending = int(counts.get("pending", 0))
    maintenance = int(counts.get("maintenance", 0))
    unknown = int(counts.get("unknown", 0))

    lines = [
        f"**{snapshot.get('title', 'Uptime Status')}**",
        f"Page: {snapshot.get('page_url', UPTIME_STATUS_PAGE_URL)}",
        f"Monitors: {total} | Up: {up} | Down: {down} | Pending: {pending} | Maintenance: {maintenance} | Unknown: {unknown}",
    ]

    last_sample = str(snapshot.get("last_sample", "")).strip()
    if last_sample:
        lines.append(f"Last sample: {last_sample} UTC")

    down_monitors = snapshot.get("down_monitors", [])
    if isinstance(down_monitors, list) and down_monitors:
        lines.append("Down monitors:")
        for item in down_monitors[:10]:
            lines.append(f"- {truncate_log_text(str(item), max_length=120)}")
        if len(down_monitors) > 10:
            lines.append(f"- ...and {len(down_monitors) - 10} more")
    else:
        lines.append("No monitors are currently down.")

    message = "\n".join(lines)
    return truncate_log_text(message, max_length=1800)


def resolve_action_db_path() -> str:
    configured_path = os.getenv("ACTION_DB_PATH", "").strip()
    preferred_path = configured_path or os.path.join(DATA_DIR, "mod_actions.db")
    fallback_root = os.path.join(tempfile.gettempdir(), "wickedyoda")
    fallback_path = os.path.join(fallback_root, "mod_actions.db")
    candidates = [preferred_path]
    if fallback_path != preferred_path:
        candidates.append(fallback_path)

    for path in candidates:
        try:
            directory = os.path.dirname(path)
            if directory:
                ensure_private_directory(directory)
            with connect_sqlite(path, timeout=5) as conn:
                conn.execute("PRAGMA user_version = 1")
                conn.commit()
            secure_sqlite_sidecars(path)
            if path != preferred_path:
                logger.warning("Action DB path %s is not writable; using fallback %s", preferred_path, path)
            return path
        except Exception as exc:
            logger.warning(
                "Unable to use action DB path %s: %s. Check mounted volume permissions for DATA_DIR=%s.",
                path,
                exc,
                DATA_DIR,
            )

    raise RuntimeError("No writable SQLite database path found for moderation action store.")


def parse_log_level(value: str, default: int = logging.INFO) -> int:
    level_name = (value or "").strip().upper()
    if not level_name:
        return default
    return getattr(logging, level_name, default)


def resolve_log_dir(db_path: str) -> str:
    configured = os.getenv("LOG_DIR", "").strip()
    preferred = configured or "/logs"
    fallback = os.path.dirname(db_path) or "."
    candidates: list[str] = [preferred]
    if fallback != preferred:
        candidates.append(fallback)

    for candidate in candidates:
        try:
            if LOG_HARDEN_FILE_PERMISSIONS:
                ensure_private_directory(candidate)
            test_path = os.path.join(candidate, ".wickedyoda-log-write-test")
            with open(test_path, "a", encoding="utf-8"):
                pass
            os.remove(test_path)
            return candidate
        except OSError as exc:
            logger.warning(
                "Unable to use LOG_DIR %s: %s. Set LOG_DIR to a writable path such as %s.",
                candidate,
                exc,
                os.path.dirname(db_path) or ".",
            )
    raise RuntimeError("No writable log directory available.")


def prune_log_directory(log_dir: str, retention_days: int) -> None:
    if retention_days <= 0:
        return
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    try:
        for entry in os.scandir(log_dir):
            if not entry.is_file():
                continue
            try:
                mtime = datetime.fromtimestamp(entry.stat().st_mtime, tz=UTC)
            except OSError:
                continue
            if mtime < cutoff:
                try:
                    os.remove(entry.path)
                except OSError:
                    logger.warning("Failed to remove old log file %s", entry.path)
    except OSError as exc:
        logger.warning("Failed to prune logs in %s: %s", log_dir, exc)


def add_file_handler(target_logger: logging.Logger, path: str, level: int) -> None:
    normalized = os.path.abspath(path)
    for handler in target_logger.handlers:
        if isinstance(handler, logging.FileHandler) and os.path.abspath(handler.baseFilename) == normalized:
            handler.setLevel(level)
            return
    if LOG_ROTATION_INTERVAL_DAYS > 0:
        backup_count = max(1, int(LOG_RETENTION_DAYS // max(LOG_ROTATION_INTERVAL_DAYS, 1))) if LOG_RETENTION_DAYS > 0 else 0
        file_handler = logging.handlers.TimedRotatingFileHandler(
            path,
            when="D",
            interval=max(1, int(LOG_ROTATION_INTERVAL_DAYS)),
            backupCount=backup_count,
            encoding="utf-8",
            utc=True,
        )
        file_handler.suffix = "%Y-%m-%d"
    else:
        file_handler = logging.FileHandler(path, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    target_logger.addHandler(file_handler)
    if LOG_HARDEN_FILE_PERMISSIONS:
        apply_best_effort_permissions(path, 0o600)


def configure_runtime_logging(log_dir: str) -> tuple[str, str, str]:
    log_level = parse_log_level(os.getenv("LOG_LEVEL", "INFO"), default=logging.INFO)
    container_log_level = parse_log_level(os.getenv("CONTAINER_LOG_LEVEL", "WARNING"), default=logging.WARNING)
    discord_log_level = parse_log_level(os.getenv("DISCORD_LOG_LEVEL", "WARNING"), default=logging.WARNING)

    root_logger = logging.getLogger()
    root_logger.setLevel(min(log_level, container_log_level, discord_log_level))
    logger.setLevel(log_level)
    bot_channel_logger.setLevel(logging.INFO)
    logging.getLogger("discord").setLevel(discord_log_level)
    logging.getLogger("werkzeug").setLevel(discord_log_level)

    bot_log_file = os.path.join(log_dir, "bot.log")
    channel_log_file = os.path.join(log_dir, "bot_log.log")
    error_log_file = os.path.join(log_dir, "container_errors.log")
    web_log_file = os.path.join(log_dir, "web_admin.log")
    web_audit_log_file = os.path.join(log_dir, "web_audit.log")

    add_file_handler(logger, bot_log_file, log_level)
    add_file_handler(bot_channel_logger, channel_log_file, logging.INFO)
    add_file_handler(root_logger, error_log_file, container_log_level)
    add_file_handler(logging.getLogger("web_admin"), web_log_file, log_level)
    add_file_handler(logging.getLogger("wickedyoda-helper.web-audit"), web_audit_log_file, log_level)
    prune_log_directory(log_dir, LOG_RETENTION_DAYS)
    return bot_log_file, channel_log_file, error_log_file


def write_startup_log_files(log_dir: str, files: list[str]) -> None:
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    for path in files:
        try:
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(f"{timestamp} [INFO] startup: Logging initialized for {log_dir}\n")
        except OSError:
            continue


def read_recent_log_lines(path: str, lines: int) -> str:
    if not os.path.exists(path) or not os.path.isfile(path):
        return ""
    with open(path, encoding="utf-8", errors="replace") as handle:
        content = handle.readlines()
    return "".join(content[-max(1, lines) :]).strip()


class ActionStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._lock = threading.Lock()
        directory = os.path.dirname(db_path)
        if directory:
            ensure_private_directory(directory)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        return connect_sqlite(self.db_path, timeout=10)

    def _initialize(self) -> None:
        with self._connect() as conn:
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
            youtube_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(youtube_subscriptions)").fetchall()}
            youtube_migrations = {
                "poll_interval_seconds": "ALTER TABLE youtube_subscriptions ADD COLUMN poll_interval_seconds INTEGER NOT NULL DEFAULT 300",
                "include_uploads": "ALTER TABLE youtube_subscriptions ADD COLUMN include_uploads INTEGER NOT NULL DEFAULT 1",
                "include_community_posts": "ALTER TABLE youtube_subscriptions ADD COLUMN include_community_posts INTEGER NOT NULL DEFAULT 0",
                "last_community_post_id": "ALTER TABLE youtube_subscriptions ADD COLUMN last_community_post_id TEXT",
                "last_community_post_title": "ALTER TABLE youtube_subscriptions ADD COLUMN last_community_post_title TEXT",
                "last_community_published_at": "ALTER TABLE youtube_subscriptions ADD COLUMN last_community_published_at TEXT",
                "last_checked_at": "ALTER TABLE youtube_subscriptions ADD COLUMN last_checked_at TEXT",
            }
            for column, statement in youtube_migrations.items():
                if column not in youtube_columns:
                    conn.execute(statement)
            conn.execute(
                "UPDATE youtube_subscriptions SET poll_interval_seconds = 300 WHERE poll_interval_seconds IS NULL OR poll_interval_seconds <= 0"
            )
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
                CREATE TABLE IF NOT EXISTS spicy_prompt_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    prompt_id TEXT NOT NULL,
                    pack_id TEXT NOT NULL,
                    used_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_spicy_prompt_usage_recent
                ON spicy_prompt_usage (guild_id, used_at)
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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS command_permissions (
                    command_key TEXT PRIMARY KEY,
                    mode TEXT NOT NULL,
                    role_ids_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tag_responses (
                    tag TEXT PRIMARY KEY,
                    response TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS guild_settings (
                    guild_id INTEGER PRIMARY KEY,
                    bot_log_channel_id INTEGER,
                    spicy_prompts_enabled INTEGER NOT NULL DEFAULT 0,
                    spicy_prompts_channel_id INTEGER,
                    uptime_alert_channel_id INTEGER,
                    color_role_ids_json TEXT NOT NULL DEFAULT "[]",
                    moderation_enabled INTEGER NOT NULL DEFAULT 0,
                    moderation_words_json TEXT NOT NULL DEFAULT "[]",
                    moderation_warning_window_hours INTEGER NOT NULL DEFAULT 72,
                    moderation_warning_threshold INTEGER NOT NULL DEFAULT 3,
                    moderation_action TEXT NOT NULL DEFAULT "timeout",
                    moderation_timeout_minutes INTEGER NOT NULL DEFAULT 10,
                    updated_at TEXT NOT NULL
                )
                """
            )
            guild_settings_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(guild_settings)").fetchall()}
            guild_settings_migrations = {
                "spicy_prompts_enabled": "ALTER TABLE guild_settings ADD COLUMN spicy_prompts_enabled INTEGER NOT NULL DEFAULT 0",
                "spicy_prompts_channel_id": "ALTER TABLE guild_settings ADD COLUMN spicy_prompts_channel_id INTEGER",
                "uptime_alert_channel_id": "ALTER TABLE guild_settings ADD COLUMN uptime_alert_channel_id INTEGER",
                "color_role_ids_json": "ALTER TABLE guild_settings ADD COLUMN color_role_ids_json TEXT NOT NULL DEFAULT '[]'",
                "moderation_enabled": "ALTER TABLE guild_settings ADD COLUMN moderation_enabled INTEGER NOT NULL DEFAULT 0",
                "moderation_words_json": "ALTER TABLE guild_settings ADD COLUMN moderation_words_json TEXT NOT NULL DEFAULT '[]'",
                "moderation_warning_window_hours": "ALTER TABLE guild_settings ADD COLUMN moderation_warning_window_hours INTEGER NOT NULL DEFAULT 72",
                "moderation_warning_threshold": "ALTER TABLE guild_settings ADD COLUMN moderation_warning_threshold INTEGER NOT NULL DEFAULT 3",
                "moderation_action": "ALTER TABLE guild_settings ADD COLUMN moderation_action TEXT NOT NULL DEFAULT 'timeout'",
                "moderation_timeout_minutes": "ALTER TABLE guild_settings ADD COLUMN moderation_timeout_minutes INTEGER NOT NULL DEFAULT 10",
            }
            for column, statement in guild_settings_migrations.items():
                if column not in guild_settings_columns:
                    conn.execute(statement)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS moderation_warnings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    message_id INTEGER,
                    channel_id INTEGER,
                    matched_word TEXT,
                    warned_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_moderation_warnings_recent
                ON moderation_warnings (guild_id, user_id, warned_at)
                """
            )
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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS member_activity_summary (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    username TEXT NOT NULL DEFAULT '',
                    display_name TEXT NOT NULL DEFAULT '',
                    first_message_at TEXT NOT NULL,
                    last_message_at TEXT NOT NULL,
                    PRIMARY KEY (guild_id, user_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS member_activity_recent_hourly (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    hour_bucket TEXT NOT NULL,
                    message_count INTEGER NOT NULL DEFAULT 0,
                    last_message_at TEXT NOT NULL,
                    PRIMARY KEY (guild_id, user_id, hour_bucket)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS member_activity_seen_messages (
                    guild_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (guild_id, message_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS member_activity_backfill_state (
                    guild_id INTEGER NOT NULL,
                    since_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (guild_id, since_at)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS random_user_picks (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    last_selected_at TEXT NOT NULL,
                    PRIMARY KEY (guild_id, user_id)
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_random_user_picks_guild_last
                    ON random_user_picks(guild_id, last_selected_at)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_member_activity_summary_last_message
                    ON member_activity_summary(guild_id, last_message_at)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_member_activity_recent_hourly_guild_bucket
                    ON member_activity_recent_hourly(guild_id, hour_bucket)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_member_activity_seen_messages_guild_created
                    ON member_activity_seen_messages(guild_id, created_at)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS birthdays (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    username TEXT NOT NULL DEFAULT '',
                    month INTEGER NOT NULL,
                    day INTEGER NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (guild_id, user_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS guess_games (
                    guild_id INTEGER PRIMARY KEY,
                    target_number INTEGER NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    created_by_user_id INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            existing_tags = conn.execute("SELECT COUNT(*) FROM tag_responses").fetchone()[0]
            if int(existing_tags) == 0:
                now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
                if GUILD_ID_CONFIGURED is not None and GUILD_ID_CONFIGURED > 0:
                    for tag, response in DEFAULT_TAG_RESPONSES.items():
                        conn.execute(
                            """
                            INSERT INTO tag_responses (tag, response, updated_at)
                            VALUES (?, ?, ?)
                            """,
                            (f"{GUILD_ID_CONFIGURED}:{tag}", response, now),
                        )
            now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
            guild_settings_ids: set[int] = set()
            if GUILD_ID_CONFIGURED is not None:
                guild_settings_ids.add(GUILD_ID_CONFIGURED)
            if MANAGED_GUILD_IDS:
                guild_settings_ids.update(MANAGED_GUILD_IDS)
            if BOT_LOG_CHANNEL > 0:
                for guild_id in sorted(guild_settings_ids):
                    existing_guild_setting = conn.execute(
                        "SELECT COUNT(*) FROM guild_settings WHERE guild_id = ?",
                        (guild_id,),
                    ).fetchone()[0]
                    if int(existing_guild_setting) == 0:
                        conn.execute(
                            """
                            INSERT INTO guild_settings (
                                guild_id,
                                bot_log_channel_id,
                                spicy_prompts_enabled,
                                spicy_prompts_channel_id,
                                color_role_ids_json,
                                moderation_enabled,
                                moderation_words_json,
                                moderation_warning_window_hours,
                                moderation_warning_threshold,
                                moderation_action,
                                moderation_timeout_minutes,
                                updated_at
                            )
                            VALUES (?, ?, 0, NULL, ?, 0, "[]", 72, 3, "timeout", 10, ?)
                            """,
                            (guild_id, BOT_LOG_CHANNEL, "[]", now),
                        )
            conn.commit()

    def record(
        self,
        action: str,
        status: str,
        moderator: str = "",
        target: str = "",
        reason: str = "",
        guild: str = "",
    ) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO actions (created_at, action, status, moderator, target, reason, guild)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
                        action,
                        status,
                        moderator,
                        target,
                        reason,
                        guild,
                    ),
                )
                conn.commit()

    def list_youtube_subscriptions(self, enabled_only: bool = True) -> list[dict]:
        query = """
            SELECT id, created_at, source_url, channel_id, channel_title, target_channel_id,
                   target_channel_name, poll_interval_seconds, include_uploads, include_community_posts,
                   last_video_id, last_video_title, last_published_at, last_community_post_id,
                   last_community_post_title, last_community_published_at, last_checked_at, enabled
            FROM youtube_subscriptions
        """
        params: tuple = ()
        if enabled_only:
            query += " WHERE enabled = 1"
        query += " ORDER BY id ASC"
        with self._lock:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def update_youtube_subscription_state(
        self,
        subscription_id: int,
        *,
        last_video_id: str | None = None,
        last_video_title: str | None = None,
        last_published_at: str | None = None,
        last_community_post_id: str | None = None,
        last_community_post_title: str | None = None,
        last_community_published_at: str | None = None,
        last_checked_at: str | None = None,
    ) -> None:
        if all(
            value is None
            for value in (
                last_video_id,
                last_video_title,
                last_published_at,
                last_community_post_id,
                last_community_post_title,
                last_community_published_at,
                last_checked_at,
            )
        ):
            return
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE youtube_subscriptions
                    SET
                        last_video_id = COALESCE(?, last_video_id),
                        last_video_title = COALESCE(?, last_video_title),
                        last_published_at = COALESCE(?, last_published_at),
                        last_community_post_id = COALESCE(?, last_community_post_id),
                        last_community_post_title = COALESCE(?, last_community_post_title),
                        last_community_published_at = COALESCE(?, last_community_published_at),
                        last_checked_at = COALESCE(?, last_checked_at)
                    WHERE id = ?
                    """,
                    (
                        last_video_id,
                        last_video_title,
                        last_published_at,
                        last_community_post_id,
                        last_community_post_title,
                        last_community_published_at,
                        last_checked_at,
                        subscription_id,
                    ),
                )
                conn.commit()

    def list_reddit_feeds(self, enabled_only: bool = True) -> list[dict]:
        query = """
            SELECT id, created_at, subreddit_name, source_url, target_channel_id, target_channel_name,
                   poll_interval_seconds, last_post_id, last_post_title, last_post_url, last_published_at,
                   last_checked_at, enabled
            FROM reddit_feeds
        """
        params: tuple = ()
        if enabled_only:
            query += " WHERE enabled = 1"
        query += " ORDER BY id ASC"
        with self._lock:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def list_wordpress_feeds(self, enabled_only: bool = True) -> list[dict]:
        query = """
            SELECT id, created_at, site_url, feed_url, site_title, target_channel_id, target_channel_name,
                   poll_interval_seconds, last_post_id, last_post_title, last_post_url, last_published_at,
                   last_checked_at, enabled
            FROM wordpress_feeds
        """
        params: tuple = ()
        if enabled_only:
            query += " WHERE enabled = 1"
        query += " ORDER BY id ASC"
        with self._lock:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def list_linkedin_feeds(self, enabled_only: bool = True) -> list[dict]:
        query = """
            SELECT id, created_at, profile_url, activity_url, profile_label, target_channel_id, target_channel_name,
                   poll_interval_seconds, last_post_id, last_post_title, last_post_url, last_published_at,
                   last_checked_at, enabled
            FROM linkedin_feeds
        """
        params: tuple = ()
        if enabled_only:
            query += " WHERE enabled = 1"
        query += " ORDER BY id ASC"
        with self._lock:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def update_reddit_feed_state(
        self,
        feed_id: int,
        *,
        last_post_id: str | None = None,
        last_post_title: str | None = None,
        last_post_url: str | None = None,
        last_published_at: str | None = None,
        last_checked_at: str | None = None,
    ) -> None:
        if all(value is None for value in (last_post_id, last_post_title, last_post_url, last_published_at, last_checked_at)):
            return
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE reddit_feeds
                    SET
                        last_post_id = COALESCE(?, last_post_id),
                        last_post_title = COALESCE(?, last_post_title),
                        last_post_url = COALESCE(?, last_post_url),
                        last_published_at = COALESCE(?, last_published_at),
                        last_checked_at = COALESCE(?, last_checked_at)
                    WHERE id = ?
                    """,
                    (
                        last_post_id,
                        last_post_title,
                        last_post_url,
                        last_published_at,
                        last_checked_at,
                        feed_id,
                    ),
                )
                conn.commit()

    def update_wordpress_feed_state(
        self,
        feed_id: int,
        *,
        last_post_id: str | None = None,
        last_post_title: str | None = None,
        last_post_url: str | None = None,
        last_published_at: str | None = None,
        last_checked_at: str | None = None,
    ) -> None:
        if all(value is None for value in (last_post_id, last_post_title, last_post_url, last_published_at, last_checked_at)):
            return
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE wordpress_feeds
                    SET
                        last_post_id = COALESCE(?, last_post_id),
                        last_post_title = COALESCE(?, last_post_title),
                        last_post_url = COALESCE(?, last_post_url),
                        last_published_at = COALESCE(?, last_published_at),
                        last_checked_at = COALESCE(?, last_checked_at)
                    WHERE id = ?
                    """,
                    (
                        last_post_id,
                        last_post_title,
                        last_post_url,
                        last_published_at,
                        last_checked_at,
                        feed_id,
                    ),
                )
                conn.commit()

    def update_linkedin_feed_state(
        self,
        feed_id: int,
        *,
        last_post_id: str | None = None,
        last_post_title: str | None = None,
        last_post_url: str | None = None,
        last_published_at: str | None = None,
        last_checked_at: str | None = None,
    ) -> None:
        if all(value is None for value in (last_post_id, last_post_title, last_post_url, last_published_at, last_checked_at)):
            return
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE linkedin_feeds
                    SET
                        last_post_id = COALESCE(?, last_post_id),
                        last_post_title = COALESCE(?, last_post_title),
                        last_post_url = COALESCE(?, last_post_url),
                        last_published_at = COALESCE(?, last_published_at),
                        last_checked_at = COALESCE(?, last_checked_at)
                    WHERE id = ?
                    """,
                    (
                        last_post_id,
                        last_post_title,
                        last_post_url,
                        last_published_at,
                        last_checked_at,
                        feed_id,
                    ),
                )
                conn.commit()

    def list_uptime_monitors(self, guild_id: int | None = None, enabled_only: bool = False) -> list[dict]:
        query = """
            SELECT id, guild_id, name, monitor_type, target, interval_seconds, timeout_seconds, enabled,
                   alert_channel_id, last_status, last_checked_at, last_change_at, last_error, last_latency_ms,
                   created_at, updated_at
            FROM uptime_monitors
        """
        params: list[object] = []
        conditions: list[str] = []
        if guild_id is not None:
            conditions.append("guild_id = ?")
            params.append(int(guild_id))
        if enabled_only:
            conditions.append("enabled = 1")
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY id ASC"
        with self._lock:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(query, tuple(params)).fetchall()
        return [dict(row) for row in rows]

    def update_uptime_monitor_state(
        self,
        monitor_id: int,
        *,
        last_status: str,
        last_checked_at: str,
        last_change_at: str | None,
        last_error: str | None,
        last_latency_ms: int | None,
    ) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE uptime_monitors
                    SET
                        last_status = ?,
                        last_checked_at = ?,
                        last_change_at = COALESCE(?, last_change_at),
                        last_error = ?,
                        last_latency_ms = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        last_status,
                        last_checked_at,
                        last_change_at,
                        last_error,
                        last_latency_ms,
                        datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
                        monitor_id,
                    ),
                )
                conn.commit()

    def replace_spicy_prompt_catalog(self, catalog: dict) -> dict:
        repo_url = str(catalog.get("repo_url", "")).strip()
        repo_branch = str(catalog.get("repo_branch", "")).strip()
        manifest_path = str(catalog.get("manifest_path", "")).strip()
        manifest_url = str(catalog.get("manifest_url", "")).strip()
        pack_rows = [item for item in catalog.get("packs", []) if isinstance(item, dict)]
        prompt_rows = [item for item in catalog.get("prompts", []) if isinstance(item, dict)]
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

        with self._lock:
            with self._connect() as conn:
                conn.execute("DELETE FROM spicy_prompt_entries")
                conn.execute("DELETE FROM spicy_prompt_packs")
                for pack in pack_rows:
                    conn.execute(
                        """
                        INSERT INTO spicy_prompt_packs (pack_id, pack_name, source_path, prompt_count, updated_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            str(pack.get("pack_id", "")).strip(),
                            str(pack.get("pack_name", "")).strip(),
                            str(pack.get("source_path", "")).strip(),
                            int(pack.get("prompt_count", 0) or 0),
                            now,
                        ),
                    )
                for prompt in prompt_rows:
                    conn.execute(
                        """
                        INSERT INTO spicy_prompt_entries (
                            pack_id, prompt_id, prompt_type, category, rating, text, tags_json, updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(prompt.get("pack_id", "")).strip(),
                            str(prompt.get("prompt_id", "")).strip(),
                            str(prompt.get("prompt_type", "prompt")).strip(),
                            str(prompt.get("category", "general")).strip(),
                            str(prompt.get("rating", "18+")).strip(),
                            str(prompt.get("text", "")).strip(),
                            json.dumps(prompt.get("tags", [])),
                            now,
                        ),
                    )
                conn.execute(
                    """
                    INSERT INTO spicy_prompt_sync_state (
                        state_id, repo_url, repo_branch, manifest_path, manifest_url,
                        last_refresh_at, last_success_at, last_error, pack_count, prompt_count
                    )
                    VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(state_id) DO UPDATE SET
                        repo_url = excluded.repo_url,
                        repo_branch = excluded.repo_branch,
                        manifest_path = excluded.manifest_path,
                        manifest_url = excluded.manifest_url,
                        last_refresh_at = excluded.last_refresh_at,
                        last_success_at = excluded.last_success_at,
                        last_error = excluded.last_error,
                        pack_count = excluded.pack_count,
                        prompt_count = excluded.prompt_count
                    """,
                    (
                        repo_url,
                        repo_branch,
                        manifest_path,
                        manifest_url,
                        now,
                        now,
                        "",
                        len(pack_rows),
                        len(prompt_rows),
                    ),
                )
                conn.commit()
        return self.get_spicy_prompt_status()

    def update_spicy_prompt_sync_failure(self, *, error: str) -> dict:
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        manifest_url = ""
        try:
            manifest_url = build_github_raw_url(SPICY_PROMPTS_REPO_URL, SPICY_PROMPTS_REPO_BRANCH, SPICY_PROMPTS_MANIFEST_PATH)
        except RuntimeError:
            manifest_url = ""
        with self._lock:
            with self._connect() as conn:
                existing_counts = conn.execute(
                    "SELECT COUNT(*), COALESCE((SELECT COUNT(*) FROM spicy_prompt_packs), 0) FROM spicy_prompt_entries"
                ).fetchone()
                prompt_count = int(existing_counts[0] or 0)
                pack_count = int(existing_counts[1] or 0)
                conn.execute(
                    """
                    INSERT INTO spicy_prompt_sync_state (
                        state_id, repo_url, repo_branch, manifest_path, manifest_url,
                        last_refresh_at, last_success_at, last_error, pack_count, prompt_count
                    )
                    VALUES (1, ?, ?, ?, ?, ?, COALESCE((SELECT last_success_at FROM spicy_prompt_sync_state WHERE state_id = 1), NULL), ?, ?, ?)
                    ON CONFLICT(state_id) DO UPDATE SET
                        repo_url = excluded.repo_url,
                        repo_branch = excluded.repo_branch,
                        manifest_path = excluded.manifest_path,
                        manifest_url = excluded.manifest_url,
                        last_refresh_at = excluded.last_refresh_at,
                        last_error = excluded.last_error,
                        pack_count = excluded.pack_count,
                        prompt_count = excluded.prompt_count
                    """,
                    (
                        SPICY_PROMPTS_REPO_URL,
                        SPICY_PROMPTS_REPO_BRANCH,
                        SPICY_PROMPTS_MANIFEST_PATH,
                        manifest_url,
                        now,
                        truncate_log_text(error, max_length=500),
                        pack_count,
                        prompt_count,
                    ),
                )
                conn.commit()
        return self.get_spicy_prompt_status()

    def get_spicy_prompt_status(self) -> dict:
        with self._lock:
            with self._connect() as conn:
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
        packs = [dict(row) for row in pack_rows]
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
            "ok": True,
            "enabled": SPICY_PROMPTS_ENABLED,
            "repo_url": state.get("repo_url", SPICY_PROMPTS_REPO_URL),
            "repo_branch": state.get("repo_branch", SPICY_PROMPTS_REPO_BRANCH),
            "manifest_path": state.get("manifest_path", SPICY_PROMPTS_MANIFEST_PATH),
            "manifest_url": state.get("manifest_url", ""),
            "last_refresh_at": state.get("last_refresh_at", ""),
            "last_success_at": state.get("last_success_at", ""),
            "last_error": state.get("last_error", ""),
            "pack_count": int(state.get("pack_count", len(packs)) or 0),
            "prompt_count": int(state.get("prompt_count", len(preview)) or 0),
            "packs": packs,
            "preview": preview,
        }

    def get_command_permissions(self, guild_id: int) -> dict[str, dict[str, str | list[int]]]:
        prefix = f"{int(guild_id)}:"
        with self._lock:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("SELECT command_key, mode, role_ids_json FROM command_permissions").fetchall()
        mapping: dict[str, dict[str, str | list[int]]] = {}
        found_prefixed = False
        for row in rows:
            command_key = str(row["command_key"]).strip()
            if command_key.startswith(prefix):
                found_prefixed = True
                command_key = command_key.removeprefix(prefix)
            elif ":" in command_key:
                continue
            elif GUILD_ID_CONFIGURED is None or int(guild_id) != GUILD_ID_CONFIGURED:
                continue
            if command_key not in COMMAND_PERMISSION_METADATA:
                continue
            raw_role_ids = row["role_ids_json"]
            try:
                parsed_role_ids = json.loads(raw_role_ids) if isinstance(raw_role_ids, str) else []
            except json.JSONDecodeError:
                parsed_role_ids = []
            mapping[command_key] = normalize_command_permission_rule({"mode": row["mode"], "role_ids": parsed_role_ids})
        if found_prefixed:
            return mapping
        if GUILD_ID_CONFIGURED is not None and int(guild_id) == GUILD_ID_CONFIGURED:
            return mapping
        return {}

    def save_command_permissions(
        self, guild_id: int, rules: dict[str, dict[str, str | list[int]]]
    ) -> dict[str, dict[str, str | list[int]]]:
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        prefix = f"{int(guild_id)}:"
        stored_rules: dict[str, dict[str, str | list[int]]] = {}
        for key, rule in (rules or {}).items():
            if key not in COMMAND_PERMISSION_METADATA:
                continue
            normalized = normalize_command_permission_rule(rule)
            if normalized["mode"] == COMMAND_PERMISSION_MODE_DEFAULT:
                continue
            stored_rules[key] = normalized

        with self._lock:
            with self._connect() as conn:
                conn.execute("DELETE FROM command_permissions WHERE command_key LIKE ?", (f"{prefix}%",))
                for key, rule in stored_rules.items():
                    conn.execute(
                        """
                        INSERT INTO command_permissions (command_key, mode, role_ids_json, updated_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (f"{prefix}{key}", str(rule["mode"]), json.dumps(rule["role_ids"]), now),
                    )
                conn.commit()
        return stored_rules

    def get_tag_responses(self, guild_id: int) -> dict[str, str]:
        prefix = f"{int(guild_id)}:"
        with self._lock:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("SELECT tag, response FROM tag_responses ORDER BY tag ASC").fetchall()
        mapping: dict[str, str] = {}
        found_prefixed = False
        for row in rows:
            raw_tag = str(row["tag"])
            if raw_tag.startswith(prefix):
                found_prefixed = True
                raw_tag = raw_tag.removeprefix(prefix)
            elif ":" in raw_tag:
                continue
            elif GUILD_ID_CONFIGURED is None or int(guild_id) != GUILD_ID_CONFIGURED:
                continue
            tag = normalize_tag(raw_tag)
            if not tag:
                continue
            response = str(row["response"]).strip()
            if response:
                mapping[tag] = response
        if found_prefixed:
            return mapping
        if GUILD_ID_CONFIGURED is not None and int(guild_id) == GUILD_ID_CONFIGURED and mapping:
            return mapping
        return dict(DEFAULT_TAG_RESPONSES)

    def save_tag_responses(self, guild_id: int, mapping: dict[str, str]) -> dict[str, str]:
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        prefix = f"{int(guild_id)}:"
        normalized: dict[str, str] = {}
        for raw_tag, raw_response in (mapping or {}).items():
            tag = normalize_tag(str(raw_tag))
            response = str(raw_response).strip()
            if not tag or not response:
                continue
            normalized[tag] = truncate_log_text(response, max_length=1900)

        with self._lock:
            with self._connect() as conn:
                conn.execute("DELETE FROM tag_responses WHERE tag LIKE ?", (f"{prefix}%",))
                for tag, response in normalized.items():
                    conn.execute(
                        """
                        INSERT INTO tag_responses (tag, response, updated_at)
                        VALUES (?, ?, ?)
                        """,
                        (f"{prefix}{tag}", response, now),
                    )
                conn.commit()
        return normalized

    def get_guild_settings(self, guild_id: int) -> dict[str, int | None | str | list[str]]:
        with self._lock:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    """
                    SELECT guild_id,
                           bot_log_channel_id,
                           spicy_prompts_enabled,
                           spicy_prompts_channel_id,
                           uptime_alert_channel_id,
                           color_role_ids_json,
                           moderation_enabled,
                           moderation_words_json,
                           moderation_warning_window_hours,
                           moderation_warning_threshold,
                           moderation_action,
                           moderation_timeout_minutes
                    FROM guild_settings
                    WHERE guild_id = ?
                    """,
                    (int(guild_id),),
                ).fetchone()
        if row is None:
            return {
                "guild_id": int(guild_id),
                "bot_log_channel_id": None,
                "spicy_prompts_enabled": 0,
                "spicy_prompts_channel_id": None,
                "uptime_alert_channel_id": None,
                "color_role_ids": [],
                "moderation_enabled": 0,
                "moderation_words": [],
                "moderation_warning_window_hours": 72,
                "moderation_warning_threshold": 3,
                "moderation_action": "timeout",
                "moderation_timeout_minutes": 10,
            }
        color_role_ids_raw = "[]"
        moderation_words_raw = "[]"
        if "color_role_ids_json" in row.keys():
            color_role_ids_raw = row["color_role_ids_json"] or "[]"
        if "moderation_words_json" in row.keys():
            moderation_words_raw = row["moderation_words_json"] or "[]"
        return {
            "guild_id": int(row["guild_id"]),
            "bot_log_channel_id": int(row["bot_log_channel_id"]) if row["bot_log_channel_id"] else None,
            "spicy_prompts_enabled": int(row["spicy_prompts_enabled"] or 0),
            "spicy_prompts_channel_id": int(row["spicy_prompts_channel_id"]) if row["spicy_prompts_channel_id"] else None,
            "uptime_alert_channel_id": int(row["uptime_alert_channel_id"]) if row["uptime_alert_channel_id"] else None,
            "color_role_ids": json.loads(str(color_role_ids_raw)),
            "moderation_enabled": int(row["moderation_enabled"] or 0),
            "moderation_words": json.loads(str(moderation_words_raw)),
            "moderation_warning_window_hours": int(row["moderation_warning_window_hours"] or 72),
            "moderation_warning_threshold": int(row["moderation_warning_threshold"] or 3),
            "moderation_action": str(row["moderation_action"] or "timeout"),
            "moderation_timeout_minutes": int(row["moderation_timeout_minutes"] or 10),
        }

    def save_guild_settings(
        self,
        guild_id: int,
        *,
        bot_log_channel_id: int | None,
        spicy_prompts_enabled: bool | None = None,
        spicy_prompts_channel_id: int | None = None,
        uptime_alert_channel_id: int | None = None,
        color_role_ids: list[int] | None = None,
        moderation_enabled: bool | None = None,
        moderation_words: list[str] | None = None,
        moderation_warning_window_hours: int | None = None,
        moderation_warning_threshold: int | None = None,
        moderation_action: str | None = None,
        moderation_timeout_minutes: int | None = None,
    ) -> dict[str, int | None | str | list[str]]:
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        current = self.get_guild_settings(guild_id)
        if spicy_prompts_enabled is None:
            spicy_prompts_enabled = bool(int(current.get("spicy_prompts_enabled", 0) or 0))
        if spicy_prompts_channel_id is None and current.get("spicy_prompts_channel_id") is not None:
            spicy_prompts_channel_id = int(current.get("spicy_prompts_channel_id", 0) or 0)
        if uptime_alert_channel_id is None and current.get("uptime_alert_channel_id") is not None:
            uptime_alert_channel_id = int(current.get("uptime_alert_channel_id", 0) or 0)
        if color_role_ids is None:
            color_role_ids = [int(value) for value in (current.get("color_role_ids") or []) if int(value) > 0]
        if moderation_enabled is None:
            moderation_enabled = bool(int(current.get("moderation_enabled", 0) or 0))
        if moderation_words is None:
            moderation_words = [str(value) for value in (current.get("moderation_words") or []) if str(value).strip()]
        if moderation_warning_window_hours is None:
            moderation_warning_window_hours = int(current.get("moderation_warning_window_hours", 72) or 72)
        if moderation_warning_threshold is None:
            moderation_warning_threshold = int(current.get("moderation_warning_threshold", 3) or 3)
        if moderation_action is None:
            moderation_action = str(current.get("moderation_action") or "timeout")
        if moderation_timeout_minutes is None:
            moderation_timeout_minutes = int(current.get("moderation_timeout_minutes", 10) or 10)
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO guild_settings (
                        guild_id,
                        bot_log_channel_id,
                        spicy_prompts_enabled,
                        spicy_prompts_channel_id,
                        uptime_alert_channel_id,
                        color_role_ids_json,
                        moderation_enabled,
                        moderation_words_json,
                        moderation_warning_window_hours,
                        moderation_warning_threshold,
                        moderation_action,
                        moderation_timeout_minutes,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(guild_id) DO UPDATE SET
                        bot_log_channel_id = excluded.bot_log_channel_id,
                        spicy_prompts_enabled = excluded.spicy_prompts_enabled,
                        spicy_prompts_channel_id = excluded.spicy_prompts_channel_id,
                        uptime_alert_channel_id = excluded.uptime_alert_channel_id,
                        color_role_ids_json = excluded.color_role_ids_json,
                        moderation_enabled = excluded.moderation_enabled,
                        moderation_words_json = excluded.moderation_words_json,
                        moderation_warning_window_hours = excluded.moderation_warning_window_hours,
                        moderation_warning_threshold = excluded.moderation_warning_threshold,
                        moderation_action = excluded.moderation_action,
                        moderation_timeout_minutes = excluded.moderation_timeout_minutes,
                        updated_at = excluded.updated_at
                    """,
                    (
                        int(guild_id),
                        bot_log_channel_id,
                        1 if spicy_prompts_enabled else 0,
                        spicy_prompts_channel_id,
                        uptime_alert_channel_id,
                        json.dumps(sorted({int(value) for value in (color_role_ids or []) if int(value) > 0})),
                        1 if moderation_enabled else 0,
                        json.dumps(sorted({str(value).strip().lower() for value in (moderation_words or []) if str(value).strip()})),
                        int(moderation_warning_window_hours),
                        int(moderation_warning_threshold),
                        str(moderation_action or "timeout"),
                        int(moderation_timeout_minutes),
                        now,
                    ),
                )
                conn.commit()
        return self.get_guild_settings(guild_id)

    def record_moderation_warning(
        self,
        guild_id: int,
        user_id: int,
        *,
        message_id: int | None = None,
        channel_id: int | None = None,
        matched_word: str | None = None,
    ) -> None:
        warned_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO moderation_warnings (
                        guild_id, user_id, message_id, channel_id, matched_word, warned_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(guild_id),
                        int(user_id),
                        int(message_id) if message_id else None,
                        int(channel_id) if channel_id else None,
                        str(matched_word or ""),
                        warned_at,
                    ),
                )
                conn.commit()

    def count_recent_moderation_warnings(
        self,
        guild_id: int,
        user_id: int,
        *,
        since_dt: datetime,
    ) -> int:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM moderation_warnings
                    WHERE guild_id = ? AND user_id = ? AND warned_at >= ?
                    """,
                    (int(guild_id), int(user_id), since_dt.strftime("%Y-%m-%d %H:%M:%S")),
                ).fetchone()
        return int(row[0] or 0)

    def record_spicy_prompt_usage(self, guild_id: int, pack_id: str, prompt_id: str) -> None:
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO spicy_prompt_usage (guild_id, pack_id, prompt_id, used_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (int(guild_id), str(pack_id), str(prompt_id), now),
                )
                conn.commit()

    def get_spicy_prompt_recent_ids(self, guild_id: int, *, since_dt: datetime) -> set[str]:
        with self._lock:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """
                    SELECT prompt_id FROM spicy_prompt_usage
                    WHERE guild_id = ? AND used_at >= ?
                    """,
                    (int(guild_id), since_dt.strftime("%Y-%m-%d %H:%M:%S")),
                ).fetchall()
        return {str(row["prompt_id"]) for row in rows if row["prompt_id"]}

    def list_spicy_prompt_categories(self) -> list[str]:
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute("SELECT DISTINCT category FROM spicy_prompt_entries").fetchall()
        categories = []
        for row in rows:
            value = str(row[0] or "").strip().lower()
            if value and value not in categories:
                categories.append(value)
        return categories

    def get_random_spicy_prompt(
        self, *, prompt_type: str | None = None, category: str | None = None, exclude_ids: set[str] | None = None
    ) -> dict | None:
        exclude_ids = exclude_ids or set()
        query = """
            SELECT pack_id, prompt_id, prompt_type, category, rating, text, tags_json
            FROM spicy_prompt_entries
        """
        params: list[object] = []
        if prompt_type:
            query += " WHERE prompt_type = ?"
            params.append(str(prompt_type).strip().lower())
        if category:
            clause = " AND " if " WHERE " in query else " WHERE "
            query += f"{clause}category = ?"
            params.append(str(category).strip().lower())
        if exclude_ids:
            placeholders = ",".join("?" for _ in exclude_ids)
            clause = " AND " if " WHERE " in query else " WHERE "
            query += f"{clause}prompt_id NOT IN ({placeholders})"
            params.extend(sorted(exclude_ids))
        query += " ORDER BY RANDOM() LIMIT 1"
        with self._lock:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(query, tuple(params)).fetchone()
        if row is None:
            return None
        item = dict(row)
        try:
            tags = json.loads(str(item.get("tags_json", "[]")))
        except json.JSONDecodeError:
            tags = []
        item["tags"] = [str(tag).strip() for tag in tags if str(tag).strip()]
        return item

    def record_member_activity(
        self,
        *,
        guild_id: int,
        user_id: int,
        username: str,
        display_name: str,
        message_id: int,
        message_dt: datetime,
    ) -> bool:
        safe_guild_id = require_managed_guild_id(guild_id, context="member activity guild")
        safe_message_dt = normalize_activity_timestamp(message_dt)
        message_iso = safe_message_dt.isoformat()
        hour_bucket = safe_message_dt.replace(minute=0, second=0, microsecond=0).isoformat()
        cutoff_dt = safe_message_dt - timedelta(days=MEMBER_ACTIVITY_RECENT_RETENTION_DAYS)
        cutoff_bucket = cutoff_dt.replace(minute=0, second=0, microsecond=0).isoformat()
        with self._lock:
            with self._connect() as conn:
                inserted = conn.execute(
                    """
                    INSERT OR IGNORE INTO member_activity_seen_messages (guild_id, message_id, created_at)
                    VALUES (?, ?, ?)
                    """,
                    (safe_guild_id, int(message_id), message_iso),
                )
                if inserted.rowcount == 0:
                    return False
                conn.execute(
                    "DELETE FROM member_activity_recent_hourly WHERE guild_id = ? AND hour_bucket < ?",
                    (safe_guild_id, cutoff_bucket),
                )
                conn.execute(
                    "DELETE FROM member_activity_seen_messages WHERE guild_id = ? AND created_at < ?",
                    (safe_guild_id, cutoff_dt.isoformat()),
                )
                conn.execute(
                    "DELETE FROM member_activity_summary WHERE guild_id = ? AND last_message_at < ?",
                    (safe_guild_id, cutoff_dt.isoformat()),
                )
                summary_row = conn.execute(
                    """
                    SELECT first_message_at
                    FROM member_activity_summary
                    WHERE guild_id = ? AND user_id = ?
                    """,
                    (safe_guild_id, int(user_id)),
                ).fetchone()
                if summary_row is None:
                    conn.execute(
                        """
                        INSERT INTO member_activity_summary (
                            guild_id, user_id, username, display_name, first_message_at, last_message_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            safe_guild_id,
                            int(user_id),
                            truncate_log_text(username, max_length=120),
                            truncate_log_text(display_name, max_length=120),
                            message_iso,
                            message_iso,
                        ),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE member_activity_summary
                        SET username = ?, display_name = ?, last_message_at = ?
                        WHERE guild_id = ? AND user_id = ?
                        """,
                        (
                            truncate_log_text(username, max_length=120),
                            truncate_log_text(display_name, max_length=120),
                            message_iso,
                            safe_guild_id,
                            int(user_id),
                        ),
                    )
                conn.execute(
                    """
                    INSERT INTO member_activity_recent_hourly (
                        guild_id, user_id, hour_bucket, message_count, last_message_at
                    )
                    VALUES (?, ?, ?, 1, ?)
                    ON CONFLICT(guild_id, user_id, hour_bucket) DO UPDATE SET
                        message_count = member_activity_recent_hourly.message_count + 1,
                        last_message_at = excluded.last_message_at
                    """,
                    (safe_guild_id, int(user_id), hour_bucket, message_iso),
                )
                conn.commit()
        return True

    def list_member_activity_window_rows(self, guild_id: int, *, since_dt: datetime) -> list[dict]:
        safe_guild_id = require_managed_guild_id(guild_id, context="member activity guild")
        cutoff_bucket = normalize_activity_timestamp(since_dt).replace(minute=0, second=0, microsecond=0).isoformat()
        with self._lock:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """
                    SELECT
                        h.user_id,
                        s.username,
                        s.display_name,
                        MAX(h.last_message_at) AS last_message_at,
                        SUM(h.message_count) AS message_count,
                        COUNT(DISTINCT substr(h.hour_bucket, 1, 10)) AS active_days
                    FROM member_activity_recent_hourly h
                    LEFT JOIN member_activity_summary s
                      ON s.guild_id = h.guild_id AND s.user_id = h.user_id
                    WHERE h.guild_id = ?
                      AND h.hour_bucket >= ?
                    GROUP BY h.user_id, s.username, s.display_name
                    ORDER BY message_count DESC, last_message_at DESC
                    """,
                    (safe_guild_id, cutoff_bucket),
                ).fetchall()
        return [dict(row) for row in rows]

    def get_member_activity_snapshot_rows(self, guild_id: int, user_id: int) -> tuple[dict | None, list[dict]]:
        safe_guild_id = require_managed_guild_id(guild_id, context="member activity guild")
        now_dt = datetime.now(UTC)
        windows: list[dict] = []
        with self._lock:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                summary_row = conn.execute(
                    """
                    SELECT user_id, username, display_name, first_message_at, last_message_at
                    FROM member_activity_summary
                    WHERE guild_id = ? AND user_id = ?
                    """,
                    (safe_guild_id, int(user_id)),
                ).fetchone()
                if summary_row is None:
                    return None, []
                for window_key, label, duration in MEMBER_ACTIVITY_WINDOW_SPECS:
                    cutoff_dt = now_dt - duration
                    row = conn.execute(
                        """
                        SELECT
                            SUM(message_count) AS message_count,
                            COUNT(DISTINCT substr(hour_bucket, 1, 10)) AS active_days,
                            MAX(last_message_at) AS last_message_at
                        FROM member_activity_recent_hourly
                        WHERE guild_id = ?
                          AND user_id = ?
                          AND hour_bucket >= ?
                        """,
                        (
                            safe_guild_id,
                            int(user_id),
                            cutoff_dt.replace(minute=0, second=0, microsecond=0).isoformat(),
                        ),
                    ).fetchone()
                    windows.append(
                        build_member_activity_window_record(
                            window_key,
                            label,
                            int((row["message_count"] or 0) if row is not None else 0),
                            int((row["active_days"] or 0) if row is not None else 0),
                            last_message_at=str((row["last_message_at"] or "") if row is not None else ""),
                        )
                    )
        return dict(summary_row), windows

    def export_member_activity_rows(self, guild_id: int) -> tuple[list[dict], list[dict]]:
        safe_guild_id = require_managed_guild_id(guild_id, context="member activity guild")
        with self._lock:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                summary_rows = conn.execute(
                    """
                    SELECT guild_id, user_id, username, display_name, first_message_at, last_message_at
                    FROM member_activity_summary
                    WHERE guild_id = ?
                    ORDER BY last_message_at DESC, user_id ASC
                    """,
                    (safe_guild_id,),
                ).fetchall()
                hourly_rows = conn.execute(
                    """
                    SELECT guild_id, user_id, hour_bucket, message_count, last_message_at
                    FROM member_activity_recent_hourly
                    WHERE guild_id = ?
                    ORDER BY hour_bucket DESC, user_id ASC
                    """,
                    (safe_guild_id,),
                ).fetchall()
        return [dict(row) for row in summary_rows], [dict(row) for row in hourly_rows]

    def save_member_activity_backfill_state(self, guild_id: int, since_dt: datetime, payload: dict) -> None:
        safe_guild_id = require_managed_guild_id(guild_id, context="member activity backfill guild")
        updated_at = datetime.now(UTC).isoformat()
        payload_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO member_activity_backfill_state (guild_id, since_at, payload_json, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(guild_id, since_at) DO UPDATE SET
                        payload_json = excluded.payload_json,
                        updated_at = excluded.updated_at
                    """,
                    (safe_guild_id, since_dt.isoformat(), payload_json, updated_at),
                )
                conn.commit()

    def load_member_activity_backfill_state(self, guild_id: int, since_dt: datetime) -> dict:
        safe_guild_id = require_managed_guild_id(guild_id, context="member activity backfill guild")
        with self._lock:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    """
                    SELECT payload_json
                    FROM member_activity_backfill_state
                    WHERE guild_id = ? AND since_at = ?
                    """,
                    (safe_guild_id, since_dt.isoformat()),
                ).fetchone()
        if row is None:
            return {}
        try:
            payload = json.loads(str(row["payload_json"]))
        except (TypeError, json.JSONDecodeError):
            payload = {}
        return payload if isinstance(payload, dict) else {}

    def list_member_activity_backfill_states(self, guild_id: int) -> list[dict]:
        safe_guild_id = require_managed_guild_id(guild_id, context="member activity backfill guild")
        with self._lock:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """
                    SELECT payload_json
                    FROM member_activity_backfill_state
                    WHERE guild_id = ?
                    """,
                    (safe_guild_id,),
                ).fetchall()
        payloads: list[dict] = []
        for row in rows:
            try:
                payload = json.loads(str(row["payload_json"]))
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                payloads.append(payload)
        return payloads

    def list_recent_random_user_ids(self, guild_id: int, since_dt: datetime) -> set[int]:
        safe_guild_id = require_managed_guild_id(guild_id, context="random user guild")
        cutoff_iso = normalize_activity_timestamp(since_dt).isoformat()
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT user_id
                    FROM random_user_picks
                    WHERE guild_id = ? AND last_selected_at >= ?
                    """,
                    (safe_guild_id, cutoff_iso),
                ).fetchall()
        return {int(row[0]) for row in rows}

    def record_random_user_pick(self, guild_id: int, user_id: int, selected_at: datetime) -> None:
        safe_guild_id = require_managed_guild_id(guild_id, context="random user guild")
        safe_selected_at = normalize_activity_timestamp(selected_at).isoformat()
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO random_user_picks (guild_id, user_id, last_selected_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(guild_id, user_id) DO UPDATE SET
                        last_selected_at = excluded.last_selected_at
                    """,
                    (safe_guild_id, int(user_id), safe_selected_at),
                )
                conn.commit()

    def save_birthday(self, guild_id: int, user_id: int, username: str, month: int, day: int) -> None:
        safe_guild_id = require_managed_guild_id(guild_id, context="birthday guild")
        updated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO birthdays (guild_id, user_id, username, month, day, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(guild_id, user_id) DO UPDATE SET
                        username = excluded.username,
                        month = excluded.month,
                        day = excluded.day,
                        updated_at = excluded.updated_at
                    """,
                    (safe_guild_id, int(user_id), truncate_log_text(username, max_length=120), int(month), int(day), updated_at),
                )
                conn.commit()

    def get_birthday(self, guild_id: int, user_id: int) -> dict | None:
        safe_guild_id = require_managed_guild_id(guild_id, context="birthday guild")
        with self._lock:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    """
                    SELECT guild_id, user_id, username, month, day, updated_at
                    FROM birthdays
                    WHERE guild_id = ? AND user_id = ?
                    """,
                    (safe_guild_id, int(user_id)),
                ).fetchone()
        return dict(row) if row is not None else None

    def delete_birthday(self, guild_id: int, user_id: int) -> bool:
        safe_guild_id = require_managed_guild_id(guild_id, context="birthday guild")
        with self._lock:
            with self._connect() as conn:
                deleted = conn.execute(
                    "DELETE FROM birthdays WHERE guild_id = ? AND user_id = ?",
                    (safe_guild_id, int(user_id)),
                )
                conn.commit()
        return bool(deleted.rowcount)

    def list_birthdays(self, guild_id: int) -> list[dict]:
        safe_guild_id = require_managed_guild_id(guild_id, context="birthday guild")
        with self._lock:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """
                    SELECT guild_id, user_id, username, month, day, updated_at
                    FROM birthdays
                    WHERE guild_id = ?
                    ORDER BY month ASC, day ASC, username ASC
                    """,
                    (safe_guild_id,),
                ).fetchall()
        return [dict(row) for row in rows]

    def get_guess_game(self, guild_id: int) -> dict | None:
        safe_guild_id = require_managed_guild_id(guild_id, context="guess guild")
        with self._lock:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    """
                    SELECT guild_id, target_number, attempt_count, created_by_user_id, updated_at
                    FROM guess_games
                    WHERE guild_id = ?
                    """,
                    (safe_guild_id,),
                ).fetchone()
        return dict(row) if row is not None else None

    def save_guess_game(self, guild_id: int, target_number: int, created_by_user_id: int, attempt_count: int = 0) -> None:
        safe_guild_id = require_managed_guild_id(guild_id, context="guess guild")
        updated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO guess_games (guild_id, target_number, attempt_count, created_by_user_id, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(guild_id) DO UPDATE SET
                        target_number = excluded.target_number,
                        attempt_count = excluded.attempt_count,
                        created_by_user_id = excluded.created_by_user_id,
                        updated_at = excluded.updated_at
                    """,
                    (safe_guild_id, int(target_number), int(attempt_count), int(created_by_user_id), updated_at),
                )
                conn.commit()

    def update_guess_game_attempts(self, guild_id: int, attempt_count: int) -> None:
        safe_guild_id = require_managed_guild_id(guild_id, context="guess guild")
        updated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE guess_games
                    SET attempt_count = ?, updated_at = ?
                    WHERE guild_id = ?
                    """,
                    (int(attempt_count), updated_at, safe_guild_id),
                )
                conn.commit()

    def clear_guess_game(self, guild_id: int) -> bool:
        safe_guild_id = require_managed_guild_id(guild_id, context="guess guild")
        with self._lock:
            with self._connect() as conn:
                deleted = conn.execute("DELETE FROM guess_games WHERE guild_id = ?", (safe_guild_id,))
                conn.commit()
        return bool(deleted.rowcount)


ACTION_DB_PATH = resolve_action_db_path()
ACTIONS_DIR = os.path.dirname(ACTION_DB_PATH) or "."
LOG_DIR = resolve_log_dir(ACTION_DB_PATH)
BOT_LOG_FILE, BOT_CHANNEL_LOG_FILE, CONTAINER_ERROR_LOG_FILE = configure_runtime_logging(LOG_DIR)
write_startup_log_files(LOG_DIR, [BOT_LOG_FILE, BOT_CHANNEL_LOG_FILE, CONTAINER_ERROR_LOG_FILE])
ACTION_STORE = ActionStore(ACTION_DB_PATH)


async def resolve_member_activity_members_async(guild_id: int, user_ids: list[int]) -> dict[int, discord.Member]:
    guild = bot.get_guild(int(guild_id))
    if guild is None:
        return {}
    members_by_id: dict[int, discord.Member] = {}
    for user_id in user_ids:
        member = guild.get_member(int(user_id))
        if member is not None:
            members_by_id[int(user_id)] = member
    missing_ids = [user_id for user_id in user_ids if user_id not in members_by_id]
    for user_id in missing_ids:
        try:
            member = await guild.fetch_member(int(user_id))
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            continue
        members_by_id[int(user_id)] = member
    return members_by_id


def resolve_member_activity_members(guild_id: int, user_ids: list[int]) -> dict[int, discord.Member]:
    unique_user_ids: list[int] = []
    seen: set[int] = set()
    for user_id in user_ids:
        try:
            normalized = int(user_id)
        except (TypeError, ValueError):
            continue
        if normalized <= 0 or normalized in seen:
            continue
        seen.add(normalized)
        unique_user_ids.append(normalized)
    if not unique_user_ids:
        return {}

    loop = getattr(bot, "loop", None)
    if loop is None or not loop.is_running():
        guild = bot.get_guild(int(guild_id))
        if guild is None:
            return {}
        return {user_id: member for user_id in unique_user_ids if (member := guild.get_member(user_id)) is not None}

    future = asyncio.run_coroutine_threadsafe(resolve_member_activity_members_async(int(guild_id), unique_user_ids), loop)
    try:
        return future.result(timeout=20)
    except concurrent.futures.TimeoutError:
        future.cancel()
        logger.warning("Timed out resolving guild members for member activity (guild=%s).", guild_id)
        return {}
    except Exception:
        logger.exception("Failed resolving guild members for member activity (guild=%s).", guild_id)
        return {}


def is_member_activity_ranking_eligible(member: discord.Member | None, role_id: int | None = None) -> bool:
    if not isinstance(member, discord.Member):
        return False
    if member.bot or is_moderator_member(member):
        return False
    if role_id is not None and not member_has_any_role_id(member, [role_id]):
        return False
    return True


def record_member_message_activity(message: discord.Message) -> bool:
    if message.guild is None or message.author.bot:
        return False
    try:
        safe_guild_id = require_managed_guild_id(message.guild.id, context="member activity guild")
    except ValueError:
        return False
    author = message.author
    display_name = getattr(author, "display_name", str(author))
    return ACTION_STORE.record_member_activity(
        guild_id=safe_guild_id,
        user_id=int(author.id),
        username=truncate_log_text(str(author), max_length=120),
        display_name=truncate_log_text(str(display_name), max_length=120),
        message_id=int(message.id),
        message_dt=normalize_activity_timestamp(getattr(message, "created_at", None)),
    )


def get_member_activity_backfill_target_guild_id() -> int:
    if MEMBER_ACTIVITY_BACKFILL_GUILD_ID is not None:
        return MEMBER_ACTIVITY_BACKFILL_GUILD_ID
    if GUILD_ID_CONFIGURED is not None and GUILD_ID_CONFIGURED > 0:
        return GUILD_ID_CONFIGURED
    if MANAGED_GUILD_IDS:
        return sorted(MANAGED_GUILD_IDS)[0]
    raise RuntimeError("MEMBER_ACTIVITY_BACKFILL_GUILD_ID is not set and no managed guild is configured.")


def list_member_activity_backfill_completed_ranges(guild_id: int) -> list[tuple[datetime, datetime]]:
    try:
        rows = ACTION_STORE.list_member_activity_backfill_states(guild_id)
    except Exception:
        logger.exception("Failed to load member activity backfill state for guild %s", guild_id)
        return []
    ranges: list[tuple[datetime, datetime]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("status") or "").strip().lower() != "completed":
            continue
        since_dt = parse_iso_datetime_utc(row.get("since_at"))
        until_dt = parse_iso_datetime_utc(row.get("until_at"))
        if since_dt is None or until_dt is None or until_dt <= since_dt:
            continue
        ranges.append((since_dt, until_dt))
    return ranges


def _can_backfill_message_channel(channel, bot_member: discord.Member | None) -> bool:
    if bot_member is None:
        return False
    try:
        permissions = channel.permissions_for(bot_member)
    except Exception:
        return False
    return bool(getattr(permissions, "view_channel", False) and getattr(permissions, "read_message_history", False))


async def iter_member_activity_backfill_channels(guild: discord.Guild):
    bot_user_id = bot.user.id if bot.user else None
    bot_member = guild.me or (guild.get_member(bot_user_id) if bot_user_id else None)
    if bot_member is None and bot_user_id:
        try:
            bot_member = await guild.fetch_member(bot_user_id)
        except (discord.Forbidden, discord.HTTPException):
            logger.warning(
                "Member activity backfill could not fetch bot member record for guild %s; channel discovery may be incomplete.",
                guild.id,
            )
    seen_channel_ids: set[int] = set()

    for channel in guild.text_channels:
        if channel.id in seen_channel_ids or not _can_backfill_message_channel(channel, bot_member):
            continue
        seen_channel_ids.add(channel.id)
        yield channel

        try:
            async for thread in channel.archived_threads(limit=None):
                if thread.id in seen_channel_ids or not _can_backfill_message_channel(thread, bot_member):
                    continue
                seen_channel_ids.add(thread.id)
                yield thread
        except (discord.Forbidden, discord.HTTPException):
            logger.warning("Skipping archived public threads for channel %s during member activity backfill.", channel.id)

        try:
            async for thread in channel.archived_threads(limit=None, private=True, joined=True):
                if thread.id in seen_channel_ids or not _can_backfill_message_channel(thread, bot_member):
                    continue
                seen_channel_ids.add(thread.id)
                yield thread
        except (TypeError, discord.Forbidden, discord.HTTPException):
            pass

    for forum in guild.forums:
        if not _can_backfill_message_channel(forum, bot_member):
            continue
        try:
            async for thread in forum.archived_threads(limit=None):
                if thread.id in seen_channel_ids or not _can_backfill_message_channel(thread, bot_member):
                    continue
                seen_channel_ids.add(thread.id)
                yield thread
        except (TypeError, discord.Forbidden, discord.HTTPException):
            pass

        try:
            async for thread in forum.archived_threads(limit=None, private=True, joined=True):
                if thread.id in seen_channel_ids or not _can_backfill_message_channel(thread, bot_member):
                    continue
                seen_channel_ids.add(thread.id)
                yield thread
        except (TypeError, discord.Forbidden, discord.HTTPException):
            pass

    for thread in guild.threads:
        if thread.id in seen_channel_ids or not _can_backfill_message_channel(thread, bot_member):
            continue
        seen_channel_ids.add(thread.id)
        yield thread


async def member_activity_backfill_job() -> None:
    if not MEMBER_ACTIVITY_BACKFILL_ENABLED:
        return
    since_dt = parse_member_activity_backfill_since(MEMBER_ACTIVITY_BACKFILL_SINCE_RAW)
    if since_dt is None:
        logger.warning("Member activity backfill is enabled but MEMBER_ACTIVITY_BACKFILL_SINCE is empty or invalid; skipping.")
        return
    try:
        guild_id = get_member_activity_backfill_target_guild_id()
    except RuntimeError as exc:
        logger.warning("Invalid member activity backfill configuration: %s", exc)
        return

    guild = bot.get_guild(guild_id)
    if guild is None:
        logger.warning("Member activity backfill skipped: guild %s is not available to the bot.", guild_id)
        return
    if not is_managed_guild_id(guild.id):
        logger.warning("Member activity backfill skipped: guild %s is outside MANAGED_GUILD_IDS.", guild.id)
        return

    state = ACTION_STORE.load_member_activity_backfill_state(guild.id, since_dt)
    previous_status = str(state.get("status") or "").strip().lower()
    previous_covered_by_existing_ranges = bool(state.get("covered_by_existing_ranges"))
    previous_channels_scanned = int(state.get("channels_scanned") or 0)
    previous_messages_processed = int(state.get("messages_processed") or 0)
    if previous_status == "completed" and (
        previous_covered_by_existing_ranges or previous_channels_scanned > 0 or previous_messages_processed > 0
    ):
        logger.info(
            "Member activity backfill already completed for guild %s since %s; skipping.",
            guild.id,
            since_dt.isoformat(),
        )
        return

    until_dt = normalize_activity_timestamp(datetime.now(UTC))
    completed_ranges = list_member_activity_backfill_completed_ranges(guild.id)
    missing_ranges = compute_member_activity_backfill_missing_ranges(since_dt, until_dt, completed_ranges)
    if not missing_ranges:
        status = {
            "status": "completed",
            "guild_id": guild.id,
            "guild_name": guild.name,
            "since_at": since_dt.isoformat(),
            "until_at": until_dt.isoformat(),
            "started_at": datetime.now(UTC).isoformat(),
            "completed_at": datetime.now(UTC).isoformat(),
            "channels_scanned": 0,
            "messages_processed": 0,
            "last_channel_id": 0,
            "last_error": "",
            "covered_by_existing_ranges": True,
        }
        ACTION_STORE.save_member_activity_backfill_state(guild.id, since_dt, status)
        logger.info(
            "Member activity backfill skipped for guild %s (%s): requested range %s to %s is already indexed.",
            guild.name,
            guild.id,
            since_dt.isoformat(),
            until_dt.isoformat(),
        )
        return

    status = {
        "status": "running",
        "guild_id": guild.id,
        "guild_name": guild.name,
        "since_at": since_dt.isoformat(),
        "until_at": until_dt.isoformat(),
        "started_at": datetime.now(UTC).isoformat(),
        "completed_at": "",
        "channels_scanned": int(state.get("channels_scanned") or 0),
        "messages_processed": int(state.get("messages_processed") or 0),
        "last_channel_id": int(state.get("last_channel_id") or 0),
        "last_error": "",
        "covered_by_existing_ranges": False,
    }
    ACTION_STORE.save_member_activity_backfill_state(guild.id, since_dt, status)
    logger.info(
        "Member activity backfill started for guild %s (%s) since %s with %s missing range(s).",
        guild.name,
        guild.id,
        since_dt.isoformat(),
        len(missing_ranges),
    )

    channels_scanned = 0
    messages_processed = 0
    try:
        async for channel in iter_member_activity_backfill_channels(guild):
            channels_scanned += 1
            status["channels_scanned"] = channels_scanned
            status["last_channel_id"] = int(channel.id)
            ACTION_STORE.save_member_activity_backfill_state(guild.id, since_dt, status)
            logger.info(
                "Member activity backfill scanning channel %s (%s) [%s].",
                getattr(channel, "name", channel.id),
                channel.id,
                channels_scanned,
            )
            try:
                for range_index, (range_start, range_end) in enumerate(missing_ranges, start=1):
                    logger.info(
                        "Member activity backfill scanning missing range %s/%s for channel %s (%s): %s to %s",
                        range_index,
                        len(missing_ranges),
                        getattr(channel, "name", channel.id),
                        channel.id,
                        range_start.isoformat(),
                        range_end.isoformat(),
                    )
                    async for message in channel.history(limit=None, after=range_start, before=range_end, oldest_first=True):
                        if message.author.bot or message.guild is None:
                            continue
                        changed = record_member_message_activity(message)
                        if changed:
                            messages_processed += 1
                            if messages_processed % MEMBER_ACTIVITY_BACKFILL_PROGRESS_LOG_INTERVAL == 0:
                                status["messages_processed"] = messages_processed
                                ACTION_STORE.save_member_activity_backfill_state(guild.id, since_dt, status)
                                logger.info(
                                    "Member activity backfill progress for guild %s: %s messages processed.",
                                    guild.id,
                                    messages_processed,
                                )
            except (discord.Forbidden, discord.HTTPException):
                logger.warning(
                    "Member activity backfill could not read channel %s (%s); continuing.",
                    getattr(channel, "name", channel.id),
                    channel.id,
                )
                continue

        if channels_scanned <= 0:
            status.update(
                {
                    "status": "failed",
                    "completed_at": datetime.now(UTC).isoformat(),
                    "channels_scanned": channels_scanned,
                    "messages_processed": messages_processed,
                    "last_error": "No readable channels were discovered for backfill.",
                }
            )
            ACTION_STORE.save_member_activity_backfill_state(guild.id, since_dt, status)
            logger.warning(
                "Member activity backfill found no readable channels for guild %s (%s); not marking run complete.",
                guild.name,
                guild.id,
            )
            return

        status.update(
            {
                "status": "completed",
                "completed_at": datetime.now(UTC).isoformat(),
                "channels_scanned": channels_scanned,
                "messages_processed": messages_processed,
                "last_error": "",
            }
        )
        ACTION_STORE.save_member_activity_backfill_state(guild.id, since_dt, status)
        logger.info(
            "Member activity backfill completed for guild %s (%s): channels=%s messages=%s since=%s until=%s",
            guild.name,
            guild.id,
            channels_scanned,
            messages_processed,
            since_dt.isoformat(),
            until_dt.isoformat(),
        )
    except Exception as exc:
        status.update(
            {
                "status": "failed",
                "completed_at": datetime.now(UTC).isoformat(),
                "channels_scanned": channels_scanned,
                "messages_processed": messages_processed,
                "last_error": str(exc),
            }
        )
        ACTION_STORE.save_member_activity_backfill_state(guild.id, since_dt, status)
        logger.exception("Member activity backfill failed for guild %s (%s).", guild.name, guild.id)


async def _collect_random_user_candidates(guild: discord.Guild, role: discord.Role | None) -> list[discord.Member]:
    if role is not None:
        candidates = [member for member in role.members if isinstance(member, discord.Member)]
    else:
        candidates = list(guild.members)
    if candidates:
        return candidates
    try:
        members = [member async for member in guild.fetch_members(limit=None)]
        if role is not None:
            role_ids = {role.id}
            members = [member for member in members if role_ids.intersection({r.id for r in member.roles})]
        return members
    except (discord.Forbidden, discord.HTTPException):
        return []


async def pick_random_user_for_guild(guild: discord.Guild, role: discord.Role | None = None) -> dict:
    cutoff_dt = datetime.now(UTC) - timedelta(days=RANDOM_USER_COOLDOWN_DAYS)
    recent_ids = ACTION_STORE.list_recent_random_user_ids(guild.id, cutoff_dt)
    candidates = await _collect_random_user_candidates(guild, role)
    filtered = [member for member in candidates if not member.bot and member.id not in recent_ids]
    if not filtered:
        total_candidates = len([member for member in candidates if not member.bot])
        return {
            "ok": False,
            "error": "No eligible members found for this selection window.",
            "eligible_count": 0,
            "candidate_count": total_candidates,
            "recent_count": len(recent_ids),
        }
    selected = secrets.choice(filtered)
    ACTION_STORE.record_random_user_pick(guild.id, selected.id, datetime.now(UTC))
    return {
        "ok": True,
        "user_id": selected.id,
        "display_name": selected.display_name,
        "mention": selected.mention,
        "eligible_count": len(filtered),
        "candidate_count": len([member for member in candidates if not member.bot]),
        "recent_count": len(recent_ids),
    }


def run_web_pick_random_user(guild_id: int, role_id: int | None = None) -> dict:
    guild = bot.get_guild(int(guild_id)) if "bot" in globals() else None
    if guild is None:
        return {"ok": False, "error": "Guild is not currently available to this bot."}
    role: discord.Role | None = None
    if isinstance(role_id, int) and role_id > 0:
        role = guild.get_role(int(role_id))
        if role is None:
            return {"ok": False, "error": "Selected role is not available in this guild."}
    try:
        future = asyncio.run_coroutine_threadsafe(pick_random_user_for_guild(guild, role), bot.loop)
        result = future.result(timeout=60)
    except Exception as exc:
        logger.exception("Failed to pick random user via web admin: %s", exc)
        return {"ok": False, "error": f"Failed to pick random user: {exc}"}
    if result.get("ok"):
        record_action_safe(
            action="random_user",
            status="success",
            moderator="web_admin",
            target=str(result.get("display_name") or result.get("user_id")),
            reason=f"role_id={role_id or 'all'}",
            guild=str(guild_id),
        )
    return result


def list_member_activity_top_window(
    guild_id: int | None, window_key: str, *, limit: int = MEMBER_ACTIVITY_WEB_TOP_LIMIT, role_id: int | None = None
) -> list[dict]:
    safe_guild_id = require_managed_guild_id(guild_id, context="member activity guild")
    window_spec = next((item for item in MEMBER_ACTIVITY_WINDOW_SPECS if item[0] == window_key), None)
    if window_spec is None:
        raise ValueError(f"Unsupported member activity window: {window_key}")
    _, label, duration = window_spec
    cutoff_dt = datetime.now(UTC) - duration
    rows = ACTION_STORE.list_member_activity_window_rows(safe_guild_id, since_dt=cutoff_dt)
    member_map = resolve_member_activity_members(safe_guild_id, [int(row.get("user_id", 0)) for row in rows])
    members: list[dict] = []
    safe_role_id = int(role_id) if isinstance(role_id, int) and role_id > 0 else None
    for row in rows:
        user_id = int(row.get("user_id", 0) or 0)
        if not is_member_activity_ranking_eligible(member_map.get(user_id), role_id=safe_role_id):
            continue
        stats = build_member_activity_window_record(
            window_key,
            label,
            int(row.get("message_count", 0) or 0),
            int(row.get("active_days", 0) or 0),
            last_message_at=str(row.get("last_message_at", "") or ""),
        )
        stats.update(
            {
                "rank": len(members) + 1,
                "user_id": user_id,
                "username": str(row.get("username", "") or ""),
                "display_name": str(row.get("display_name", "") or ""),
            }
        )
        members.append(stats)
        if len(members) >= max(1, min(int(limit), 100)):
            break
    return members


def get_member_activity_snapshot(guild_id: int | None, user_id: int) -> dict:
    safe_guild_id = require_managed_guild_id(guild_id, context="member activity guild")
    summary_row, windows = ACTION_STORE.get_member_activity_snapshot_rows(safe_guild_id, int(user_id))
    if summary_row is None:
        return {"ok": True, "user_id": int(user_id), "username": "", "display_name": "", "windows": []}
    return {
        "ok": True,
        "user_id": int(summary_row.get("user_id", 0) or 0),
        "username": str(summary_row.get("username", "") or ""),
        "display_name": str(summary_row.get("display_name", "") or ""),
        "windows": windows,
    }


def build_member_activity_web_payload(guild_id: int, role_id: int | None = None) -> dict:
    safe_guild_id = require_managed_guild_id(guild_id, context="member activity guild")
    safe_role_id = int(role_id) if isinstance(role_id, int) and role_id > 0 else None
    windows = []
    for window_key, label, _ in MEMBER_ACTIVITY_WINDOW_SPECS:
        windows.append(
            {
                "key": window_key,
                "label": label,
                "members": list_member_activity_top_window(
                    safe_guild_id, window_key, limit=MEMBER_ACTIVITY_WEB_TOP_LIMIT, role_id=safe_role_id
                ),
            }
        )
    return {
        "ok": True,
        "guild_id": safe_guild_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "top_limit": MEMBER_ACTIVITY_WEB_TOP_LIMIT,
        "selected_role_id": safe_role_id or 0,
        "excluded_role_ids": [],
        "excluded_role_names": [],
        "windows": windows,
    }


def export_member_activity_archive(guild_id: int, role_id: int | None = None) -> dict:
    safe_guild_id = require_managed_guild_id(guild_id, context="member activity guild")
    safe_role_id = int(role_id) if isinstance(role_id, int) and role_id > 0 else None
    payload = build_member_activity_web_payload(safe_guild_id, role_id=safe_role_id)
    generated_at = datetime.now(UTC).replace(microsecond=0)
    summary_rows, hourly_rows = ACTION_STORE.export_member_activity_rows(safe_guild_id)

    def build_csv_bytes(headers: list[str], rows: list[list[object]]) -> bytes:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(headers)
        writer.writerows(rows)
        return buffer.getvalue().encode("utf-8")

    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "summary.json",
            json.dumps(
                {
                    "guild_id": safe_guild_id,
                    "generated_at": generated_at.isoformat(),
                    "retention_days": MEMBER_ACTIVITY_RECENT_RETENTION_DAYS,
                    "windows": payload.get("windows", []),
                },
                indent=2,
                sort_keys=True,
            ).encode("utf-8"),
        )
        for window in payload.get("windows", []):
            members = window.get("members", []) if isinstance(window, dict) else []
            archive.writestr(
                f"{str(window.get('key') or 'window')}.csv",
                build_csv_bytes(
                    ["rank", "user_id", "display_name", "username", "message_count", "active_days", "last_message_at"],
                    [
                        [
                            int(member.get("rank") or 0),
                            int(member.get("user_id") or 0),
                            str(member.get("display_name") or ""),
                            str(member.get("username") or ""),
                            int(member.get("message_count") or 0),
                            int(member.get("active_days") or 0),
                            str(member.get("last_message_at") or ""),
                        ]
                        for member in members
                    ],
                ),
            )
        archive.writestr(
            "member_activity_summary.csv",
            build_csv_bytes(
                ["guild_id", "user_id", "username", "display_name", "first_message_at", "last_message_at"],
                [
                    [
                        int(row.get("guild_id", 0) or 0),
                        int(row.get("user_id", 0) or 0),
                        str(row.get("username", "") or ""),
                        str(row.get("display_name", "") or ""),
                        str(row.get("first_message_at", "") or ""),
                        str(row.get("last_message_at", "") or ""),
                    ]
                    for row in summary_rows
                ],
            ),
        )
        archive.writestr(
            "member_activity_recent_hourly.csv",
            build_csv_bytes(
                ["guild_id", "user_id", "hour_bucket", "message_count", "last_message_at"],
                [
                    [
                        int(row.get("guild_id", 0) or 0),
                        int(row.get("user_id", 0) or 0),
                        str(row.get("hour_bucket", "") or ""),
                        int(row.get("message_count", 0) or 0),
                        str(row.get("last_message_at", "") or ""),
                    ]
                    for row in hourly_rows
                ],
            ),
        )
    role_suffix = f"_role_{safe_role_id}" if safe_role_id is not None else ""
    return {
        "ok": True,
        "filename": f"member_activity_guild_{safe_guild_id}{role_suffix}_{generated_at.strftime('%Y%m%dT%H%M%SZ')}.zip",
        "content_type": "application/zip",
        "data": archive_buffer.getvalue(),
        "generated_at": generated_at.isoformat(),
    }


def run_web_get_member_activity(guild_id: int, role_id: int | None = None) -> dict:
    try:
        return build_member_activity_web_payload(guild_id, role_id=role_id)
    except Exception as exc:
        logger.exception("Failed to build member activity web payload")
        return {"ok": False, "error": str(exc)}


def run_web_export_member_activity(guild_id: int, role_id: int | None = None) -> dict:
    try:
        return export_member_activity_archive(guild_id, role_id=role_id)
    except Exception as exc:
        logger.exception("Failed to export member activity archive")
        return {"ok": False, "error": str(exc)}


def run_web_get_spicy_prompts_status() -> dict:
    try:
        return ACTION_STORE.get_spicy_prompt_status()
    except Exception as exc:
        logger.exception("Failed to load Spicy Prompts status: %s", exc)
        return {"ok": False, "error": "Failed to load Spicy Prompts status."}


def run_web_refresh_spicy_prompts(actor_email: str) -> dict:
    try:
        catalog = fetch_spicy_prompt_catalog()
        status = ACTION_STORE.replace_spicy_prompt_catalog(catalog)
    except Exception as exc:
        logger.exception("Failed to refresh Spicy Prompts via web admin (%s): %s", actor_email, exc)
        ACTION_STORE.update_spicy_prompt_sync_failure(error=str(exc))
        record_action_safe(
            action="spicy_prompts_refresh",
            status="failed",
            moderator=actor_email,
            target="spicy-prompts",
            reason=truncate_log_text(str(exc), max_length=250),
            guild="system",
        )
        return {"ok": False, "error": f"Failed to refresh Spicy Prompts: {exc}"}

    record_action_safe(
        action="spicy_prompts_refresh",
        status="success",
        moderator=actor_email,
        target="spicy-prompts",
        reason=f"{status.get('pack_count', 0)} packs, {status.get('prompt_count', 0)} prompts",
        guild="system",
    )
    return {
        "ok": True,
        "message": f"Refreshed Spicy Prompts: {status.get('pack_count', 0)} packs, {status.get('prompt_count', 0)} prompts.",
        **status,
    }


def build_activity_leaderboard(window_key: str, guild_id: int, *, limit: int = 10) -> tuple[str, list[dict]]:
    window_spec = next((item for item in MEMBER_ACTIVITY_WINDOW_SPECS if item[0] == window_key), None)
    if window_spec is None:
        raise ValueError(f"Unsupported leaderboard window: {window_key}")
    _, label, _ = window_spec
    return label, list_member_activity_top_window(guild_id, window_key, limit=limit)


def get_color_role_ids(guild_id: int) -> list[int]:
    settings = ACTION_STORE.get_guild_settings(guild_id)
    raw = settings.get("color_role_ids") if isinstance(settings, dict) else []
    return [int(value) for value in (raw or []) if int(value) > 0]


def get_spicy_prompt_channel_lock(guild_id: int) -> dict:
    settings = ACTION_STORE.get_guild_settings(guild_id)
    return {
        "enabled": bool(int(settings.get("spicy_prompts_enabled", 0) or 0)),
        "channel_id": int(settings.get("spicy_prompts_channel_id", 0) or 0),
    }


def list_upcoming_birthdays(guild_id: int, *, days_ahead: int = 30, limit: int = 10) -> list[dict]:
    entries = ACTION_STORE.list_birthdays(guild_id)
    now_dt = datetime.now(UTC)
    upcoming: list[dict] = []
    for row in entries:
        month = int(row.get("month", 0) or 0)
        day = int(row.get("day", 0) or 0)
        try:
            next_occurrence = next_birthday_occurrence(month, day, now_dt=now_dt)
        except ValueError:
            continue
        days_until = (next_occurrence.date() - now_dt.date()).days
        if days_until > max(1, int(days_ahead)):
            continue
        upcoming.append(
            {
                **row,
                "label": birthday_label(month, day),
                "next_occurrence": next_occurrence.strftime("%Y-%m-%d"),
                "days_until": days_until,
            }
        )
    upcoming.sort(key=lambda item: (int(item["days_until"]), str(item["username"]).lower()))
    return upcoming[: max(1, min(int(limit), 25))]


def resolve_command_permission_state(command_key: str, guild_id: int) -> tuple[str, str, list[int]]:
    default_policy = COMMAND_PERMISSION_METADATA.get(command_key, {}).get("default_policy", COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC)
    stored_rules = ACTION_STORE.get_command_permissions(guild_id=guild_id)
    rule = normalize_command_permission_rule(stored_rules.get(command_key))
    return str(default_policy), str(rule["mode"]), normalize_role_ids(rule["role_ids"])


def can_use_command(member: discord.Member | discord.User, command_key: str, guild_id: int) -> bool:
    default_policy, mode, role_ids = resolve_command_permission_state(command_key, guild_id=guild_id)
    if mode == COMMAND_PERMISSION_MODE_DISABLED:
        return False
    if mode == COMMAND_PERMISSION_MODE_PUBLIC:
        return True
    if mode == COMMAND_PERMISSION_MODE_CUSTOM_ROLES:
        return member_has_any_role_id(member, role_ids)
    if default_policy == COMMAND_PERMISSION_DEFAULT_POLICY_MODERATOR:
        return is_moderator_member(member)
    return True


def build_command_permission_denied_message(command_key: str, guild_id: int, guild: discord.Guild | None = None) -> str:
    default_policy, mode, role_ids = resolve_command_permission_state(command_key, guild_id=guild_id)
    if mode == COMMAND_PERMISSION_MODE_CUSTOM_ROLES:
        if guild is None or not role_ids:
            return "You do not have one of the roles required to run this command."
        role_mentions: list[str] = []
        for role_id in role_ids:
            role = guild.get_role(role_id)
            role_mentions.append(role.mention if role else f"`{role_id}`")
        return f"You need one of these roles: {', '.join(role_mentions)}."
    if default_policy == COMMAND_PERMISSION_DEFAULT_POLICY_MODERATOR:
        return "Only moderators can use this command."
    return "You do not have permission to use this command."


def build_command_permissions_web_payload(guild_id: int) -> dict:
    rules = ACTION_STORE.get_command_permissions(guild_id=guild_id)
    commands_payload: list[dict] = []
    for command_key, metadata in COMMAND_PERMISSION_METADATA.items():
        rule = normalize_command_permission_rule(rules.get(command_key))
        default_policy = metadata.get("default_policy", COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC)
        commands_payload.append(
            {
                "key": command_key,
                "label": metadata.get("label", command_key),
                "description": metadata.get("description", ""),
                "default_policy": default_policy,
                "default_policy_label": COMMAND_PERMISSION_POLICY_LABELS.get(default_policy, default_policy),
                "mode": rule["mode"],
                "role_ids": rule["role_ids"],
            }
        )
    return {"ok": True, "commands": commands_payload, "guild_id": int(guild_id)}


def run_web_get_command_permissions(guild_id: int) -> dict:
    try:
        return build_command_permissions_web_payload(guild_id=guild_id)
    except Exception as exc:
        logger.exception("Failed to build command permissions payload: %s", exc)
        return {"ok": False, "error": "Failed to load command permissions."}


def run_web_update_command_permissions(payload: dict, _actor_email: str, guild_id: int) -> dict:
    if not isinstance(payload, dict):
        return {"ok": False, "error": "Invalid payload."}
    commands_payload = payload.get("commands")
    if not isinstance(commands_payload, dict):
        return {"ok": False, "error": "Missing commands payload."}

    updated_rules: dict[str, dict[str, str | list[int]]] = {}
    for command_key in COMMAND_PERMISSION_METADATA:
        raw_rule = commands_payload.get(command_key, {})
        if not isinstance(raw_rule, dict):
            raw_rule = {}
        mode = normalize_permission_mode(str(raw_rule.get("mode", COMMAND_PERMISSION_MODE_DEFAULT)))
        role_ids = normalize_role_ids(raw_rule.get("role_ids"))
        if mode == COMMAND_PERMISSION_MODE_CUSTOM_ROLES and not role_ids:
            return {"ok": False, "error": f"{command_key}: custom_roles requires at least one role ID."}
        updated_rules[command_key] = {"mode": mode, "role_ids": role_ids}

    try:
        ACTION_STORE.save_command_permissions(guild_id=guild_id, rules=updated_rules)
    except Exception as exc:
        logger.exception("Failed to save command permissions: %s", exc)
        return {"ok": False, "error": "Failed to save command permissions."}
    response = build_command_permissions_web_payload(guild_id=guild_id)
    response["message"] = "Command permissions updated."
    return response


def run_web_get_tag_responses(guild_id: int) -> dict:
    try:
        mapping = ACTION_STORE.get_tag_responses(guild_id=guild_id)
    except Exception as exc:
        logger.exception("Failed to load tag responses: %s", exc)
        return {"ok": False, "error": "Failed to load tag responses."}
    return {"ok": True, "mapping": mapping}


def run_web_save_tag_responses(mapping: dict, _actor_email: str, guild_id: int) -> dict:
    if not isinstance(mapping, dict):
        return {"ok": False, "error": "Tag responses payload must be an object."}
    normalized: dict[str, str] = {}
    for raw_tag, raw_response in mapping.items():
        if not isinstance(raw_tag, str) or not isinstance(raw_response, str):
            return {"ok": False, "error": "All tag keys and values must be strings."}
        tag = normalize_tag(raw_tag)
        response = raw_response.strip()
        if not tag or not response:
            continue
        normalized[tag] = response

    try:
        saved = ACTION_STORE.save_tag_responses(guild_id=guild_id, mapping=normalized)
    except Exception as exc:
        logger.exception("Failed to save tag responses: %s", exc)
        return {"ok": False, "error": "Failed to save tag responses."}
    return {"ok": True, "mapping": saved, "message": "Tag responses updated."}


def run_web_get_spicy_prompt_status(guild_id: int) -> dict:
    try:
        safe_guild_id = require_managed_guild_id(guild_id, context="spicy prompt status")
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    lock = get_spicy_prompt_channel_lock(safe_guild_id)
    return {
        "ok": True,
        "guild_id": safe_guild_id,
        "enabled": bool(lock.get("enabled")),
        "channel_id": int(lock.get("channel_id", 0) or 0),
    }


def run_web_get_guild_settings(guild_id: int) -> dict:
    try:
        payload = ACTION_STORE.get_guild_settings(guild_id=guild_id)
    except Exception as exc:
        logger.exception("Failed to load guild settings for %s: %s", guild_id, exc)
        return {"ok": False, "error": "Failed to load guild settings."}
    return {"ok": True, **payload}


def run_web_save_guild_settings(payload: dict, _actor_email: str, guild_id: int) -> dict:
    if not isinstance(payload, dict):
        return {"ok": False, "error": "Invalid payload."}
    raw_channel_id = str(payload.get("bot_log_channel_id", "")).strip()
    has_spicy_channel = "spicy_prompts_channel_id" in payload
    has_spicy_enabled = "spicy_prompts_enabled" in payload
    raw_spicy_channel_id = str(payload.get("spicy_prompts_channel_id", "")).strip()
    raw_spicy_enabled = str(payload.get("spicy_prompts_enabled", "")).strip().lower()
    raw_uptime_channel_id = str(payload.get("uptime_alert_channel_id", "")).strip()
    raw_moderation_enabled = str(payload.get("moderation_enabled", "")).strip().lower()
    raw_moderation_words = payload.get("moderation_words", "")
    raw_warning_window = str(payload.get("moderation_warning_window_hours", "")).strip()
    raw_warning_threshold = str(payload.get("moderation_warning_threshold", "")).strip()
    raw_moderation_action = str(payload.get("moderation_action", "")).strip().lower()
    raw_timeout_minutes = str(payload.get("moderation_timeout_minutes", "")).strip()
    color_role_names = payload.get("color_role_names", [])
    color_role_ids_payload = payload.get("color_role_ids", [])
    bot_log_channel_id: int | None
    spicy_prompts_channel_id: int | None
    spicy_prompts_enabled: bool | None
    uptime_alert_channel_id: int | None
    moderation_enabled: bool | None
    moderation_words: list[str] | None
    moderation_warning_window_hours: int | None
    moderation_warning_threshold: int | None
    moderation_action: str | None
    moderation_timeout_minutes: int | None
    if not raw_channel_id:
        bot_log_channel_id = None
    elif raw_channel_id.isdigit():
        bot_log_channel_id = int(raw_channel_id)
    else:
        return {"ok": False, "error": "Bot log channel ID must be numeric."}
    if not has_spicy_channel:
        spicy_prompts_channel_id = None
    elif not raw_spicy_channel_id:
        spicy_prompts_channel_id = None
    elif raw_spicy_channel_id.isdigit():
        spicy_prompts_channel_id = int(raw_spicy_channel_id)
    else:
        return {"ok": False, "error": "Spicy Prompts channel ID must be numeric."}
    spicy_prompts_enabled = raw_spicy_enabled in {"1", "true", "yes", "on"} if has_spicy_enabled else None
    if spicy_prompts_enabled and spicy_prompts_channel_id is None:
        return {"ok": False, "error": "Spicy Prompts requires a configured Discord channel."}
    if not raw_uptime_channel_id:
        uptime_alert_channel_id = None
    elif raw_uptime_channel_id.isdigit():
        uptime_alert_channel_id = int(raw_uptime_channel_id)
    else:
        return {"ok": False, "error": "Uptime alert channel ID must be numeric."}

    moderation_enabled = raw_moderation_enabled in {"1", "true", "yes", "on"} if raw_moderation_enabled else None
    moderation_words = None
    if isinstance(raw_moderation_words, list):
        moderation_words = [str(value).strip() for value in raw_moderation_words if str(value).strip()]
    elif isinstance(raw_moderation_words, str):
        moderation_words = [line.strip() for line in raw_moderation_words.replace(",", "\n").splitlines() if line.strip()]

    if raw_warning_window:
        if not raw_warning_window.isdigit():
            return {"ok": False, "error": "Moderation warning window must be numeric hours."}
        moderation_warning_window_hours = int(raw_warning_window)
    else:
        moderation_warning_window_hours = None

    if raw_warning_threshold:
        if not raw_warning_threshold.isdigit():
            return {"ok": False, "error": "Moderation warning threshold must be numeric."}
        moderation_warning_threshold = int(raw_warning_threshold)
    else:
        moderation_warning_threshold = None

    if raw_moderation_action:
        if raw_moderation_action not in {"timeout", "warn_only"}:
            return {"ok": False, "error": "Moderation action must be timeout or warn_only."}
        moderation_action = raw_moderation_action
    else:
        moderation_action = None

    if raw_timeout_minutes:
        if not raw_timeout_minutes.isdigit():
            return {"ok": False, "error": "Moderation timeout minutes must be numeric."}
        moderation_timeout_minutes = int(raw_timeout_minutes)
    else:
        moderation_timeout_minutes = None

    parsed_role_ids: list[int] = []
    if isinstance(color_role_ids_payload, list):
        for value in color_role_ids_payload:
            if str(value).isdigit():
                parsed_role_ids.append(int(value))
    elif isinstance(color_role_ids_payload, str):
        for part in color_role_ids_payload.split(","):
            if part.strip().isdigit():
                parsed_role_ids.append(int(part.strip()))
    role_names: list[str] = []
    if isinstance(color_role_names, list):
        role_names = [str(value) for value in color_role_names]
    elif isinstance(color_role_names, str):
        role_names = [color_role_names]

    try:
        created_ids: list[int] = []
        if role_names:
            future = asyncio.run_coroutine_threadsafe(_ensure_color_roles(guild_id, role_names), bot.loop)
            created_ids = future.result(timeout=30)
        merged_ids = sorted({*parsed_role_ids, *created_ids})
        saved = ACTION_STORE.save_guild_settings(
            guild_id=guild_id,
            bot_log_channel_id=bot_log_channel_id,
            spicy_prompts_enabled=spicy_prompts_enabled,
            spicy_prompts_channel_id=spicy_prompts_channel_id,
            uptime_alert_channel_id=uptime_alert_channel_id,
            color_role_ids=merged_ids,
            moderation_enabled=moderation_enabled,
            moderation_words=moderation_words,
            moderation_warning_window_hours=moderation_warning_window_hours,
            moderation_warning_threshold=moderation_warning_threshold,
            moderation_action=moderation_action,
            moderation_timeout_minutes=moderation_timeout_minutes,
        )
    except Exception as exc:
        logger.exception("Failed to save guild settings for %s: %s", guild_id, exc)
        return {"ok": False, "error": "Failed to save guild settings."}
    return {"ok": True, **saved, "message": "Guild settings updated."}


def run_web_get_bot_profile(guild_id: int) -> dict:
    selected_guild_id = int(guild_id) if isinstance(guild_id, int) else GUILD_ID
    guild = bot.get_guild(selected_guild_id) if "bot" in globals() else None
    if guild is None and "bot" in globals():
        managed = bot.get_managed_guilds()
        if managed:
            guild = managed[0]
            selected_guild_id = guild.id
    user = bot.user if "bot" in globals() else None
    if user is None:
        return {"ok": False, "error": "Bot user is not ready yet."}

    member = guild.get_member(user.id) if guild else None
    return {
        "ok": True,
        "id": user.id,
        "name": user.name,
        "global_name": user.global_name or "",
        "avatar_url": str(user.display_avatar.url) if user.display_avatar else "",
        "guild_id": guild.id if guild else selected_guild_id,
        "guild_name": guild.name if guild else "",
        "server_nickname": member.nick if member else "",
        "message": "Bot profile loaded.",
    }


async def _apply_bot_profile_update(username: str | None, server_nickname: str | None, clear_server_nickname: bool, guild_id: int) -> None:
    if bot.user is None:
        raise RuntimeError("Bot user is not ready yet.")
    if username:
        current = str(bot.user.name or "").strip()
        if username != current:
            await bot.user.edit(username=username)

    guild = bot.get_guild(int(guild_id))
    if guild is None:
        return
    bot_member = guild.get_member(bot.user.id)
    if bot_member is None:
        return
    if clear_server_nickname:
        await bot_member.edit(nick=None, reason="Updated via web admin")
    elif server_nickname is not None and server_nickname != "":
        await bot_member.edit(nick=server_nickname, reason="Updated via web admin")


async def _apply_bot_avatar_update(payload: bytes) -> None:
    if bot.user is None:
        raise RuntimeError("Bot user is not ready yet.")
    await bot.user.edit(avatar=payload)


def run_web_update_bot_profile(payload: dict, actor_email: str, guild_id: int) -> dict:
    if not isinstance(payload, dict):
        return {"ok": False, "error": "Invalid payload."}
    raw_username = str(payload.get("bot_name", "")).strip()
    raw_server_nickname = str(payload.get("server_nickname", "")).strip()
    clear_server_nickname = bool(payload.get("clear_server_nickname", False))
    username = raw_username if raw_username else None
    server_nickname: str | None
    if clear_server_nickname:
        server_nickname = None
    else:
        server_nickname = raw_server_nickname if raw_server_nickname else None
    if username and (len(username) < 2 or len(username) > 32):
        return {"ok": False, "error": "Bot username must be between 2 and 32 characters."}
    if server_nickname and len(server_nickname) > 32:
        return {"ok": False, "error": "Server nickname must be 32 characters or fewer."}

    try:
        future = asyncio.run_coroutine_threadsafe(
            _apply_bot_profile_update(username, server_nickname, clear_server_nickname, int(guild_id)),
            bot.loop,
        )
        future.result(timeout=25)
    except Exception as exc:
        logger.exception("Failed to update bot profile via web admin (%s): %s", actor_email, exc)
        return {"ok": False, "error": f"Failed to update bot profile: {exc}"}
    profile = run_web_get_bot_profile(guild_id=int(guild_id))
    profile["message"] = "Bot profile updated."
    return profile


def run_web_update_bot_avatar(payload: bytes, filename: str, actor_email: str, guild_id: int) -> dict:
    if not isinstance(payload, bytes):
        return {"ok": False, "error": "Avatar payload must be bytes."}
    if len(payload) == 0:
        return {"ok": False, "error": "Avatar file is empty."}
    if len(payload) > WEB_AVATAR_MAX_UPLOAD_BYTES:
        return {
            "ok": False,
            "error": f"Avatar file too large ({len(payload)} bytes). Max is {WEB_AVATAR_MAX_UPLOAD_BYTES} bytes.",
        }
    lowered = str(filename or "").strip().lower()
    if not lowered.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
        return {"ok": False, "error": "Avatar must be PNG, JPG, JPEG, WEBP, or GIF."}

    try:
        future = asyncio.run_coroutine_threadsafe(_apply_bot_avatar_update(payload), bot.loop)
        future.result(timeout=25)
    except Exception as exc:
        logger.exception("Failed to update bot avatar via web admin (%s): %s", actor_email, exc)
        return {"ok": False, "error": f"Failed to update bot avatar: {exc}"}
    profile = run_web_get_bot_profile(guild_id=int(guild_id))
    profile["message"] = "Bot avatar updated."
    return profile


def run_web_request_restart(actor_email: str) -> dict:
    if not WEB_RESTART_ENABLED:
        return {"ok": False, "error": "WEB_RESTART_ENABLED is false."}
    logger.warning("Restart requested from web admin by %s", actor_email)
    record_action_safe(
        action="restart_requested",
        status="success",
        moderator=actor_email,
        target="container",
        reason="Web admin restart request",
        guild="system",
    )

    def _exit_process() -> None:
        logger.warning("Exiting process due to web admin restart request.")
        os._exit(0)

    timer = threading.Timer(1.0, _exit_process)
    timer.daemon = True
    timer.start()
    return {"ok": True, "message": "Restart requested. Container should restart shortly."}


def run_web_get_honeypot(guild_id: int) -> dict:
    return {"ok": False, "error": "Honeypot callback is not configured."}


def run_web_manage_honeypot(payload: dict, actor_email: str, guild_id: int) -> dict:
    return {"ok": False, "error": "Honeypot callback is not configured."}


def run_web_get_role_access_mappings(guild_id: int) -> dict:
    return {"ok": False, "error": "Role access callback is not configured."}


def run_web_manage_role_access_mappings(payload: dict, actor_email: str, guild_id: int) -> dict:
    return {"ok": False, "error": "Role access callback is not configured."}


def run_web_get_reaction_roles(guild_id: int) -> dict:
    return {"ok": False, "error": "Reaction roles callback is not configured."}


def run_web_manage_reaction_roles(payload: dict, actor_email: str, guild_id: int) -> dict:
    return {"ok": False, "error": "Reaction roles callback is not configured."}


def run_web_get_discourse_settings(guild_id: int) -> dict:
    return {"ok": False, "error": "Discourse callback is not configured."}


def run_web_manage_discourse_settings(payload: dict, actor_email: str, guild_id: int) -> dict:
    return {"ok": False, "error": "Discourse callback is not configured."}


async def _ensure_color_roles(guild_id: int, names: list[str]) -> list[int]:
    guild = bot.get_guild(int(guild_id))
    if guild is None:
        raise RuntimeError("Guild is not currently available to this bot.")
    normalized: list[str] = []
    for name in names:
        value = str(name).strip()
        if value and value not in normalized:
            normalized.append(value)
    if not normalized:
        return []
    existing = {role.name.lower(): role for role in guild.roles}
    created_ids: list[int] = []
    for name in normalized:
        existing_role = existing.get(name.lower())
        if existing_role:
            created_ids.append(existing_role.id)
            continue
        color_value = POPULAR_COLOR_ROLES.get(name, 0x000000)
        try:
            role = await guild.create_role(name=name, colour=discord.Colour(color_value), reason="Create color role")
        except discord.Forbidden as exc:
            raise RuntimeError("Missing permissions to create roles.") from exc
        created_ids.append(role.id)
    return created_ids


class ModerationBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.commands_synced = 0
        self.expected_commands = 0
        self.started_at = datetime.now(UTC)
        self.web_thread: threading.Thread | None = None
        self.web_tls_thread: threading.Thread | None = None
        self.youtube_monitor_task: asyncio.Task | None = None
        self.member_activity_backfill_task: asyncio.Task | None = None
        self.web_channel_options: list[dict] = []
        self.web_role_options: list[dict] = []

    def get_managed_guilds(self) -> list[discord.Guild]:
        guilds = sorted(self.guilds, key=lambda item: item.id)
        if MANAGED_GUILD_IDS is None:
            return guilds
        return [guild for guild in guilds if guild.id in MANAGED_GUILD_IDS]

    async def sync_guild_commands(self, reason: str) -> None:
        managed_guilds = self.get_managed_guilds()
        expected_per_guild = len(self.tree.get_commands())
        self.expected_commands = expected_per_guild * max(1, len(managed_guilds))
        synced_total = 0
        for guild in managed_guilds:
            guild_obj = discord.Object(id=guild.id)
            self.tree.copy_global_to(guild=guild_obj)
            synced = await self.tree.sync(guild=guild_obj)
            synced_total += len(synced)
            synced_names = ", ".join(f"/{command.name}" for command in synced)
            logger.info(
                "Synced %s/%s command(s) to guild %s (%s): %s",
                len(synced),
                expected_per_guild,
                guild.id,
                reason,
                synced_names or "(none)",
            )
        self.commands_synced = synced_total

    async def setup_hook(self) -> None:
        ensure_dnd_schema()
        if WEB_ENABLED and self.web_thread is None:
            self.web_thread = start_web_admin(
                db_path=ACTION_DB_PATH,
                get_bot_snapshot=self.get_web_snapshot,
                get_managed_guilds=self.get_web_managed_guilds,
                get_discord_catalog=self.get_web_discord_catalog,
                get_command_permissions=run_web_get_command_permissions,
                save_command_permissions=run_web_update_command_permissions,
                get_tag_responses=run_web_get_tag_responses,
                save_tag_responses=run_web_save_tag_responses,
                get_guild_settings=run_web_get_guild_settings,
                save_guild_settings=run_web_save_guild_settings,
                get_bot_profile=run_web_get_bot_profile,
                update_bot_profile=run_web_update_bot_profile,
                update_bot_avatar=run_web_update_bot_avatar,
                get_member_activity=run_web_get_member_activity,
                get_spicy_prompt_status=run_web_get_spicy_prompt_status,
                export_member_activity=run_web_export_member_activity,
                get_spicy_prompts_status=run_web_get_spicy_prompts_status,
                refresh_spicy_prompts=run_web_refresh_spicy_prompts,
                pick_random_user=run_web_pick_random_user,
                kick_member=run_web_kick_member,
                ban_member=run_web_ban_member,
                timeout_member=run_web_timeout_member,
                untimeout_member=run_web_untimeout_member,
                leave_guild=run_web_leave_guild,
                request_restart=run_web_request_restart,
                resolve_youtube_subscription=lambda source_url: resolve_youtube_subscription_seed(source_url),
                resolve_youtube_community_seed=lambda source_url: resolve_youtube_community_seed(source_url),
                resolve_wordpress_feed=lambda source_url: resolve_wordpress_feed_seed(source_url),
                resolve_linkedin_feed=lambda source_url: resolve_linkedin_feed_seed(source_url),
                get_honeypot=run_web_get_honeypot,
                manage_honeypot=run_web_manage_honeypot,
                get_role_access=run_web_get_role_access_mappings,
                manage_role_access=run_web_manage_role_access_mappings,
                get_reaction_roles=run_web_get_reaction_roles,
                manage_reaction_roles=run_web_manage_reaction_roles,
                get_discourse=run_web_get_discourse_settings,
                manage_discourse=run_web_manage_discourse_settings,
                host=WEB_BIND_HOST,
                port=WEB_PORT,
            )
            logger.info("Web admin HTTP started at http://%s:%s", WEB_BIND_HOST, WEB_PORT)
            if WEB_TLS_ENABLED and self.web_tls_thread is None:
                ssl_context: str | tuple[str, str] | None = None
                if WEB_TLS_CERT_FILE and WEB_TLS_KEY_FILE:
                    ssl_context = (WEB_TLS_CERT_FILE, WEB_TLS_KEY_FILE)
                elif importlib.util.find_spec("cryptography") is not None:
                    ssl_context = "adhoc"
                else:
                    logger.error(
                        "WEB_TLS_ENABLED is true but cryptography is not installed and no WEB_TLS_CERT_FILE/WEB_TLS_KEY_FILE were set. "
                        "HTTPS listener on port %s is disabled; install cryptography or provide certificate files.",
                        WEB_TLS_PORT,
                    )
                if ssl_context is not None:
                    self.web_tls_thread = start_web_admin(
                        db_path=ACTION_DB_PATH,
                        get_bot_snapshot=self.get_web_snapshot,
                        get_managed_guilds=self.get_web_managed_guilds,
                        get_discord_catalog=self.get_web_discord_catalog,
                        get_command_permissions=run_web_get_command_permissions,
                        save_command_permissions=run_web_update_command_permissions,
                        get_tag_responses=run_web_get_tag_responses,
                        save_tag_responses=run_web_save_tag_responses,
                        get_guild_settings=run_web_get_guild_settings,
                        save_guild_settings=run_web_save_guild_settings,
                        get_bot_profile=run_web_get_bot_profile,
                        update_bot_profile=run_web_update_bot_profile,
                        update_bot_avatar=run_web_update_bot_avatar,
                        get_member_activity=run_web_get_member_activity,
                        get_spicy_prompt_status=run_web_get_spicy_prompt_status,
                        export_member_activity=run_web_export_member_activity,
                        get_spicy_prompts_status=run_web_get_spicy_prompts_status,
                        refresh_spicy_prompts=run_web_refresh_spicy_prompts,
                        pick_random_user=run_web_pick_random_user,
                        kick_member=run_web_kick_member,
                        ban_member=run_web_ban_member,
                        timeout_member=run_web_timeout_member,
                        untimeout_member=run_web_untimeout_member,
                        leave_guild=run_web_leave_guild,
                        request_restart=run_web_request_restart,
                        resolve_youtube_subscription=lambda source_url: resolve_youtube_subscription_seed(source_url),
                        resolve_youtube_community_seed=lambda source_url: resolve_youtube_community_seed(source_url),
                        resolve_wordpress_feed=lambda source_url: resolve_wordpress_feed_seed(source_url),
                        resolve_linkedin_feed=lambda source_url: resolve_linkedin_feed_seed(source_url),
                        host=WEB_BIND_HOST,
                        port=WEB_TLS_PORT,
                        ssl_context=ssl_context,
                    )
                    logger.info("Web admin HTTPS started at https://%s:%s", WEB_BIND_HOST, WEB_TLS_PORT)
        if self.youtube_monitor_task is None:
            self.youtube_monitor_task = self.loop.create_task(self.youtube_monitor_loop(), name="youtube-monitor")

    async def on_ready(self) -> None:
        logger.info("Logged in as %s (%s)", self.user, self.user.id if self.user else "n/a")
        await self.sync_guild_commands(reason="ready-sync")
        managed = self.get_managed_guilds()
        default_guild_id = managed[0].id if managed else GUILD_ID
        self.web_channel_options = self.build_web_channel_options(guild_id=default_guild_id)
        self.web_role_options = self.build_web_role_options(guild_id=default_guild_id)
        if not ENABLE_MEMBERS_INTENT:
            logger.info("ENABLE_MEMBERS_INTENT is disabled; no privileged members intent requested.")
        if not ENABLE_MESSAGE_CONTENT_INTENT:
            logger.warning("ENABLE_MESSAGE_CONTENT_INTENT is disabled; member activity tracking needs Message Content intent.")
        if managed:
            for guild in managed:
                await log_action(
                    self,
                    "Bot Started",
                    f"{self.user.mention if self.user else 'Bot'} is online and ready.",
                    color=discord.Color.green(),
                    guild_id=guild.id,
                )
        else:
            await log_action(
                self,
                "Bot Started",
                f"{self.user.mention if self.user else 'Bot'} is online and ready.",
                color=discord.Color.green(),
                guild_id=GUILD_ID,
            )
        if MEMBER_ACTIVITY_BACKFILL_ENABLED and (self.member_activity_backfill_task is None or self.member_activity_backfill_task.done()):
            self.member_activity_backfill_task = asyncio.create_task(
                member_activity_backfill_job(),
                name="member-activity-backfill",
            )
        ACTION_STORE.record(
            action="bot_started",
            status="success",
            moderator="system",
            target=str(self.user) if self.user else "bot",
            reason="Bot connected to Discord.",
            guild="multi-guild",
        )

    def get_web_snapshot(self) -> dict:
        latency_ms = max(int(self.latency * 1000), 0) if self.is_ready() else 0
        managed = self.get_managed_guilds()
        invite_url = ""
        if self.user is not None:
            invite_url = discord.utils.oauth_url(
                self.user.id,
                scopes=("bot", "applications.commands"),
            )
        return {
            "bot_name": str(self.user) if self.user else "Starting...",
            "bot_ready": bool(self.is_ready()),
            "guild_id": GUILD_ID,
            "guild_count": len(managed),
            "latency_ms": latency_ms,
            "commands_synced": self.commands_synced,
            "started_at": self.started_at.isoformat(),
            "server_time": datetime.now().astimezone().isoformat(timespec="seconds"),
            "invite_url": invite_url,
        }

    def build_web_channel_options(self, guild_id: int) -> list[dict]:
        guild = self.get_guild(guild_id)
        if guild is None:
            return []
        options: list[dict] = []
        for channel in sorted(guild.text_channels, key=lambda item: (item.position, item.name.lower())):
            options.append({"id": channel.id, "name": f"#{channel.name}", "nsfw": bool(channel.is_nsfw())})
        return options

    def build_web_role_options(self, guild_id: int) -> list[dict]:
        guild = self.get_guild(guild_id)
        if guild is None:
            return []
        options: list[dict] = []
        for role in sorted(guild.roles, key=lambda item: item.position, reverse=True):
            if role.is_default():
                continue
            options.append({"id": role.id, "name": f"@{role.name}"})
        return options

    def build_web_member_options(self, guild_id: int) -> list[dict]:
        guild = self.get_guild(guild_id)
        if guild is None:
            return []
        bot_member = guild.me
        options: list[dict] = []
        for member in sorted(guild.members, key=lambda item: item.display_name.lower()):
            if member.bot:
                continue
            if member.id == guild.owner_id:
                continue
            if bot_member is not None and bot_member.top_role <= member.top_role:
                continue
            options.append(
                {
                    "id": member.id,
                    "name": member.display_name,
                    "username": str(member),
                }
            )
        return options

    def get_web_managed_guilds(self) -> list[dict]:
        managed = self.get_managed_guilds()
        primary_guild_id = GUILD_ID_CONFIGURED or (sorted(MANAGED_GUILD_IDS)[0] if MANAGED_GUILD_IDS else None)
        return [
            {
                "id": guild.id,
                "name": guild.name,
                "member_count": guild.member_count,
                "icon_url": str(guild.icon.url) if guild.icon else "",
                "is_primary": primary_guild_id == guild.id,
            }
            for guild in managed
        ]

    def get_web_discord_catalog(self, guild_id: int | None = None) -> dict:
        selected_guild_id = int(guild_id) if isinstance(guild_id, int) else GUILD_ID
        guild = self.get_guild(selected_guild_id)
        if guild is None:
            managed = self.get_managed_guilds()
            if managed:
                guild = managed[0]
                selected_guild_id = guild.id
            else:
                return {"ok": False, "error": "No managed guilds available."}
        if MANAGED_GUILD_IDS is not None and guild.id not in MANAGED_GUILD_IDS:
            return {"ok": False, "error": "Selected guild is not managed by this bot."}

        channels = self.build_web_channel_options(guild_id=selected_guild_id)
        roles = self.build_web_role_options(guild_id=selected_guild_id)
        members = self.build_web_member_options(guild_id=selected_guild_id)
        self.web_channel_options = channels
        self.web_role_options = roles
        if guild is None:
            return {"ok": False, "error": "Guild not available."}
        return {
            "ok": True,
            "guild": {"id": guild.id, "name": guild.name},
            "channels": channels,
            "roles": roles,
            "members": members,
            "members_intent_enabled": ENABLE_MEMBERS_INTENT,
        }

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        managed_ids = {guild.id for guild in self.get_managed_guilds()}
        if message.guild and message.guild.id in managed_ids:
            try:
                record_member_message_activity(message)
            except Exception:
                logger.exception(
                    "Failed to record member activity for message %s in guild %s",
                    getattr(message, "id", "unknown"),
                    message.guild.id,
                )
        if message.guild and message.guild.id in managed_ids and isinstance(message.author, discord.Member):
            await apply_moderation_filter(
                message,
                action_store=ACTION_STORE,
                log_action=log_action,
                record_action_safe=record_action_safe,
                truncate_log_text=truncate_log_text,
                logger=logger,
                bot_client=self,
            )
        if isinstance(message.author, discord.Member) and message.guild and message.guild.id in managed_ids:
            content = (message.content or "").strip()
            if content.startswith("!"):
                tag_key = normalize_tag(content.split()[0])
                if tag_key:
                    tag_mapping = ACTION_STORE.get_tag_responses(guild_id=message.guild.id)
                    response = tag_mapping.get(tag_key)
                    if response and can_use_command(message.author, "tag", guild_id=message.guild.id):
                        await message.channel.send(response)
        await self.process_commands(message)

    async def refresh_spicy_prompt_catalog(self, *, reason: str, actor: str = "system") -> None:
        if not SPICY_PROMPTS_ENABLED or not SPICY_PROMPTS_REPO_URL:
            return
        try:
            catalog = await asyncio.to_thread(fetch_spicy_prompt_catalog)
            status = ACTION_STORE.replace_spicy_prompt_catalog(catalog)
            await log_action(
                self,
                "Spicy Prompts Refresh",
                (
                    "Action: `spicy_prompts_refresh`\n"
                    f"Status: **Success**\nReason: {reason}\n"
                    f"Packs: {status.get('pack_count', 0)} | Prompts: {status.get('prompt_count', 0)}"
                ),
                discord.Color.orange(),
            )
            record_action_safe(
                action="spicy_prompts_refresh",
                status="success",
                moderator=actor,
                target="spicy-prompts",
                reason=truncate_log_text(f"{reason} refresh"),
                guild="",
            )
        except Exception as exc:
            ACTION_STORE.update_spicy_prompt_sync_failure(error=str(exc))
            await log_action(
                self,
                "Spicy Prompts Refresh",
                f"Action: `spicy_prompts_refresh`\nStatus: **Failed**\nReason: {reason}\nError: {exc}",
                discord.Color.red(),
            )
            record_action_safe(
                action="spicy_prompts_refresh",
                status="failed",
                moderator=actor,
                target="spicy-prompts",
                reason=truncate_log_text(f"{reason} refresh failed: {exc}"),
                guild="",
            )

    async def youtube_monitor_loop(self) -> None:
        await self.wait_until_ready()
        logger.info("Notification loop started. Tick interval: %ss", NOTIFICATION_LOOP_SECONDS)
        last_spicy_refresh_at: datetime | None = None
        if SPICY_PROMPTS_ENABLED and SPICY_PROMPTS_REPO_URL:
            if SPICY_PROMPTS_REFRESH_ON_BOOT:
                await self.refresh_spicy_prompt_catalog(reason="boot")
                last_spicy_refresh_at = datetime.now(UTC)
            else:
                status = ACTION_STORE.get_spicy_prompt_status()
                last_spicy_refresh_at = parse_db_timestamp(str(status.get("last_refresh_at", "")).strip())
        while not self.is_closed():
            try:
                if SPICY_PROMPTS_ENABLED and SPICY_PROMPTS_REPO_URL and SPICY_PROMPTS_REFRESH_INTERVAL_HOURS > 0:
                    refresh_interval = timedelta(hours=SPICY_PROMPTS_REFRESH_INTERVAL_HOURS)
                    now = datetime.now(UTC)
                    if last_spicy_refresh_at is None or now - last_spicy_refresh_at >= refresh_interval:
                        await self.refresh_spicy_prompt_catalog(reason="scheduled")
                        last_spicy_refresh_at = now
                if YOUTUBE_NOTIFY_ENABLED:
                    await self.poll_youtube_subscriptions()
                await self.poll_reddit_feeds()
                await self.poll_wordpress_feeds()
                await self.poll_linkedin_feeds()
                await self.poll_uptime_monitors()
                if LOG_RETENTION_DAYS > 0:
                    prune_log_directory(LOG_DIR, LOG_RETENTION_DAYS)
            except Exception as exc:
                logger.exception("Notification poll failed: %s", exc)
            await asyncio.sleep(NOTIFICATION_LOOP_SECONDS)

    async def poll_youtube_subscriptions(self) -> None:
        subscriptions = ACTION_STORE.list_youtube_subscriptions(enabled_only=True)
        if not subscriptions:
            return
        for subscription in subscriptions:
            await self._process_youtube_subscription(subscription)

    async def _process_youtube_subscription(self, subscription: dict) -> None:
        subscription_id = int(subscription.get("id", 0))
        channel_id = str(subscription.get("channel_id", "")).strip()
        source_url = str(subscription.get("source_url", "")).strip()
        target_channel_id = int(subscription.get("target_channel_id", 0))
        if subscription_id <= 0 or not channel_id or target_channel_id <= 0:
            return
        if not subscription_due(subscription.get("last_checked_at"), subscription.get("poll_interval_seconds")):
            return

        checked_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        include_uploads = bool(subscription.get("include_uploads", 1))
        include_community_posts = bool(subscription.get("include_community_posts", 0))
        if not include_uploads and not include_community_posts:
            ACTION_STORE.update_youtube_subscription_state(subscription_id, last_checked_at=checked_at)
            return

        notify_channel = await get_text_channel(self, target_channel_id)
        if notify_channel is None:
            logger.warning("Notify channel %s not found for YouTube subscription %s", target_channel_id, subscription_id)
            ACTION_STORE.update_youtube_subscription_state(subscription_id, last_checked_at=checked_at)
            return

        youtube_updates: dict[str, str] = {"last_checked_at": checked_at}
        if include_uploads:
            try:
                uploads = await asyncio.to_thread(fetch_recent_youtube_uploads, channel_id, 10)
            except RuntimeError as exc:
                logger.warning("Unable to fetch YouTube feed for %s: %s", channel_id, exc)
                uploads = []
            last_video_id = str(subscription.get("last_video_id", "")).strip()
            new_uploads: list[dict] = []
            for item in uploads:
                if item["video_id"] == last_video_id:
                    break
                new_uploads.append(item)
            for item in reversed(new_uploads):
                upload_kind = "short" if "/shorts/" in item["video_url"] else "upload"
                embed = discord.Embed(
                    title=f"New {upload_kind} from {item['channel_title']}",
                    description=f"[{item['video_title']}]({item['video_url']})",
                    color=discord.Color.red(),
                )
                embed.set_footer(text="YouTube Notification")
                await notify_channel.send(embed=embed)
                await log_action(
                    self,
                    "YouTube Notification",
                    (
                        f"Action: `youtube_notify`\nStatus: **Success**\nGuild: {notify_channel.guild.id}\n"
                        f"Target: {notify_channel.mention} ({notify_channel.id})\nReason: {item['channel_title']} - {item['video_title']}"
                    ),
                    discord.Color.red(),
                    guild_id=notify_channel.guild.id,
                )
                record_action_safe(
                    action="youtube_notify",
                    status="success",
                    moderator="system",
                    target=f"{notify_channel.name} ({notify_channel.id})",
                    reason=truncate_log_text(f"{item['channel_title']} - {item['video_title']}"),
                    guild=str(notify_channel.guild.id),
                )
            if uploads:
                youtube_updates.update(
                    {
                        "last_video_id": uploads[0]["video_id"],
                        "last_video_title": uploads[0]["video_title"],
                        "last_published_at": uploads[0]["published_at"],
                    }
                )

        if include_community_posts and source_url:
            try:
                community_posts = await asyncio.to_thread(fetch_recent_youtube_community_posts, source_url, 10)
            except RuntimeError as exc:
                logger.warning("Unable to fetch YouTube community page for %s: %s", source_url, exc)
                community_posts = []
            last_community_post_id = str(subscription.get("last_community_post_id", "")).strip()
            new_posts: list[dict] = []
            for item in community_posts:
                if item["post_id"] == last_community_post_id:
                    break
                new_posts.append(item)
            for item in reversed(new_posts):
                embed = discord.Embed(
                    title=f"New community post from {subscription.get('channel_title', 'YouTube Channel')}",
                    description=f"[{item['post_title']}]({item['post_url']})",
                    color=discord.Color.orange(),
                )
                embed.set_footer(text="YouTube Community Post")
                await notify_channel.send(embed=embed)
                await log_action(
                    self,
                    "YouTube Community Post",
                    (
                        f"Action: `youtube_community_post`\nStatus: **Success**\nGuild: {notify_channel.guild.id}\n"
                        f"Target: {notify_channel.mention} ({notify_channel.id})\nReason: {item['post_title']}"
                    ),
                    discord.Color.orange(),
                    guild_id=notify_channel.guild.id,
                )
                record_action_safe(
                    action="youtube_community_post",
                    status="success",
                    moderator="system",
                    target=f"{notify_channel.name} ({notify_channel.id})",
                    reason=truncate_log_text(item["post_title"]),
                    guild=str(notify_channel.guild.id),
                )
            if community_posts:
                youtube_updates.update(
                    {
                        "last_community_post_id": community_posts[0]["post_id"],
                        "last_community_post_title": community_posts[0]["post_title"],
                        "last_community_published_at": community_posts[0]["published_at"],
                    }
                )

        ACTION_STORE.update_youtube_subscription_state(subscription_id, **youtube_updates)

    async def poll_reddit_feeds(self) -> None:
        feeds = ACTION_STORE.list_reddit_feeds(enabled_only=True)
        if not feeds:
            return
        for feed in feeds:
            await self._process_reddit_feed(feed)

    async def _process_reddit_feed(self, feed: dict) -> None:
        feed_id = int(feed.get("id", 0))
        subreddit_name = str(feed.get("subreddit_name", "")).strip()
        target_channel_id = int(feed.get("target_channel_id", 0))
        if feed_id <= 0 or not subreddit_name or target_channel_id <= 0:
            return
        if not subscription_due(feed.get("last_checked_at"), feed.get("poll_interval_seconds")):
            return
        checked_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        notify_channel = await get_text_channel(self, target_channel_id)
        if notify_channel is None:
            logger.warning("Notify channel %s not found for Reddit feed %s", target_channel_id, feed_id)
            ACTION_STORE.update_reddit_feed_state(feed_id, last_checked_at=checked_at)
            return
        try:
            posts = await asyncio.to_thread(fetch_recent_reddit_posts, subreddit_name, 10)
        except RuntimeError as exc:
            logger.warning("Unable to fetch Reddit feed for r/%s: %s", subreddit_name, exc)
            ACTION_STORE.update_reddit_feed_state(feed_id, last_checked_at=checked_at)
            return
        last_post_id = str(feed.get("last_post_id", "")).strip()
        new_posts: list[dict] = []
        for item in posts:
            if item["post_id"] == last_post_id:
                break
            new_posts.append(item)
        for item in reversed(new_posts):
            embed = discord.Embed(
                title=f"New Reddit post in r/{item['subreddit_name']}",
                description=f"[{item['post_title']}]({item['post_url']})",
                color=discord.Color.orange(),
            )
            embed.set_footer(text="Reddit Feed")
            await notify_channel.send(embed=embed)
            await log_action(
                self,
                "Reddit Feed Notification",
                (
                    f"Action: `reddit_feed_notify`\nStatus: **Success**\nGuild: {notify_channel.guild.id}\n"
                    f"Target: {notify_channel.mention} ({notify_channel.id})\nReason: r/{item['subreddit_name']} - {item['post_title']}"
                ),
                discord.Color.orange(),
                guild_id=notify_channel.guild.id,
            )
            record_action_safe(
                action="reddit_feed_notify",
                status="success",
                moderator="system",
                target=f"{notify_channel.name} ({notify_channel.id})",
                reason=truncate_log_text(f"r/{item['subreddit_name']} - {item['post_title']}"),
                guild=str(notify_channel.guild.id),
            )
        latest = posts[0] if posts else None
        ACTION_STORE.update_reddit_feed_state(
            feed_id,
            last_checked_at=checked_at,
            last_post_id=latest["post_id"] if latest else None,
            last_post_title=latest["post_title"] if latest else None,
            last_post_url=latest["post_url"] if latest else None,
            last_published_at=latest["published_at"] if latest else None,
        )

    async def poll_wordpress_feeds(self) -> None:
        feeds = ACTION_STORE.list_wordpress_feeds(enabled_only=True)
        if not feeds:
            return
        for feed in feeds:
            await self._process_wordpress_feed(feed)

    async def _process_wordpress_feed(self, feed: dict) -> None:
        feed_id = int(feed.get("id", 0))
        site_url = str(feed.get("site_url", "")).strip()
        target_channel_id = int(feed.get("target_channel_id", 0))
        if feed_id <= 0 or not site_url or target_channel_id <= 0:
            return
        if not subscription_due(feed.get("last_checked_at"), feed.get("poll_interval_seconds")):
            return
        checked_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        notify_channel = await get_text_channel(self, target_channel_id)
        if notify_channel is None:
            logger.warning("Notify channel %s not found for WordPress feed %s", target_channel_id, feed_id)
            ACTION_STORE.update_wordpress_feed_state(feed_id, last_checked_at=checked_at)
            return
        try:
            payload = await asyncio.to_thread(fetch_recent_wordpress_posts, site_url, 10)
        except RuntimeError as exc:
            logger.warning("Unable to fetch WordPress feed for %s: %s", site_url, exc)
            ACTION_STORE.update_wordpress_feed_state(feed_id, last_checked_at=checked_at)
            return
        posts = payload.get("posts", []) if isinstance(payload, dict) else []
        last_post_id = str(feed.get("last_post_id", "")).strip()
        new_posts: list[dict] = []
        for item in posts:
            if str(item.get("post_id", "")).strip() == last_post_id:
                break
            new_posts.append(item)
        site_title = str(payload.get("site_title", "")).strip() or str(feed.get("site_title", "WordPress Site")).strip()
        for item in reversed(new_posts):
            post_title = str(item.get("post_title", "Untitled Post")).strip()
            post_url = str(item.get("post_url", site_url)).strip() or site_url
            embed = discord.Embed(
                title=f"New WordPress post from {site_title}",
                description=f"[{post_title}]({post_url})",
                color=discord.Color.blue(),
            )
            embed.set_footer(text="WordPress Feed")
            await notify_channel.send(embed=embed)
            await log_action(
                self,
                "WordPress Feed Notification",
                (
                    f"Action: `wordpress_feed_notify`\nStatus: **Success**\nGuild: {notify_channel.guild.id}\n"
                    f"Target: {notify_channel.mention} ({notify_channel.id})\nReason: {site_title} - {post_title}"
                ),
                discord.Color.blue(),
                guild_id=notify_channel.guild.id,
            )
            record_action_safe(
                action="wordpress_feed_notify",
                status="success",
                moderator="system",
                target=f"{notify_channel.name} ({notify_channel.id})",
                reason=truncate_log_text(f"{site_title} - {post_title}"),
                guild=str(notify_channel.guild.id),
            )
        latest = posts[0] if posts else None
        ACTION_STORE.update_wordpress_feed_state(
            feed_id,
            last_checked_at=checked_at,
            last_post_id=str(latest.get("post_id", "")) if latest else None,
            last_post_title=str(latest.get("post_title", "")) if latest else None,
            last_post_url=str(latest.get("post_url", "")) if latest else None,
            last_published_at=str(latest.get("published_at", "")) if latest else None,
        )

    async def poll_linkedin_feeds(self) -> None:
        feeds = ACTION_STORE.list_linkedin_feeds(enabled_only=True)
        if not feeds:
            return
        for feed in feeds:
            await self._process_linkedin_feed(feed)

    async def _process_linkedin_feed(self, feed: dict) -> None:
        feed_id = int(feed.get("id", 0))
        profile_url = str(feed.get("profile_url", "")).strip()
        target_channel_id = int(feed.get("target_channel_id", 0))
        if feed_id <= 0 or not profile_url or target_channel_id <= 0:
            return
        if not subscription_due(feed.get("last_checked_at"), feed.get("poll_interval_seconds")):
            return
        checked_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        notify_channel = await get_text_channel(self, target_channel_id)
        if notify_channel is None:
            logger.warning("Notify channel %s not found for LinkedIn feed %s", target_channel_id, feed_id)
            ACTION_STORE.update_linkedin_feed_state(feed_id, last_checked_at=checked_at)
            return
        try:
            payload = await asyncio.to_thread(fetch_recent_linkedin_posts, profile_url, 10)
        except RuntimeError as exc:
            logger.warning("Unable to fetch LinkedIn feed for %s: %s", profile_url, exc)
            ACTION_STORE.update_linkedin_feed_state(feed_id, last_checked_at=checked_at)
            return
        posts = payload.get("posts", []) if isinstance(payload, dict) else []
        last_post_id = str(feed.get("last_post_id", "")).strip()
        new_posts: list[dict] = []
        for item in posts:
            if str(item.get("post_id", "")).strip() == last_post_id:
                break
            new_posts.append(item)
        profile_label = str(payload.get("profile_label", "")).strip() or str(feed.get("profile_label", "LinkedIn Profile")).strip()
        for item in reversed(new_posts):
            post_title = str(item.get("post_title", "New LinkedIn post")).strip()
            post_url = str(item.get("post_url", profile_url)).strip() or profile_url
            embed = discord.Embed(
                title=f"New LinkedIn post from {profile_label}",
                description=f"[{post_title}]({post_url})",
                color=discord.Color.dark_blue(),
            )
            embed.set_footer(text="LinkedIn Feed")
            await notify_channel.send(embed=embed)
            await log_action(
                self,
                "LinkedIn Feed Notification",
                (
                    f"Action: `linkedin_feed_notify`\nStatus: **Success**\nGuild: {notify_channel.guild.id}\n"
                    f"Target: {notify_channel.mention} ({notify_channel.id})\nReason: {profile_label} - {post_title}"
                ),
                discord.Color.dark_blue(),
                guild_id=notify_channel.guild.id,
            )
            record_action_safe(
                action="linkedin_feed_notify",
                status="success",
                moderator="system",
                target=f"{notify_channel.name} ({notify_channel.id})",
                reason=truncate_log_text(f"{profile_label} - {post_title}"),
                guild=str(notify_channel.guild.id),
            )
        latest = posts[0] if posts else None
        ACTION_STORE.update_linkedin_feed_state(
            feed_id,
            last_checked_at=checked_at,
            last_post_id=str(latest.get("post_id", "")) if latest else None,
            last_post_title=str(latest.get("post_title", "")) if latest else None,
            last_post_url=str(latest.get("post_url", "")) if latest else None,
            last_published_at=str(latest.get("published_at", "")) if latest else None,
        )

    async def poll_uptime_monitors(self) -> None:
        monitors = ACTION_STORE.list_uptime_monitors(enabled_only=True)
        if not monitors:
            return
        for monitor in monitors:
            await self._process_uptime_monitor(monitor)

    async def _process_uptime_monitor(self, monitor: dict) -> None:
        monitor_id = int(monitor.get("id", 0))
        guild_id = int(monitor.get("guild_id", 0))
        name = str(monitor.get("name", "")).strip() or "Monitor"
        monitor_type = str(monitor.get("monitor_type", "")).strip().lower()
        target = str(monitor.get("target", "")).strip()
        if monitor_id <= 0 or guild_id <= 0 or not target:
            return
        if not monitor_due(monitor.get("last_checked_at"), monitor.get("interval_seconds")):
            return

        timeout_seconds = normalize_monitor_timeout_seconds(monitor.get("timeout_seconds"))
        checked_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        previous_status = str(monitor.get("last_status") or "unknown").lower()
        status = "down"
        latency_ms: int | None = None
        detail = ""
        error_text: str | None = None
        try:
            if monitor_type == "http":
                ok, latency_ms, detail = await asyncio.to_thread(check_http_endpoint, target, timeout_seconds)
            elif monitor_type == "tcp":
                host, port = parse_tcp_target(target)
                ok, latency_ms, detail = await asyncio.to_thread(check_tcp_endpoint, host, port, timeout_seconds)
            elif monitor_type == "statuspage":
                ok, latency_ms, detail = await asyncio.to_thread(check_statuspage_endpoint, target, timeout_seconds)
            else:
                raise ValueError("Unsupported monitor type.")
            status = "up" if ok else "down"
            if not ok:
                error_text = detail
        except Exception as exc:
            status = "down"
            error_text = str(exc)
            detail = error_text or "Check failed"

        status_changed = previous_status in {"up", "down"} and status != previous_status
        change_at = checked_at if status_changed else None
        ACTION_STORE.update_uptime_monitor_state(
            monitor_id,
            last_status=status,
            last_checked_at=checked_at,
            last_change_at=change_at,
            last_error=error_text,
            last_latency_ms=latency_ms,
        )

        if status_changed:
            await self._notify_uptime_monitor_change(
                guild_id=guild_id,
                name=name,
                target=target,
                monitor_type=monitor_type,
                status=status,
                detail=detail,
                latency_ms=latency_ms,
                alert_channel_id=int(monitor.get("alert_channel_id", 0) or 0),
            )

    async def _notify_uptime_monitor_change(
        self,
        *,
        guild_id: int,
        name: str,
        target: str,
        monitor_type: str,
        status: str,
        detail: str,
        latency_ms: int | None,
        alert_channel_id: int,
    ) -> None:
        guild_settings = ACTION_STORE.get_guild_settings(guild_id=guild_id)
        resolved_channel_id = alert_channel_id or int(guild_settings.get("uptime_alert_channel_id", 0) or 0)
        if resolved_channel_id <= 0:
            resolved_channel_id = resolve_bot_log_channel_id(guild_id=guild_id)
        channel = await get_text_channel(self, resolved_channel_id)
        if channel is None or channel.guild.id != guild_id:
            logger.warning("Uptime monitor alert channel %s not found for guild %s", resolved_channel_id, guild_id)
            return

        is_up = status == "up"
        title = "Service Online" if is_up else "Service Offline"
        color = discord.Color.green() if is_up else discord.Color.red()
        latency_text = f"{latency_ms} ms" if isinstance(latency_ms, int) else "-"
        description = (
            f"Monitor: **{name}**\n"
            f"Type: `{monitor_type}`\n"
            f"Target: `{target}`\n"
            f"Status: **{status.upper()}**\n"
            f"Detail: {detail}\n"
            f"Latency: {latency_text}"
        )
        embed = discord.Embed(title=title, description=description, color=color)
        await channel.send(embed=embed)
        record_action_safe(
            action="uptime_monitor",
            status="success" if is_up else "failed",
            moderator="system",
            target=name,
            reason=truncate_log_text(f"{status} - {detail}"),
            guild=str(guild_id),
        )


bot = ModerationBot()
birthday_group = app_commands.Group(name="birthday", description="Birthday commands")
dnd_group = app_commands.Group(name="dnd", description="D&D 20th helper commands")


def record_action_safe(
    action: str,
    status: str,
    moderator: str = "",
    target: str = "",
    reason: str = "",
    guild: str = "",
) -> None:
    try:
        ACTION_STORE.record(
            action=action,
            status=status,
            moderator=moderator,
            target=target,
            reason=reason,
            guild=guild,
        )
    except Exception as exc:
        logger.exception("Failed to persist action log: %s", exc)


configure_web_moderation(bot=bot, logger=logger, record_action_safe=record_action_safe)


def parse_stored_datetime(raw_value: object) -> datetime | None:
    candidate = str(raw_value or "").strip()
    if not candidate:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S"):
        try:
            parsed = datetime.strptime(candidate, fmt)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        except ValueError:
            continue
    return None


def subscription_due(last_checked_at: object, interval_seconds: object) -> bool:
    last_checked = parse_stored_datetime(last_checked_at)
    if last_checked is None:
        return True
    interval = normalize_feed_interval_seconds(interval_seconds)
    return datetime.now(UTC) >= (last_checked + timedelta(seconds=interval))


def monitor_due(last_checked_at: object, interval_seconds: object) -> bool:
    last_checked = parse_stored_datetime(last_checked_at)
    if last_checked is None:
        return True
    interval = normalize_monitor_interval_seconds(interval_seconds)
    return datetime.now(UTC) >= (last_checked + timedelta(seconds=interval))


async def reply_ephemeral(interaction: discord.Interaction, message: str) -> None:
    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=COMMAND_RESPONSES_EPHEMERAL)
        else:
            await interaction.response.send_message(message, ephemeral=COMMAND_RESPONSES_EPHEMERAL)
    except discord.NotFound:
        try:
            await interaction.followup.send(message, ephemeral=COMMAND_RESPONSES_EPHEMERAL)
        except discord.HTTPException:
            logger.warning("Unable to respond to interaction; token expired.")


async def get_text_channel(client: commands.Bot, channel_id: int) -> discord.TextChannel | None:
    channel = client.get_channel(channel_id)
    if isinstance(channel, discord.TextChannel):
        return channel
    try:
        fetched = await client.fetch_channel(channel_id)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        return None
    if isinstance(fetched, discord.TextChannel):
        return fetched
    return None


def channel_supports_spicy_prompts(channel: discord.abc.GuildChannel | None) -> bool:
    if not isinstance(channel, discord.TextChannel):
        return False
    try:
        return bool(channel.is_nsfw())
    except AttributeError:
        return False


def resolve_bot_log_channel_id(guild_id: int | None = None) -> int:
    if guild_id is not None:
        try:
            guild_settings = ACTION_STORE.get_guild_settings(guild_id=guild_id)
            configured = guild_settings.get("bot_log_channel_id")
            if isinstance(configured, int) and configured > 0:
                return configured
        except Exception as exc:
            logger.warning("Unable to load guild settings for %s: %s", guild_id, exc)
    return BOT_LOG_CHANNEL


def warn_invalid_bot_log_channel(guild_id: int | None, channel_id: int, reason: str) -> None:
    if channel_id <= 0:
        return
    cache_key = (guild_id, channel_id)
    INVALID_BOT_LOG_CHANNEL_CACHE.add(cache_key)
    if cache_key in WARNED_INVALID_BOT_LOG_CHANNEL_CACHE:
        return
    logger.warning(
        "Bot log channel %s is unusable for guild %s: %s. Configure a valid per-guild bot log channel in /admin/guild-settings or update Bot_Log_Channel.",
        channel_id,
        guild_id if guild_id is not None else "default",
        reason,
    )
    WARNED_INVALID_BOT_LOG_CHANNEL_CACHE.add(cache_key)


def bot_can_send_log_messages(client: commands.Bot, channel: discord.TextChannel) -> bool:
    bot_user = getattr(client, "user", None)
    guild = getattr(channel, "guild", None)
    if bot_user is None or guild is None:
        return True
    member = guild.get_member(bot_user.id)
    if member is None:
        member = getattr(guild, "me", None)
    if member is None:
        return True
    permissions = channel.permissions_for(member)
    return permissions.view_channel and permissions.send_messages and permissions.embed_links


async def get_log_channel(client: commands.Bot, guild_id: int | None = None) -> discord.TextChannel | None:
    channel_id = resolve_bot_log_channel_id(guild_id=guild_id)
    if channel_id <= 0:
        return None
    channel = await get_text_channel(client, channel_id)
    if isinstance(channel, discord.TextChannel):
        if guild_id is not None and channel.guild.id != guild_id:
            warn_invalid_bot_log_channel(
                guild_id,
                channel_id,
                f"channel belongs to guild {channel.guild.id}, not the selected guild",
            )
            return None
        if not bot_can_send_log_messages(client, channel):
            warn_invalid_bot_log_channel(guild_id, channel_id, "missing View Channel, Send Messages, or Embed Links permission")
            return None
        INVALID_BOT_LOG_CHANNEL_CACHE.discard((guild_id, channel_id))
        WARNED_INVALID_BOT_LOG_CHANNEL_CACHE.discard((guild_id, channel_id))
        return channel
    warn_invalid_bot_log_channel(guild_id, channel_id, "channel was not found, accessible, or a text channel")
    return None


async def log_action(client: commands.Bot, title: str, description: str, color: discord.Color, guild_id: int | None = None) -> None:
    try:
        bot_channel_logger.info("%s | %s", title, description.replace("\n", " | "))
        channel = await get_log_channel(client, guild_id=guild_id)
        if channel is None:
            return
        embed = discord.Embed(title=title, description=description, color=color)
        for attempt in range(1, BOT_LOG_SEND_MAX_ATTEMPTS + 1):
            try:
                await channel.send(embed=embed)
                return
            except discord.Forbidden as exc:
                warn_invalid_bot_log_channel(guild_id, channel.id, f"Discord denied access while sending embeds ({exc})")
                return
            except discord.DiscordServerError as exc:
                if attempt >= BOT_LOG_SEND_MAX_ATTEMPTS:
                    logger.warning(
                        "Failed to write log action to channel %s for guild %s after %s attempt(s): %s",
                        channel.id,
                        guild_id if guild_id is not None else "default",
                        attempt,
                        exc,
                    )
                    return
                await asyncio.sleep(BOT_LOG_SEND_RETRY_DELAY_SECONDS * attempt)
            except discord.HTTPException as exc:
                status = int(getattr(exc, "status", 0) or 0)
                code = int(getattr(exc, "code", 0) or 0)
                is_server_error = status >= 500
                if is_server_error and attempt < BOT_LOG_SEND_MAX_ATTEMPTS:
                    await asyncio.sleep(BOT_LOG_SEND_RETRY_DELAY_SECONDS * attempt)
                    continue
                if status == 403 or code in {50001, 50013, 10003}:
                    warn_invalid_bot_log_channel(
                        guild_id,
                        channel.id,
                        f"Discord API rejected the channel (status={status or 'unknown'}, code={code or 'unknown'})",
                    )
                    return
                logger.warning(
                    "Failed to write log action to channel %s for guild %s (status=%s): %s",
                    channel.id,
                    guild_id if guild_id is not None else "default",
                    status or "unknown",
                    exc,
                )
                return
    except Exception as exc:
        logger.exception("Failed to write log action: %s", exc)


async def log_interaction(
    interaction: discord.Interaction,
    action: str,
    target: discord.abc.User | None = None,
    reason: str | None = None,
    success: bool = True,
) -> None:
    actor_mention = interaction.user.mention if interaction.user else "Unknown"
    actor_label = f"{interaction.user} ({interaction.user.id})" if interaction.user else "Unknown"
    guild_name = interaction.guild.name if interaction.guild else "Unknown Guild"
    guild_identifier = str(interaction.guild.id) if interaction.guild else "dm"
    status = "Success" if success else "Failed"
    status_db = "success" if success else "failed"
    target_text = f"\nTarget: {target.mention} ({target.id})" if target else ""
    target_db = f"{target} ({target.id})" if target else ""
    reason_text = f"\nReason: {reason}" if reason else ""
    description = f"Action: `{action}`\nStatus: **{status}**\nModerator: {actor_mention}\nGuild: {guild_name}{target_text}{reason_text}"
    await log_action(
        bot,
        f"Moderation Action - {action}",
        description,
        discord.Color.blurple() if success else discord.Color.red(),
        guild_id=interaction.guild.id if interaction.guild else None,
    )
    record_action_safe(
        action=action,
        status=status_db,
        moderator=actor_label,
        target=target_db,
        reason=reason or "",
        guild=guild_identifier,
    )


async def ensure_interaction_command_access(interaction: discord.Interaction, command_key: str) -> bool:
    guild_id = interaction.guild.id if interaction.guild else GUILD_ID
    if can_use_command(interaction.user, command_key, guild_id=guild_id):
        return True
    message = build_command_permission_denied_message(command_key, guild_id=guild_id, guild=interaction.guild)
    await reply_ephemeral(interaction, message)
    await log_interaction(interaction, action="permission_denied", reason=f"{command_key}: {message}", success=False)
    return False


@bot.tree.command(name="ping", description="Check if the bot is online.")
async def ping(interaction: discord.Interaction) -> None:
    if not await ensure_interaction_command_access(interaction, "ping"):
        return
    await interaction.response.send_message(
        "Wicked Yoda's Little Helper is online.",
        ephemeral=COMMAND_RESPONSES_EPHEMERAL,
    )
    await log_interaction(interaction, action="ping", success=True)


@bot.tree.command(name="sayhi", description="Introduce the bot in the channel.")
async def sayhi(interaction: discord.Interaction) -> None:
    if not await ensure_interaction_command_access(interaction, "sayhi"):
        return
    intro = "Hi everyone, I am Wicked Yoda's Little Helper.\nI can help with moderation, URL short links, and uptime checks."
    await interaction.response.send_message(intro)
    await log_interaction(interaction, action="sayhi", reason="Posted channel introduction", success=True)


@bot.tree.command(name="happy", description="Post a random puppy picture.")
async def happy(interaction: discord.Interaction) -> None:
    if not await ensure_interaction_command_access(interaction, "happy"):
        return
    await interaction.response.defer(ephemeral=COMMAND_RESPONSES_EPHEMERAL)
    try:
        image_url = await asyncio.to_thread(fetch_random_puppy_image_url)
        embed = discord.Embed(
            title="Puppy Time",
            description="Here is a random puppy picture.",
            color=discord.Color.green(),
        )
        embed.set_image(url=image_url)
        await interaction.followup.send(embed=embed, ephemeral=COMMAND_RESPONSES_EPHEMERAL)
        await log_interaction(
            interaction,
            action="happy",
            reason=truncate_log_text(image_url),
            success=True,
        )
    except RuntimeError as exc:
        await interaction.followup.send(
            f"Failed to fetch puppy picture: {exc}",
            ephemeral=COMMAND_RESPONSES_EPHEMERAL,
        )
        await log_interaction(
            interaction,
            action="happy",
            reason=truncate_log_text(str(exc)),
            success=False,
        )


@bot.tree.command(name="cat", description="Post a random cat picture.")
async def cat(interaction: discord.Interaction) -> None:
    if not await ensure_interaction_command_access(interaction, "cat"):
        return
    await interaction.response.defer(ephemeral=COMMAND_RESPONSES_EPHEMERAL)
    try:
        image_url = await asyncio.to_thread(fetch_random_cat_image_url)
        embed = discord.Embed(title="Cat Break", description="Here is a random cat picture.", color=discord.Color.gold())
        embed.set_image(url=image_url)
        await interaction.followup.send(embed=embed, ephemeral=COMMAND_RESPONSES_EPHEMERAL)
        await log_interaction(interaction, action="cat", reason=truncate_log_text(image_url), success=True)
    except RuntimeError as exc:
        await interaction.followup.send(f"Failed to fetch cat picture: {exc}", ephemeral=COMMAND_RESPONSES_EPHEMERAL)
        await log_interaction(interaction, action="cat", reason=truncate_log_text(str(exc)), success=False)


@bot.tree.command(name="meme", description="Post a random meme.")
async def meme(interaction: discord.Interaction) -> None:
    if not await ensure_interaction_command_access(interaction, "meme"):
        return
    await interaction.response.defer(ephemeral=COMMAND_RESPONSES_EPHEMERAL)
    try:
        meme_payload = await asyncio.to_thread(fetch_random_meme)
        embed = discord.Embed(
            title=meme_payload["title"],
            description=f"Source: r/{meme_payload['subreddit']}" if meme_payload["subreddit"] else "Random meme",
            color=discord.Color.orange(),
            url=meme_payload["post_url"] or None,
        )
        embed.set_image(url=meme_payload["image_url"])
        await interaction.followup.send(embed=embed, ephemeral=COMMAND_RESPONSES_EPHEMERAL)
        await log_interaction(
            interaction,
            action="meme",
            reason=truncate_log_text(f"{meme_payload['subreddit']} - {meme_payload['title']}"),
            success=True,
        )
    except RuntimeError as exc:
        await interaction.followup.send(f"Failed to fetch meme: {exc}", ephemeral=COMMAND_RESPONSES_EPHEMERAL)
        await log_interaction(interaction, action="meme", reason=truncate_log_text(str(exc)), success=False)


@bot.tree.command(name="dadjoke", description="Get a random dad joke.")
async def dadjoke(interaction: discord.Interaction) -> None:
    if not await ensure_interaction_command_access(interaction, "dadjoke"):
        return
    await interaction.response.defer(ephemeral=COMMAND_RESPONSES_EPHEMERAL)
    try:
        joke = await asyncio.to_thread(fetch_dad_joke)
        await interaction.followup.send(joke, ephemeral=COMMAND_RESPONSES_EPHEMERAL)
        await log_interaction(interaction, action="dadjoke", reason=truncate_log_text(joke), success=True)
    except RuntimeError as exc:
        await interaction.followup.send(f"Failed to fetch a dad joke: {exc}", ephemeral=COMMAND_RESPONSES_EPHEMERAL)
        await log_interaction(interaction, action="dadjoke", reason=truncate_log_text(str(exc)), success=False)


@bot.tree.command(name="eightball", description="Ask the magic eight-ball a question.")
@app_commands.describe(question="Question to ask the magic eight-ball")
async def eightball(interaction: discord.Interaction, question: str) -> None:
    if not await ensure_interaction_command_access(interaction, "eightball"):
        return
    cleaned = truncate_log_text(question.strip(), max_length=160)
    if not cleaned:
        await reply_ephemeral(interaction, "Ask a real question first.")
        await log_interaction(interaction, action="eightball", reason="empty question", success=False)
        return
    answer = secure_choice(EIGHTBALL_RESPONSES)
    await interaction.response.send_message(
        f"Question: {cleaned}\nAnswer: **{answer}**",
        ephemeral=COMMAND_RESPONSES_EPHEMERAL,
    )
    await log_interaction(interaction, action="eightball", reason=truncate_log_text(f"{cleaned} -> {answer}"), success=True)


@bot.tree.command(name="coinflip", description="Flip a coin.")
async def coinflip(interaction: discord.Interaction) -> None:
    if not await ensure_interaction_command_access(interaction, "coinflip"):
        return
    result = secure_choice(["Heads", "Tails"])
    await interaction.response.send_message(f"The coin says: **{result}**", ephemeral=COMMAND_RESPONSES_EPHEMERAL)
    await log_interaction(interaction, action="coinflip", reason=result.lower(), success=True)


@bot.tree.command(name="roll", description="Roll TTRPG dice with common RPG presets.")
@app_commands.describe(
    dice_type="Dice style / RPG preset.",
    count="Number of dice to roll.",
    modifier="Numeric modifier, for example +2 or -1.",
)
@app_commands.choices(dice_type=DICE_CHOICES)
async def roll(
    interaction: discord.Interaction,
    dice_type: str = "d20",
    count: int = 1,
    modifier: int = 0,
) -> None:
    if not await ensure_interaction_command_access(interaction, "roll"):
        return
    preset = str(dice_type or "d20").strip().lower()
    if preset == "d00":
        preset = "d100"
    try:
        result = execute_roll_expression(f"{count}{preset}{modifier:+d}")
    except ValueError as exc:
        await reply_ephemeral(interaction, str(exc))
        await log_interaction(interaction, action="roll", reason=truncate_log_text(str(exc)), success=False)
        return
    preset_meaning = DICE_MEANING.get("d00" if preset == "d100" and result["sides"] == 100 else preset, "")
    rolls_text = ", ".join(str(value) for value in result["rolls"])
    result_expression = str(result["expression"])
    display_preset = "d00 / percentile" if str(result_expression).startswith("1d100") else f"{result['count']}d{result['sides']}"
    if result["modifier"]:
        display_preset += f" {result['modifier']:+d}"
    parts = [
        f"Preset: `{display_preset}`",
        f"Rolls: [{rolls_text}]",
        f"Subtotal: {result['subtotal']}",
    ]
    if result["modifier"]:
        parts.append(f"Modifier: {result['modifier']:+d}")
    parts.append(f"Total: **{result['total']}**")
    if preset_meaning:
        parts.append(f"Used for: {preset_meaning}")
    await interaction.response.send_message("\n".join(parts), ephemeral=COMMAND_RESPONSES_EPHEMERAL)
    await log_interaction(interaction, action="roll", reason=truncate_log_text(f"{display_preset}={result['total']}"), success=True)


@bot.tree.command(name="choose", description="Choose between multiple options.")
@app_commands.describe(options="Comma-separated, pipe-separated, or line-separated options")
async def choose(interaction: discord.Interaction, options: str) -> None:
    if not await ensure_interaction_command_access(interaction, "choose"):
        return
    parsed_options = split_option_values(options)
    if len(parsed_options) < 2:
        await reply_ephemeral(interaction, "Provide at least two options separated by commas, pipes, or new lines.")
        await log_interaction(interaction, action="choose", reason="not enough options", success=False)
        return
    selected = secure_choice(parsed_options)
    await interaction.response.send_message(f"I choose: **{selected}**", ephemeral=COMMAND_RESPONSES_EPHEMERAL)
    await log_interaction(interaction, action="choose", reason=truncate_log_text(selected), success=True)


@bot.tree.command(name="roastme", description="Get a playful roast.")
@app_commands.describe(target="Optional member to roast instead of yourself")
async def roastme(interaction: discord.Interaction, target: discord.Member | None = None) -> None:
    if not await ensure_interaction_command_access(interaction, "roastme"):
        return
    selected_target = target or interaction.user
    line = secure_choice(PLAYFUL_ROASTS)
    await interaction.response.send_message(f"{selected_target.mention}: {line}", ephemeral=COMMAND_RESPONSES_EPHEMERAL)
    await log_interaction(interaction, action="roastme", target=selected_target, reason=truncate_log_text(line), success=True)


@bot.tree.command(name="compliment", description="Send a friendly compliment.")
@app_commands.describe(target="Optional member to compliment instead of yourself")
async def compliment(interaction: discord.Interaction, target: discord.Member | None = None) -> None:
    if not await ensure_interaction_command_access(interaction, "compliment"):
        return
    selected_target = target or interaction.user
    line = secure_choice(COMPLIMENTS)
    await interaction.response.send_message(f"{selected_target.mention}: {line}", ephemeral=COMMAND_RESPONSES_EPHEMERAL)
    await log_interaction(interaction, action="compliment", target=selected_target, reason=truncate_log_text(line), success=True)


@bot.tree.command(name="wisdom", description="Receive a Yoda-style bit of wisdom.")
async def wisdom(interaction: discord.Interaction) -> None:
    if not await ensure_interaction_command_access(interaction, "wisdom"):
        return
    line = secure_choice(YODA_WISDOM_LINES)
    await interaction.response.send_message(line, ephemeral=COMMAND_RESPONSES_EPHEMERAL)
    await log_interaction(interaction, action="wisdom", reason=truncate_log_text(line), success=True)


@bot.tree.command(name="gif", description="Post a reaction GIF.")
@app_commands.describe(theme="Reaction theme")
@app_commands.choices(
    theme=[
        app_commands.Choice(name="Random", value="random"),
        app_commands.Choice(name="Celebrate", value="celebrate"),
        app_commands.Choice(name="Laugh", value="laugh"),
        app_commands.Choice(name="Hype", value="hype"),
        app_commands.Choice(name="Cute", value="cute"),
    ]
)
async def gif(interaction: discord.Interaction, theme: app_commands.Choice[str] | None = None) -> None:
    if not await ensure_interaction_command_access(interaction, "gif"):
        return
    selected = choose_random_gif(theme.value if theme else "random")
    embed = discord.Embed(title=selected["title"], description=f"Theme: {selected['theme']}", color=discord.Color.purple())
    embed.set_image(url=selected["url"])
    await interaction.response.send_message(embed=embed, ephemeral=COMMAND_RESPONSES_EPHEMERAL)
    await log_interaction(interaction, action="gif", reason=selected["theme"], success=True)


@bot.tree.command(name="poll", description="Create a quick poll in the current channel.")
@app_commands.describe(question="Poll question", options="Two to ten options separated by commas or pipes")
async def poll(interaction: discord.Interaction, question: str, options: str) -> None:
    if not await ensure_interaction_command_access(interaction, "poll"):
        return
    parsed_options = split_option_values(options, max_options=10)
    if len(parsed_options) < 2:
        await reply_ephemeral(interaction, "A poll needs at least two options.")
        await log_interaction(interaction, action="poll", reason="not enough options", success=False)
        return
    lines = [f"**{truncate_log_text(question.strip(), max_length=200) or 'Quick Poll'}**", ""]
    for index, option in enumerate(parsed_options):
        lines.append(f"{NUMBER_EMOJIS[index]} {option}")
    await interaction.response.send_message("\n".join(lines))
    try:
        original = await interaction.original_response()
        for index in range(len(parsed_options)):
            await original.add_reaction(NUMBER_EMOJIS[index])
    except Exception:
        logger.debug("Unable to add poll reactions for interaction %s", getattr(interaction, "id", "unknown"))
    await log_interaction(interaction, action="poll", reason=truncate_log_text(question), success=True)


@bot.tree.command(name="questionoftheday", description="Post a random question of the day.")
async def questionoftheday(interaction: discord.Interaction) -> None:
    if not await ensure_interaction_command_access(interaction, "questionoftheday"):
        return
    prompt = secure_choice(QUESTION_OF_THE_DAY_PROMPTS)
    await interaction.response.send_message(f"Question of the Day:\n**{prompt}**")
    await log_interaction(interaction, action="questionoftheday", reason=truncate_log_text(prompt), success=True)


@bot.tree.command(name="spicy", description="Post a random spicy prompt in the configured 18+ channel.")
@app_commands.describe(tag="Optional category tag, or 'help' to list categories")
async def spicy(interaction: discord.Interaction, tag: str | None = None) -> None:
    if not await ensure_interaction_command_access(interaction, "spicy"):
        return
    if interaction.guild is None or interaction.channel is None:
        await reply_ephemeral(interaction, "This command can only be used in a server.")
        await log_interaction(interaction, action="spicy", reason="no guild context", success=False)
        return
    if not SPICY_PROMPTS_ENABLED:
        await reply_ephemeral(interaction, "Spicy Prompts is disabled.")
        await log_interaction(interaction, action="spicy", reason="feature disabled", success=False)
        return

    lock = get_spicy_prompt_channel_lock(interaction.guild.id)
    locked_channel_id = int(lock.get("channel_id", 0) or 0)
    if not bool(lock.get("enabled")) or locked_channel_id <= 0:
        await reply_ephemeral(interaction, "Spicy Prompts is not configured for this server yet.")
        await log_interaction(interaction, action="spicy", reason="guild config missing", success=False)
        return
    if interaction.channel.id != locked_channel_id:
        await reply_ephemeral(
            interaction,
            f"Incorrect channel for /spicy. Please use <#{locked_channel_id}>.",
        )
        await log_interaction(interaction, action="spicy", reason=f"wrong channel: {interaction.channel.id}", success=False)
        return
    if not channel_supports_spicy_prompts(interaction.channel):
        await reply_ephemeral(interaction, "The configured Spicy Prompts channel must be age-restricted.")
        await log_interaction(interaction, action="spicy", reason="configured channel not age-restricted", success=False)
        return

    def _normalize_category(value: str) -> str:
        return str(value or "").strip().lower().replace(" ", "_")

    recent_cutoff = datetime.now(UTC) - timedelta(hours=4)
    recent_ids = ACTION_STORE.get_spicy_prompt_recent_ids(interaction.guild.id, since_dt=recent_cutoff)
    categories = ACTION_STORE.list_spicy_prompt_categories()
    normalized_categories = {_normalize_category(item): item for item in categories}
    if tag:
        tag_value = _normalize_category(tag)
        if tag_value == "help":
            if not categories:
                await reply_ephemeral(interaction, "No categories are available yet. Refresh the repo in the web GUI first.")
            else:
                sample = sorted(normalized_categories.keys())
                shown = ", ".join(sample[:30])
                suffix = f" (+{len(sample) - 30} more)" if len(sample) > 30 else ""
                await reply_ephemeral(
                    interaction,
                    f"Use `/spicy` for a random prompt, or `/spicy tag:<category>`.\nAvailable categories: {shown}{suffix}",
                )
            await log_interaction(interaction, action="spicy", reason="help", success=True)
            return
        selected_category = normalized_categories.get(tag_value)
        if not selected_category:
            await reply_ephemeral(
                interaction,
                "Unknown category tag. Use `/spicy tag:help` to list available categories.",
            )
            await log_interaction(interaction, action="spicy", reason="unknown category", success=False)
            return
    else:
        selected_category = secure_choice(categories) if categories else None

    prompt = ACTION_STORE.get_random_spicy_prompt(category=selected_category, exclude_ids=recent_ids)
    if prompt is None and selected_category is not None:
        prompt = ACTION_STORE.get_random_spicy_prompt(exclude_ids=recent_ids)
    if prompt is None:
        await reply_ephemeral(interaction, "No Spicy Prompts are cached yet. Refresh the repo in the web GUI first.")
        await log_interaction(interaction, action="spicy", reason="no cached prompts", success=False)
        return

    prompt_type = str(prompt.get("prompt_type", "prompt")).replace("_", " ").title()
    category = str(prompt.get("category", "general")).replace("_", " ").title()
    text = str(prompt.get("text", "")).strip()
    await interaction.response.send_message(f"**Spicy Prompt**\nType: {prompt_type}\nCategory: {category}\n\n{text}")
    ACTION_STORE.record_spicy_prompt_usage(interaction.guild.id, str(prompt.get("pack_id", "")), str(prompt.get("prompt_id", "")))
    await log_interaction(
        interaction,
        action="spicy",
        reason=truncate_log_text(f"{prompt.get('pack_id', '')}:{prompt.get('prompt_id', '')}"),
        success=True,
    )


@bot.tree.command(name="randomuser", description="Pick a random user (no repeats within 30 days).")
@app_commands.describe(role="Optional role to pick from")
async def randomuser(interaction: discord.Interaction, role: discord.Role | None = None) -> None:
    if not await ensure_interaction_command_access(interaction, "randomuser"):
        await log_interaction(interaction, action="randomuser", reason="permission denied", success=False)
        return
    if interaction.guild is None:
        await reply_ephemeral(interaction, "This command can only be used in a server.")
        await log_interaction(interaction, action="randomuser", reason="no guild", success=False)
        return
    try:
        result = await pick_random_user_for_guild(interaction.guild, role)
    except Exception as exc:
        await reply_ephemeral(interaction, f"Failed to pick a random user: {exc}")
        await log_interaction(interaction, action="randomuser", reason=str(exc), success=False)
        return
    if not result.get("ok"):
        await reply_ephemeral(interaction, str(result.get("error") or "No eligible members found."))
        await log_interaction(interaction, action="randomuser", reason="no eligible members", success=False)
        return
    selection_text = f"Random pick: {result.get('mention')}."
    meta = f"Eligible: {result.get('eligible_count')} | Excluded last {RANDOM_USER_COOLDOWN_DAYS}d: {result.get('recent_count')}"
    await reply_ephemeral(interaction, f"{selection_text}\n{meta}")
    await log_interaction(
        interaction,
        action="randomuser",
        reason=truncate_log_text(str(result.get("display_name") or result.get("user_id"))),
        success=True,
    )


@bot.tree.command(name="translate", description="Translate text to a selected language.")
@app_commands.describe(text="Text to translate", language="Target language")
@app_commands.choices(language=TRANSLATE_LANGUAGE_OPTIONS)
async def translate(interaction: discord.Interaction, text: str, language: app_commands.Choice[str]) -> None:
    if not await ensure_interaction_command_access(interaction, "translate"):
        await log_interaction(interaction, action="translate", reason="permission denied", success=False)
        return
    if not text.strip():
        await reply_ephemeral(interaction, "Please provide text to translate.")
        await log_interaction(interaction, action="translate", reason="missing text", success=False)
        return
    if not language or not language.value:
        await reply_ephemeral(interaction, "Please choose a target language.")
        await log_interaction(interaction, action="translate", reason="missing language", success=False)
        return
    if not TRANSLATE_API_URL:
        await reply_ephemeral(interaction, "Translation service is not configured.")
        await log_interaction(interaction, action="translate", reason="missing api url", success=False)
        return

    try:
        translated = await asyncio.to_thread(translate_text, text, language.value)
    except Exception as exc:
        await reply_ephemeral(interaction, f"Translation failed: {exc}")
        await log_interaction(interaction, action="translate", reason=str(exc), success=False)
        return

    label = TRANSLATE_LANGUAGE_BY_CODE.get(language.value, language.value)
    if len(translated) > 1900:
        translated = translated[:1897] + "..."
    await interaction.response.send_message(
        f"**Translated to {label}:**\n{translated}",
        ephemeral=COMMAND_RESPONSES_EPHEMERAL,
    )
    await log_interaction(interaction, action="translate", reason=f"target={language.value}", success=True)


@bot.tree.command(name="wikihelp", description="Search the game help wiki.")
@app_commands.describe(query="Search term for the help wiki")
async def wikihelp(interaction: discord.Interaction, query: str) -> None:
    if not await ensure_interaction_command_access(interaction, "wikihelp"):
        await log_interaction(interaction, action="wikihelp", reason="permission denied", success=False)
        return
    if not WIKI_SEARCH_ENABLED:
        await reply_ephemeral(interaction, "Wiki search is disabled.")
        await log_interaction(interaction, action="wikihelp", reason="disabled", success=False)
        return
    if not query.strip():
        await reply_ephemeral(interaction, "Please provide a search term.")
        await log_interaction(interaction, action="wikihelp", reason="missing query", success=False)
        return
    try:
        matches = await asyncio.to_thread(search_wiki_help, query)
    except Exception as exc:
        await reply_ephemeral(interaction, f"Wiki search failed: {exc}")
        await log_interaction(interaction, action="wikihelp", reason=str(exc), success=False)
        return
    if not matches:
        await reply_ephemeral(interaction, "No matches found in the wiki.")
        await log_interaction(interaction, action="wikihelp", reason="no matches", success=True)
        return
    lines = "\n".join(f"- {truncate_log_text(match, max_length=200)}" for match in matches)
    await interaction.response.send_message(
        f"**Wiki matches for** `{query}`:\n{lines}",
        ephemeral=COMMAND_RESPONSES_EPHEMERAL,
    )
    await log_interaction(interaction, action="wikihelp", reason=truncate_log_text(query), success=True)


@bot.tree.command(name="ollama", description="Ask the configured Ollama model.")
@app_commands.describe(prompt="Question or prompt to send to the model")
async def ollama(interaction: discord.Interaction, prompt: str) -> None:
    if not await ensure_interaction_command_access(interaction, "ollama"):
        await log_interaction(interaction, action="ollama", reason="permission denied", success=False)
        return
    if not OLLAMA_ENABLED:
        await reply_ephemeral(interaction, "Ollama integration is disabled.")
        await log_interaction(interaction, action="ollama", reason="disabled", success=False)
        return
    if not prompt.strip():
        await reply_ephemeral(interaction, "Please provide a prompt.")
        await log_interaction(interaction, action="ollama", reason="missing prompt", success=False)
        return
    try:
        response_text = await asyncio.to_thread(call_ollama, prompt)
    except Exception as exc:
        await reply_ephemeral(interaction, f"Ollama request failed: {exc}")
        await log_interaction(interaction, action="ollama", reason=str(exc), success=False)
        return
    if len(response_text) > 1900:
        response_text = response_text[:1897] + "..."
    await interaction.response.send_message(
        f"**Ollama ({OLLAMA_MODEL}):**\n{response_text}",
        ephemeral=COMMAND_RESPONSES_EPHEMERAL,
    )
    await log_interaction(interaction, action="ollama", reason=f"model={OLLAMA_MODEL}", success=True)


@bot.tree.command(name="color", description="Choose your name color from the configured list.")
@app_commands.describe(choice="Color role to apply, or clear to remove")
async def color(interaction: discord.Interaction, choice: str | None = None) -> None:
    if not await ensure_interaction_command_access(interaction, "color"):
        return
    if interaction.guild is None:
        await reply_ephemeral(interaction, "This command can only be used in a server.")
        return
    if not isinstance(interaction.user, discord.Member):
        await reply_ephemeral(interaction, "Member context unavailable.")
        return
    guild = interaction.guild
    member = interaction.user
    color_role_ids = get_color_role_ids(guild.id)
    if not color_role_ids:
        await reply_ephemeral(interaction, "No color roles are configured yet.")
        return
    available_roles = [role for role in guild.roles if role.id in color_role_ids]
    if not available_roles:
        await reply_ephemeral(interaction, "No color roles are available in this server.")
        return
    # resolve desired role
    target_role = None
    if choice:
        choice_value = str(choice).strip()
        for role in available_roles:
            if choice_value == str(role.id) or choice_value.lower() == role.name.lower():
                target_role = role
                break
        if target_role is None:
            await reply_ephemeral(interaction, "That color role is not available.")
            return
    # remove existing color roles first
    roles_to_remove = [role for role in member.roles if role.id in color_role_ids]
    if roles_to_remove:
        try:
            await member.remove_roles(*roles_to_remove, reason="Color role change")
        except discord.Forbidden:
            await reply_ephemeral(interaction, "I don't have permission to manage those roles.")
            return
    if target_role is None:
        await interaction.response.send_message("Color cleared.", ephemeral=COMMAND_RESPONSES_EPHEMERAL)
        return
    # ensure bot can manage role
    if guild.me is None or guild.me.top_role <= target_role:
        await reply_ephemeral(interaction, "I can only apply roles below my highest role.")
        return
    if target_role.managed:
        await reply_ephemeral(interaction, "That role is managed and cannot be assigned.")
        return
    try:
        await member.add_roles(target_role, reason="Color role change")
    except discord.Forbidden:
        await reply_ephemeral(interaction, "I don't have permission to assign that role.")
        return
    await interaction.response.send_message(f"Color updated to {target_role.name}.", ephemeral=COMMAND_RESPONSES_EPHEMERAL)


@bot.tree.command(name="countdown", description="Count down to a future date.")
@app_commands.describe(event="Event name", when="Date in YYYY-MM-DD or YYYY-MM-DD HH:MM (UTC unless timezone provided)")
async def countdown(interaction: discord.Interaction, event: str, when: str) -> None:
    if not await ensure_interaction_command_access(interaction, "countdown"):
        return
    try:
        target_dt = parse_countdown_target(when)
    except ValueError as exc:
        await reply_ephemeral(interaction, str(exc))
        await log_interaction(interaction, action="countdown", reason=truncate_log_text(str(exc)), success=False)
        return
    duration = format_duration_until(target_dt)
    if duration == "already passed":
        await reply_ephemeral(interaction, "That time has already passed.")
        await log_interaction(interaction, action="countdown", reason="date already passed", success=False)
        return
    event_label = truncate_log_text(event.strip(), max_length=120) or "Event"
    await interaction.response.send_message(
        f"Countdown to **{event_label}**: {duration}\nTarget: `{target_dt.isoformat()}`",
        ephemeral=COMMAND_RESPONSES_EPHEMERAL,
    )
    await log_interaction(
        interaction, action="countdown", reason=truncate_log_text(f"{event_label} @ {target_dt.isoformat()}"), success=True
    )


@bot.tree.command(name="leaderboard", description="Show member activity leaderboard.")
@app_commands.describe(window="Activity window")
@app_commands.choices(
    window=[
        app_commands.Choice(name="24 Hours", value="1d"),
        app_commands.Choice(name="7 Days", value="7d"),
        app_commands.Choice(name="30 Days", value="30d"),
        app_commands.Choice(name="90 Days", value="90d"),
    ]
)
async def leaderboard(interaction: discord.Interaction, window: app_commands.Choice[str] | None = None) -> None:
    if not await ensure_interaction_command_access(interaction, "leaderboard"):
        return
    if interaction.guild is None:
        await reply_ephemeral(interaction, "This command can only be used in a server.")
        await log_interaction(interaction, action="leaderboard", reason="no guild context", success=False)
        return
    selected_window = window.value if window else "7d"
    try:
        label, entries = build_activity_leaderboard(selected_window, interaction.guild.id, limit=10)
    except Exception as exc:
        await reply_ephemeral(interaction, f"Failed to build leaderboard: {exc}")
        await log_interaction(interaction, action="leaderboard", reason=truncate_log_text(str(exc)), success=False)
        return
    if not entries:
        await reply_ephemeral(interaction, "No activity data is available for that leaderboard yet.")
        await log_interaction(interaction, action="leaderboard", reason="no activity data", success=False)
        return
    lines = [f"**{interaction.guild.name} - {label}**", ""]
    for entry in entries:
        display_name = str(entry.get("display_name") or entry.get("username") or entry.get("user_id"))
        lines.append(f"{int(entry.get('rank') or 0)}. {display_name} - {int(entry.get('message_count') or 0)} messages")
    await interaction.response.send_message("\n".join(lines), ephemeral=COMMAND_RESPONSES_EPHEMERAL)
    await log_interaction(interaction, action="leaderboard", reason=selected_window, success=True)


@bot.tree.command(name="trivia", description="Get a random trivia question.")
async def trivia(interaction: discord.Interaction) -> None:
    if not await ensure_interaction_command_access(interaction, "trivia"):
        return
    selected = secure_choice(TRIVIA_QUESTIONS)
    choices = selected["choices"]
    lines = ["**Trivia Time**", selected["question"], ""]
    for index, choice in enumerate(choices):
        lines.append(f"{NUMBER_EMOJIS[index]} {choice}")
    lines.append("")
    lines.append(f"Answer: ||{selected['answer']}||")
    await interaction.response.send_message("\n".join(lines), ephemeral=COMMAND_RESPONSES_EPHEMERAL)
    await log_interaction(interaction, action="trivia", reason=truncate_log_text(selected["question"]), success=True)


@bot.tree.command(name="wouldyourather", description="Get a would-you-rather prompt.")
async def wouldyourather(interaction: discord.Interaction) -> None:
    if not await ensure_interaction_command_access(interaction, "wouldyourather"):
        return
    prompt = secure_choice(WOULD_YOU_RATHER_PROMPTS)
    await interaction.response.send_message(prompt, ephemeral=COMMAND_RESPONSES_EPHEMERAL)
    await log_interaction(interaction, action="wouldyourather", reason=truncate_log_text(prompt), success=True)


@bot.tree.command(name="rps", description="Play rock paper scissors against the bot.")
@app_commands.describe(choice="Your choice")
@app_commands.choices(
    choice=[
        app_commands.Choice(name="Rock", value="rock"),
        app_commands.Choice(name="Paper", value="paper"),
        app_commands.Choice(name="Scissors", value="scissors"),
    ]
)
async def rps(interaction: discord.Interaction, choice: app_commands.Choice[str]) -> None:
    if not await ensure_interaction_command_access(interaction, "rps"):
        return
    user_choice = choice.value
    bot_choice = secure_choice(sorted(RPS_BEATS))
    if bot_choice == user_choice:
        outcome = "It's a tie."
    elif RPS_BEATS[user_choice] == bot_choice:
        outcome = "You win."
    else:
        outcome = "I win."
    await interaction.response.send_message(
        f"You picked **{user_choice}**. I picked **{bot_choice}**. {outcome}",
        ephemeral=COMMAND_RESPONSES_EPHEMERAL,
    )
    await log_interaction(interaction, action="rps", reason=f"{user_choice}/{bot_choice}", success=True)


@bot.tree.command(name="guess", description="Play the guild guessing game.")
@app_commands.describe(number="Guess a number between 1 and 100")
async def guess(interaction: discord.Interaction, number: int | None = None) -> None:
    if not await ensure_interaction_command_access(interaction, "guess"):
        return
    if interaction.guild is None:
        await reply_ephemeral(interaction, "This command can only be used in a server.")
        await log_interaction(interaction, action="guess", reason="no guild context", success=False)
        return
    if number is not None and (int(number) < 1 or int(number) > 100):
        await reply_ephemeral(interaction, "Guess must be between 1 and 100.")
        await log_interaction(interaction, action="guess", reason=f"invalid guess: {number}", success=False)
        return
    guild_id = interaction.guild.id
    game = ACTION_STORE.get_guess_game(guild_id)
    if game is None:
        ACTION_STORE.save_guess_game(guild_id, secure_randint(1, 100), interaction.user.id, attempt_count=0)
        game = ACTION_STORE.get_guess_game(guild_id)
    if game is None:
        await reply_ephemeral(interaction, "Failed to start the guessing game.")
        await log_interaction(interaction, action="guess", reason="game init failed", success=False)
        return
    if number is None:
        await interaction.response.send_message(
            "I picked a number between **1** and **100**. Use `/guess number:<value>` to make a guess.",
            ephemeral=COMMAND_RESPONSES_EPHEMERAL,
        )
        await log_interaction(interaction, action="guess", reason="game prompt", success=True)
        return
    target_number = int(game.get("target_number", 0) or 0)
    attempts = int(game.get("attempt_count", 0) or 0) + 1
    if int(number) == target_number:
        ACTION_STORE.clear_guess_game(guild_id)
        await interaction.response.send_message(
            f"Correct. The number was **{target_number}**. Solved in {attempts} attempt(s). Starting a fresh game now.",
            ephemeral=COMMAND_RESPONSES_EPHEMERAL,
        )
        ACTION_STORE.save_guess_game(guild_id, secure_randint(1, 100), interaction.user.id, attempt_count=0)
        await log_interaction(interaction, action="guess", reason=f"solved in {attempts}", success=True)
        return
    ACTION_STORE.update_guess_game_attempts(guild_id, attempts)
    hint = "higher" if int(number) < target_number else "lower"
    await interaction.response.send_message(
        f"Not it. Try **{hint}**. Attempts so far: {attempts}.",
        ephemeral=COMMAND_RESPONSES_EPHEMERAL,
    )
    await log_interaction(interaction, action="guess", reason=f"{number} -> {hint}", success=True)


@birthday_group.command(name="set", description="Set your birthday.")
@app_commands.describe(date="Birthday in MM-DD, MM/DD, or YYYY-MM-DD format")
async def birthday_set(interaction: discord.Interaction, date: str) -> None:
    if not await ensure_interaction_command_access(interaction, "birthday_set"):
        return
    if interaction.guild is None:
        await reply_ephemeral(interaction, "This command can only be used in a server.")
        await log_interaction(interaction, action="birthday_set", reason="no guild context", success=False)
        return
    try:
        month, day = parse_month_day_input(date)
        next_occurrence = next_birthday_occurrence(month, day)
    except ValueError as exc:
        await reply_ephemeral(interaction, str(exc))
        await log_interaction(interaction, action="birthday_set", reason=truncate_log_text(str(exc)), success=False)
        return
    ACTION_STORE.save_birthday(interaction.guild.id, interaction.user.id, str(interaction.user), month, day)
    await interaction.response.send_message(
        f"Birthday saved as **{birthday_label(month, day)}**. Next one is `{next_occurrence.strftime('%Y-%m-%d')}`.",
        ephemeral=COMMAND_RESPONSES_EPHEMERAL,
    )
    await log_interaction(interaction, action="birthday_set", reason=f"{month:02d}-{day:02d}", success=True)


@birthday_group.command(name="view", description="View a stored birthday.")
@app_commands.describe(member="Member to view; defaults to you")
async def birthday_view(interaction: discord.Interaction, member: discord.Member | None = None) -> None:
    if not await ensure_interaction_command_access(interaction, "birthday_view"):
        return
    if interaction.guild is None:
        await reply_ephemeral(interaction, "This command can only be used in a server.")
        await log_interaction(interaction, action="birthday_view", reason="no guild context", success=False)
        return
    target = member or interaction.user
    stored = ACTION_STORE.get_birthday(interaction.guild.id, target.id)
    if stored is None:
        await reply_ephemeral(interaction, f"No birthday is stored for {target.mention}.")
        await log_interaction(interaction, action="birthday_view", target=target, reason="not set", success=False)
        return
    month = int(stored["month"])
    day = int(stored["day"])
    next_occurrence = next_birthday_occurrence(month, day)
    days_until = (next_occurrence.date() - datetime.now(UTC).date()).days
    await interaction.response.send_message(
        f"{target.mention}'s birthday is **{birthday_label(month, day)}**.\nNext occurrence: `{next_occurrence.strftime('%Y-%m-%d')}` ({days_until} day(s) away).",
        ephemeral=COMMAND_RESPONSES_EPHEMERAL,
    )
    await log_interaction(interaction, action="birthday_view", target=target, reason=f"{month:02d}-{day:02d}", success=True)


@birthday_group.command(name="upcoming", description="Show upcoming birthdays for this server.")
@app_commands.describe(days="How many days ahead to include")
async def birthday_upcoming(interaction: discord.Interaction, days: app_commands.Range[int, 1, 365] = 30) -> None:
    if not await ensure_interaction_command_access(interaction, "birthday_upcoming"):
        return
    if interaction.guild is None:
        await reply_ephemeral(interaction, "This command can only be used in a server.")
        await log_interaction(interaction, action="birthday_upcoming", reason="no guild context", success=False)
        return
    upcoming = list_upcoming_birthdays(interaction.guild.id, days_ahead=int(days), limit=10)
    if not upcoming:
        await reply_ephemeral(interaction, f"No birthdays are coming up in the next {int(days)} day(s).")
        await log_interaction(interaction, action="birthday_upcoming", reason="no upcoming birthdays", success=False)
        return
    lines = [f"**Upcoming birthdays in {interaction.guild.name}**", ""]
    for entry in upcoming:
        lines.append(f"- {entry['username']}: {entry['label']} ({entry['days_until']} day(s), next `{entry['next_occurrence']}`)")
    await interaction.response.send_message("\n".join(lines), ephemeral=COMMAND_RESPONSES_EPHEMERAL)
    await log_interaction(interaction, action="birthday_upcoming", reason=f"days={int(days)}", success=True)


@birthday_group.command(name="remove", description="Remove your stored birthday.")
async def birthday_remove(interaction: discord.Interaction) -> None:
    if not await ensure_interaction_command_access(interaction, "birthday_remove"):
        return
    if interaction.guild is None:
        await reply_ephemeral(interaction, "This command can only be used in a server.")
        await log_interaction(interaction, action="birthday_remove", reason="no guild context", success=False)
        return
    deleted = ACTION_STORE.delete_birthday(interaction.guild.id, interaction.user.id)
    if not deleted:
        await reply_ephemeral(interaction, "You do not have a stored birthday to remove.")
        await log_interaction(interaction, action="birthday_remove", reason="not set", success=False)
        return
    await interaction.response.send_message("Your birthday has been removed.", ephemeral=COMMAND_RESPONSES_EPHEMERAL)
    await log_interaction(interaction, action="birthday_remove", success=True)


bot.tree.add_command(birthday_group)
bot.tree.add_command(dnd_group)
register_dnd_commands(
    bot,
    helpers={
        "reply_ephemeral": reply_ephemeral,
        "log_interaction": log_interaction,
        "ensure_interaction_command_access": ensure_interaction_command_access,
    },
)


@bot.tree.command(name="shorten", description="Create a short URL.")
@app_commands.describe(url="URL to shorten using the configured shortener")
async def shorten(interaction: discord.Interaction, url: str) -> None:
    if not await ensure_interaction_command_access(interaction, "shorten"):
        return
    if not SHORTENER_ENABLED:
        await reply_ephemeral(interaction, "Shortener integration is disabled.")
        await log_interaction(interaction, action="shorten", reason="shortener disabled", success=False)
        return

    try:
        normalized_url = normalize_target_url(url)
    except ValueError as exc:
        await reply_ephemeral(interaction, str(exc))
        await log_interaction(interaction, action="shorten", reason=str(exc), success=False)
        return

    await interaction.response.defer(ephemeral=COMMAND_RESPONSES_EPHEMERAL)
    try:
        _, short_url = await asyncio.to_thread(create_short_url, normalized_url)
        await interaction.followup.send(
            f"Short URL: {short_url}",
            ephemeral=COMMAND_RESPONSES_EPHEMERAL,
        )
        await log_interaction(
            interaction,
            action="shorten",
            reason=truncate_log_text(f"{normalized_url} -> {short_url}"),
            success=True,
        )
    except RuntimeError as exc:
        await interaction.followup.send(
            f"Failed to shorten URL: {exc}",
            ephemeral=COMMAND_RESPONSES_EPHEMERAL,
        )
        await log_interaction(interaction, action="shorten", reason=truncate_log_text(str(exc)), success=False)


@bot.tree.command(name="expand", description="Expand a short code or short URL.")
@app_commands.describe(value="Short code (example: 1234) or full short URL")
async def expand(interaction: discord.Interaction, value: str) -> None:
    if not await ensure_interaction_command_access(interaction, "expand"):
        return
    if not SHORTENER_ENABLED:
        await reply_ephemeral(interaction, "Shortener integration is disabled.")
        await log_interaction(interaction, action="expand", reason="shortener disabled", success=False)
        return

    try:
        short_url = normalize_short_reference(value)
    except ValueError as exc:
        await reply_ephemeral(interaction, str(exc))
        await log_interaction(interaction, action="expand", reason=str(exc), success=False)
        return

    await interaction.response.defer(ephemeral=COMMAND_RESPONSES_EPHEMERAL)
    try:
        resolved_url = await asyncio.to_thread(expand_short_url, short_url)
        await interaction.followup.send(
            f"Expanded URL: {resolved_url}",
            ephemeral=COMMAND_RESPONSES_EPHEMERAL,
        )
        await log_interaction(
            interaction,
            action="expand",
            reason=truncate_log_text(f"{short_url} -> {resolved_url}"),
            success=True,
        )
    except RuntimeError as exc:
        await interaction.followup.send(
            f"Failed to expand URL: {exc}",
            ephemeral=COMMAND_RESPONSES_EPHEMERAL,
        )
        await log_interaction(interaction, action="expand", reason=truncate_log_text(str(exc)), success=False)


@bot.tree.command(name="uptime", description="Show current uptime monitor status.")
async def uptime(interaction: discord.Interaction) -> None:
    if not await ensure_interaction_command_access(interaction, "uptime"):
        return
    if not UPTIME_STATUS_ENABLED:
        await reply_ephemeral(interaction, "Uptime status integration is disabled.")
        await log_interaction(interaction, action="uptime", reason="uptime integration disabled", success=False)
        return

    await interaction.response.defer(ephemeral=COMMAND_RESPONSES_EPHEMERAL)
    try:
        snapshot = await asyncio.to_thread(fetch_uptime_snapshot)
        summary = format_uptime_summary(snapshot)
        await interaction.followup.send(summary, ephemeral=COMMAND_RESPONSES_EPHEMERAL)
        counts = snapshot.get("counts", {})
        await log_interaction(
            interaction,
            action="uptime",
            reason=truncate_log_text(f"up={counts.get('up', 0)} down={counts.get('down', 0)} pending={counts.get('pending', 0)}"),
            success=True,
        )
    except RuntimeError as exc:
        await interaction.followup.send(
            f"Failed to fetch uptime status: {exc}",
            ephemeral=COMMAND_RESPONSES_EPHEMERAL,
        )
        await log_interaction(interaction, action="uptime", reason=truncate_log_text(str(exc)), success=False)


@bot.tree.command(name="monitor", description="Show internal monitor status summary.")
async def monitor(interaction: discord.Interaction) -> None:
    if not await ensure_interaction_command_access(interaction, "monitor"):
        return
    if interaction.guild_id is None:
        await reply_ephemeral(interaction, "Monitor status is only available inside a guild.")
        return
    monitors = ACTION_STORE.list_uptime_monitors(guild_id=interaction.guild_id, enabled_only=False)
    if not monitors:
        await reply_ephemeral(interaction, "No uptime monitors are configured for this server yet.")
        await log_interaction(interaction, action="monitor", reason="no monitors configured", success=False)
        return
    enabled = [item for item in monitors if int(item.get("enabled", 0)) == 1]
    down = [item for item in enabled if str(item.get("last_status", "")).lower() == "down"]
    lines = [
        f"Monitors: {len(monitors)} total ({len(enabled)} enabled)",
        f"Down: {len(down)}",
    ]
    if down:
        lines.append("Down monitors:")
        for item in down[:10]:
            name = str(item.get("name") or "Monitor").strip()
            target = str(item.get("target") or "").strip()
            lines.append(f"- {name} ({target})")
    await reply_ephemeral(interaction, "\n".join(lines))
    await log_interaction(interaction, action="monitor", reason="status summary", success=True)


@bot.tree.command(name="logs", description="View recent container error logs.")
@app_commands.checks.has_permissions(manage_messages=True)
@app_commands.describe(lines="Number of recent lines to show (10-400)")
async def logs(interaction: discord.Interaction, lines: app_commands.Range[int, 10, 400] = 120) -> None:
    if not await ensure_interaction_command_access(interaction, "logs"):
        return

    log_tail = read_recent_log_lines(CONTAINER_ERROR_LOG_FILE, int(lines))
    if not log_tail:
        await reply_ephemeral(interaction, "No container error logs have been written yet.")
        await log_interaction(interaction, action="logs", reason="no logs available", success=False)
        return

    response_header = f"Showing last `{int(lines)}` lines from `{os.path.basename(CONTAINER_ERROR_LOG_FILE)}`."
    if len(log_tail) <= 1700:
        await reply_ephemeral(interaction, f"{response_header}\n```log\n{log_tail}\n```")
    else:
        if interaction.response.is_done():
            await interaction.followup.send(
                response_header,
                ephemeral=COMMAND_RESPONSES_EPHEMERAL,
                file=discord.File(io.BytesIO(log_tail.encode("utf-8")), filename=f"container_errors_last_{int(lines)}.log"),
            )
        else:
            await interaction.response.send_message(
                response_header,
                ephemeral=COMMAND_RESPONSES_EPHEMERAL,
                file=discord.File(io.BytesIO(log_tail.encode("utf-8")), filename=f"container_errors_last_{int(lines)}.log"),
            )
    await log_interaction(interaction, action="logs", reason=f"lines={int(lines)}", success=True)


@bot.tree.command(name="stats", description="Show your private member activity stats.")
async def stats(interaction: discord.Interaction) -> None:
    if not await ensure_interaction_command_access(interaction, "stats"):
        return
    if interaction.guild is None:
        await reply_ephemeral(interaction, "This command can only be used in a server.")
        await log_interaction(interaction, action="stats", reason="No guild context", success=False)
        return
    try:
        snapshot = get_member_activity_snapshot(interaction.guild.id, interaction.user.id)
    except Exception as exc:
        await reply_ephemeral(interaction, f"Failed to load your activity stats: {exc}")
        await log_interaction(interaction, action="stats", reason=truncate_log_text(str(exc)), success=False)
        return
    windows = snapshot.get("windows", []) if isinstance(snapshot, dict) else []
    if not windows:
        await reply_ephemeral(interaction, "No member activity has been recorded for you in this server yet.")
        await log_interaction(interaction, action="stats", reason="no activity", success=True)
        return
    display_name = str(snapshot.get("display_name") or interaction.user.display_name or interaction.user.name)
    lines = [
        "Your Activity Stats",
        f"Server: {interaction.guild.name}",
        f"Member: {display_name}",
        "",
    ]
    for index, window in enumerate(windows):
        if index > 0:
            lines.append("")
        lines.append(format_member_activity_window_summary(window))
    await reply_ephemeral(interaction, "\n".join(lines))
    await log_interaction(
        interaction,
        action="stats",
        reason=truncate_log_text(f"messages={sum(int(window.get('message_count') or 0) for window in windows)}"),
        success=True,
    )


@bot.tree.command(name="help", description="Show available bot features.")
async def help_command(interaction: discord.Interaction) -> None:
    if not await ensure_interaction_command_access(interaction, "help"):
        return
    message = (
        "**Wicked Yoda's Little Helper**\n"
        "General: `/ping`, `/sayhi`, `/happy`, `/cat`, `/meme`, `/dadjoke`, `/help`\n"
        "Fun: `/eightball`, `/coinflip`, `/roll`, `/choose`, `/roastme`, `/compliment`, `/wisdom`, `/gif`, `/poll`, `/questionoftheday`, `/spicy` (supports `tag`), `/randomuser`, `/translate`, `/wikihelp`, `/ollama`, `/countdown`, `/trivia`, `/wouldyourather`, `/rps`, `/guess`\n"
        "Community: `/birthday set`, `/birthday view`, `/birthday upcoming`, `/birthday remove`, `/leaderboard`\n"
        "Utilities: `/shorten`, `/expand`, `/uptime`, `/monitor`, `/logs`, `/stats`\n"
        "Tags: `/tags`, `/tag <name>`, message tags like `!rules`\n"
        "Moderation: `/kick`, `/ban`, `/timeout`, `/untimeout`, `/purge`, `/unban`, `/addrole`, `/removerole`\n"
        "Use the web admin panel for settings, users, logs, wiki, command permissions, and tag responses."
    )
    await interaction.response.send_message(message, ephemeral=COMMAND_RESPONSES_EPHEMERAL)
    await log_interaction(interaction, action="help", success=True)


@bot.tree.command(name="tags", description="List configured tags.")
async def tags(interaction: discord.Interaction) -> None:
    if not await ensure_interaction_command_access(interaction, "tags"):
        return
    guild_id = interaction.guild.id if interaction.guild else GUILD_ID
    mapping = ACTION_STORE.get_tag_responses(guild_id=guild_id)
    if not mapping:
        await reply_ephemeral(interaction, "No tags are configured.")
        await log_interaction(interaction, action="tags", reason="no tags configured", success=False)
        return
    tag_list = ", ".join(sorted(mapping.keys()))
    await reply_ephemeral(interaction, f"Configured tags: {tag_list}")
    await log_interaction(interaction, action="tags", reason=truncate_log_text(tag_list), success=True)


@bot.tree.command(name="tag", description="Post a configured tag response.")
@app_commands.describe(name="Tag name (with or without !)")
async def tag(interaction: discord.Interaction, name: str) -> None:
    if not await ensure_interaction_command_access(interaction, "tag"):
        return
    tag_key = normalize_tag(name)
    guild_id = interaction.guild.id if interaction.guild else GUILD_ID
    mapping = ACTION_STORE.get_tag_responses(guild_id=guild_id)
    if not tag_key or tag_key not in mapping:
        await reply_ephemeral(interaction, "Tag not found. Use `/tags` to list available tags.")
        await log_interaction(interaction, action="tag", reason=f"missing tag: {name}", success=False)
        return
    await interaction.response.send_message(mapping[tag_key], ephemeral=COMMAND_RESPONSES_EPHEMERAL)
    await log_interaction(interaction, action="tag", reason=tag_key, success=True)


@bot.tree.command(name="kick", description="Kick a member from the server.")
@app_commands.checks.has_permissions(kick_members=True)
@app_commands.describe(member="Member to kick", reason="Reason for the kick")
async def kick(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str | None = "No reason provided",
) -> None:
    if not await ensure_interaction_command_access(interaction, "kick"):
        return
    try:
        await member.kick(reason=reason)
        await reply_ephemeral(interaction, f"Kicked {member.mention}.")
        await log_interaction(interaction, action="kick", target=member, reason=reason, success=True)
    except Exception as exc:
        await reply_ephemeral(interaction, f"Failed to kick member: {exc}")
        await log_interaction(interaction, action="kick", target=member, reason=str(reason), success=False)


@bot.tree.command(name="ban", description="Ban a member from the server.")
@app_commands.checks.has_permissions(ban_members=True)
@app_commands.describe(member="Member to ban", reason="Reason for the ban", delete_days="Delete message history (0-7)")
async def ban(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str | None = "No reason provided",
    delete_days: app_commands.Range[int, 0, 7] = 0,
) -> None:
    if not await ensure_interaction_command_access(interaction, "ban"):
        return
    try:
        if interaction.guild is None:
            await reply_ephemeral(interaction, "This command can only be used in a server.")
            await log_interaction(interaction, action="ban", reason="No guild context", success=False)
            return
        await interaction.guild.ban(
            member,
            reason=reason,
            delete_message_seconds=delete_days * 24 * 60 * 60,
        )
        await reply_ephemeral(interaction, f"Banned {member.mention}.")
        await log_interaction(interaction, action="ban", target=member, reason=reason, success=True)
    except Exception as exc:
        await reply_ephemeral(interaction, f"Failed to ban member: {exc}")
        await log_interaction(interaction, action="ban", target=member, reason=str(reason), success=False)


@bot.tree.command(name="timeout", description="Timeout a member for a number of minutes.")
@app_commands.checks.has_permissions(moderate_members=True)
@app_commands.describe(member="Member to timeout", minutes="Timeout duration in minutes", reason="Reason for timeout")
async def timeout(
    interaction: discord.Interaction,
    member: discord.Member,
    minutes: app_commands.Range[int, 1, 40320],
    reason: str | None = "No reason provided",
) -> None:
    if not await ensure_interaction_command_access(interaction, "timeout"):
        return
    try:
        until = discord.utils.utcnow() + timedelta(minutes=minutes)
        await member.edit(timed_out_until=until, reason=reason)
        await reply_ephemeral(interaction, f"Timed out {member.mention} for {minutes} minute(s).")
        await log_interaction(interaction, action="timeout", target=member, reason=reason, success=True)
    except Exception as exc:
        await reply_ephemeral(interaction, f"Failed to timeout member: {exc}")
        await log_interaction(interaction, action="timeout", target=member, reason=str(reason), success=False)


@bot.tree.command(name="untimeout", description="Remove timeout from a member.")
@app_commands.checks.has_permissions(moderate_members=True)
@app_commands.describe(member="Member to remove timeout from", reason="Reason for removing timeout")
async def untimeout(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str | None = "No reason provided",
) -> None:
    if not await ensure_interaction_command_access(interaction, "untimeout"):
        return
    try:
        await member.edit(timed_out_until=None, reason=reason)
        await reply_ephemeral(interaction, f"Removed timeout for {member.mention}.")
        await log_interaction(interaction, action="untimeout", target=member, reason=reason, success=True)
    except Exception as exc:
        await reply_ephemeral(interaction, f"Failed to remove timeout: {exc}")
        await log_interaction(interaction, action="untimeout", target=member, reason=str(reason), success=False)


@bot.tree.command(name="purge", description="Delete a number of recent messages.")
@app_commands.checks.has_permissions(manage_messages=True)
@app_commands.describe(amount="Number of messages to delete (1-100)")
async def purge(interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100]) -> None:
    if not await ensure_interaction_command_access(interaction, "purge"):
        return
    if interaction.channel is None:
        await reply_ephemeral(interaction, "This command can only be used in a server channel.")
        await log_interaction(interaction, action="purge", reason="No channel context", success=False)
        return

    try:
        await interaction.response.defer(ephemeral=COMMAND_RESPONSES_EPHEMERAL)
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.followup.send(
            f"Deleted {len(deleted)} message(s).",
            ephemeral=COMMAND_RESPONSES_EPHEMERAL,
        )
        await log_interaction(interaction, action="purge", reason=f"Deleted {len(deleted)} messages", success=True)
    except Exception as exc:
        await reply_ephemeral(interaction, f"Failed to purge messages: {exc}")
        await log_interaction(interaction, action="purge", reason=str(exc), success=False)


@bot.tree.command(name="unban", description="Unban a member by user ID.")
@app_commands.checks.has_permissions(ban_members=True)
@app_commands.describe(user_id="User ID to unban", reason="Reason for unban")
async def unban(interaction: discord.Interaction, user_id: str, reason: str | None = "No reason provided") -> None:
    if not await ensure_interaction_command_access(interaction, "unban"):
        return
    if interaction.guild is None:
        await reply_ephemeral(interaction, "This command can only be used in a server.")
        await log_interaction(interaction, action="unban", reason="No guild context", success=False)
        return
    target_user_id = parse_user_id_input(user_id)
    if target_user_id is None:
        await reply_ephemeral(interaction, "Invalid user ID.")
        await log_interaction(interaction, action="unban", reason=f"invalid id: {user_id}", success=False)
        return
    try:
        await interaction.guild.unban(discord.Object(id=target_user_id), reason=reason)
        await reply_ephemeral(interaction, f"Unbanned user ID `{target_user_id}`.")
        await log_interaction(interaction, action="unban", reason=f"{target_user_id}: {reason}", success=True)
    except discord.NotFound:
        await reply_ephemeral(interaction, f"User `{target_user_id}` is not currently banned.")
        await log_interaction(interaction, action="unban", reason=f"not banned: {target_user_id}", success=False)
    except Exception as exc:
        await reply_ephemeral(interaction, f"Failed to unban user: {exc}")
        await log_interaction(interaction, action="unban", reason=f"{target_user_id}: {exc}", success=False)


@bot.tree.command(name="addrole", description="Add a role to a member.")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.describe(member="Member to update", role="Role to add", reason="Reason for role assignment")
async def addrole(
    interaction: discord.Interaction,
    member: discord.Member,
    role: discord.Role,
    reason: str | None = "No reason provided",
) -> None:
    if not await ensure_interaction_command_access(interaction, "addrole"):
        return
    if interaction.guild is None or not isinstance(interaction.user, discord.Member):
        await reply_ephemeral(interaction, "This command can only be used in a server.")
        await log_interaction(interaction, action="addrole", reason="No guild/member context", success=False)
        return
    bot_member = interaction.guild.me or interaction.guild.get_member(bot.user.id if bot.user else 0)
    if bot_member is None:
        await reply_ephemeral(interaction, "Could not resolve bot member in this guild.")
        await log_interaction(interaction, action="addrole", target=member, reason="bot member missing", success=False)
        return
    can_target, target_error = validate_moderation_target(interaction.user, member, bot_member)
    if not can_target:
        await reply_ephemeral(interaction, str(target_error))
        await log_interaction(interaction, action="addrole", target=member, reason=target_error, success=False)
        return
    can_manage, role_error = validate_manageable_role(interaction.user, role, bot_member)
    if not can_manage:
        await reply_ephemeral(interaction, str(role_error))
        await log_interaction(interaction, action="addrole", target=member, reason=role_error, success=False)
        return
    if role in member.roles:
        await reply_ephemeral(interaction, f"{member.mention} already has {role.mention}.")
        await log_interaction(interaction, action="addrole", target=member, reason="already has role", success=False)
        return
    try:
        await member.add_roles(role, reason=reason)
        await reply_ephemeral(interaction, f"Added {role.mention} to {member.mention}.")
        await log_interaction(interaction, action="addrole", target=member, reason=f"{role.id}: {reason}", success=True)
    except Exception as exc:
        await reply_ephemeral(interaction, f"Failed to add role: {exc}")
        await log_interaction(interaction, action="addrole", target=member, reason=str(exc), success=False)


@bot.tree.command(name="removerole", description="Remove a role from a member.")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.describe(member="Member to update", role="Role to remove", reason="Reason for role removal")
async def removerole(
    interaction: discord.Interaction,
    member: discord.Member,
    role: discord.Role,
    reason: str | None = "No reason provided",
) -> None:
    if not await ensure_interaction_command_access(interaction, "removerole"):
        return
    if interaction.guild is None or not isinstance(interaction.user, discord.Member):
        await reply_ephemeral(interaction, "This command can only be used in a server.")
        await log_interaction(interaction, action="removerole", reason="No guild/member context", success=False)
        return
    bot_member = interaction.guild.me or interaction.guild.get_member(bot.user.id if bot.user else 0)
    if bot_member is None:
        await reply_ephemeral(interaction, "Could not resolve bot member in this guild.")
        await log_interaction(interaction, action="removerole", target=member, reason="bot member missing", success=False)
        return
    can_target, target_error = validate_moderation_target(interaction.user, member, bot_member)
    if not can_target:
        await reply_ephemeral(interaction, str(target_error))
        await log_interaction(interaction, action="removerole", target=member, reason=target_error, success=False)
        return
    can_manage, role_error = validate_manageable_role(interaction.user, role, bot_member)
    if not can_manage:
        await reply_ephemeral(interaction, str(role_error))
        await log_interaction(interaction, action="removerole", target=member, reason=role_error, success=False)
        return
    if role not in member.roles:
        await reply_ephemeral(interaction, f"{member.mention} does not currently have {role.mention}.")
        await log_interaction(interaction, action="removerole", target=member, reason="role not assigned", success=False)
        return
    try:
        await member.remove_roles(role, reason=reason)
        await reply_ephemeral(interaction, f"Removed {role.mention} from {member.mention}.")
        await log_interaction(interaction, action="removerole", target=member, reason=f"{role.id}: {reason}", success=True)
    except Exception as exc:
        await reply_ephemeral(interaction, f"Failed to remove role: {exc}")
        await log_interaction(interaction, action="removerole", target=member, reason=str(exc), success=False)


@kick.error
@ban.error
@timeout.error
@untimeout.error
@purge.error
@logs.error
@unban.error
@addrole.error
@removerole.error
async def command_permission_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    if isinstance(error, app_commands.MissingPermissions):
        await reply_ephemeral(interaction, "You do not have permission to use this command.")
        await log_interaction(interaction, action="permission_denied", reason=str(error), success=False)
        return
    if isinstance(error, app_commands.BotMissingPermissions):
        await reply_ephemeral(interaction, "I do not have the permissions needed for that action.")
        await log_interaction(interaction, action="bot_missing_permissions", reason=str(error), success=False)
        return
    await reply_ephemeral(interaction, "An unexpected error occurred.")
    await log_interaction(interaction, action="command_error", reason=str(error), success=False)


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
