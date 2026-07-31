from __future__ import annotations

from typing import Any, Dict

_STATS_5E = ["strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"]
_STATS_20TH = [
    "strength",
    "dexterity",
    "stamina",
    "charisma",
    "manipulation",
    "appearance",
    "perception",
    "intelligence",
    "wits",
]


def _modifier(score: int | float | None) -> int:
    try:
        value = int(score or 0)
    except Exception:
        return 0
    return (value - 10) // 2


def _label(key: str) -> str:
    return {
        "strength": "STR",
        "dexterity": "DEX",
        "constitution": "CON",
        "intelligence": "INT",
        "wisdom": "WIS",
        "charisma": "CHA",
        "stamina": "STA",
        "manipulation": "MAN",
        "appearance": "APP",
        "perception": "PER",
        "wits": "WIT",
    }.get(key, key.upper())


def edition_stats(edition: str) -> list[str]:
    edition = (edition or "").strip().lower()
    if edition.startswith("20th"):
        return list(_STATS_20TH)
    return list(_STATS_5E)


def build_derived(edition: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    edition = (edition or "").strip().lower()
    stats_key = edition_stats(edition)
    score_map = {stat: _to_int(fields.get(stat)) for stat in stats_key}
    mods = {f"{stat}_mod": _modifier(score_map.get(stat)) for stat in stats_key}
    derived: Dict[str, Any] = {"stats": stats_key, "scores": score_map, "modifiers": mods}

    if edition.startswith("20th") or edition.startswith("custom"):
        derived.update(
            {
                "willpower": _to_int(fields.get("willpower")),
                "health": _to_int(fields.get("health")),
                "aggravated": _to_int(fields.get("aggravated")),
            }
        )
        return derived

    dex_mod = mods.get("dexterity_mod", 0)
    ac_base = _to_int(fields.get("ac_base"))
    ac = max(10 + dex_mod, ac_base if ac_base else 10 + dex_mod)
    con_mod = mods.get("constitution_mod", 0)
    level = _to_int(fields.get("level"))
    hit_die = _to_int(fields.get("hit_die") or fields.get("hit_dice") or 8)
    max_hp = _to_int(fields.get("max_hp") or (hit_die + con_mod * level))
    proficiency = 2 + max(0, level - 1) // 4
    speed = _to_int(fields.get("speed") or 30)
    passive = 10 + _to_int(fields.get("passive_perception") or 0)
    derived.update(
        {
            "ac": ac,
            "max_hp": max_hp,
            "current_hp": _to_int(fields.get("current_hp") or derived["max_hp"]),
            "hit_die": hit_die,
            "level": level,
            "proficiency": proficiency,
            "speed": speed,
            "passive_perception": passive,
            "armor": fields.get("armor") or "",
            "shield": fields.get("shield") or "",
            "weapons": _clean_list(fields.get("weapons")),
        }
    )
    return derived


def render_derived(edition: str, derived: Dict[str, Any]) -> str:
    edition = (edition or "").strip().lower()
    lines = ["**Derived Stats**"]
    if edition.startswith("20th") or edition.startswith("custom"):
        labels = {
            "willpower": "Willpower",
            "health": "Health",
            "aggravated": "Aggravated",
        }
        for key in ["willpower", "health", "aggravated"]:
            lines.append(f"{labels[key]}: {derived.get(key, 0)}")
        return "\n".join(lines)

    lines.append(f"AC: {derived.get('ac', 10)}")
    lines.append(f"HP: {derived.get('current_hp', 0)}/{derived.get('max_hp', 0)}")
    lines.append(f"Proficiency: +{derived.get('proficiency', 2)}")
    lines.append(f"Speed: {derived.get('speed', 30)} ft")
    if derived.get("armor"):
        lines.append(f"Armor: {derived['armor']}")
    if derived.get("shield"):
        lines.append(f"Shield: {derived['shield']}")
    weapons = derived.get("weapons") or []
    if weapons:
        lines.append("Weapons: " + ", ".join(weapons))
    return "\n".join(lines)


def render_ability_block(edition: str, derived: Dict[str, Any]) -> str:
    edition = (edition or "").strip().lower()
    stats = derived.get("stats") or edition_stats(edition)
    scores = derived.get("scores") or {}
    mods = derived.get("modifiers") or {}
    lines = ["**Abilities**"]
    for stat in stats:
        score = scores.get(stat, 0)
        mod = mods.get(f"{stat}_mod", _modifier(score))
        lines.append(f"{_label(stat)}: {score} ({mod:+})")
    return "\n".join(lines)


def _to_int(value: Any) -> int:
    if value is None:
        return 0
    text = str(value).strip()
    if not text:
        return 0
    try:
        return int(text)
    except Exception:
        return 0


def _clean_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value)
    if "," in text:
        return [part.strip() for part in text.split(",") if part.strip()]
    return [part.strip() for part in text.splitlines() if part.strip()]
