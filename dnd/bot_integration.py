from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

from dnd import characters as character_repo
from dnd import chronicle_service
from dnd import general_roll
from dnd import initiative as initiative_domain
from dnd.characters import delete_character as delete_char_repo, find_character, list_characters, save_character
from dnd.chronicle_service import add_xp, create_reward_rule, evaluate_rewards, get_chronicle, list_xp_entries, update_chronicle, upsert_member, upsert_reward_tier
from dnd.initiative_repo import load_tracker, save_tracker
from dnd.proxy_service import add_proxy_identity, create_proxy, delete_proxy, get_proxy, list_proxies
from dnd import roll_20th as d20

DND_DB_PATH = "/app/data/dnd.db"


def _utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def ensure_dnd_schema() -> None:
    from dnd.chronicle_schema import ensure_schema as ensure_chronicle_schema
    from dnd.characters import ensure_schema as ensure_character_schema
    from dnd.initiative_repo import ensure_schema as ensure_init_schema
    ensure_chronicle_schema(DND_DB_PATH)
    ensure_character_schema(DND_DB_PATH)
    ensure_init_schema(DND_DB_PATH)


def register_dnd_commands(bot: Any, helpers: Optional[Dict[str, Any]] = None) -> None:
    bound: Dict[str, Any] = {
        "reply_ephemeral": None,
        "log_interaction": None,
        "ensure_interaction_command_access": None,
    }
    if helpers:
        bound.update(helpers)
    reply_ephemeral = bound["reply_ephemeral"]
    log_interaction = bound["log_interaction"]
    ensure_interaction_command_access = bound["ensure_interaction_command_access"]

    async def _log(interaction: Any, action: str, reason: str = "", *, success: bool = True) -> None:
        if log_interaction is None:
            return
        await log_interaction({"guild": getattr(interaction, "guild", None), "user": getattr(interaction, "user", None)}, action=action, reason=reason, success=success)

    dnd_group = bot.tree.get_command("dnd")
    if dnd_group is None:
        raise RuntimeError("Missing `/dnd` application group.")

    @dnd_group.command(name="roll", description="20th Anniversary Edition dice roll.")
    async def dice_roll(interaction: Any, pool: int, difficulty: int, willpower: bool = False, modifier: int = 0, speciality: str | None = None, nightmare: int = 0, no_botch: bool = False, character: str | None = None, notes: str | None = None) -> None:  # type: ignore[misc]
        if ensure_interaction_command_access and not await ensure_interaction_command_access(interaction, "dnd_roll"):
            return
        try:
            validated_pool = d20.parse_20th_pool(str(pool or ""))
            validated_diff = d20.parse_difficulty(str(difficulty or ""))
            validated_nightmare = max(0, min(int(nightmare or 0), validated_pool))
        except ValueError as exc:
            if reply_ephemeral:
                await reply_ephemeral(interaction, str(exc))
            await _log(interaction, "dnd_roll", str(exc), success=False)
            return
        result = d20.roll_pool(validated_pool, validated_diff, validated_nightmare)
        result.mod = int(modifier)
        result.willpower = bool(willpower)
        result.spec = str(speciality or "").strip()
        result.cancel_ones = bool(no_botch)
        result.compute()
        author_name = str(getattr(interaction.user, "display_name", ""))
        author_icon = getattr(getattr(interaction.user, "display_avatar", None), "url", None)
        char_name = str(character).strip() if character else None
        if char_name and hasattr(interaction, "guild_id") and interaction.guild_id is not None:
            resolved = find_character(DND_DB_PATH, int(interaction.guild_id), int(interaction.user.id), char_name)
            if resolved:
                char_name = resolved["name"]
        try:
            import discord as _discord
            emb = d20.build_dice_embed(result, author_name=author_name, author_icon=author_icon, character_name=char_name, notes=notes)
            await interaction.response.send_message(embed=_discord.Embed.from_dict(emb))
        except Exception:
            await interaction.response.send_message(str(result.successes))
        await _log(interaction, "dnd_roll", f"pool={validated_pool} diff={validated_diff} result={result.successes}", success=True)

    @dnd_group.command(name="general", description="General multi-set dice roll.")
    async def dice_general(interaction: Any, dice_set_01: str, modifier: int = 0, dice_set_02: str | None = None, dice_set_03: str | None = None, dice_set_04: str | None = None, dice_set_05: str | None = None, difficulty: int | None = None, notes: str | None = None) -> None:  # type: ignore[misc]
        if ensure_interaction_command_access and not await ensure_interaction_command_access(interaction, "dnd_general"):
            return
        try:
            sets = general_roll.parse_sets(dice_set_01, dice_set_02, dice_set_03, dice_set_04, dice_set_05)
        except ValueError as exc:
            if reply_ephemeral:
                await reply_ephemeral(interaction, str(exc))
            await _log(interaction, "dnd_general", str(exc), success=False)
            return
        author_name = str(getattr(interaction.user, "display_name", ""))
        author_icon = getattr(getattr(interaction.user, "display_avatar", None), "url", None)
        emb = general_roll.build_general_embed(sets, modifier=modifier, difficulty=difficulty, notes=notes, author_name=author_name, author_icon=author_icon)
        try:
            import discord as _discord
            await interaction.response.send_message(embed=_discord.Embed.from_dict(emb))
        except Exception:
            await interaction.response.send_message(str(emb))
        await _log(interaction, "dnd_general", f"sets={len(sets)}", success=True)

    @dnd_group.command(name="initiative", description="Initiative tracker helpers.")
    async def dice_initiative(interaction: Any, action: str = "new", dex_wits: int = 0, character: str | None = None, notes: str | None = None) -> None:  # type: ignore[misc]
        if ensure_interaction_command_access and not await ensure_interaction_command_access(interaction, "dnd_initiative"):
            return
        if hasattr(interaction, "guild") and interaction.guild is not None and hasattr(interaction.guild, "id") and interaction.guild.id is not None:
            channel_id = int(interaction.channel_id)
            guild_id = int(interaction.guild.id)
            owner_id = int(interaction.user.id)
        else:
            if reply_ephemeral:
                await reply_ephemeral(interaction, "This command can only be used in a server.")
            return
        if action == "new":
            if load_tracker(DND_DB_PATH, channel_id):
                if reply_ephemeral:
                    await reply_ephemeral(interaction, "This channel already has an initiative tracker.")
                return
            tracker = initiative_domain.InitiativeTracker(channel_id=channel_id, guild_id=guild_id, owner_id=owner_id)
            tracker.characters.append(initiative_domain.InitiativeCharacter(member_id=owner_id, display_name=str(interaction.user), dex_wits=max(1, int(dex_wits or 0))))
            tracker.characters[-1].compute()
            save_tracker(DND_DB_PATH, tracker)
            if reply_ephemeral:
                await reply_ephemeral(interaction, "Started a new initiative tracker.")
        elif action == "roll":
            tracker = load_tracker(DND_DB_PATH, channel_id)
            if not tracker:
                if reply_ephemeral:
                    await reply_ephemeral(interaction, "No tracker in this channel. Start with `new`.")
                return
            char = initiative_domain.InitiativeCharacter(member_id=owner_id, display_name=str(interaction.user), dex_wits=max(1, int(dex_wits or 0)))
            char.compute()
            tracker.characters.append(char)
            save_tracker(DND_DB_PATH, tracker)
            order = sorted(tracker.characters, key=lambda x: (-x.total, x.member_id))
            lines = [f"Initiative rolled for {char.display_name}: **{char.total}**", "Order:"]
            lines.extend(f"- {c.display_name}: {c.total}" for c in order)
            await interaction.response.send_message("\n".join(lines))
            await _log(interaction, "dnd_initiative", f"action={action} total={char.total}", success=True)
        else:
            if reply_ephemeral:
                await reply_ephemeral(interaction, "Use `new` to start or `roll` to roll into the current tracker.")

    @dnd_group.command(name="character", description="Storage-backed character helpers.")
    async def dice_character(interaction: Any, action: str = "find", splat: str | None = None, name: str | None = None) -> None:  # type: ignore[misc]
        if ensure_interaction_command_access and not await ensure_interaction_command_access(interaction, "dnd_character"):
            return
        if action in {"find", "list", "delete"} and not hasattr(interaction, "guild"):
            if reply_ephemeral:
                await reply_ephemeral(interaction, "Guild context is required for character commands.")
            return
        if action == "find":
            target = name or (splat or "")
            if not target:
                if reply_ephemeral:
                    await reply_ephemeral(interaction, "Provide a character name.")
                return
            result = find_character(DND_DB_PATH, int(interaction.guild.id), int(interaction.user.id), target)
            if not result:
                if reply_ephemeral:
                    await reply_ephemeral(interaction, "No matching character found.")
            else:
                if reply_ephemeral:
                    await reply_ephemeral(interaction, f"Found `{result['name']}` ({result['splat']}).")
                else:
                    await interaction.response.send_message(f"Found `{result['name']}` ({result['splat']}).", ephemeral=True)
        elif action == "list":
            results = list_characters(DND_DB_PATH, int(interaction.guild.id), int(interaction.user.id))
            if not results:
                if reply_ephemeral:
                    await reply_ephemeral(interaction, "You have no saved characters on this server.")
            else:
                lines = "\n".join(f"- {r['name']} ({r['splat']})" for r in results)
                if reply_ephemeral:
                    await reply_ephemeral(interaction, lines)
                else:
                    await interaction.response.send_message(lines, ephemeral=True)
        elif action == "delete":
            target = name or (splat or "")
            if not target:
                if reply_ephemeral:
                    await reply_ephemeral(interaction, "Provide a character name to delete.")
                return
            deleted = delete_char_repo(DND_DB_PATH, int(interaction.guild.id), int(interaction.user.id), target)
            if reply_ephemeral:
                await reply_ephemeral(interaction, "Character deleted." if deleted else "Character not found.")
        else:
            if reply_ephemeral:
                await reply_ephemeral(interaction, "Character storage is ready; full editor commands are in progress.")

    @dnd_group.command(name="proxy", description="Proxy identity helpers.")
    async def proxy_command(interaction: Any, action: str = "create", name: str = "", template: str = "{name}: {content}", avatar_url: str = "") -> None:  # type: ignore[misc]
        if ensure_interaction_command_access and not await ensure_interaction_command_access(interaction, "dnd_proxy"):
            return
        if not getattr(interaction, "guild", None):
            if reply_ephemeral:
                await reply_ephemeral(interaction, "Guild context is required for proxies.")
            return
        if action == "create":
            if not name:
                if reply_ephemeral:
                    await reply_ephemeral(interaction, "Provide a proxy name.")
                return
            proxy = proxy_service.add_proxy_identity(DND_DB_PATH, int(interaction.guild.id), int(interaction.user.id), name, name, avatar_url=avatar_url)
            if reply_ephemeral:
                await reply_ephemeral(interaction, f"Proxy `{proxy['name']}` created.")
            await _log(interaction, "dnd_proxy_create", f"name={name}")
        elif action == "send":
            if not name:
                if reply_ephemeral:
                    await reply_ephemeral(interaction, "Provide a proxy name and message.")
                return
            if not hasattr(interaction, "channel") or not hasattr(interaction, "guild") or interaction.guild is None:
                if reply_ephemeral:
                    await reply_ephemeral(interaction, "This command must be used in a server channel.")
                return
            proxy = proxy_service.get_proxy(DND_DB_PATH, int(interaction.guild.id), int(interaction.user.id), name)
            if not proxy:
                if reply_ephemeral:
                    await reply_ephemeral(interaction, "Proxy not found. Create it first.")
                return
            display_name = proxy.get("name", name)
            avatar_url = proxy.get("avatar_url", "")
            channel = interaction.channel
            if not all(hasattr(channel, attr) for attr in ("create_webhook", "permissions_for", "webhooks")):
                if reply_ephemeral:
                    await reply_ephemeral(interaction, "Proxy sending is not supported in this channel type.")
                return
            bot_member = interaction.guild.me
            if bot_member is None or not channel.permissions_for(bot_member).manage_webhooks:
                if reply_ephemeral:
                    await reply_ephemeral(interaction, "Bot needs Manage Webhooks here.")
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
                    if reply_ephemeral:
                        await reply_ephemeral(interaction, "Failed to create webhook.")
                    return
            await webhook.send(content=template, username=display_name, avatar_url=avatar_url, wait=True)
            await _log(interaction, "dnd_proxy_send", f"name={name}")
        elif action == "list":
            proxies = proxy_service.list_proxies(DND_DB_PATH, int(interaction.guild.id), int(interaction.user.id))
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
            deleted = proxy_service.delete_proxy(DND_DB_PATH, int(interaction.guild.id), int(interaction.user.id), name)
            if reply_ephemeral:
                await reply_ephemeral(interaction, "Proxy deleted." if deleted else "Proxy not found.")
        else:
            if reply_ephemeral:
                await reply_ephemeral(interaction, "Use `create`, `send`, `list`, or `delete`.")

    @dnd_group.command(name="chronicle", description="Chronicle server helpers.")
    async def dice_chronicle(interaction: Any, action: str = "create", name: str = "Chronicle") -> None:  # type: ignore[misc]
        if ensure_interaction_command_access and not await ensure_interaction_command_access(interaction, "dnd_chronicle"):
            return
        if not getattr(interaction, "guild", None):
            if reply_ephemeral:
                await reply_ephemeral(interaction, "Guild context is required for chronicle commands.")
            return
        guild_id = int(interaction.guild.id)
        owner_id = int(interaction.user.id)
        if action == "create":
            data = chronicle_service.create_chronicle(DND_DB_PATH, guild_id, owner_id, name=name)
            if reply_ephemeral:
                await reply_ephemeral(interaction, f"Created chronicle `{data['name']}`.")
        elif action == "show":
            data = chronicle_service.get_chronicle(DND_DB_PATH, guild_id)
            if not data:
                if reply_ephemeral:
                    await reply_ephemeral(interaction, "No chronicle in this server.")
                return
            monitored = len(data.get("monitored_channel_ids", []))
            excluded = len(data.get("excluded_channel_ids", []))
            lines = [
                f"Chronicle: {data['name']}",
                f"XP tracking: {data['xp_tracking_enabled']}",
                f"Auto rewards: {data['auto_reward_enabled']}",
                f"Monitored channels: {monitored}",
                f"Excluded channels: {excluded}",
            ]
            if reply_ephemeral:
                await reply_ephemeral(interaction, "\n".join(lines))
            else:
                await interaction.response.send_message("\n".join(lines), ephemeral=True)
        elif action == "update":
            chronicle_service.update_chronicle(DND_DB_PATH, guild_id, name=name, owner_id=owner_id)
            if reply_ephemeral:
                await reply_ephemeral(interaction, "Updated chronicle settings.")
        else:
            if reply_ephemeral:
                await reply_ephemeral(interaction, "Use `create`, `show`, or `update`.")

    @dnd_group.command(name="xp", description="Experience point helpers.")
    async def dice_xp(interaction: Any, action: str = "add", amount: float = 1, reason: str = "") -> None:  # type: ignore[misc]
        if ensure_interaction_command_access and not await ensure_interaction_command_access(interaction, "dnd_xp"):
            return
        if not getattr(interaction, "guild", None):
            if reply_ephemeral:
                await reply_ephemeral(interaction, "Guild context is required for XP commands.")
            return
        guild_id = int(interaction.guild.id)
        user_id = int(interaction.user.id)
        if action == "add":
            add_xp(DND_DB_PATH, guild_id, user_id, float(amount), reason or "XP from command")
            if reply_ephemeral:
                await reply_ephemeral(interaction, f"Added {amount} XP.")
        elif action == "history":
            entries = list_xp_entries(DND_DB_PATH, guild_id, user_id)
            if not entries:
                if reply_ephemeral:
                    await reply_ephemeral(interaction, "No XP history.")
            else:
                lines = "\n".join(f"- {e['amount']}: {e['reason']}" for e in entries[-10:])
                if reply_ephemeral:
                    await reply_ephemeral(interaction, lines)
                else:
                    await interaction.response.send_message(lines, ephemeral=True)
        else:
            if reply_ephemeral:
                await reply_ephemeral(interaction, "Use `add` or `history`.")

    @dnd_group.command(name="reward", description="Auto reward helpers.")
    async def dice_reward(interaction: Any, action: str = "status", rule_name: str = "", threshold: int = 10, reward: float = 1) -> None:  # type: ignore[misc]
        if ensure_interaction_command_access and not await ensure_interaction_command_access(interaction, "dnd_reward"):
            return
        if not getattr(interaction, "guild", None):
            if reply_ephemeral:
                await reply_ephemeral(interaction, "Guild context is required for reward commands.")
            return
        guild_id = int(interaction.guild.id)
        user_id = int(interaction.user.id)
        if action == "create":
            if not rule_name:
                if reply_ephemeral:
                    await reply_ephemeral(interaction, "Provide rule_name.")
                return
            rule = create_reward_rule(DND_DB_PATH, guild_id, rule_name)
            upsert_reward_tier(DND_DB_PATH, rule["id"], idx=0, threshold=int(threshold), reward=float(reward))
            if reply_ephemeral:
                await reply_ephemeral(interaction, f"Created reward rule `{rule_name}`.")
        elif action == "status":
            stats = evaluate_rewards(DND_DB_PATH, guild_id, user_id)
            if not stats:
                content = "No active reward rules or no XP tracking."
            else:
                lines = []
                for r in stats:
                    pct = int(min(100, r.get("current_count", 0) / max(1, r.get("threshold", 1)) * 100))
                    lines.append(f"- {r.get('name')}: {r.get('current_count')}/{r.get('threshold')} ({pct}%)")
                content = "\n".join(lines)
            if reply_ephemeral:
                await reply_ephemeral(interaction, content)
            else:
                await interaction.response.send_message(content, ephemeral=True)
        else:
            if reply_ephemeral:
                await reply_ephemeral(interaction, "Use `create` or `status`.")
