from __future__ import annotations

from typing import Any, Optional

import discord
from discord import app_commands

from dnd import chronicle_service
from dnd import proxy_service
from dnd import proxy_render
from dnd import characters as character_repo
from dnd import general_roll
from dnd import initiative as initiative_domain
from dnd.characters import delete_character as delete_char_repo, find_character, list_characters
from dnd import roll_20th as d20

DND_DB_PATH = "/app/data/dnd.db"


def _ensure_chronicle_schema(db_path: str) -> None:
    from dnd import chronicle_schema as _chronicle_schema
    _chronicle_schema.ensure_schema(db_path)


def ensure_dnd_schema() -> None:
    _ensure_chronicle_schema(DND_DB_PATH)


def register_dnd_commands(bot: Any, helpers: Optional[dict[str, Any]] = None) -> None:
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

    async def _log(action: str, reason: str = "", *, success: bool = True) -> None:
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
            await _log("dnd_roll", str(exc), success=False)
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
        emb = d20.build_dice_embed(result, author_name=author_name, author_icon=author_icon, character_name=char_name, notes=notes)
        await interaction.response.send_message(embed=discord.Embed.from_dict(emb))
        await _log("dnd_roll", f"pool={validated_pool} diff={validated_diff} result={result.successes}", success=True)

    @dnd_group.command(name="general", description="General multi-set dice roll.")
    async def dice_general(interaction: discord.Interaction, dice_set_01: str, modifier: int = 0, dice_set_02: str | None = None, dice_set_03: str | None = None, dice_set_04: str | None = None, dice_set_05: str | None = None, difficulty: int | None = None, notes: str | None = None) -> None:  # type: ignore[misc]
        if ensure_interaction_command_access and not await ensure_interaction_command_access(interaction, "dnd_general"):
            return
        try:
            sets = general_roll.parse_sets(dice_set_01, dice_set_02, dice_set_03, dice_set_04, dice_set_05)
        except ValueError as exc:
            if reply_ephemeral:
                await reply_ephemeral(interaction, str(exc))
            await _log("dnd_general", str(exc), success=False)
            return
        author_name = str(interaction.user.display_name)
        author_icon = interaction.user.display_avatar.url if interaction.user.display_avatar else None
        emb = general_roll.build_general_embed(sets, modifier=modifier, difficulty=difficulty, notes=notes, author_name=author_name, author_icon=author_icon)
        await interaction.response.send_message(embed=discord.Embed.from_dict(emb))
        await _log("dnd_general", f"sets={len(sets)}", success=True)

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
            if proxy_service.load_init_tracker if False else None:
                pass
            from dnd.initiative_repo import load_tracker
            if load_tracker(DND_DB_PATH, channel_id):
                if reply_ephemeral:
                    await reply_ephemeral(interaction, "This channel already has an initiative tracker.")
                return
            tracker = initiative_domain.InitiativeTracker(channel_id=channel_id, guild_id=guild_id, owner_id=owner_id)
            tracker.characters.append(initiative_domain.InitiativeCharacter(member_id=owner_id, display_name=interaction.user.display_name, dex_wits=max(1, int(dex_wits or 0))))
            tracker.characters[-1].compute()
            from dnd.initiative_repo import save_tracker
            save_tracker(DND_DB_PATH, tracker)
            if reply_ephemeral:
                await reply_ephemeral(interaction, "Started a new initiative tracker. Use `/dnd initiative` next.")
        elif action == "roll":
            from dnd.initiative_repo import load_tracker
            tracker = load_tracker(DND_DB_PATH, channel_id)
            if not tracker:
                if reply_ephemeral:
                    await reply_ephemeral(interaction, "No tracker in this channel. Start with `new`.")
                return
            char = initiative_domain.InitiativeCharacter(member_id=owner_id, display_name=interaction.user.display_name, dex_wits=max(1, int(dex_wits or 0)))
            char.compute()
            tracker.characters.append(char)
            from dnd.initiative_repo import save_tracker
            save_tracker(DND_DB_PATH, tracker)
            order = sorted(tracker.characters, key=lambda x: (-x.total, x.member_id))
            lines = [f"Initiative rolled for {char.display_name}: **{char.total}**", "Order:"]
            lines.extend(f"- {c.display_name}: {c.total}" for c in order)
            await interaction.response.send_message("\n".join(lines))
            await _log("dnd_initiative", f"action={action} total={char.total}", success=True)
        else:
            if reply_ephemeral:
                await reply_ephemeral(interaction, "Use `new` to start or `roll` to roll into the current tracker.")

    @dnd_group.command(name="character", description="Storage-backed character helpers.")
    async def dice_character(interaction: discord.Interaction, action: str = "find", splat: str | None = None, name: str | None = None) -> None:  # type: ignore[misc]
        if ensure_interaction_command_access and not await ensure_interaction_command_access(interaction, "dnd_character"):
            return
        if action in {"find", "list", "delete"} and not interaction.guild:
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
            return
        if action == "list":
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
            return
        if action == "delete":
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
                await reply_ephemeral(interaction, f"Unsupported `action={action}`.")
