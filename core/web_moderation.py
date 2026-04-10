import asyncio
import logging
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import discord

_BOT: Any | None = None
_LOGGER: logging.Logger | None = None
_RECORD_ACTION_SAFE: Callable[..., None] | None = None


def configure_web_moderation(*, bot: Any, logger: logging.Logger, record_action_safe: Callable[..., None]) -> None:
    global _BOT, _LOGGER, _RECORD_ACTION_SAFE
    _BOT = bot
    _LOGGER = logger
    _RECORD_ACTION_SAFE = record_action_safe


def _require_runtime() -> tuple[Any, logging.Logger, Callable[..., None]]:
    if _BOT is None or _LOGGER is None or _RECORD_ACTION_SAFE is None:
        raise RuntimeError("Web moderation runtime has not been configured.")
    return _BOT, _LOGGER, _RECORD_ACTION_SAFE


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


async def _leave_guild(guild_id: int) -> None:
    bot, _, _ = _require_runtime()
    guild = bot.get_guild(int(guild_id))
    if guild is None:
        raise RuntimeError("Guild is not currently available to this bot.")
    await guild.leave()


async def _resolve_web_moderation_target(guild_id: int, member_id: int) -> tuple[discord.Guild, discord.Member, discord.Member]:
    bot, _, _ = _require_runtime()
    guild = bot.get_guild(int(guild_id))
    if guild is None:
        raise RuntimeError("Guild is not currently available to this bot.")
    bot_member = guild.me
    if bot_member is None:
        raise RuntimeError("Bot member is not available for this guild.")

    target = guild.get_member(int(member_id))
    if target is None:
        try:
            target = await guild.fetch_member(int(member_id))
        except discord.NotFound as exc:
            raise RuntimeError("Selected member is no longer in this guild.") from exc
        except discord.Forbidden as exc:
            raise RuntimeError("Bot is not allowed to inspect guild members in this guild.") from exc
        except discord.HTTPException as exc:
            raise RuntimeError("Failed to resolve the selected member.") from exc

    if target.bot:
        raise RuntimeError("Bot accounts cannot be moderated from the web admin.")
    if target.id == guild.owner_id:
        raise RuntimeError("The server owner cannot be moderated.")
    if target.id == bot_member.id:
        raise RuntimeError("The bot cannot moderate itself.")
    if bot_member.top_role <= target.top_role:
        raise RuntimeError("Bot can only moderate members below its top role.")
    return guild, target, bot_member


async def _kick_guild_member(guild_id: int, member_id: int, reason: str) -> dict:
    guild, target, bot_member = await _resolve_web_moderation_target(guild_id, member_id)
    if not bot_member.guild_permissions.kick_members:
        raise RuntimeError("Bot does not have permission to kick members in this guild.")
    await target.kick(reason=reason)
    return {"ok": True, "member_id": target.id, "member_name": str(target), "guild_id": guild.id, "guild_name": guild.name}


async def _ban_guild_member(guild_id: int, member_id: int, reason: str, delete_days: int) -> dict:
    guild, target, bot_member = await _resolve_web_moderation_target(guild_id, member_id)
    if not bot_member.guild_permissions.ban_members:
        raise RuntimeError("Bot does not have permission to ban members in this guild.")
    delete_message_seconds = max(0, min(7, int(delete_days))) * 24 * 60 * 60
    await guild.ban(target, reason=reason, delete_message_seconds=delete_message_seconds)
    return {"ok": True, "member_id": target.id, "member_name": str(target), "guild_id": guild.id, "guild_name": guild.name}


async def _timeout_guild_member(guild_id: int, member_id: int, reason: str, minutes: int) -> dict:
    guild, target, bot_member = await _resolve_web_moderation_target(guild_id, member_id)
    if not bot_member.guild_permissions.moderate_members:
        raise RuntimeError("Bot does not have permission to timeout members in this guild.")
    timeout_minutes = max(1, min(40320, int(minutes)))
    until = discord.utils.utcnow() + timedelta(minutes=timeout_minutes)
    await target.edit(timed_out_until=until, reason=reason)
    return {
        "ok": True,
        "member_id": target.id,
        "member_name": str(target),
        "guild_id": guild.id,
        "guild_name": guild.name,
        "minutes": timeout_minutes,
    }


async def _untimeout_guild_member(guild_id: int, member_id: int, reason: str) -> dict:
    guild, target, bot_member = await _resolve_web_moderation_target(guild_id, member_id)
    if not bot_member.guild_permissions.moderate_members:
        raise RuntimeError("Bot does not have permission to remove timeouts in this guild.")
    await target.edit(timed_out_until=None, reason=reason)
    return {"ok": True, "member_id": target.id, "member_name": str(target), "guild_id": guild.id, "guild_name": guild.name}


def run_web_leave_guild(actor_email: str, guild_id: int) -> dict:
    bot, logger, record_action_safe = _require_runtime()
    selected_guild_id = int(guild_id)
    guild = bot.get_guild(selected_guild_id)
    if guild is None:
        return {"ok": False, "error": "Guild is not currently available to this bot."}
    guild_name = guild.name
    try:
        future = asyncio.run_coroutine_threadsafe(_leave_guild(selected_guild_id), bot.loop)
        future.result(timeout=30)
    except Exception as exc:
        logger.exception("Failed to leave guild %s via web admin (%s): %s", selected_guild_id, actor_email, exc)
        return {"ok": False, "error": f"Failed to leave guild: {exc}"}
    record_action_safe(
        action="leave_guild",
        status="success",
        moderator=actor_email,
        target=f"{guild_name} ({selected_guild_id})",
        reason="Web admin leave guild request",
        guild=str(selected_guild_id),
    )
    return {"ok": True, "message": f"Left guild {guild_name}.", "guild_id": selected_guild_id}


