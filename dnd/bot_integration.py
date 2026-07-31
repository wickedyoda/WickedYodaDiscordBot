from __future__ import annotations

import discord
from typing import Any, Dict, List, Optional

from discord import app_commands

from dnd import chronicle_service
from dnd import character_builder
from dnd import editions
from dnd import proxy_group_service
from dnd import proxy_service
from dnd.chronicle_service import add_xp, create_reward_rule, evaluate_rewards, get_chronicle, list_xp_entries, update_chronicle, upsert_member, upsert_reward_tier

DND_DB_PATH = "/app/data/dnd.db"

EDITION_CHOICES = [
    app_commands.Choice(name="20th Anniversary / World of Darkness", value="20th"),
    app_commands.Choice(name="5th Edition / 2024 Edition", value="5e"),
    app_commands.Choice(name="Custom", value="custom"),
]


def _edition_defaults(edition: str) -> List[str]:
    edition = (edition or "").strip().lower()
    return editions.EDITION_DEFAULTS.get(edition, editions.EDITION_DEFAULTS["custom"])


def _edition_label(edition: str) -> str:
    return editions.EDITION_LABELS.get(edition, edition or "Custom")


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
        if await _enforce_setup(interaction):
            return
        edition = _edition_for_guild(interaction)
        edition_info = editions.get_edition(edition)
        allowed_systems = edition_info.roll_systems if edition_info else []
        if system not in allowed_systems:
            label = _edition_label(edition)
            await interaction.response.send_message(
                f"`/dnd roll system:{system}` is not available for **{label}**. Allowed: {', '.join(allowed_systems)}.",
                ephemeral=True,
            )
            return
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
        if await _enforce_setup(interaction):
            return
        edition = _edition_for_guild(interaction)
        edition_info = editions.get_edition(edition)
        allowed = _allowed_splats_for_guild(interaction)
        if splat and splat not in allowed:
            label = _edition_label(edition)
            await interaction.response.send_message(
                f"`splat:{splat}` is not allowed under **{label}**. Choose from: {', '.join(allowed)}.",
                ephemeral=True,
            )
            return
        system = edition_info.roll_systems[0] if edition_info and edition_info.roll_systems else edition
        sheet_supported = bool(edition_info.sheet_roll_supported) if edition_info else False
        if sheet_supported:
            try:
                from dnd.roll_5th import build_sheet_pool, roll_sheet_pool as _roll_sheet_pool
                pool = 3 + int(modifier or 0)
                result = _roll_sheet_pool(pool=pool, difficulty=difficulty, hunger=bool(discipline), modifier=0)
                lines = [
                    f"Sheet roll for `{edition}`: pool={result.pool} diff={difficulty}",
                    f"Dice: {result.dice}",
                    f"Successes: {result.successes}",
                    f"Outcome: {result.outcome}",
                ]
                await interaction.response.send_message("\n".join(lines), ephemeral=True)
            except Exception as exc:  # pragma: no cover
                await interaction.response.send_message(f"Sheet roll engine error: {exc}", ephemeral=True)
        else:
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
        if not interaction.guild:
            await interaction.response.send_message("Use in a server.", ephemeral=True)
            return
        allowed = _allowed_splats_for_guild(interaction)
        data = chronicle_service.get_chronicle(DND_DB_PATH, int(interaction.guild.id))
        edition = (data or {}).get("edition") or "custom"
        label = _edition_label(edition)
        lines = [
            f"Edition: {label}",
            f"Setup complete: {bool((data or {}).get('edition_setup_completed'))}",
            f"Allowed splats/species: {', '.join(allowed) if allowed else 'none - rerun /dnd server setup'}",
        ]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)
        await _log(interaction, "dnd_setup", f"edition={edition}", success=True)

    @dnd.command(name="info", description="Edition/splat reference info.")
    async def info(interaction: Any, topic: str = "edition", choice: str = "") -> None:  # type: ignore[misc]
        if topic == "edition":
            edition = choice.strip().lower() if choice else _edition_for_guild(interaction)
            if not edition:
                await interaction.response.send_message("Specify an edition: `20th`, `5e`, `custom`.", ephemeral=True)
                return
            info_data = editions.edition_help(edition)
            reference = (
                f"\nReference: {editions.WIKI_REFERENCE_URL}\n"
                f"Summary: {editions.WIKI_SUMMARY}"
            )
            await interaction.response.send_message(info_data + reference, ephemeral=True)
        elif topic == "splat":
            splat = choice.strip()
            edition = _edition_for_guild(interaction)
            allowed = _allowed_splats_for_guild(interaction)
            if splat not in allowed and allowed:
                await interaction.response.send_message(f"`{splat}` is not in this edition's allowed list.", ephemeral=True)
                return
            edition_key = edition or "custom"
            edition_info = editions.get_edition(edition_key)
            meta = (edition_info.splat_metadata or {}).get(splat) if edition_info else None
            if meta:
                lines = [f"Splat: {meta.get('name', splat)}", f"Edition: {_edition_label(edition_key)}", f"Slug: {meta.get('slug', splat)}"]
                if meta.get("sheetSlug"):
                    lines.append(f"Sheet slug: {meta.get('sheetSlug')}")
                await interaction.response.send_message("\n".join(lines), ephemeral=True)
            else:
                await interaction.response.send_message(f"No metadata for `{splat}` under {_edition_label(edition_key)}.", ephemeral=True)
        else:
            await interaction.response.send_message("Use `info edition:<choice>` or `info splat:<choice>`.", ephemeral=True)
        await _log(interaction, "dnd_info", f"topic={topic} choice={choice}", success=True)

    @dnd.command(name="character", description="Edition-aware character helpers.")
    async def character(interaction: Any, action: str = "show", name: str = "", splat: str = "") -> None:  # type: ignore[misc]
        if await _enforce_setup(interaction):
            return
        if not interaction.guild:
            if reply_ephemeral:
                await reply_ephemeral(interaction, "Use in a server.")
            return
        guild_id = int(interaction.guild.id)
        user_id = int(interaction.user.id)
        edition = _edition_for_guild(interaction)
        allowed = _allowed_splats_for_guild(interaction)
        if action == "create":
            if not name:
                await interaction.response.send_message("Provide character name.", ephemeral=True)
                return
            splat_key = splat or (allowed[0] if allowed else "custom")
            if allowed and splat_key not in allowed:
                await interaction.response.send_message(
                    f"`{splat_key}` is not allowed for this edition. Allowed: {', '.join(allowed)}",
                    ephemeral=True,
                )
                return
            upsert_member(DND_DB_PATH, guild_id, user_id, name=name)
            template = character_builder.sheet_template(splat_key)
            lines = [
                f"Created character `{name}` for `{splat_key}`.",
                "Template fields: " + ", ".join(template.keys()),
            ]
            await interaction.response.send_message("\n".join(lines), ephemeral=True)
        elif action == "show":
            members = chronicle_service.list_members(DND_DB_PATH, guild_id)
            member = next((m for m in members if m.get("user_id") == user_id), None)
            if not member:
                await interaction.response.send_message("No character found for this server.", ephemeral=True)
                return
            edition_label = _edition_label(edition)
            lines = [
                f"Member: {member.get('name')}",
                f"Edition: {edition_label}",
                f"Allowed splats: {', '.join(allowed)}",
            ]
            await interaction.response.send_message("\n".join(lines), ephemeral=True)
        else:
            await interaction.response.send_message("Use `create` or `show`.", ephemeral=True)

    @dnd.command(name="xp", description="XP tracking helpers.")
    async def xp(interaction: Any, action: str = "add", amount: float = 1.0, reason: str = "") -> None:  # type: ignore[misc]
        if await _enforce_setup(interaction):
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
                return
            lines = "\n".join(f"- {e['amount']}: {e['reason']}" for e in entries[-10:])
            await interaction.response.send_message(lines, ephemeral=True)
        else:
            await interaction.response.send_message("Use `add` or `history`.", ephemeral=True)

    @dnd.command(name="reward", description="Auto reward helpers.")
    async def reward(interaction: Any, action: str = "status", rule_name: str = "", threshold: int = 10, reward: float = 1.0) -> None:  # type: ignore[misc]
        if await _enforce_setup(interaction):
            return
        if not interaction.guild:
            if reply_ephemeral:
                await reply_ephemeral(interaction, "Use in a server.")
            return
        guild_id = int(interaction.guild.id)
        user_id = int(interaction.user.id)
        if action == "create":
            if not rule_name:
                await interaction.response.send_message("Provide rule_name.", ephemeral=True)
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
            await interaction.response.send_message(content or "No data.", ephemeral=True)
        else:
            await interaction.response.send_message("Use `create` or `status`.", ephemeral=True)

    @dnd.command(name="server", description="D&D server/chronicle settings.")
    async def server(interaction: Any, action: str = "show", name: str = "Chronicle", edition: str = "") -> None:  # type: ignore[misc]
        if not interaction.guild:
            if reply_ephemeral:
                await reply_ephemeral(interaction, "Use in a server.")
            return
        guild_id = int(interaction.guild.id)
        if action == "setup":
            if not edition:
                await interaction.response.send_message("Choose an edition: `/dnd server setup edition:20th`", ephemeral=True)
                return
            label = _edition_label(edition)
            defaults = _edition_defaults(edition)
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
        if await _enforce_setup(interaction):
            return
        if not interaction.guild:
            if reply_ephemeral:
                await reply_ephemeral(interaction, "Use in a server.")
            return
        guild_id = int(interaction.guild.id)
        user_id = int(interaction.user.id)
        from dnd import proxy_group_service
        if action == "create":
            if not name:
                await interaction.response.send_message("Provide group name.", ephemeral=True)
                return
            proxy_group_service.create_proxy_group(DND_DB_PATH, guild_id, user_id, name, description)
            await interaction.response.send_message(f"Created proxy group `{name}`.", ephemeral=True)
        elif action == "add":
            if not name or not proxy:
                await interaction.response.send_message("Provide group name and proxy name.", ephemeral=True)
                return
            result = proxy_group_service.add_proxy_to_group(DND_DB_PATH, guild_id, user_id, name, proxy)
            if not result:
                await interaction.response.send_message("Proxy not found.", ephemeral=True)
                return
            await interaction.response.send_message(f"Added proxy `{proxy}` to group `{name}`.", ephemeral=True)
        elif action == "remove":
            if not name or not proxy:
                await interaction.response.send_message("Provide group name and proxy name.", ephemeral=True)
                return
            removed = proxy_group_service.remove_proxy_from_group(DND_DB_PATH, guild_id, user_id, name, proxy)
            await interaction.response.send_message("Removed." if removed else "Proxy not in group.", ephemeral=True)
        elif action == "list":
            groups = proxy_group_service.list_proxy_groups(DND_DB_PATH, guild_id, user_id)
            if not groups:
                await interaction.response.send_message("No proxy groups yet.", ephemeral=True)
                return
            lines = []
            for g in groups:
                members = proxy_group_service.list_group_proxies(DND_DB_PATH, guild_id, user_id, g["name"])
                members_hint = ", ".join(m.get("name", "") for m in members) if members else "empty"
                lines.append(f"- {g['name']}: {members_hint}")
            await interaction.response.send_message("\n".join(lines), ephemeral=True)
        else:
            await interaction.response.send_message("Use `create`, `add`, `remove`, or `list`.", ephemeral=True)

    @dnd.command(name="reproxy", description="Reproxy/message tracking helpers.")
    async def reproxy(interaction: Any, action: str = "list", group: str = "", proxy: str = "", target_channel: str = "", source_message: str = "", content: str = "") -> None:  # type: ignore[misc]
        if await _enforce_setup(interaction):
            return
        if not interaction.guild:
            if reply_ephemeral:
                await reply_ephemeral(interaction, "Use in a server.")
            return
        guild_id = int(interaction.guild.id)
        user_id = int(interaction.user.id)
        from dnd import proxy_group_service
        if action == "create":
            if not group or not proxy or not target_channel:
                await interaction.response.send_message("Provide group, proxy, and target_channel.", ephemeral=True)
                return
            try:
                channel_id = int(target_channel)
            except ValueError:
                await interaction.response.send_message("target_channel must be a channel ID.", ephemeral=True)
                return
            proxy_row = proxy_service.get_proxy(DND_DB_PATH, guild_id, user_id, proxy)
            if not proxy_row:
                await interaction.response.send_message("Proxy not found.", ephemeral=True)
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
        elif action == "list":
            jobs = proxy_group_service.list_reproxy_jobs(DND_DB_PATH, guild_id, user_id)
            if not jobs:
                await interaction.response.send_message("No reproxy jobs yet.", ephemeral=True)
                return
            lines = "\n".join(
                f"- {j['created_at']}: {j['group_name']} -> <#{j['target_channel_id']}> proxy={j['proxy_id']} src={j['source_message_id']}"
                for j in jobs[:20]
            )
            await interaction.response.send_message(lines, ephemeral=True)
        else:
            await interaction.response.send_message("Use `create` or `list`.", ephemeral=True)
