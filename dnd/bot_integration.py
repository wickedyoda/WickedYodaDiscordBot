from __future__ import annotations

from typing import Any

import discord
from discord import app_commands

from dnd import characters as character_repo
from dnd import general_roll
from dnd import initiative as initiative_domain
from dnd.characters import ensure_schema as ensure_char_schema
from dnd.characters import delete_character as delete_char_repo, find_character, list_characters
from dnd import roll_20th as d20
from dnd.initiative_repo import save_tracker as save_init_tracker
from dnd.initiative_repo import load_tracker as load_init_tracker


DND_DB_PATH = "/app/data/dnd.db"


def ensure_dnd_schema() -> None:
    ensure_init_schema(DND_DB_PATH)
    ensure_char_schema(DND_DB_PATH)


def register_dnd_commands(bot, helpers=None) -> None:
    reply_ephemeral = helpers["reply_ephemeral"] if helpers else None
    log_interaction = helpers["log_interaction"] if helpers else None
    ensure_interaction_command_access = helpers["ensure_interaction_command_access"] if helpers else None


    dnd_group = bot.tree.get_command("dnd")
    if dnd_group is None:
        raise RuntimeError("Missing `/dnd` application group.")

    @dnd_group.command(name="roll", description="20th Anniversary Edition dice roll.")
    async def dice_roll(interaction: discord.Interaction, pool: int, difficulty: int, willpower: bool = False, modifier: int = 0, speciality: str | None = None, nightmare: int = 0, no_botch: bool = False, character: str | None = None, notes: str | None = None) -> None:  # type: ignore[misc]
        if not await ensure_interaction_command_access(interaction, "dnd_roll"):
            return
        try:
            validated_pool = d20.parse_20th_pool(pool)
            validated_diff = d20.parse_difficulty(difficulty)
            validated_nightmare = max(0, min(int(nightmare or 0), validated_pool))
        except ValueError as exc:
            await reply_ephemeral(interaction, str(exc))
            await log_interaction(interaction, action="dnd_roll", reason=str(exc), success=False)
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
        await log_interaction(interaction, action="dnd_roll", reason=f"pool={validated_pool} diff={validated_diff} result={result.successes}", success=True)

    @dnd_group.command(name="general", description="General multi-set dice roll.")
    async def dice_general(interaction: discord.Interaction, dice_set_01: str, modifier: int = 0, dice_set_02: str | None = None, dice_set_03: str | None = None, dice_set_04: str | None = None, dice_set_05: str | None = None, difficulty: int | None = None, notes: str | None = None) -> None:  # type: ignore[misc]
        if not await ensure_interaction_command_access(interaction, "dnd_general"):
            return
        try:
            sets = general_roll.parse_sets(dice_set_01, dice_set_02, dice_set_03, dice_set_04, dice_set_05)
        except ValueError as exc:
            await reply_ephemeral(interaction, str(exc))
            await log_interaction(interaction, action="dnd_general", reason=str(exc), success=False)
            return
        author_name = str(interaction.user.display_name)
        author_icon = interaction.user.display_avatar.url if interaction.user.display_avatar else None
        emb = general_roll.build_general_embed(sets, modifier=modifier, difficulty=difficulty, notes=notes, author_name=author_name, author_icon=author_icon)
        await interaction.response.send_message(embed=discord.Embed.from_dict(emb))
        await log_interaction(interaction, action="dnd_general", reason=f"sets={len(sets)}", success=True)

    @dnd_group.command(name="initiative", description="Initiative tracker helpers.")
    async def dice_initiative(interaction: discord.Interaction, action: str = "new", dex_wits: int = 0, character: str | None = None, notes: str | None = None) -> None:  # type: ignore[misc]
        if not await ensure_interaction_command_access(interaction, "dnd_initiative"):
            return
        if not interaction.guild:
            await reply_ephemeral(interaction, "This command can only be used in a server.")
            return
        channel_id = interaction.channel_id
        guild_id = interaction.guild.id
        owner_id = interaction.user.id
        if action == "new":
            if load_init_tracker(DND_DB_PATH, channel_id):
                await reply_ephemeral(interaction, "This channel already has an initiative tracker.")
                return
            tracker = initiative_domain.InitiativeTracker(channel_id=channel_id, guild_id=guild_id, owner_id=owner_id)
            tracker.characters.append(initiative_domain.InitiativeCharacter(member_id=owner_id, display_name=interaction.user.display_name, dex_wits=max(1, int(dex_wits))))
            tracker.characters[-1].compute()
            save_init_tracker(DND_DB_PATH, tracker)
            await reply_ephemeral(interaction, "Started a new initiative tracker. Use `/dnd roll` next.")
        elif action == "roll":
            tracker = load_init_tracker(DND_DB_PATH, channel_id)
            if not tracker:
                await reply_ephemeral(interaction, "No tracker in this channel. Start with `new`.")
                return
            char = initiative_domain.InitiativeCharacter(member_id=owner_id, display_name=interaction.user.display_name, dex_wits=max(1, int(dex_wits)))
            char.compute()
            tracker.characters.append(char)
            save_init_tracker(DND_DB_PATH, tracker)
            order = sorted(tracker.characters, key=lambda x: (-x.total, x.member_id))
            lines = [f"Initiative rolled for {char.display_name}: **{char.total}**", "Order:"]
            lines.extend(f"- {c.display_name}: {c.total}" for c in order)
            await interaction.response.send_message("\n".join(lines))
            await log_interaction(interaction, action="dnd_initiative", reason=f"action={action} total={char.total}", success=True)
        else:
            await reply_ephemeral(interaction, "Use `new` to start or `roll` to roll into the current tracker.")

    @dnd_group.command(name="character", description="Storage-backed character helpers.")
    async def dice_character(interaction: discord.Interaction, action: str = "find", splat: str | None = None, name: str | None = None) -> None:  # type: ignore[misc]
        if not await ensure_interaction_command_access(interaction, "dnd_character"):
            return
        if action in {"find", "list", "delete"} and not interaction.guild:
            await reply_ephemeral(interaction, "Guild context is required for character commands.")
            return
        db_path = DND_DB_PATH
        if action == "find":
            target = name or (splat or "")
            if not target:
                await reply_ephemeral(interaction, "Provide a character name.")
                return
            result = find_character(db_path, interaction.guild.id, interaction.user.id, target)
            if not result:
                await reply_ephemeral(interaction, "No matching character found.")
            else:
                await interaction.response.send_message(f"Found `{result['name']}` ({result['splat']}).", ephemeral=True)
            return
        if action == "list":
            results = list_characters(db_path, interaction.guild.id, interaction.user.id)
            if not results:
                await reply_ephemeral(interaction, "You have no saved characters on this server.")
            else:
                lines = "\n".join(f"- {r['name']} ({r['splat']})" for r in results)
                await interaction.response.send_message(lines, ephemeral=True)
            return
        if action == "delete":
            target = name or (splat or "")
            if not target:
                await reply_ephemeral(interaction, "Provide a character name to delete.")
                return
            deleted = delete_char_repo(db_path, interaction.guild.id, interaction.user.id, target)
            await reply_ephemeral(interaction, "Character deleted." if deleted else "Character not found.")
            return
        await reply_ephemeral(interaction, "Character storage is ready; full editor commands are in progress.")
