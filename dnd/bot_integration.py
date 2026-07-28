from __future__ import annotations

import asyncio
import datetime
from typing import Any, Dict, List, Optional

from dnd import proxy_render
from dnd.characters import find_character as find_character_repo
from dnd.chronicle_service import get_chronicle, update_chronicle, list_members, upsert_member
from dnd.proxy_service import add_proxy_identity, create_proxy, delete_proxy, get_proxy, list_proxies

DND_DB_PATH = "/app/data/dnd.db"


def _utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


async def _post_proxy_webhook(interaction: Any, name: str, message: str, character: Optional[str] = None) -> None:
    if interaction.guild is None:
        return
    proxy = get_proxy(DND_DB_PATH, int(interaction.guild.id), int(interaction.user.id), name)
    if not proxy:
        return
    display_name = proxy.get("name", name)
    avatar_url = proxy.get("avatar_url", "")
    if character:
        char = find_character_repo(DND_DB_PATH, int(interaction.guild.id), int(interaction.user.id), character)
        if char:
            display_name = f"{display_name} ({char['name']})"
    channel = interaction.channel
    if not hasattr(channel, "create_webhook"):
        return
    if not hasattr(channel, "permissions_for"):
        return
    bot_member = interaction.guild.me
    if bot_member is None:
        return
    if not channel.permissions_for(bot_member).manage_webhooks:
        return
    webhook = None
    try:
        webhooks = await channel.webhooks()
        webhook = next((w for w in webhooks if w.name == "DND Proxy"), None)
    except Exception:
        webhook = None
    if webhook is None:
        try:
            webhook = await channel.create_webhook(name="DND Proxy", reason="DND proxy command")
        except Exception:
            return
    await webhook.send(content=message, username=display_name, avatar_url=avatar_url, wait=True)


def _proxy_commands(bot: Any, helpers: Dict[str, Any]) -> None:
    dnd_group = bot.tree.get_command("dnd")
    if dnd_group is None:
        return

    reply_ephemeral = helpers.get("reply_ephemeral")
    log_interaction = helpers.get("log_interaction")
    ensure_interaction_command_access = helpers.get("ensure_interaction_command_access")

    async def _log(action: str, reason: str = "", *, success: bool = True) -> None:
        if log_interaction is None:
            return
        await log_interaction({"guild": interaction.guild, "user": interaction.user}, action=action, reason=reason, success=success)

    @dnd_group.command(name="proxy", description="Proxy identity helpers.")
    async def proxy_command(interaction: Any, action: str = "create", name: str = "", template: str = "{name}: {content}", avatar_url: str = "") -> None:
        if ensure_interaction_command_access and not await ensure_interaction_command_access(interaction, "dnd_proxy"):
            return
        if not interaction.guild:
            if reply_ephemeral:
                await reply_ephemeral(interaction, "Guild context is required for proxies.")
            return
        if action == "create":
            if not name:
                if reply_ephemeral:
                    await reply_ephemeral(interaction, "Provide a proxy name.")
                return
            proxy = add_proxy_identity(DND_DB_PATH, int(interaction.guild.id), int(interaction.user.id), name, name, avatar_url=avatar_url)
            if reply_ephemeral:
                await reply_ephemeral(interaction, f"Proxy `{proxy['name']}` created.")
            await _log("dnd_proxy_create", f"name={name}")
        elif action == "send":
            if not name:
                if reply_ephemeral:
                    await reply_ephemeral(interaction, "Provide a proxy name and message.")
                return
            await _post_proxy_webhook(interaction, name, template, None)
            await _log("dnd_proxy_send", f"name={name}")
        elif action == "list":
            proxies = list_proxies(DND_DB_PATH, int(interaction.guild.id), int(interaction.user.id))
            if not proxies:
                if reply_ephemeral:
                    await reply_ephemeral(interaction, "You have no proxies.")
            else:
                lines = "\n".join(f"- {p['name']}" for p in proxies)
                if reply_ephemeral:
                    await reply_ephemeral(interaction, lines)
                else:
                    await interaction.response.send_message(lines, ephemeral=True)
        elif action == "delete":
            if not name:
                if reply_ephemeral:
                    await reply_ephemeral(interaction, "Provide a proxy name to delete.")
                return
            deleted = delete_proxy(DND_DB_PATH, int(interaction.guild.id), int(interaction.user.id), name)
            if reply_ephemeral:
                await reply_ephemeral(interaction, "Proxy deleted." if deleted else "Proxy not found.")
        else:
            if reply_ephemeral:
                await reply_ephemeral(interaction, "Use `create`, `send`, `list`, or `delete`.")




