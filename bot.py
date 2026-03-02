import logging
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional

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

DATA_DIR = os.getenv("DATA_DIR", "data")
ACTION_DB_PATH = os.path.join(DATA_DIR, "mod_actions.db")
WEB_ENABLED = env_bool("WEB_ENABLED", True)
WEB_BIND_HOST = os.getenv("WEB_BIND_HOST", "0.0.0.0")
WEB_PORT = env_int("WEB_PORT", 8080)

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.messages = True
intents.message_content = False


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
                        datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                        action,
                        status,
                        moderator,
                        target,
                        reason,
                        guild,
                    ),
                )
                conn.commit()


ACTION_STORE = ActionStore(ACTION_DB_PATH)


class ModerationBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(command_prefix="!", intents=intents)
        self.guild_object = discord.Object(id=GUILD_ID)
        self.commands_synced = 0
        self.started_at = datetime.now(timezone.utc)
        self.web_thread: Optional[threading.Thread] = None

    async def setup_hook(self) -> None:
        self.tree.copy_global_to(guild=self.guild_object)
        synced = await self.tree.sync(guild=self.guild_object)
        self.commands_synced = len(synced)
        logger.info("Synced %s command(s) to guild %s", self.commands_synced, GUILD_ID)
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


async def get_log_channel(client: commands.Bot) -> Optional[discord.TextChannel]:
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
    target: Optional[discord.abc.User] = None,
    reason: Optional[str] = None,
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
    description = (
        f"Action: `{action}`\n"
        f"Status: **{status}**\n"
        f"Moderator: {actor_mention}\n"
        f"Guild: {guild_name}{target_text}{reason_text}"
    )
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


@bot.tree.command(name="kick", description="Kick a member from the server.", guild=discord.Object(id=GUILD_ID))
@app_commands.checks.has_permissions(kick_members=True)
@app_commands.describe(member="Member to kick", reason="Reason for the kick")
async def kick(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: Optional[str] = "No reason provided",
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
    reason: Optional[str] = "No reason provided",
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
    reason: Optional[str] = "No reason provided",
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
    reason: Optional[str] = "No reason provided",
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
