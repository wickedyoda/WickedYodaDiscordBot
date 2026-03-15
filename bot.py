import asyncio
import http.client
import importlib.util
import io
import json
import logging
import os
import re
import sqlite3
import tempfile
import threading
import urllib.parse
from datetime import UTC, datetime, timedelta

import discord
from defusedxml import ElementTree as DefusedET
from discord import app_commands
from discord.ext import commands

from web_admin import start_web_admin

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("wickedyoda-helper")
bot_channel_logger = logging.getLogger("wickedyoda-helper.channel-log")


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
COMMAND_RESPONSES_EPHEMERAL = env_bool("COMMAND_RESPONSES_EPHEMERAL", False)
SHORTENER_ENABLED = env_bool("SHORTENER_ENABLED", False)
SHORTENER_TIMEOUT_SECONDS = env_int("SHORTENER_TIMEOUT_SECONDS", 8)
PUPPY_IMAGE_API_URL = os.getenv("PUPPY_IMAGE_API_URL", "https://dog.ceo/api/breeds/image/random").strip()
PUPPY_IMAGE_TIMEOUT_SECONDS = env_int("PUPPY_IMAGE_TIMEOUT_SECONDS", 8)
YOUTUBE_NOTIFY_ENABLED = env_bool("YOUTUBE_NOTIFY_ENABLED", True)
YOUTUBE_POLL_INTERVAL_SECONDS = env_int("YOUTUBE_POLL_INTERVAL_SECONDS", 300)
YOUTUBE_REQUEST_TIMEOUT_SECONDS = env_int("YOUTUBE_REQUEST_TIMEOUT_SECONDS", 12)
UPTIME_STATUS_ENABLED = env_bool("UPTIME_STATUS_ENABLED", True)
UPTIME_STATUS_TIMEOUT_SECONDS = env_int("UPTIME_STATUS_TIMEOUT_SECONDS", 8)
WEB_RESTART_ENABLED = env_bool("WEB_RESTART_ENABLED", False)
WEB_AVATAR_MAX_UPLOAD_BYTES = max(1024, env_int("WEB_AVATAR_MAX_UPLOAD_BYTES", 2 * 1024 * 1024))

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

SHORT_CODE_REGEX = re.compile(r"Link saved:\s*([0-9]{4,})")
STATUS_PAGE_PATH_REGEX = re.compile(r"^/status/([^/]+)/?$")
YOUTUBE_CHANNEL_ID_PATTERN = re.compile(r"(UC[a-zA-Z0-9_-]{22})")
YOUTUBE_CHANNEL_ID_META_PATTERNS = (
    re.compile(r'"channelId":"(UC[a-zA-Z0-9_-]{22})"'),
    re.compile(r'itemprop="channelId"\s+content="(UC[a-zA-Z0-9_-]{22})"'),
    re.compile(r'"externalId":"(UC[a-zA-Z0-9_-]{22})"'),
)
USER_ID_INPUT_PATTERN = re.compile(r"^\d{17,20}$")

COMMAND_PERMISSION_MODE_DEFAULT = "default"
COMMAND_PERMISSION_MODE_PUBLIC = "public"
COMMAND_PERMISSION_MODE_CUSTOM_ROLES = "custom_roles"
COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC = "public"
COMMAND_PERMISSION_DEFAULT_POLICY_MODERATOR = "moderator"
COMMAND_PERMISSION_POLICY_LABELS = {
    COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC: "Public (all members)",
    COMMAND_PERMISSION_DEFAULT_POLICY_MODERATOR: "Moderator (ban/kick/manage roles/messages/moderate)",
}
COMMAND_PERMISSION_METADATA: dict[str, dict[str, str]] = {
    "ping": {"label": "/ping", "description": "Health check", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC},
    "sayhi": {"label": "/sayhi", "description": "Bot introduction", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC},
    "happy": {"label": "/happy", "description": "Random puppy image", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC},
    "shorten": {"label": "/shorten", "description": "Create short URL", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC},
    "expand": {"label": "/expand", "description": "Expand short URL", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC},
    "uptime": {"label": "/uptime", "description": "Uptime monitor summary", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC},
    "logs": {"label": "/logs", "description": "Read recent error logs", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_MODERATOR},
    "help": {"label": "/help", "description": "Command overview", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC},
    "tags": {"label": "/tags", "description": "List configured tags", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC},
    "tag": {"label": "/tag", "description": "Post a configured tag", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC},
    "kick": {"label": "/kick", "description": "Kick member", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_MODERATOR},
    "ban": {"label": "/ban", "description": "Ban member", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_MODERATOR},
    "timeout": {"label": "/timeout", "description": "Timeout member", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_MODERATOR},
    "untimeout": {"label": "/untimeout", "description": "Remove timeout", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_MODERATOR},
    "purge": {"label": "/purge", "description": "Purge messages", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_MODERATOR},
    "unban": {"label": "/unban", "description": "Unban by user ID", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_MODERATOR},
    "addrole": {"label": "/addrole", "description": "Add role to member", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_MODERATOR},
    "removerole": {
        "label": "/removerole",
        "description": "Remove role from member",
        "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_MODERATOR,
    },
}
DEFAULT_TAG_RESPONSES = {
    "!rules": "Please review the server rules and pinned messages before posting.",
    "!support": "Need help? Open a support thread with details and device/version info.",
}


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
    if candidate in {COMMAND_PERMISSION_MODE_DEFAULT, COMMAND_PERMISSION_MODE_PUBLIC, COMMAND_PERMISSION_MODE_CUSTOM_ROLES}:
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
if YOUTUBE_POLL_INTERVAL_SECONDS <= 0:
    raise RuntimeError("YOUTUBE_POLL_INTERVAL_SECONDS must be a positive integer.")
