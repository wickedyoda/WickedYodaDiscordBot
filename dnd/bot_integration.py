from __future__ import annotations

import datetime
import json
from typing import Any

import discord
from discord import app_commands

from dnd import chronicle_service, general_roll
from dnd import initiative as initiative_domain
from dnd import roll_20th as d20
from dnd.characters import delete_character as delete_char_repo
from dnd.characters import find_character, list_characters, save_character
from dnd.chronicle_service import (
    add_xp,
    create_reward_rule,
    evaluate_rewards,
    list_xp_entries,
    upsert_reward_tier,
)
from dnd.initiative_repo import load_tracker, save_tracker
from dnd.proxy_service import (
    add_proxy_identity,
    delete_proxy,
    get_proxy,
    list_proxies,
)

bound: dict[str, Any] | None = None

DND_DB_PATH = "/app/data/dnd.db"


def _utc_now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def ensure_dnd_schema() -> None:
    from dnd.characters import ensure_schema as ensure_character_schema
    from dnd.chronicle_schema import ensure_schema as ensure_chronicle_schema
    from dnd.initiative_repo import ensure_schema as ensure_init_schema
    ensure_chronicle_schema(DND_DB_PATH)
    ensure_character_schema(DND_DB_PATH)
    ensure_init_schema(DND_DB_PATH)


def _get_db_rows(db_path: str, sql: str, params: tuple) -> list[dict]:
    import sqlite3

    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    with conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def _parse_json_list(raw: str) -> list[str]:
    try:
        data = json.loads(raw or "[]")
    except Exception:
        data = []
    if isinstance(data, list):
        return [str(item) for item in data]
    return []


def _allowed_splats(db_path: str, guild_id: int) -> list[str]:
    rows = _get_db_rows(db_path, "SELECT allowed_splats FROM dnd_chronicles WHERE guild_id=?", (int(guild_id),))
    fallback = '["vampire20th"]'
    return _parse_json_list(rows[0]["allowed_splats"] if rows else fallback)


def _sheet_fields_for_splat(splat: str, name: str, data: dict) -> list[str]:
    if splat in {"vampire20th", "vampire"}:
        return [f"**{name}** - Vampire 20th", f"- Generation: {data.get('generation', '?')}", f"- Clan: {data.get('clan', '?')}", f"- Blood Pool: {data.get('blood', '?')}", f"- Embrace: {data.get('embrace', '?')}", f"- Sire: {data.get('sire', '?')}", f"- Path: {data.get('path', '?')}"]
    if splat in {"werewolf", "garou"}:
        return [f"**{name}** - Werewolf", f"- Tribe: {data.get('tribe', '?')}", f"- Auspice: {data.get('auspice', '?')}", f"- Breed: {data.get('breed', '?')}", f"- Gnosis: {data.get('gnosis', '?')}"]
    if splat in {"mage", "m20"}:
        return [f"**{name}** - Mage", f"- Tradition: {data.get('tradition', '?')}", f"- Essence: {data.get('essence', '?')}", f"- Paradox: {data.get('paradox', '?')}", f"- Spheres: {data.get('spheres', '?')}"]
    if splat in {"demon", "demon20th"}:
        return [f"**{name}** - Demon", f"- House: {data.get('house', '?')}", f"- Species: {data.get('species', '?')}", f"- Faith: {data.get('faith', '?')}", f"- Torment: {data.get('torment', '?')}"]
    if splat in {"changeling", "ctd"}:
        return [f"**{name}** - Changeling", f"- Kith: {data.get('kith', '?')}", f"- Seeming: {data.get('seeming', '?')}", f"- House: {data.get('house', '?')}", f"- Glamour: {data.get('glamour', '?')}"]
    if splat in {"wraith", "wto"}:
        return [f"**{name}** - Wraith", f"- Legion: {data.get('legion', '?')}", f"- Guild: {data.get('guild', '?')}", f"- Shadow: {data.get('shadow', '?')}", f"- Pathos: {data.get('pathos', '?')}"]
    fields = [f"**{name}**"]
    if data:
        fields.extend(f"- {k}: {v}" for k, v in data.items())
    return fields