def run_web_kick_member(actor_email: str, guild_id: int, member_id: int, reason: str | None = None) -> dict:
    bot, logger, record_action_safe = _require_runtime()
    selected_guild_id = int(guild_id)
    selected_member_id = int(member_id)
    kick_reason = (reason or "").strip() or "Web admin kick request"
    try:
        future = asyncio.run_coroutine_threadsafe(_kick_guild_member(selected_guild_id, selected_member_id, kick_reason), bot.loop)
        result = future.result(timeout=30)
    except Exception as exc:
        logger.exception(
            "Failed to kick member %s in guild %s via web admin (%s): %s",
            selected_member_id,
            selected_guild_id,
            actor_email,
            exc,
        )
        return {"ok": False, "error": f"Failed to kick member: {exc}"}
    record_action_safe(
        action="kick_member_web",
        status="success",
        moderator=actor_email,
        target=f"{result['member_name']} ({result['member_id']})",
        reason=kick_reason,
        guild=str(selected_guild_id),
    )
    return {
        "ok": True,
        "message": f"Kicked {result['member_name']} from {result['guild_name']}.",
        "member_id": result["member_id"],
        "guild_id": result["guild_id"],
    }


def run_web_ban_member(actor_email: str, guild_id: int, member_id: int, reason: str | None = None, delete_days: int = 0) -> dict:
    bot, logger, record_action_safe = _require_runtime()
    selected_guild_id = int(guild_id)
    selected_member_id = int(member_id)
    ban_reason = (reason or "").strip() or "Web admin ban request"
    delete_days_value = max(0, min(7, int(delete_days)))
    try:
        future = asyncio.run_coroutine_threadsafe(
            _ban_guild_member(selected_guild_id, selected_member_id, ban_reason, delete_days_value),
            bot.loop,
        )
        result = future.result(timeout=30)
    except Exception as exc:
        logger.exception(
            "Failed to ban member %s in guild %s via web admin (%s): %s",
            selected_member_id,
            selected_guild_id,
            actor_email,
            exc,
        )
        return {"ok": False, "error": f"Failed to ban member: {exc}"}
    record_action_safe(
        action="ban_member_web",
        status="success",
        moderator=actor_email,
        target=f"{result['member_name']} ({result['member_id']})",
        reason=f"delete_days={delete_days_value}; {ban_reason}",
        guild=str(selected_guild_id),
    )
    return {
        "ok": True,
        "message": f"Banned {result['member_name']} from {result['guild_name']}.",
        "member_id": result["member_id"],
        "guild_id": result["guild_id"],
    }


def run_web_timeout_member(actor_email: str, guild_id: int, member_id: int, minutes: int, reason: str | None = None) -> dict:
    bot, logger, record_action_safe = _require_runtime()
    selected_guild_id = int(guild_id)
    selected_member_id = int(member_id)
    timeout_minutes = max(1, min(40320, int(minutes)))
    timeout_reason = (reason or "").strip() or "Web admin timeout request"
    try:
        future = asyncio.run_coroutine_threadsafe(
            _timeout_guild_member(selected_guild_id, selected_member_id, timeout_reason, timeout_minutes),
            bot.loop,
        )
        result = future.result(timeout=30)
    except Exception as exc:
        logger.exception(
            "Failed to timeout member %s in guild %s via web admin (%s): %s",
            selected_member_id,
            selected_guild_id,
            actor_email,
            exc,
        )
        return {"ok": False, "error": f"Failed to timeout member: {exc}"}
    record_action_safe(
        action="timeout_member_web",
        status="success",
        moderator=actor_email,
        target=f"{result['member_name']} ({result['member_id']})",
        reason=f"minutes={result['minutes']}; {timeout_reason}",
        guild=str(selected_guild_id),
    )
    return {
        "ok": True,
        "message": f"Timed out {result['member_name']} for {result['minutes']} minute(s).",
        "member_id": result["member_id"],
        "guild_id": result["guild_id"],
    }


def run_web_untimeout_member(actor_email: str, guild_id: int, member_id: int, reason: str | None = None) -> dict:
    bot, logger, record_action_safe = _require_runtime()
    selected_guild_id = int(guild_id)
    selected_member_id = int(member_id)
    untimeout_reason = (reason or "").strip() or "Web admin untimeout request"
    try:
        future = asyncio.run_coroutine_threadsafe(
            _untimeout_guild_member(selected_guild_id, selected_member_id, untimeout_reason),
            bot.loop,
        )
        result = future.result(timeout=30)
    except Exception as exc:
        logger.exception(
            "Failed to remove timeout for member %s in guild %s via web admin (%s): %s",
            selected_member_id,
            selected_guild_id,
            actor_email,
            exc,
        )
        return {"ok": False, "error": f"Failed to remove timeout: {exc}"}
    record_action_safe(
        action="untimeout_member_web",
        status="success",
        moderator=actor_email,
        target=f"{result['member_name']} ({result['member_id']})",
        reason=untimeout_reason,
        guild=str(selected_guild_id),
    )
    return {
        "ok": True,
        "message": f"Removed timeout for {result['member_name']}.",
        "member_id": result["member_id"],
        "guild_id": result["guild_id"],
    }