if YOUTUBE_REQUEST_TIMEOUT_SECONDS <= 0:
    raise RuntimeError("YOUTUBE_REQUEST_TIMEOUT_SECONDS must be a positive integer.")
if UPTIME_STATUS_TIMEOUT_SECONDS <= 0:
    raise RuntimeError("UPTIME_STATUS_TIMEOUT_SECONDS must be a positive integer.")

intents = discord.Intents.default()
intents.guilds = True
intents.members = ENABLE_MEMBERS_INTENT
intents.messages = True
intents.message_content = False


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
    entry = root.find("atom:entry", ns)
    if entry is None:
        raise RuntimeError("YouTube feed has no entries.")

    video_id = entry.findtext("yt:videoId", default="", namespaces=ns).strip()
    video_title = entry.findtext("atom:title", default="Untitled", namespaces=ns).strip()
    published_at = entry.findtext("atom:published", default="", namespaces=ns).strip()
    link_el = entry.find("atom:link[@rel='alternate']", ns)
    video_url = link_el.get("href", "").strip() if link_el is not None else ""
    if not video_url and video_id:
        video_url = f"https://www.youtube.com/watch?v={video_id}"

    if not video_id:
        raise RuntimeError("YouTube feed entry is missing video ID.")
    if not video_url:
        raise RuntimeError("YouTube feed entry is missing video URL.")

    return {
        "channel_id": channel_id,
        "channel_title": channel_title,
        "video_id": video_id,
        "video_title": video_title,
        "video_url": video_url,
        "published_at": published_at,
    }


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
                os.makedirs(directory, exist_ok=True)
            with sqlite3.connect(path, timeout=5) as conn:
                conn.execute("PRAGMA user_version = 1")
                conn.commit()
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
    preferred = configured or os.path.dirname(db_path) or "."
    fallback = os.path.dirname(db_path) or "."
    candidates: list[str] = [preferred]
    if fallback != preferred:
        candidates.append(fallback)

    for candidate in candidates:
        try:
            os.makedirs(candidate, exist_ok=True)
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


