from __future__ import annotations

import discord
from typing import Any, Dict, List, Optional

from discord import app_commands

from dnd import chronicle_service
from dnd import editions
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

    dnd = bot.tree.get_command("dnd")
    if dnd is None:
        raise RuntimeError("Missing `/dnd` application group.")

    @dnd.command(name="roll", description="20th / 5th Edition dice roll.")
    async def roll(interaction: Any, system: str = "20th", pool: int = 1, difficulty: int = 6, modifier: int = 0, willpower: bool = False, speciality: str | None = None, notes: str | None = None) -> None:  # type: ignore[misc]
        if await _enforce_setup(interaction):
            return
        await _log(interaction, "dnd_roll", f"system={system} pool={pool} diff={difficulty}", success=True)

    @dnd.command(name="sheet", description="Roll a 5th edition sheet pool.")
    async def sheet(interaction: Any, attribute: str, attribute2: str | None = None, skill: str | None = None, discipline: str | None = None, modifier: int = 0, difficulty: int = 6, notes: str | None = None) -> None:  # type: ignore[misc]
        if await _enforce_setup(interaction):
            return
        await _log(interaction, "dnd_sheet", f"attribute={attribute} skill={skill} discipline={discipline}", success=True)

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
