from __future__ import annotations

from typing import Optional


def render_proxy_payload(proxy: dict, content: str) -> tuple[str, str, str]:
    display_name = proxy.get("name", "Proxy")
    avatar_url = proxy.get("avatar_url", "")
    template = proxy.get("template", "{name}: {content}")
    rendered = template.replace("{name}", display_name).replace("{content}", content)
    return display_name, avatar_url, rendered


async def proxy_now(interaction: "discord.Interaction", name: str, message: str, character: Optional[str] = None, db_path: Optional[str] = None, discover_webhook: bool = True) -> None:
    import discord
    from dnd import proxy_service as _proxy_service
    from dnd.characters import find_character as _find_character
    path = db_path or "/app/data/dnd.db"
    proxy = _proxy_service.get_proxy(path, int(interaction.guild.id), int(interaction.user.id), name)
    if not proxy:
        return
    display_name = proxy.get("name", name)
    avatar_url = proxy.get("avatar_url", "")
    if character:
        char = _find_character(path, int(interaction.guild.id), int(interaction.user.id), character)
        if char:
            display_name = f"{display_name} ({char['name']})"
    channel = interaction.channel
    bot_member = interaction.guild.me
    if not isinstance(channel, (discord.TextChannel, discord.Thread)):
        return
    if not channel.permissions_for(bot_member).manage_webhooks:
        return
    webhook = None
    if discover_webhook:
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
