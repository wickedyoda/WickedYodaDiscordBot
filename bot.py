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
SHORTENER_ENABLED = env_bool("SHORTENER_ENABLED", False)
SHORTENER_TIMEOUT_SECONDS = env_int("SHORTENER_TIMEOUT_SECONDS", 8)
UPTIME_STATUS_ENABLED = env_bool("UPTIME_STATUS_ENABLED", True)
UPTIME_STATUS_TIMEOUT_SECONDS = env_int("UPTIME_STATUS_TIMEOUT_SECONDS", 8)

SHORT_CODE_REGEX = re.compile(r"Link saved:\s*([0-9]{4,})")
STATUS_PAGE_PATH_REGEX = re.compile(r"^/status/([^/]+)/?$")


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
UPTIME_STATUS_PAGE_URL = normalize_status_page_url(
    os.getenv("UPTIME_STATUS_PAGE_URL", "https://randy.wickedyoda.com/status/everything")
)
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


ACTION_DB_PATH = resolve_action_db_path()
ACTION_STORE = ActionStore(ACTION_DB_PATH)


class ModerationBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.guild_object = discord.Object(id=GUILD_ID)
        self.commands_synced = 0
        self.expected_commands = 0
        self.started_at = datetime.now(UTC)
        self.web_thread: threading.Thread | None = None

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
                host=WEB_BIND_HOST,
                port=WEB_PORT,
            )
            logger.info("Web admin started at http://%s:%s", WEB_BIND_HOST, WEB_PORT)

    async def on_ready(self) -> None:
        logger.info("Logged in as %s (%s)", self.user, self.user.id if self.user else "n/a")
        if self.commands_synced < self.expected_commands:
            logger.warning(
                "Guild command sync appears incomplete (%s/%s). Retrying sync once.",
                self.commands_synced,
                self.expected_commands,
            )
            await self.sync_guild_commands(reason="ready-retry")
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
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


async def get_log_channel(client: commands.Bot) -> discord.TextChannel | None:
    channel = client.get_channel(BOT_LOG_CHANNEL)
    if isinstance(channel, discord.TextChannel):
        return channel
    fetched = await client.fetch_channel(BOT_LOG_CHANNEL)
    if isinstance(fetched, discord.TextChannel):
        return fetched
    return None


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


@bot.tree.command(name="ping", description="Check if the bot is online.", guild=discord.Object(id=GUILD_ID))
async def ping(interaction: discord.Interaction) -> None:
    await interaction.response.send_message("WickedYoda's Little Helper is online.", ephemeral=True)
    await log_interaction(interaction, action="ping", success=True)


@bot.tree.command(name="shorten", description="Create a short URL.", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(url="URL to shorten using the configured shortener")
async def shorten(interaction: discord.Interaction, url: str) -> None:
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

    await interaction.response.defer(ephemeral=True)
    try:
        _, short_url = await asyncio.to_thread(create_short_url, normalized_url)
        await interaction.followup.send(f"Short URL: {short_url}", ephemeral=True)
        await log_interaction(
            interaction,
            action="shorten",
            reason=truncate_log_text(f"{normalized_url} -> {short_url}"),
            success=True,
        )
    except RuntimeError as exc:
        await interaction.followup.send(f"Failed to shorten URL: {exc}", ephemeral=True)
        await log_interaction(interaction, action="shorten", reason=truncate_log_text(str(exc)), success=False)


@bot.tree.command(name="expand", description="Expand a short code or short URL.", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(value="Short code (example: 1234) or full short URL")
async def expand(interaction: discord.Interaction, value: str) -> None:
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

    await interaction.response.defer(ephemeral=True)
    try:
        resolved_url = await asyncio.to_thread(expand_short_url, short_url)
        await interaction.followup.send(f"Expanded URL: {resolved_url}", ephemeral=True)
        await log_interaction(
            interaction,
            action="expand",
            reason=truncate_log_text(f"{short_url} -> {resolved_url}"),
            success=True,
        )
    except RuntimeError as exc:
        await interaction.followup.send(f"Failed to expand URL: {exc}", ephemeral=True)
        await log_interaction(interaction, action="expand", reason=truncate_log_text(str(exc)), success=False)


@bot.tree.command(name="uptime", description="Show current uptime monitor status.", guild=discord.Object(id=GUILD_ID))
async def uptime(interaction: discord.Interaction) -> None:
    if not UPTIME_STATUS_ENABLED:
        await reply_ephemeral(interaction, "Uptime status integration is disabled.")
        await log_interaction(interaction, action="uptime", reason="uptime integration disabled", success=False)
        return

    await interaction.response.defer(ephemeral=True)
    try:
        snapshot = await asyncio.to_thread(fetch_uptime_snapshot)
        summary = format_uptime_summary(snapshot)
        await interaction.followup.send(summary, ephemeral=True)
        counts = snapshot.get("counts", {})
        await log_interaction(
            interaction,
            action="uptime",
            reason=truncate_log_text(
                f"up={counts.get('up', 0)} down={counts.get('down', 0)} pending={counts.get('pending', 0)}"
            ),
            success=True,
        )
    except RuntimeError as exc:
        await interaction.followup.send(f"Failed to fetch uptime status: {exc}", ephemeral=True)
        await log_interaction(interaction, action="uptime", reason=truncate_log_text(str(exc)), success=False)


@bot.tree.command(name="kick", description="Kick a member from the server.", guild=discord.Object(id=GUILD_ID))
@app_commands.checks.has_permissions(kick_members=True)
@app_commands.describe(member="Member to kick", reason="Reason for the kick")
async def kick(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str | None = "No reason provided",
) -> None:
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
    if interaction.channel is None:
        await reply_ephemeral(interaction, "This command can only be used in a server channel.")
        await log_interaction(interaction, action="purge", reason="No channel context", success=False)
        return

    try:
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.followup.send(f"Deleted {len(deleted)} message(s).", ephemeral=True)
        await log_interaction(interaction, action="purge", reason=f"Deleted {len(deleted)} messages", success=True)
    except Exception as exc:
        await reply_ephemeral(interaction, f"Failed to purge messages: {exc}")
        await log_interaction(interaction, action="purge", reason=str(exc), success=False)


@kick.error
@ban.error
@timeout.error
@untimeout.error
@purge.error
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
