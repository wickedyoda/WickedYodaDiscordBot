from __future__ import annotations

import discord
from typing import Any, Dict, List, Optional

from discord import app_commands

from dnd import chronicle_service
from dnd import character_builder
from dnd import editions
from dnd import proxy_group_service
from dnd import proxy_service
from dnd import characters as character_service
from dnd.chronicle_service import add_xp, create_reward_rule, evaluate_rewards, get_chronicle, list_xp_entries, update_chronicle, upsert_member, upsert_reward_tier
from dnd.roll_router import route_roll, RollError
from dnd.debug_logger import get_logger, log_command
from dnd.character_derived import build_derived, render_ability_block, render_derived
from dnd.editions import _edition_for_splat

DND_DB_PATH = "/app/data/dnd.db"
DEBUG_LOGGER = get_logger("wickedyoda.dnd")

EDITION_CHOICES = [
    app_commands.Choice(name="20th Anniversary / World of Darkness", value="20th"),
    app_commands.Choice(name="5th Edition / 2024 Edition", value="5e"),
    app_commands.Choice(name="Custom", value="custom"),
]


def _edition_defaults(edition: str) -> List[str]:
    edition = (edition or "").strip().lower()
    info = editions.get_edition(edition)
    if info:
        return list(info.default_splats)
    custom = editions.get_edition("custom")
    if custom:
        return list(custom.default_splats)
    return []


def _edition_label(edition: str) -> str:
    edition = (edition or "").strip().lower()
    info = editions.get_edition(edition)
    return info.label if info else edition or "Custom"


