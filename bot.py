import asyncio
import http.client
import json
import logging
import os
import re
import sqlite3
import tempfile
import threading
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta

import discord
from discord import app_commands
from discord.ext import commands

from web_admin import start_web_admin

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("wickedyoda-helper")


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


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
GUILD_ID = int(required_env("GUILD_ID"))
BOT_LOG_CHANNEL = int(required_env("Bot_Log_Channel"))

DATA_DIR = os.getenv("DATA_DIR", "/app/data")
WEB_ENABLED = env_bool("WEB_ENABLED", True)
WEB_BIND_HOST = os.getenv("WEB_BIND_HOST", "127.0.0.1")
WEB_PORT = env_int("WEB_PORT", 8080)
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
        root = ET.fromstring(body_text)
    except ET.ParseError as exc:
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
            logger.warning("Unable to use action DB path %s: %s", path, exc)

    raise RuntimeError("No writable SQLite database path found for moderation action store.")


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
            existing_tags = conn.execute("SELECT COUNT(*) FROM tag_responses").fetchone()[0]
            if int(existing_tags) == 0:
                now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
                for tag, response in DEFAULT_TAG_RESPONSES.items():
                    conn.execute(
                        """
                        INSERT INTO tag_responses (tag, response, updated_at)
                        VALUES (?, ?, ?)
                        """,
                        (tag, response, now),
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

    def get_command_permissions(self) -> dict[str, dict[str, str | list[int]]]:
        with self._lock:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("SELECT command_key, mode, role_ids_json FROM command_permissions").fetchall()
        mapping: dict[str, dict[str, str | list[int]]] = {}
        for row in rows:
            command_key = str(row["command_key"]).strip()
            if command_key not in COMMAND_PERMISSION_METADATA:
                continue
            raw_role_ids = row["role_ids_json"]
            try:
                parsed_role_ids = json.loads(raw_role_ids) if isinstance(raw_role_ids, str) else []
            except json.JSONDecodeError:
                parsed_role_ids = []
            mapping[command_key] = normalize_command_permission_rule({"mode": row["mode"], "role_ids": parsed_role_ids})
        return mapping

    def save_command_permissions(self, rules: dict[str, dict[str, str | list[int]]]) -> dict[str, dict[str, str | list[int]]]:
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
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
                conn.execute("DELETE FROM command_permissions")
                for key, rule in stored_rules.items():
                    conn.execute(
                        """
                        INSERT INTO command_permissions (command_key, mode, role_ids_json, updated_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (key, str(rule["mode"]), json.dumps(rule["role_ids"]), now),
                    )
                conn.commit()
        return stored_rules

    def get_tag_responses(self) -> dict[str, str]:
        with self._lock:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("SELECT tag, response FROM tag_responses ORDER BY tag ASC").fetchall()
        mapping: dict[str, str] = {}
        for row in rows:
            tag = normalize_tag(str(row["tag"]))
            if not tag:
                continue
            response = str(row["response"]).strip()
            if response:
                mapping[tag] = response
        return mapping

    def save_tag_responses(self, mapping: dict[str, str]) -> dict[str, str]:
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        normalized: dict[str, str] = {}
        for raw_tag, raw_response in (mapping or {}).items():
            tag = normalize_tag(str(raw_tag))
            response = str(raw_response).strip()
            if not tag or not response:
                continue
            normalized[tag] = truncate_log_text(response, max_length=1900)

        with self._lock:
            with self._connect() as conn:
                conn.execute("DELETE FROM tag_responses")
                for tag, response in normalized.items():
                    conn.execute(
                        """
                        INSERT INTO tag_responses (tag, response, updated_at)
                        VALUES (?, ?, ?)
                        """,
                        (tag, response, now),
                    )
                conn.commit()
        return normalized


ACTION_DB_PATH = resolve_action_db_path()
ACTION_STORE = ActionStore(ACTION_DB_PATH)


def resolve_command_permission_state(command_key: str) -> tuple[str, str, list[int]]:
    default_policy = COMMAND_PERMISSION_METADATA.get(command_key, {}).get("default_policy", COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC)
    stored_rules = ACTION_STORE.get_command_permissions()
    rule = normalize_command_permission_rule(stored_rules.get(command_key))
    return str(default_policy), str(rule["mode"]), normalize_role_ids(rule["role_ids"])


def can_use_command(member: discord.Member | discord.User, command_key: str) -> bool:
    default_policy, mode, role_ids = resolve_command_permission_state(command_key)
    if mode == COMMAND_PERMISSION_MODE_PUBLIC:
        return True
    if mode == COMMAND_PERMISSION_MODE_CUSTOM_ROLES:
        return member_has_any_role_id(member, role_ids)
    if default_policy == COMMAND_PERMISSION_DEFAULT_POLICY_MODERATOR:
        return is_moderator_member(member)
    return True


def build_command_permission_denied_message(command_key: str, guild: discord.Guild | None = None) -> str:
    default_policy, mode, role_ids = resolve_command_permission_state(command_key)
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


def build_command_permissions_web_payload() -> dict:
    rules = ACTION_STORE.get_command_permissions()
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
    return {"ok": True, "commands": commands_payload}


def run_web_get_command_permissions() -> dict:
    try:
        return build_command_permissions_web_payload()
    except Exception as exc:
        logger.exception("Failed to build command permissions payload: %s", exc)
        return {"ok": False, "error": "Failed to load command permissions."}


def run_web_update_command_permissions(payload: dict, _actor_email: str) -> dict:
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
        ACTION_STORE.save_command_permissions(updated_rules)
    except Exception as exc:
        logger.exception("Failed to save command permissions: %s", exc)
        return {"ok": False, "error": "Failed to save command permissions."}
    response = build_command_permissions_web_payload()
    response["message"] = "Command permissions updated."
    return response


def run_web_get_tag_responses() -> dict:
    try:
        mapping = ACTION_STORE.get_tag_responses()
    except Exception as exc:
        logger.exception("Failed to load tag responses: %s", exc)
        return {"ok": False, "error": "Failed to load tag responses."}
    return {"ok": True, "mapping": mapping}


def run_web_save_tag_responses(mapping: dict, _actor_email: str) -> dict:
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
        saved = ACTION_STORE.save_tag_responses(normalized)
    except Exception as exc:
        logger.exception("Failed to save tag responses: %s", exc)
        return {"ok": False, "error": "Failed to save tag responses."}
    return {"ok": True, "mapping": saved, "message": "Tag responses updated."}


class ModerationBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.guild_object = discord.Object(id=GUILD_ID)
        self.commands_synced = 0
        self.expected_commands = 0
        self.started_at = datetime.now(UTC)
        self.web_thread: threading.Thread | None = None
        self.youtube_monitor_task: asyncio.Task | None = None
        self.web_channel_options: list[dict] = []
        self.web_role_options: list[dict] = []

    async def sync_guild_commands(self, reason: str) -> None:
        expected = len(self.tree.get_commands(guild=self.guild_object))
        synced = await self.tree.sync(guild=self.guild_object)
        self.commands_synced = len(synced)
        self.expected_commands = expected
        synced_names = ", ".join(f"/{command.name}" for command in synced)
        logger.info(
            "Synced %s/%s command(s) to guild %s (%s): %s",
            self.commands_synced,
            self.expected_commands,
            GUILD_ID,
            reason,
            synced_names or "(none)",
        )

    async def setup_hook(self) -> None:
        await self.sync_guild_commands(reason="startup")
        if WEB_ENABLED and self.web_thread is None:
            self.web_thread = start_web_admin(
                db_path=ACTION_DB_PATH,
                get_bot_snapshot=self.get_web_snapshot,
                get_notification_channels=self.get_web_channel_options,
                get_discord_catalog=self.get_web_discord_catalog,
                get_command_permissions=run_web_get_command_permissions,
                save_command_permissions=run_web_update_command_permissions,
                get_tag_responses=run_web_get_tag_responses,
                save_tag_responses=run_web_save_tag_responses,
                resolve_youtube_subscription=lambda source_url: resolve_youtube_subscription_seed(source_url),
                host=WEB_BIND_HOST,
                port=WEB_PORT,
            )
            logger.info("Web admin started at http://%s:%s", WEB_BIND_HOST, WEB_PORT)
        if YOUTUBE_NOTIFY_ENABLED and self.youtube_monitor_task is None:
            self.youtube_monitor_task = self.loop.create_task(self.youtube_monitor_loop(), name="youtube-monitor")

    async def on_ready(self) -> None:
        logger.info("Logged in as %s (%s)", self.user, self.user.id if self.user else "n/a")
        if self.commands_synced < self.expected_commands:
            logger.warning(
                "Guild command sync appears incomplete (%s/%s). Retrying sync once.",
                self.commands_synced,
                self.expected_commands,
            )
            await self.sync_guild_commands(reason="ready-retry")
        self.web_channel_options = self.build_web_channel_options()
        self.web_role_options = self.build_web_role_options()
        if not ENABLE_MEMBERS_INTENT:
            logger.info("ENABLE_MEMBERS_INTENT is disabled; no privileged members intent requested.")
        await log_action(
            self,
            "Bot Started",
            f"{self.user.mention if self.user else 'Bot'} is online and ready.",
            color=discord.Color.green(),
        )
        ACTION_STORE.record(
            action="bot_started",
            status="success",
            moderator="system",
            target=str(self.user) if self.user else "bot",
            reason="Bot connected to Discord.",
            guild=str(GUILD_ID),
        )

    def get_web_snapshot(self) -> dict:
        latency_ms = max(int(self.latency * 1000), 0) if self.is_ready() else 0
        return {
            "bot_name": str(self.user) if self.user else "Starting...",
            "guild_id": GUILD_ID,
            "latency_ms": latency_ms,
            "commands_synced": self.commands_synced,
            "started_at": self.started_at.isoformat(),
        }

    def build_web_channel_options(self) -> list[dict]:
        guild = self.get_guild(GUILD_ID)
        if guild is None:
            return []
        options: list[dict] = []
        for channel in sorted(guild.text_channels, key=lambda item: (item.position, item.name.lower())):
            options.append({"id": channel.id, "name": f"#{channel.name}"})
        return options

    def get_web_channel_options(self) -> list[dict]:
        return list(self.web_channel_options)

    def build_web_role_options(self) -> list[dict]:
        guild = self.get_guild(GUILD_ID)
        if guild is None:
            return []
        options: list[dict] = []
        for role in sorted(guild.roles, key=lambda item: item.position, reverse=True):
            if role.is_default():
                continue
            options.append({"id": role.id, "name": f"@{role.name}"})
        return options

    def get_web_discord_catalog(self) -> dict:
        guild = self.get_guild(GUILD_ID)
        if guild is None:
            return {"ok": False, "error": "Guild not available."}
        self.web_channel_options = self.build_web_channel_options()
        self.web_role_options = self.build_web_role_options()
        return {
            "ok": True,
            "guild": {"id": guild.id, "name": guild.name},
            "channels": list(self.web_channel_options),
            "roles": list(self.web_role_options),
        }

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if isinstance(message.author, discord.Member) and message.guild and message.guild.id == GUILD_ID:
            content = (message.content or "").strip()
            if content.startswith("!"):
                tag_key = normalize_tag(content.split()[0])
                if tag_key:
                    tag_mapping = ACTION_STORE.get_tag_responses()
                    response = tag_mapping.get(tag_key)
                    if response and can_use_command(message.author, "tag"):
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
        self.web_channel_options = self.build_web_channel_options()
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
            f"Guild: {GUILD_ID}\n"
            f"Target: {notify_channel.mention} ({notify_channel.id})\n"
            f"Reason: {latest['channel_title']} - {latest['video_title']}"
        )
        await log_action(self, "YouTube Notification", description, discord.Color.red())
        record_action_safe(
            action="youtube_notify",
            status="success",
            moderator="system",
            target=f"{notify_channel.name} ({notify_channel.id})",
            reason=truncate_log_text(f"{latest['channel_title']} - {latest['video_title']}"),
            guild=str(GUILD_ID),
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


async def get_log_channel(client: commands.Bot) -> discord.TextChannel | None:
    return await get_text_channel(client, BOT_LOG_CHANNEL)


async def log_action(client: commands.Bot, title: str, description: str, color: discord.Color) -> None:
    try:
        channel = await get_log_channel(client)
        if channel is None:
            logger.error("Bot_Log_Channel %s not found or not a text channel.", BOT_LOG_CHANNEL)
            return
        embed = discord.Embed(title=title, description=description, color=color)
        await channel.send(embed=embed)
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
    )
    record_action_safe(
        action=action,
        status=status_db,
        moderator=actor_label,
        target=target_db,
        reason=reason or "",
        guild=guild_name,
    )


async def ensure_interaction_command_access(interaction: discord.Interaction, command_key: str) -> bool:
    if can_use_command(interaction.user, command_key):
        return True
    message = build_command_permission_denied_message(command_key, interaction.guild)
    await reply_ephemeral(interaction, message)
    await log_interaction(interaction, action="permission_denied", reason=f"{command_key}: {message}", success=False)
    return False


@bot.tree.command(name="ping", description="Check if the bot is online.", guild=discord.Object(id=GUILD_ID))
async def ping(interaction: discord.Interaction) -> None:
    if not await ensure_interaction_command_access(interaction, "ping"):
        return
    await interaction.response.send_message(
        "WickedYoda's Little Helper is online.",
        ephemeral=COMMAND_RESPONSES_EPHEMERAL,
    )
    await log_interaction(interaction, action="ping", success=True)


@bot.tree.command(name="sayhi", description="Introduce the bot in the channel.", guild=discord.Object(id=GUILD_ID))
async def sayhi(interaction: discord.Interaction) -> None:
    if not await ensure_interaction_command_access(interaction, "sayhi"):
        return
    intro = "Hi everyone, I am WickedYoda's Little Helper.\nI can help with moderation, URL short links, and uptime checks."
    await interaction.response.send_message(intro)
    await log_interaction(interaction, action="sayhi", reason="Posted channel introduction", success=True)


@bot.tree.command(name="happy", description="Post a random puppy picture.", guild=discord.Object(id=GUILD_ID))
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


@bot.tree.command(name="shorten", description="Create a short URL.", guild=discord.Object(id=GUILD_ID))
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


@bot.tree.command(name="expand", description="Expand a short code or short URL.", guild=discord.Object(id=GUILD_ID))
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


@bot.tree.command(name="uptime", description="Show current uptime monitor status.", guild=discord.Object(id=GUILD_ID))
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


@bot.tree.command(name="help", description="Show available bot features.", guild=discord.Object(id=GUILD_ID))
async def help_command(interaction: discord.Interaction) -> None:
    if not await ensure_interaction_command_access(interaction, "help"):
        return
    message = (
        "**WickedYoda's Little Helper**\n"
        "General: `/ping`, `/sayhi`, `/happy`, `/help`\n"
        "Utilities: `/shorten`, `/expand`, `/uptime`\n"
        "Tags: `/tags`, `/tag <name>`, message tags like `!rules`\n"
        "Moderation: `/kick`, `/ban`, `/timeout`, `/untimeout`, `/purge`, `/unban`, `/addrole`, `/removerole`\n"
        "Use the web admin panel for settings, users, logs, wiki, command permissions, and tag responses."
    )
    await interaction.response.send_message(message, ephemeral=COMMAND_RESPONSES_EPHEMERAL)
    await log_interaction(interaction, action="help", success=True)


@bot.tree.command(name="tags", description="List configured tags.", guild=discord.Object(id=GUILD_ID))
async def tags(interaction: discord.Interaction) -> None:
    if not await ensure_interaction_command_access(interaction, "tags"):
        return
    mapping = ACTION_STORE.get_tag_responses()
    if not mapping:
        await reply_ephemeral(interaction, "No tags are configured.")
        await log_interaction(interaction, action="tags", reason="no tags configured", success=False)
        return
    tag_list = ", ".join(sorted(mapping.keys()))
    await reply_ephemeral(interaction, f"Configured tags: {tag_list}")
    await log_interaction(interaction, action="tags", reason=truncate_log_text(tag_list), success=True)


@bot.tree.command(name="tag", description="Post a configured tag response.", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(name="Tag name (with or without !)")
async def tag(interaction: discord.Interaction, name: str) -> None:
    if not await ensure_interaction_command_access(interaction, "tag"):
        return
    tag_key = normalize_tag(name)
    mapping = ACTION_STORE.get_tag_responses()
    if not tag_key or tag_key not in mapping:
        await reply_ephemeral(interaction, "Tag not found. Use `/tags` to list available tags.")
        await log_interaction(interaction, action="tag", reason=f"missing tag: {name}", success=False)
        return
    await interaction.response.send_message(mapping[tag_key], ephemeral=COMMAND_RESPONSES_EPHEMERAL)
    await log_interaction(interaction, action="tag", reason=tag_key, success=True)


@bot.tree.command(name="kick", description="Kick a member from the server.", guild=discord.Object(id=GUILD_ID))
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


@bot.tree.command(name="ban", description="Ban a member from the server.", guild=discord.Object(id=GUILD_ID))
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


@bot.tree.command(name="timeout", description="Timeout a member for a number of minutes.", guild=discord.Object(id=GUILD_ID))
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


@bot.tree.command(name="untimeout", description="Remove timeout from a member.", guild=discord.Object(id=GUILD_ID))
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


@bot.tree.command(name="purge", description="Delete a number of recent messages.", guild=discord.Object(id=GUILD_ID))
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


@bot.tree.command(name="unban", description="Unban a member by user ID.", guild=discord.Object(id=GUILD_ID))
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


@bot.tree.command(name="addrole", description="Add a role to a member.", guild=discord.Object(id=GUILD_ID))
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


@bot.tree.command(name="removerole", description="Remove a role from a member.", guild=discord.Object(id=GUILD_ID))
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