def register_dnd_commands(bot: Any, helpers: dict[str, Any] | None = None) -> None:
    bound: dict[str, Any] = {
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
    async def dice_roll(interaction: discord.Interaction, pool: int, difficulty: int, willpower: bool = False, modifier: int = 0, speciality: str | None = None, nightmare: int = 0, no_botch: bool = False, character: str | None = None, notes: str | None = None) -> None:  # type: ignore[misc]
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
        author_name = str(interaction.user.display_name)
        author_icon = interaction.user.display_avatar.url if interaction.user.display_avatar else None
        char_name = str(character).strip() if character else None
        if char_name and interaction.guild_id is not None:
            resolved = find_character(DND_DB_PATH, int(interaction.guild_id), int(interaction.user.id), char_name)
            if resolved:
                char_name = resolved["name"]
        try:
            emb = d20.build_dice_embed(result, author_name=author_name, author_icon=author_icon, character_name=char_name, notes=notes)
            await interaction.response.send_message(embed=discord.Embed.from_dict(emb))
        except Exception:
            await interaction.response.send_message(str(result.successes))
        await _log(interaction, "dnd_roll", f"pool={validated_pool} diff={validated_diff} result={result.successes}", success=True)

    @dnd_group.command(name="general", description="General multi-set dice roll.")
    async def dice_general(interaction: discord.Interaction, dice_set_01: str, modifier: int = 0, dice_set_02: str | None = None, dice_set_03: str | None = None, dice_set_04: str | None = None, dice_set_05: str | None = None, difficulty: int | None = None, notes: str | None = None) -> None:  # type: ignore[misc]
        if ensure_interaction_command_access and not await ensure_interaction_command_access(interaction, "dnd_general"):
            return
        try:
            sets = general_roll.parse_sets(dice_set_01, dice_set_02, dice_set_03, dice_set_04, dice_set_05)
        except ValueError as exc:
            if reply_ephemeral:
                await reply_ephemeral(interaction, str(exc))
            await _log(interaction, "dnd_general", str(exc), success=False)
            return
        author_name = str(interaction.user.display_name)
        author_icon = interaction.user.display_avatar.url if interaction.user.display_avatar else None
        emb = general_roll.build_general_embed(sets, modifier=modifier, difficulty=difficulty, notes=notes, author_name=author_name, author_icon=author_icon)
        await interaction.response.send_message(embed=discord.Embed.from_dict(emb))
        await _log(interaction, "dnd_general", f"sets={len(sets)}", success=True)

    @dnd_group.command(name="initiative", description="Initiative tracker helpers.")
    async def dice_initiative(interaction: discord.Interaction, action: str = "new", dex_wits: int = 0, character: str | None = None, notes: str | None = None) -> None:  # type: ignore[misc]
        if ensure_interaction_command_access and not await ensure_interaction_command_access(interaction, "dnd_initiative"):
            return
        if not interaction.guild:
            if reply_ephemeral:
                await reply_ephemeral(interaction, "This command can only be used in a server.")
            return
        channel_id = interaction.channel_id
        guild_id = interaction.guild.id
        owner_id = interaction.user.id
        if action == "new":
            tracker = initiative_domain.InitiativeTracker(channel_id=channel_id, guild_id=guild_id, owner_id=owner_id)
            tracker.characters.append(initiative_domain.InitiativeCharacter(member_id=owner_id, display_name=interaction.user.display_name, dex_wits=max(1, int(dex_wits or 0))))
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
            char = initiative_domain.InitiativeCharacter(member_id=owner_id, display_name=interaction.user.display_name, dex_wits=max(1, int(dex_wits or 0)))
            char.compute()
            tracker.characters.append(char)
            save_tracker(DND_DB_PATH, tracker)
            order = sorted(tracker.characters, key=lambda x: (-x.total, x.member_id))
            lines = [f"Initiative rolled for {char.display_name}: **{char.total}**", "Order:"]
            lines.extend(f"- {c.display_name}: {c.total}" for c in order)
            await interaction.response.send_message("\n".join(lines))
            await _log(interaction, "dnd_initiative", f"action={action} total={char.total}", success=True)
        elif action == "end":
            tracker = load_tracker(DND_DB_PATH, channel_id)
            if tracker:
                _end_tracker(DND_DB_PATH, channel_id)
                await interaction.response.send_message("Ended this channel's initiative tracker.", ephemeral=True)
            else:
                await interaction.response.send_message("No active tracker in this channel.", ephemeral=True)
        else:
            await interaction.response.send_message("Use `new`, `roll`, or `end`.", ephemeral=True)

    @dnd_group.command(name="character", description="Storage-backed character helpers.")
    async def dice_character(interaction: discord.Interaction, action: str = "find", splat: str | None = None, name: str | None = None, payload: str | None = None) -> None:  # type: ignore[misc]
        await _run_character_command(interaction, action=action, splat=splat, name=name, payload=payload)

    @app_commands.describe(action="Create, send, list, or delete a proxy.", name="Proxy name.", template="Message template. `{name}` and `{content}` are replaced.", avatar_url="Avatar URL for the proxy.", message="Optional message text to send.")
    @dnd_group.command(name="proxy", description="Proxy identity helpers.")
    async def dice_proxy(interaction: discord.Interaction, action: str = "create", name: str = "", template: str = "{name}: {content}", avatar_url: str = "", message: str | None = None) -> None:  # type: ignore[misc]
        await _run_proxy_command(interaction, action=action, name=name, template=template, avatar_url=avatar_url, message=message)

    @dnd_group.command(name="chronicle", description="Chronicle server helpers.")
    async def dice_chronicle(interaction: discord.Interaction, action: str = "create", name: str = "Chronicle") -> None:  # type: ignore[misc]
        if ensure_interaction_command_access and not await ensure_interaction_command_access(interaction, "dnd_chronicle"):
            return
        if not interaction.guild:
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
    async def dice_xp(interaction: discord.Interaction, action: str = "add", amount: float = 1, reason: str = "") -> None:  # type: ignore[misc]
        if ensure_interaction_command_access and not await ensure_interaction_command_access(interaction, "dnd_xp"):
            return
        if not interaction.guild:
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
                return
            lines = "\n".join(f"- {e['amount']}: {e['reason']}" for e in entries[-10:])
            if reply_ephemeral:
                await reply_ephemeral(interaction, lines)
            else:
                await interaction.response.send_message(lines, ephemeral=True)
        else:
            await interaction.response.send_message("Use `add` or `history`.", ephemeral=True)

    @dnd_group.command(name="reward", description="Auto reward helpers.")
    async def dice_reward(interaction: discord.Interaction, action: str = "status", rule_name: str = "", threshold: int = 10, reward: float = 1) -> None:  # type: ignore[misc]
        if ensure_interaction_command_access and not await ensure_interaction_command_access(interaction, "dnd_reward"):
            return
        if not interaction.guild:
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
            await interaction.response.send_message(f"Created reward rule `{rule_name}`.", ephemeral=True)
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
            await interaction.response.send_message(content, ephemeral=True)
        elif action == "ledger":
            stats = evaluate_rewards(DND_DB_PATH, guild_id, user_id)
            if not stats:
                content = "No active reward rules or no XP tracking."
            else:
                lines = []
                for r in stats:
                    pct = int(min(100, r.get("current_count", 0) / max(1, r.get("threshold", 1)) * 100))
                    lines.append(f"- {r.get('name')}: {r.get('current_count')}/{r.get('threshold')} ({pct}%)")
                content = "\n".join(lines)
            await interaction.response.send_message(content, ephemeral=True)
        else:
            await interaction.response.send_message("Use `create`, `status`, or `ledger`.", ephemeral=True)


def _end_tracker(db_path: str, channel_id: int) -> None:
    import sqlite3
    with sqlite3.connect(db_path, timeout=10) as conn:
        conn.execute("DELETE FROM dnd_initiative_trackers WHERE channel_id=?", (int(channel_id),))


async def _run_character_command(interaction: Any, *, action: str, splat: str | None, name: str | None, payload: str | None) -> None:
    reply_ephemeral = bound["reply_ephemeral"] if "bound" in globals() else None

    if action != "show" and not getattr(interaction, "guild", None):
        if reply_ephemeral:
            await reply_ephemeral(interaction, "Guild context is required for character commands.")
        return
    if action == "save" and not name and not splat:
        if reply_ephemeral:
            await reply_ephemeral(interaction, "Provide a character name.")
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
            return
        lines = [f"Name: {result['name']}", f"Splat: {result['splat']}", f"Updated: {result['updated_at']}"]
        data = result.get("data") or {}
        if data:
            lines.append("Data:")
            lines.extend(f"- {k}: {v}" for k, v in data.items())
        if reply_ephemeral:
            await reply_ephemeral(interaction, "\n".join(lines))
        else:
            await interaction.response.send_message("\n".join(lines), ephemeral=True)
    elif action == "show":
        target = name or (splat or "")
        if not target:
            if reply_ephemeral:
                await reply_ephemeral(interaction, "Provide a character name.")
            return
        resolved = find_character(DND_DB_PATH, int(interaction.guild.id), int(interaction.user.id), target)
        if not resolved:
            if reply_ephemeral:
                await reply_ephemeral(interaction, "No matching character found.")
            return
        data = resolved.get("data") or {}
        title = f"{resolved['name']} ({resolved['splat']})"
        description = "\n".join(f"**{k}**: {v}" for k, v in data.items()) if data else "No stored sheet data."
        try:
            await interaction.response.send_message(embed=discord.Embed(title=title, description=description))
        except Exception:
            await interaction.response.send_message(f"{title}\n{description}")
    elif action == "sheet":
        target = name or (splat or "")
        if not target:
            if reply_ephemeral:
                await reply_ephemeral(interaction, "Provide a character name.")
            return
        resolved = find_character(DND_DB_PATH, int(interaction.guild.id), int(interaction.user.id), target)
        if not resolved:
            if reply_ephemeral:
                await reply_ephemeral(interaction, "No matching character found.")
            return
        character_data = resolved.get("data") or {}
        allowed = _allowed_splats(DND_DB_PATH, int(interaction.guild.id))
        fields = [f"**Sheet**: {resolved['name']}", f"**Splat**: {resolved['splat']}"]
        if resolved["splat"] not in allowed:
            fields.append("⚠ Splat not allowed in this chronicle.")
        fields.extend(_sheet_fields_for_splat(resolved["splat"], resolved["name"], character_data))
        message = "\n".join(fields)
        if reply_ephemeral:
            await reply_ephemeral(interaction, message)
        else:
            await interaction.response.send_message(message, ephemeral=True)
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
    elif action == "save":
        target = name or (splat or "")
        if not target:
            if reply_ephemeral:
                await reply_ephemeral(interaction, "Provide a character name.")
            return
        data = {"raw": payload or ""}
        save_character(DND_DB_PATH, int(interaction.guild.id), int(interaction.user.id), splat or "", target, data)
        await interaction.response.send_message(f"Saved character `{target}`.", ephemeral=True)
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
            await reply_ephemeral(interaction, "Use `find`, `show`, `sheet`, `list`, `save`, or `delete`.")


async def _run_proxy_command(interaction: Any, *, action: str, name: str, template: str, avatar_url: str, message: str | None) -> None:
    reply_ephemeral = bound["reply_ephemeral"] if "bound" in globals() else None
    if not getattr(interaction, "guild", None):
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
    elif action == "send":
        if not name or message is None:
            if reply_ephemeral:
                await reply_ephemeral(interaction, "Provide a proxy name and message.")
            return
        proxy = get_proxy(DND_DB_PATH, int(interaction.guild.id), int(interaction.user.id), name)
        if not proxy:
            if reply_ephemeral:
                await reply_ephemeral(interaction, "Proxy not found. Create it first.")
            return
        content = template.replace("{name}", proxy.get("name", name)).replace("{content}", message)
        await interaction.channel.send(content)
    elif action == "reply":
        if not name:
            if reply_ephemeral:
                await reply_ephemeral(interaction, "Provide a proxy name for auto-reply.")
            return
        proxy = get_proxy(DND_DB_PATH, int(interaction.guild.id), int(interaction.user.id), name)
        if not proxy:
            if reply_ephemeral:
                await reply_ephemeral(interaction, "Proxy not found.")
            return
        await interaction.response.send_message(f"Auto-reply proxy `{name}` is active in this channel.", ephemeral=True)
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
            await reply_ephemeral(interaction, "Use `create`, `send`, `reply`, `list`, or `delete`.")