def _get_db_path() -> str:
    return DND_DB_PATH


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

    async def _enforce_setup(interaction: Any) -> bool:
        if not getattr(interaction, "guild", None):
            return False
        data = chronicle_service.get_chronicle(DND_DB_PATH, int(interaction.guild.id))
        if not data:
            await interaction.response.send_message(
                "No D&D chronicle is set up here yet. Use `/dnd server setup` to choose your edition.",
                ephemeral=True,
            )
            return True
        if not bool(data.get("edition_setup_completed")):
            label = _edition_label(data.get("edition", "") or "custom")
            await interaction.response.send_message(
                f"Edition setup is incomplete: **{label}**. Finish with `/dnd server setup` or rerun `/dnd server restart` to start over.",
                ephemeral=True,
            )
            return True
        return False

    def _allowed_splats_for_guild(interaction: Any) -> List[str]:
        if not getattr(interaction, "guild", None):
            return []
        data = chronicle_service.get_chronicle(DND_DB_PATH, int(interaction.guild.id))
        if not data:
            return []
        allowed = list(data.get("allowed_splats", []) or [])
        return allowed

    def _edition_for_guild(interaction: Any) -> str:
        if not getattr(interaction, "guild", None):
            return "custom"
        data = chronicle_service.get_chronicle(DND_DB_PATH, int(interaction.guild.id))
        if not data:
            return "custom"
        edition = (data.get("edition") or "custom").strip().lower()
        return edition

    def _ensure_splat(interaction: Any, splat: str) -> bool:
        allowed = _allowed_splats_for_guild(interaction)
        if not allowed:
            return False
        return splat in allowed

    def _edition_choices(interaction: Any) -> List[app_commands.Choice]:
        edition = _edition_for_guild(interaction)
        allowed = _allowed_splats_for_guild(interaction)
        out: List[app_commands.Choice] = []
        for name in allowed[:25]:
            label = editions.splat_label(name)
            out.append(app_commands.Choice(name=label or name, value=name))
        return out

    dnd = bot.tree.get_command("dnd")
    if dnd is None:
        raise RuntimeError("Missing `/dnd` application group.")

    @dnd.command(name="roll", description="20th / 5th Edition dice roll.")
    async def roll(
        interaction: Any,
        system: str = "20th",
        pool: int = 1,
        difficulty: int = 6,
        modifier: int = 0,
        willpower: bool = False,
        speciality: str | None = None,
        notes: str | None = None,
    ) -> None:  # type: ignore[misc]
        DEBUG_LOGGER.debug("ENTER /dnd roll system=%s pool=%s difficulty=%s modifier=%s", system, pool, difficulty, modifier)
        log_command(DEBUG_LOGGER, interaction, "roll", system=system, pool=pool, difficulty=difficulty, modifier=modifier, willpower=willpower, speciality=speciality, notes=notes)
        if await _enforce_setup(interaction):
            DEBUG_LOGGER.debug("BLOCKED /dnd roll setup not complete guild=%s user=%s", getattr(getattr(interaction, "guild", None), "id", "dm"), getattr(getattr(interaction, "user", None), "id", "unknown"))
            return
        edition = _edition_for_guild(interaction)
        edition_info = editions.get_edition(edition)
        allowed_systems = edition_info.roll_systems if edition_info else []
        if system not in allowed_systems:
            label = _edition_label(edition)
            DEBUG_LOGGER.debug("REJECT /dnd roll invalid system=%s edition=%s allowed=%s", system, edition, allowed_systems)
            await interaction.response.send_message(
                f"`/dnd roll system:{system}` is not available for **{label}**. Allowed: {', '.join(allowed_systems)}.",
                ephemeral=True,
            )
            return
        DEBUG_LOGGER.debug("ACCEPT /dnd roll edition=%s system=%s", edition, system)
        try:
            result = route_roll(edition=edition, system=system, pool=pool, difficulty=difficulty, modifier=modifier)
            lines = [
                f"Roll `{system}` for {_edition_label(edition)}: pool={result['pool']} diff={result['difficulty']}",
                f"Dice: {', '.join(str(x) for x in result['dice'])}",
                f"Successes: {result['successes']} | Outcome: {result['outcome']}",
            ]
            await interaction.response.send_message("\n".join(lines), ephemeral=True)
            DEBUG_LOGGER.debug("ACCEPT /dnd roll result successes=%s outcome=%s", result.get("successes"), result.get("outcome"))
        except RollError as exc:
            DEBUG_LOGGER.debug("ERROR /dnd roll router=%s", exc, exc_info=True)
            await interaction.response.send_message(f"Roll error: {exc}", ephemeral=True)
        await _log(interaction, "dnd_roll", f"system={system} pool={pool} diff={difficulty}", success=True)

    @roll.autocomplete("system")
    async def roll_system_autocomplete(interaction: Any, current: str) -> List[app_commands.Choice]:
        edition = _edition_for_guild(interaction)
        edition_info = editions.get_edition(edition)
        allowed = edition_info.roll_systems if edition_info else []
        out = []
        for item in allowed:
            if current.lower() in item.lower():
                out.append(app_commands.Choice(name=item, value=item))
        return out[:25]

    @dnd.command(name="sheet", description="Roll a 5th edition sheet pool.")
    async def sheet(
        interaction: Any,
        attribute: str,
        attribute2: str | None = None,
        skill: str | None = None,
        discipline: str | None = None,
        splat: str = "",
        modifier: int = 0,
        difficulty: int = 6,
        notes: str | None = None,
    ) -> None:  # type: ignore[misc]
        DEBUG_LOGGER.debug("ENTER /dnd sheet splat=%s attribute=%s modifier=%s difficulty=%s", splat, attribute, modifier, difficulty)
        log_command(DEBUG_LOGGER, interaction, "sheet", attribute=attribute, attribute2=attribute2, skill=skill, discipline=discipline, splat=splat, modifier=modifier, difficulty=difficulty, notes=notes)
        if await _enforce_setup(interaction):
            DEBUG_LOGGER.debug("BLOCKED /dnd sheet setup not complete")
            return
        edition = _edition_for_guild(interaction)
        edition_info = editions.get_edition(edition)
        allowed = _allowed_splats_for_guild(interaction)
        if splat and splat not in allowed:
            label = _edition_label(edition)
            DEBUG_LOGGER.debug("REJECT /dnd sheet splat=%s edition=%s allowed=%s", splat, edition, allowed)
            await interaction.response.send_message(
                f"`splat:{splat}` is not allowed under **{label}**. Choose from: {', '.join(allowed)}.",
                ephemeral=True,
            )
            return
        system = edition_info.roll_systems[0] if edition_info and edition_info.roll_systems else edition
        sheet_supported = bool(edition_info.sheet_roll_supported) if edition_info else False
        if sheet_supported:
            DEBUG_LOGGER.debug("EXECUTE /dnd sheet system=%s hunger=%s", system, bool(discipline))
            try:
                result = route_roll(edition=edition, system=system or edition, pool=3 + int(modifier or 0), difficulty=difficulty, hunger=bool(discipline))
                if discipline:
                    result["outcome"] = result.get("outcome", "") + " (Hunger)"
                lines = [
                    f"Sheet roll for `{edition}`: pool={result['pool']} diff={difficulty}",
                    f"Dice: {', '.join(str(x) for x in result['dice'])}",
                    f"Successes: {result['successes']} | Outcome: {result['outcome']}",
                ]
                await interaction.response.send_message("\n".join(lines), ephemeral=True)
            except RollError as exc:
                DEBUG_LOGGER.debug("ERROR /dnd sheet engine=%s", exc, exc_info=True)
                await interaction.response.send_message(f"Sheet roll engine error: {exc}", ephemeral=True)
        else:
            DEBUG_LOGGER.debug("SKIP /dnd sheet sheet_roll_supported=False for %s", edition)
            await interaction.response.send_message(
                f"Sheet rolls are not enabled for **{_edition_label(edition)}**.",
                ephemeral=True,
            )
        await _log(interaction, "dnd_sheet", f"attribute={attribute} skill={skill} splat={splat}", success=True)

    @sheet.autocomplete("splat")
    async def sheet_splat_autocomplete(interaction: Any, current: str) -> List[app_commands.Choice]:
        allowed = _edition_choices(interaction)
        out = []
        for choice in allowed:
            if current.lower() in choice.value.lower() or current.lower() in choice.name.lower():
                out.append(choice)
        return out[:25]

    @dnd.command(name="setup", description="Edition-aware D&D setup helpers.")
    async def setup(interaction: Any, action: str = "show") -> None:  # type: ignore[misc]
        DEBUG_LOGGER.debug("ENTER /dnd setup action=%s", action)
        log_command(DEBUG_LOGGER, interaction, "setup", action=action)
        if not interaction.guild:
            DEBUG_LOGGER.debug("BLOCKED /dnd setup dm_context")
            await interaction.response.send_message("Use in a server.", ephemeral=True)
            return
        allowed = _allowed_splats_for_guild(interaction)
        data = chronicle_service.get_chronicle(DND_DB_PATH, int(interaction.guild.id))
        edition = (data or {}).get("edition") or "custom"
        label = _edition_label(edition)
        DEBUG_LOGGER.debug("EXECUTE /dnd setup edition=%s allowed=%s", edition, allowed)
        lines = [
            f"Edition: {label}",
            f"Setup complete: {bool((data or {}).get('edition_setup_completed'))}",
            f"Allowed splats/species: {', '.join(allowed) if allowed else 'none - rerun /dnd server setup'}",
        ]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)
        await _log(interaction, "dnd_setup", f"edition={edition}", success=True)
        DEBUG_LOGGER.debug("ACCEPT /dnd setup edition=%s", edition)

    @dnd.command(name="info", description="Edition/splat reference info.")
    async def info(interaction: Any, topic: str = "edition", choice: str = "") -> None:  # type: ignore[misc]
        DEBUG_LOGGER.debug("ENTER /dnd info topic=%s choice=%s", topic, choice)
        log_command(DEBUG_LOGGER, interaction, "info", topic=topic, choice=choice)
        if topic == "edition":
            edition = choice.strip().lower() if choice else _edition_for_guild(interaction)
            if not edition:
                await interaction.response.send_message("Specify an edition: `20th`, `5e`, `custom`.", ephemeral=True)
                DEBUG_LOGGER.debug("REJECT /dnd info missing edition")
                return
            info_data = editions.edition_help(edition)
            reference = (
                f"\nReference: {editions.WIKI_REFERENCE_URL}\n"
                f"Summary: {editions.WIKI_SUMMARY}"
            )
            await interaction.response.send_message(info_data + reference, ephemeral=True)
            DEBUG_LOGGER.debug("ACCEPT /dnd info edition=%s", edition)
        elif topic == "splat":
            splat = choice.strip()
            edition = _edition_for_guild(interaction)
            allowed = _allowed_splats_for_guild(interaction)
            if splat not in allowed and allowed:
                await interaction.response.send_message(f"`{splat}` is not in this edition's allowed list.", ephemeral=True)
                DEBUG_LOGGER.debug("REJECT /dnd info bad splat=%s edition=%s", splat, edition)
                return
            edition_key = edition or "custom"
            edition_info = editions.get_edition(edition_key)
            meta = (edition_info.splat_metadata or {}).get(splat) if edition_info else None
            if meta:
                lines = [f"Splat: {meta.get('name', splat)}", f"Edition: {_edition_label(edition_key)}", f"Slug: {meta.get('slug', splat)}"]
                if meta.get("sheetSlug"):
                    lines.append(f"Sheet slug: {meta.get('sheetSlug')}")
                await interaction.response.send_message("\n".join(lines), ephemeral=True)
                DEBUG_LOGGER.debug("ACCEPT /dnd info splat=%s edition=%s", splat, edition_key)
            else:
                await interaction.response.send_message(f"No metadata for `{splat}` under {_edition_label(edition_key)}.", ephemeral=True)
        else:
            DEBUG_LOGGER.debug("REJECT /dnd info bad topic=%s choice=%s", topic, choice)
            await interaction.response.send_message("Use `info edition:<choice>` or `info splat:<choice>`.", ephemeral=True)
        await _log(interaction, "dnd_info", f"topic={topic} choice={choice}", success=True)

    @dnd.command(name="character", description="Edition-aware character helpers.")
    async def character(interaction: Any, action: str = "show", name: str = "", splat: str = "", field: str = "", value: str = "") -> None:  # type: ignore[misc]
        DEBUG_LOGGER.debug("ENTER /dnd character action=%s name=%s splat=%s field=%s value=%s", action, name, splat, field, value)
        log_command(DEBUG_LOGGER, interaction, "character", action=action, name=name, splat=splat, field=field, value=value)
        if await _enforce_setup(interaction):
            DEBUG_LOGGER.debug("BLOCKED /dnd character setup not complete")
            return
        if not interaction.guild:
            if reply_ephemeral:
                await reply_ephemeral(interaction, "Use in a server.")
            DEBUG_LOGGER.debug("REJECT /dnd character dm_context")
            return
        guild_id = int(interaction.guild.id)
        user_id = int(interaction.user.id)
        edition = _edition_for_guild(interaction)
        allowed = _allowed_splats_for_guild(interaction)
        if action == "create":
            if not name:
                await interaction.response.send_message("Provide character name.", ephemeral=True)
                DEBUG_LOGGER.debug("REJECT /dnd character create missing name")
                return
            splat_key = splat or (allowed[0] if allowed else "custom")
            if allowed and splat_key not in allowed:
                await interaction.response.send_message(
                    f"`{splat_key}` is not allowed for this edition. Allowed: {', '.join(allowed)}",
                    ephemeral=True,
                )
                DEBUG_LOGGER.debug("REJECT /dnd character create invalid splat=%s allowed=%s", splat_key, allowed)
                return
            upsert_member(DND_DB_PATH, guild_id, user_id, default_character=name)
            template = character_builder.sheet_template(splat_key)
            payload = {"splat": splat_key, "fields": template}
            character_service.save_character(DND_DB_PATH, guild_id, user_id, splat_key, name, payload)
            lines = [
                f"Created character `{name}` for `{splat_key}`.",
                "Template fields: " + ", ".join(template.keys()),
            ]
            await interaction.response.send_message("\n".join(lines), ephemeral=True)
            DEBUG_LOGGER.debug("ACCEPT /dnd character create name=%s splat=%s template_fields=%d", name, splat_key, len(template))
        elif action == "show":
            target_name = name.strip()
            if not target_name:
                chars = character_service.list_characters(DND_DB_PATH, guild_id, user_id)
                if not chars:
                    await interaction.response.send_message("No characters found. Use `/dnd character create`.", ephemeral=True)
                    DEBUG_LOGGER.debug("REJECT /dnd character show empty")
                    return
                lines = ["Characters:"] + [f"- {c['name']} ({c['splat']})" for c in chars]
                await interaction.response.send_message("\n".join(lines), ephemeral=True)
                DEBUG_LOGGER.debug("ACCEPT /dnd character show list count=%d", len(chars))
                return
            record = character_service.find_character(DND_DB_PATH, guild_id, user_id, target_name)
            if not record:
                await interaction.response.send_message(f"Character `{target_name}` not found.", ephemeral=True)
                DEBUG_LOGGER.debug("REJECT /dnd character show missing name=%s", target_name)
                return
            data = record.get("data", {})
            fields = data.get("fields") or {}
            splat_for_edition = record.get("splat") or ""
            splat_edition = _edition_for_splat(splat_for_edition)
            edition_key = edition or (splat_edition.key if splat_edition else "custom")
            derived = build_derived(edition_key, fields)
            lines = [
                f"**{record['name']}** | {record['splat']} | {_edition_label(edition_key)}",
                render_ability_block(edition_key, derived),
                render_derived(edition_key, derived),
            ]
            await interaction.response.send_message("\n".join(lines), ephemeral=True)
            DEBUG_LOGGER.debug("ACCEPT /dnd character show name=%s edition=%s", target_name, edition_key)
        elif action == "edit":
            target_name = name.strip()
            if not target_name or not field:
                await interaction.response.send_message("Provide `name` and `field` to edit.", ephemeral=True)
                DEBUG_LOGGER.debug("REJECT /dnd character edit missing fields")
                return
            record = character_service.find_character(DND_DB_PATH, guild_id, user_id, target_name)
            if not record:
                await interaction.response.send_message(f"Character `{target_name}` not found.", ephemeral=True)
                DEBUG_LOGGER.debug("REJECT /dnd character edit missing name=%s", target_name)
                return
            data = record.get("data", {})
            fields = data.get("fields") or {}
            fields[field] = value
            data["fields"] = fields
            character_service.save_character(DND_DB_PATH, guild_id, user_id, record["splat"], target_name, data)
            await interaction.response.send_message(f"Updated `{field}` for `{target_name}`.", ephemeral=True)
            DEBUG_LOGGER.debug("ACCEPT /dnd character edit name=%s field=%s", target_name, field)
        elif action == "delete":
            target_name = name.strip()
            if not target_name:
                await interaction.response.send_message("Provide `name` to delete.", ephemeral=True)
                DEBUG_LOGGER.debug("REJECT /dnd character delete missing name")
                return
            removed = character_service.delete_character(DND_DB_PATH, guild_id, user_id, target_name)
            await interaction.response.send_message("Deleted." if removed else "Character not found.", ephemeral=True)
            DEBUG_LOGGER.debug("ACCEPT /dnd character delete name=%s removed=%s", target_name, removed)
        else:
            DEBUG_LOGGER.debug("REJECT /dnd character bad action=%s", action)
            await interaction.response.send_message("Use `create`, `show`, `edit`, `list`, or `delete`.", ephemeral=True)

    @dnd.command(name="xp", description="XP tracking helpers.")
    async def xp(interaction: Any, action: str = "add", amount: float = 1.0, reason: str = "") -> None:  # type: ignore[misc]
        DEBUG_LOGGER.debug("ENTER /dnd xp action=%s amount=%s reason=%s", action, amount, reason)
        log_command(DEBUG_LOGGER, interaction, "xp", action=action, amount=amount, reason=reason)
        if await _enforce_setup(interaction):
            DEBUG_LOGGER.debug("BLOCKED /dnd xp setup not complete")
            return
        if not interaction.guild:
            if reply_ephemeral:
                await reply_ephemeral(interaction, "Use in a server.")
            return
        guild_id = int(interaction.guild.id)
        user_id = int(interaction.user.id)
        if action == "add":
            add_xp(DND_DB_PATH, guild_id, user_id, float(amount), reason or "XP from slash")
            await interaction.response.send_message(f"Added {amount} XP.", ephemeral=True)
        elif action == "history":
            entries = chronicle_service.list_xp_entries(DND_DB_PATH, guild_id, user_id)
            if not entries:
                await interaction.response.send_message("No XP history.", ephemeral=True)
                DEBUG_LOGGER.debug("REJECT /dnd xp history empty guild=%s user=%s", guild_id, user_id)
                return
            lines = "\n".join(f"- {e['amount']}: {e['reason']}" for e in entries[-10:])
            await interaction.response.send_message(lines, ephemeral=True)
            DEBUG_LOGGER.debug("ACCEPT /dnd xp history guild=%s user=%s entries=%d", guild_id, user_id, len(entries))
        else:
            DEBUG_LOGGER.debug("REJECT /dnd xp bad action=%s", action)
            await interaction.response.send_message("Use `add` or `history`.", ephemeral=True)

    @dnd.command(name="reward", description="Auto reward helpers.")
    async def reward(interaction: Any, action: str = "status", rule_name: str = "", threshold: int = 10, reward: float = 1.0) -> None:  # type: ignore[misc]
        DEBUG_LOGGER.debug("ENTER /dnd reward action=%s rule_name=%s threshold=%s reward=%s", action, rule_name, threshold, reward)
        log_command(DEBUG_LOGGER, interaction, "reward", action=action, rule_name=rule_name, threshold=threshold, reward=reward)
        if await _enforce_setup(interaction):
            DEBUG_LOGGER.debug("BLOCKED /dnd reward setup not complete")
            return
        if not interaction.guild:
            if reply_ephemeral:
                await reply_ephemeral(interaction, "Use in a server.")
            DEBUG_LOGGER.debug("REJECT /dnd reward dm_context")
            return
        guild_id = int(interaction.guild.id)
        user_id = int(interaction.user.id)
        if action == "create":
            if not rule_name:
                await interaction.response.send_message("Provide rule_name.", ephemeral=True)
                DEBUG_LOGGER.debug("REJECT /dnd reward create missing rule_name")
                return
            rule = create_reward_rule(DND_DB_PATH, guild_id, rule_name)
            upsert_reward_tier(DND_DB_PATH, rule["id"], idx=0, threshold=int(threshold), reward=float(reward))
            await interaction.response.send_message(f"Created reward rule `{rule_name}`.", ephemeral=True)
            DEBUG_LOGGER.debug("ACCEPT /dnd reward create rule_name=%s threshold=%s reward=%s", rule_name, threshold, reward)
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
            await interaction.response.send_message(content or "No data.", ephemeral=True)
            DEBUG_LOGGER.debug("ACCEPT /dnd reward status guild=%s user=%s rules=%d", guild_id, user_id, len(stats))
        else:
            DEBUG_LOGGER.debug("REJECT /dnd reward bad action=%s", action)
            await interaction.response.send_message("Use `create` or `status`.", ephemeral=True)

    @dnd.command(name="server", description="D&D server/chronicle settings.")
    async def server(interaction: Any, action: str = "show", name: str = "Chronicle", edition: str = "") -> None:  # type: ignore[misc]
        DEBUG_LOGGER.debug("ENTER /dnd server action=%s name=%s edition=%s", action, name, edition)
        log_command(DEBUG_LOGGER, interaction, "server", action=action, name=name, edition=edition)
        if not interaction.guild:
            DEBUG_LOGGER.debug("BLOCKED /dnd server dm_context")
            if reply_ephemeral:
                await reply_ephemeral(interaction, "Use in a server.")
            return
        guild_id = int(interaction.guild.id)
        if action == "setup":
            if not edition:
                DEBUG_LOGGER.debug("REJECT /dnd server missing edition")
                await interaction.response.send_message("Choose an edition: `/dnd server setup edition:20th`", ephemeral=True)
                return
            label = _edition_label(edition)
            defaults = _edition_defaults(edition)
            DEBUG_LOGGER.debug("EXECUTE /dnd server setup edition=%s defaults=%s", edition, defaults)
            chronicle_service.update_chronicle(
                DND_DB_PATH,
                guild_id,
                edition=edition,
                edition_setup_completed=1,
                allowed_splats=defaults,
                owner_id=int(interaction.user.id),
            )
            splats_hint = ", ".join(defaults) if defaults else "none"
            await interaction.response.send_message(
                f"Edition set to **{label}**. Default splats/species: {splats_hint}. Use `/dnd server update` to change settings.",
                ephemeral=True,
            )
        elif action == "restart":
            data = chronicle_service.get_chronicle(DND_DB_PATH, guild_id)
            chronicle_service.update_chronicle(
                DND_DB_PATH,
                guild_id,
                edition="",
                edition_setup_completed=0,
                allowed_splats=[],
                owner_id=int(interaction.user.id),
            )
            await interaction.response.send_message(
                "D&D setup has been reset. Use `/dnd server setup edition:<choice>` to start again.",
                ephemeral=True,
            )
        elif action == "show":
            data = chronicle_service.get_chronicle(DND_DB_PATH, guild_id)
            if not data:
                await interaction.response.send_message("No chronicle in this server. Use `/dnd server setup`.", ephemeral=True)
                return
            monitored = len(data.get("monitored_channel_ids", []))
            excluded = len(data.get("excluded_channel_ids", []))
            edition = data.get("edition") or "unset"
            setup = "complete" if data.get("edition_setup_completed") else "incomplete"
            lines = [
                f"Chronicle: {data['name']}",
                f"Edition: {_edition_label(edition)} ({setup})",
                f"Allowed splats/species: {', '.join(data.get('allowed_splats', [])) or 'none'}",
                f"XP tracking: {data['xp_tracking_enabled']}",
                f"Auto rewards: {data['auto_reward_enabled']}",
                f"Monitored channels: {monitored}",
                f"Excluded channels: {excluded}",
            ]
            await interaction.response.send_message("\n".join(lines), ephemeral=True)
        else:
            update_chronicle(DND_DB_PATH, guild_id, name=name, owner_id=int(interaction.user.id))
            await interaction.response.send_message("Updated chronicle settings.", ephemeral=True)

    @dnd.command(name="group", description="Proxy group CRUD.")
    async def group(interaction: Any, action: str = "list", name: str = "", description: str = "", proxy: str = "") -> None:  # type: ignore[misc]
        DEBUG_LOGGER.debug("ENTER /dnd group action=%s name=%s description=%s proxy=%s", action, name, description, proxy)
        log_command(DEBUG_LOGGER, interaction, "group", action=action, name=name, description=description, proxy=proxy)
        if await _enforce_setup(interaction):
            DEBUG_LOGGER.debug("BLOCKED /dnd group setup not complete")
            return
        if not interaction.guild:
            if reply_ephemeral:
                await reply_ephemeral(interaction, "Use in a server.")
            DEBUG_LOGGER.debug("REJECT /dnd group dm_context")
            return
        guild_id = int(interaction.guild.id)
        user_id = int(interaction.user.id)
        from dnd import proxy_group_service
        if action == "create":
            if not name:
                await interaction.response.send_message("Provide group name.", ephemeral=True)
                DEBUG_LOGGER.debug("REJECT /dnd group create missing name")
                return
            proxy_group_service.create_proxy_group(DND_DB_PATH, guild_id, user_id, name, description)
            await interaction.response.send_message(f"Created proxy group `{name}`.", ephemeral=True)
            DEBUG_LOGGER.debug("ACCEPT /dnd group create name=%s", name)
        elif action == "add":
            if not name or not proxy:
                await interaction.response.send_message("Provide group name and proxy name.", ephemeral=True)
                DEBUG_LOGGER.debug("REJECT /dnd group add missing fields")
                return
            result = proxy_group_service.add_proxy_to_group(DND_DB_PATH, guild_id, user_id, name, proxy)
            if not result:
                await interaction.response.send_message("Proxy not found.", ephemeral=True)
                DEBUG_LOGGER.debug("REJECT /dnd group add proxy not found group=%s proxy=%s", name, proxy)
                return
            await interaction.response.send_message(f"Added proxy `{proxy}` to group `{name}`.", ephemeral=True)
            DEBUG_LOGGER.debug("ACCEPT /dnd group add group=%s proxy=%s", name, proxy)
        elif action == "remove":
            if not name or not proxy:
                await interaction.response.send_message("Provide group name and proxy name.", ephemeral=True)
                DEBUG_LOGGER.debug("REJECT /dnd group remove missing fields")
                return
            removed = proxy_group_service.remove_proxy_from_group(DND_DB_PATH, guild_id, user_id, name, proxy)
            await interaction.response.send_message("Removed." if removed else "Proxy not in group.", ephemeral=True)
            DEBUG_LOGGER.debug("ACCEPT /dnd group remove group=%s proxy=%s removed=%s", name, proxy, removed)
        elif action == "list":
            groups = proxy_group_service.list_proxy_groups(DND_DB_PATH, guild_id, user_id)
            if not groups:
                await interaction.response.send_message("No proxy groups yet.", ephemeral=True)
                DEBUG_LOGGER.debug("ACCEPT /dnd group list empty")
                return
            lines = []
            for g in groups:
                members = proxy_group_service.list_group_proxies(DND_DB_PATH, guild_id, user_id, g["name"])
                members_hint = ", ".join(m.get("name", "") for m in members) if members else "empty"
                lines.append(f"- {g['name']}: {members_hint}")
            await interaction.response.send_message("\n".join(lines), ephemeral=True)
            DEBUG_LOGGER.debug("ACCEPT /dnd group list groups=%d", len(groups))
        else:
            DEBUG_LOGGER.debug("REJECT /dnd group bad action=%s", action)
            await interaction.response.send_message("Use `create`, `add`, `remove`, or `list`.", ephemeral=True)

    @dnd.command(name="reproxy", description="Reproxy/message tracking helpers.")
    async def reproxy(interaction: Any, action: str = "list", group: str = "", proxy: str = "", target_channel: str = "", source_message: str = "", content: str = "") -> None:  # type: ignore[misc]
        DEBUG_LOGGER.debug("ENTER /dnd reproxy action=%s group=%s proxy=%s target_channel=%s source_message=%s", action, group, proxy, target_channel, source_message)
        log_command(DEBUG_LOGGER, interaction, "reproxy", action=action, group=group, proxy=proxy, target_channel=target_channel, source_message=source_message, content=content)
        if await _enforce_setup(interaction):
            DEBUG_LOGGER.debug("BLOCKED /dnd reproxy setup not complete")
            return
        if not interaction.guild:
            if reply_ephemeral:
                await reply_ephemeral(interaction, "Use in a server.")
            DEBUG_LOGGER.debug("REJECT /dnd reproxy dm_context")
            return
        guild_id = int(interaction.guild.id)
        user_id = int(interaction.user.id)
        from dnd import proxy_group_service
        if action == "create":
            if not group or not proxy or not target_channel:
                await interaction.response.send_message("Provide group, proxy, and target_channel.", ephemeral=True)
                DEBUG_LOGGER.debug("REJECT /dnd reproxy create missing fields")
                return
            try:
                channel_id = int(target_channel)
            except ValueError:
                await interaction.response.send_message("target_channel must be a channel ID.", ephemeral=True)
                DEBUG_LOGGER.debug("REJECT /dnd reproxy invalid target_channel=%s", target_channel)
                return
            proxy_row = proxy_service.get_proxy(DND_DB_PATH, guild_id, user_id, proxy)
            if not proxy_row:
                await interaction.response.send_message("Proxy not found.", ephemeral=True)
                DEBUG_LOGGER.debug("REJECT /dnd reproxy proxy not found proxy=%s", proxy)
                return
            proxy_group_service.record_reproxy(
                DND_DB_PATH,
                guild_id=guild_id,
                target_channel_id=channel_id,
                owner_id=user_id,
                group_name=group,
                proxy_id=int(proxy_row["id"]),
                source_message_id=source_message,
                content=content,
            )
            await interaction.response.send_message(f"Recorded reproxy to <#{channel_id}> for `{proxy}` from `{group}`.", ephemeral=True)
            DEBUG_LOGGER.debug("ACCEPT /dnd reproxy create group=%s proxy=%s channel=%s", group, proxy, channel_id)
        elif action == "list":
            jobs = proxy_group_service.list_reproxy_jobs(DND_DB_PATH, guild_id, user_id)
            if not jobs:
                await interaction.response.send_message("No reproxy jobs yet.", ephemeral=True)
                DEBUG_LOGGER.debug("ACCEPT /dnd reproxy list empty")
                return
            lines = "\n".join(
                f"- {j['created_at']}: {j['group_name']} -> <#{j['target_channel_id']}> proxy={j['proxy_id']} src={j['source_message_id']}"
                for j in jobs[:20]
            )
            await interaction.response.send_message(lines, ephemeral=True)
            DEBUG_LOGGER.debug("ACCEPT /dnd reproxy list jobs=%d", len(jobs))
        else:
            DEBUG_LOGGER.debug("REJECT /dnd reproxy bad action=%s", action)
            await interaction.response.send_message("Use `create` or `list`.", ephemeral=True)