def add_file_handler(target_logger: logging.Logger, path: str, level: int) -> None:
    normalized = os.path.abspath(path)
    for handler in target_logger.handlers:
        if isinstance(handler, logging.FileHandler) and os.path.abspath(handler.baseFilename) == normalized:
            handler.setLevel(level)
            return
    file_handler = logging.FileHandler(path, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    target_logger.addHandler(file_handler)


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

    add_file_handler(logger, bot_log_file, log_level)
    add_file_handler(bot_channel_logger, channel_log_file, logging.INFO)
    add_file_handler(root_logger, error_log_file, container_log_level)
    return bot_log_file, channel_log_file, error_log_file


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
            os.makedirs(directory, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, timeout=10)

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
                    last_video_id TEXT,
                    last_video_title TEXT,
                    last_published_at TEXT,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    UNIQUE(channel_id, target_channel_id)
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
                            INSERT INTO guild_settings (guild_id, bot_log_channel_id, updated_at)
                            VALUES (?, ?, ?)
                            """,
                            (guild_id, BOT_LOG_CHANNEL, now),
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
                   target_channel_name, last_video_id, last_video_title, last_published_at, enabled
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

    def update_youtube_last_video(
        self,
        subscription_id: int,
        video_id: str,
        video_title: str,
        published_at: str,
    ) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE youtube_subscriptions
                    SET last_video_id = ?, last_video_title = ?, last_published_at = ?
                    WHERE id = ?
                    """,
                    (video_id, video_title, published_at, subscription_id),
                )
                conn.commit()

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

    def get_guild_settings(self, guild_id: int) -> dict[str, int | None]:
        with self._lock:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT guild_id, bot_log_channel_id FROM guild_settings WHERE guild_id = ?",
                    (int(guild_id),),
                ).fetchone()
        if row is None:
            return {"guild_id": int(guild_id), "bot_log_channel_id": None}
        return {
            "guild_id": int(row["guild_id"]),
            "bot_log_channel_id": int(row["bot_log_channel_id"]) if row["bot_log_channel_id"] else None,
        }

    def save_guild_settings(self, guild_id: int, *, bot_log_channel_id: int | None) -> dict[str, int | None]:
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO guild_settings (guild_id, bot_log_channel_id, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(guild_id) DO UPDATE SET
                        bot_log_channel_id = excluded.bot_log_channel_id,
                        updated_at = excluded.updated_at
                    """,
                    (int(guild_id), bot_log_channel_id, now),
                )
                conn.commit()
        return self.get_guild_settings(guild_id)


ACTION_DB_PATH = resolve_action_db_path()
ACTIONS_DIR = os.path.dirname(ACTION_DB_PATH) or "."
LOG_DIR = resolve_log_dir(ACTION_DB_PATH)
BOT_LOG_FILE, BOT_CHANNEL_LOG_FILE, CONTAINER_ERROR_LOG_FILE = configure_runtime_logging(LOG_DIR)
ACTION_STORE = ActionStore(ACTION_DB_PATH)


def resolve_command_permission_state(command_key: str, guild_id: int) -> tuple[str, str, list[int]]:
    default_policy = COMMAND_PERMISSION_METADATA.get(command_key, {}).get("default_policy", COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC)
    stored_rules = ACTION_STORE.get_command_permissions(guild_id=guild_id)
    rule = normalize_command_permission_rule(stored_rules.get(command_key))
    return str(default_policy), str(rule["mode"]), normalize_role_ids(rule["role_ids"])


def can_use_command(member: discord.Member | discord.User, command_key: str, guild_id: int) -> bool:
    default_policy, mode, role_ids = resolve_command_permission_state(command_key, guild_id=guild_id)
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


def validate_moderation_target(actor: discord.Member, target: discord.Member, bot_member: discord.Member) -> tuple[bool, str | None]:
    if target.id == actor.id:
        return False, "You cannot moderate yourself."
    if target.id == actor.guild.owner_id:
        return False, "You cannot moderate the server owner."
    if target.id == bot_member.id:
        return False, "You cannot moderate the bot."
    if actor.id != actor.guild.owner_id and actor.top_role <= target.top_role:
        return False, "You can only moderate members below your top role."
    if bot_member.top_role <= target.top_role:
        return False, "I can only moderate members below my top role."
    return True, None


def validate_manageable_role(actor: discord.Member, role: discord.Role, bot_member: discord.Member) -> tuple[bool, str | None]:
    if role == actor.guild.default_role:
        return False, "You cannot manage the @everyone role."
    if role.managed:
        return False, "That role is managed by an integration."
    if actor.id != actor.guild.owner_id and actor.top_role <= role:
        return False, "You can only manage roles below your top role."
    if bot_member.top_role <= role:
        return False, "I can only manage roles below my top role."
    return True, None


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
    bot_log_channel_id: int | None
    if not raw_channel_id:
        bot_log_channel_id = None
    elif raw_channel_id.isdigit():
        bot_log_channel_id = int(raw_channel_id)
    else:
        return {"ok": False, "error": "Bot log channel ID must be numeric."}

    try:
        saved = ACTION_STORE.save_guild_settings(
            guild_id=guild_id,
            bot_log_channel_id=bot_log_channel_id,
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


class ModerationBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.commands_synced = 0
        self.expected_commands = 0
        self.started_at = datetime.now(UTC)
        self.web_thread: threading.Thread | None = None
        self.web_tls_thread: threading.Thread | None = None
        self.youtube_monitor_task: asyncio.Task | None = None
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
                request_restart=run_web_request_restart,
                resolve_youtube_subscription=lambda source_url: resolve_youtube_subscription_seed(source_url),
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
                        request_restart=run_web_request_restart,
                        resolve_youtube_subscription=lambda source_url: resolve_youtube_subscription_seed(source_url),
                        host=WEB_BIND_HOST,
                        port=WEB_TLS_PORT,
                        ssl_context=ssl_context,
                    )
                    logger.info("Web admin HTTPS started at https://%s:%s", WEB_BIND_HOST, WEB_TLS_PORT)
        if YOUTUBE_NOTIFY_ENABLED and self.youtube_monitor_task is None:
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
        return {
            "bot_name": str(self.user) if self.user else "Starting...",
            "guild_id": GUILD_ID,
            "guild_count": len(managed),
            "latency_ms": latency_ms,
            "commands_synced": self.commands_synced,
            "started_at": self.started_at.isoformat(),
        }

    def build_web_channel_options(self, guild_id: int) -> list[dict]:
        guild = self.get_guild(guild_id)
        if guild is None:
            return []
        options: list[dict] = []
        for channel in sorted(guild.text_channels, key=lambda item: (item.position, item.name.lower())):
            options.append({"id": channel.id, "name": f"#{channel.name}"})
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
        self.web_channel_options = channels
        self.web_role_options = roles
        if guild is None:
            return {"ok": False, "error": "Guild not available."}
        return {
            "ok": True,
            "guild": {"id": guild.id, "name": guild.name},
            "channels": channels,
            "roles": roles,
        }

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        managed_ids = {guild.id for guild in self.get_managed_guilds()}
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

    async def youtube_monitor_loop(self) -> None:
        await self.wait_until_ready()
        logger.info("YouTube notifier loop started. Poll interval: %ss", YOUTUBE_POLL_INTERVAL_SECONDS)
        while not self.is_closed():
            try:
                await self.poll_youtube_subscriptions()
            except Exception as exc:
                logger.exception("YouTube notifier poll failed: %s", exc)
            await asyncio.sleep(YOUTUBE_POLL_INTERVAL_SECONDS)

    async def poll_youtube_subscriptions(self) -> None:
        subscriptions = ACTION_STORE.list_youtube_subscriptions(enabled_only=True)
        if not subscriptions:
            return
        for subscription in subscriptions:
            await self._process_youtube_subscription(subscription)

    async def _process_youtube_subscription(self, subscription: dict) -> None:
        subscription_id = int(subscription.get("id", 0))
        channel_id = str(subscription.get("channel_id", "")).strip()
        target_channel_id = int(subscription.get("target_channel_id", 0))
        if subscription_id <= 0 or not channel_id or target_channel_id <= 0:
            return

        try:
            latest = await asyncio.to_thread(fetch_latest_youtube_video, channel_id)
        except RuntimeError as exc:
            logger.warning("Unable to fetch YouTube feed for %s: %s", channel_id, exc)
            return

        last_video_id = str(subscription.get("last_video_id", "")).strip()
        if latest["video_id"] == last_video_id:
            return

        notify_channel = await get_text_channel(self, target_channel_id)
        if notify_channel is None:
            logger.warning("Notify channel %s not found for YouTube subscription %s", target_channel_id, subscription_id)
            return

        embed = discord.Embed(
            title=f"New video from {latest['channel_title']}",
            description=f"[{latest['video_title']}]({latest['video_url']})",
            color=discord.Color.red(),
        )
        embed.set_footer(text="YouTube Notification")
        await notify_channel.send(embed=embed)

        ACTION_STORE.update_youtube_last_video(
            subscription_id=subscription_id,
            video_id=latest["video_id"],
            video_title=latest["video_title"],
            published_at=latest["published_at"],
        )
        description = (
            f"Action: `youtube_notify`\n"
            f"Status: **Success**\n"
            f"Guild: {notify_channel.guild.id}\n"
            f"Target: {notify_channel.mention} ({notify_channel.id})\n"
            f"Reason: {latest['channel_title']} - {latest['video_title']}"
        )
        await log_action(self, "YouTube Notification", description, discord.Color.red(), guild_id=notify_channel.guild.id)
        record_action_safe(
            action="youtube_notify",
            status="success",
            moderator="system",
            target=f"{notify_channel.name} ({notify_channel.id})",
            reason=truncate_log_text(f"{latest['channel_title']} - {latest['video_title']}"),
            guild=str(notify_channel.guild.id),
        )


bot = ModerationBot()


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


async def reply_ephemeral(interaction: discord.Interaction, message: str) -> None:
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=COMMAND_RESPONSES_EPHEMERAL)
    else:
        await interaction.response.send_message(message, ephemeral=COMMAND_RESPONSES_EPHEMERAL)


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
        "WickedYoda's Little Helper is online.",
        ephemeral=COMMAND_RESPONSES_EPHEMERAL,
    )
    await log_interaction(interaction, action="ping", success=True)


@bot.tree.command(name="sayhi", description="Introduce the bot in the channel.")
async def sayhi(interaction: discord.Interaction) -> None:
    if not await ensure_interaction_command_access(interaction, "sayhi"):
        return
    intro = "Hi everyone, I am WickedYoda's Little Helper.\nI can help with moderation, URL short links, and uptime checks."
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


@bot.tree.command(name="help", description="Show available bot features.")
async def help_command(interaction: discord.Interaction) -> None:
    if not await ensure_interaction_command_access(interaction, "help"):
        return
    message = (
        "**WickedYoda's Little Helper**\n"
        "General: `/ping`, `/sayhi`, `/happy`, `/help`\n"
        "Utilities: `/shorten`, `/expand`, `/uptime`, `/logs`\n"
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
