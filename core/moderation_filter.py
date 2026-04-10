from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import discord

ActionStoreLike = Any
LogActionCallable = Callable[[discord.Client, str, str, discord.Color, int | None], Awaitable[None]]
RecordActionCallable = Callable[..., None]
TruncateCallable = Callable[[str], str]


async def apply_moderation_filter(
    message: discord.Message,
    *,
    action_store: ActionStoreLike,
    log_action: LogActionCallable,
    record_action_safe: RecordActionCallable,
    truncate_log_text: TruncateCallable,
    logger: Any,
    bot_client: discord.Client,
) -> None:
    if not message.guild or not isinstance(message.author, discord.Member):
        return
    if message.author.guild_permissions.administrator or message.author.guild_permissions.manage_messages:
        return
    try:
        settings = action_store.get_guild_settings(guild_id=message.guild.id)
    except Exception:
        logger.exception("Failed to load guild settings for moderation filter (guild=%s).", message.guild.id)
        return
    if not int(settings.get("moderation_enabled", 0) or 0):
        return
    words = [str(value).strip().lower() for value in (settings.get("moderation_words") or []) if str(value).strip()]
    if not words:
        return
    content = (message.content or "").strip()
    if not content:
        return
    content_lower = content.lower()
    matched_word = ""
    for word in words:
        if re.search(rf"(?<!\\w){re.escape(word)}(?!\\w)", content_lower):
            matched_word = word
            break
    if not matched_word:
        return
    action_store.record_moderation_warning(
        guild_id=message.guild.id,
        user_id=message.author.id,
        message_id=message.id if getattr(message, "id", None) else None,
        channel_id=message.channel.id if getattr(message.channel, "id", None) else None,
        matched_word=matched_word,
    )
    window_hours = int(settings.get("moderation_warning_window_hours", 72) or 72)
    threshold = int(settings.get("moderation_warning_threshold", 3) or 3)
    since_dt = datetime.now(UTC) - timedelta(hours=max(1, window_hours))
    warning_count = action_store.count_recent_moderation_warnings(
        guild_id=message.guild.id,
        user_id=message.author.id,
        since_dt=since_dt,
    )
    reason_text = f"Matched banned word: {matched_word}"
    try:
        await message.author.send(
            f"Warning for {message.guild.name}: your message included a banned word.\n"
            f"Reason: {matched_word}\n"
            f"Warnings in last {window_hours}h: {warning_count}/{threshold}"
        )
    except Exception:
        logger.warning("Failed to DM warning to user %s in guild %s.", message.author.id, message.guild.id)
    await log_action(
        bot_client,
        "Moderation Warning",
        (
            "Action: `moderation_warn`\n"
            "Status: **Success**\n"
            f"Moderator: Auto\nGuild: {message.guild.name}\n"
            f"Target: {message.author.mention}\nReason: {reason_text}"
        ),
        discord.Color.gold(),
        guild_id=message.guild.id,
    )
    record_action_safe(
        action="moderation_warn",
        status="success",
        moderator="auto",
        target=f"{message.author} ({message.author.id})",
        reason=truncate_log_text(reason_text),
        guild=str(message.guild.id),
    )
    moderation_action = str(settings.get("moderation_action") or "timeout").lower()
    timeout_minutes = int(settings.get("moderation_timeout_minutes", 10) or 10)
    if warning_count >= threshold and moderation_action == "timeout":
        try:
            until = datetime.now(UTC) + timedelta(minutes=max(1, timeout_minutes))
            await message.author.timeout(until, reason="Automated moderation warnings threshold reached.")
            await log_action(
                bot_client,
                "Moderation Timeout",
                (
                    "Action: `moderation_timeout`\n"
                    "Status: **Success**\n"
                    f"Moderator: Auto\nGuild: {message.guild.name}\n"
                    f"Target: {message.author.mention}\nReason: {reason_text}\n"
                    f"Timeout: {timeout_minutes} minutes"
                ),
                discord.Color.red(),
                guild_id=message.guild.id,
            )
            record_action_safe(
                action="moderation_timeout",
                status="success",
                moderator="auto",
                target=f"{message.author} ({message.author.id})",
                reason=truncate_log_text(reason_text),
                guild=str(message.guild.id),
            )
        except Exception as exc:
            logger.warning(
                "Failed to timeout user %s in guild %s: %s",
                message.author.id,
                message.guild.id,
                exc,
            )
