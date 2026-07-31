from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class EditionInfo:
    key: str
    label: str
    default_splats: List[str]
    description: str
    roll_systems: List[str]
    character_sheet_supported: bool
    proxy_supported: bool = True
    xp_supported: bool = True
    reward_supported: bool = True
    sheet_roll_supported: bool = False


_EDITIONS: Dict[str, EditionInfo] = {}


def _register(key: str, label: str, default_splats: List[str], description: str, roll_systems: List[str], character_sheet_supported: bool, sheet_roll_supported: bool = False, proxy_supported: bool = True, xp_supported: bool = True, reward_supported: bool = True) -> None:
    info = EditionInfo(
        key=key,
        label=label,
        default_splats=default_splats,
        description=description,
        roll_systems=roll_systems,
        character_sheet_supported=character_sheet_supported,
        sheet_roll_supported=sheet_roll_supported,
        proxy_supported=proxy_supported,
        xp_supported=xp_supported,
        reward_supported=reward_supported,
    )
    _EDITIONS[key] = info


_register(
    key="20th",
    label="20th Anniversary (World of Darkness)",
    default_splats=["vampire20th", "werewolf20th", "mage20th", "demon20th", "changeling20th", "wraith20th", "ghoul20th", "human20th"],
    description="Classic World of Darkness 20th Anniversary rules with splat-based character types.",
    roll_systems=["20th"],
    character_sheet_supported=True,
    sheet_roll_supported=False,
)

_register(
    key="5e",
    label="5th Edition / 2024 Edition",
    default_splats=["vampire5th", "werewolf5th", "hunter5th", "ghoul5th", "human5th", "dragonborn", "dwarf", "elf", "gnome", "half-elf", "half-orc", "halfling", "human", "tiefling"],
    description="D&D 5th/2024 edition rules with core races and WoD 5th splat support.",
    roll_systems=["5e", "5th", "2024"],
    character_sheet_supported=True,
    sheet_roll_supported=True,
)

_register(
    key="5th",
    label="5th Edition / 2024 Edition",
    default_splats=["vampire5th", "werewolf5th", "hunter5th", "ghoul5th", "human5th", "dragonborn", "dwarf", "elf", "gnome", "half-elf", "half-orc", "halfling", "human", "tiefling"],
    description="D&D 5th/2024 edition rules with core races and WoD 5th splat support.",
    roll_systems=["5e", "5th", "2024"],
    character_sheet_supported=True,
    sheet_roll_supported=True,
)

_register(
    key="2024",
    label="5th Edition / 2024 Edition",
    default_splats=["vampire5th", "werewolf5th", "hunter5th", "ghoul5th", "human5th", "dragonborn", "dwarf", "elf", "gnome", "half-elf", "half-orc", "halfling", "human", "tiefling"],
    description="D&D 5th/2024 edition rules with core races and WoD 5th splat support.",
    roll_systems=["5e", "5th", "2024"],
    character_sheet_supported=True,
    sheet_roll_supported=True,
)

_register(
    key="custom",
    label="Custom",
    default_splats=[],
    description="Custom campaign settings. Configure allowed splats/species manually.",
    roll_systems=["custom"],
    character_sheet_supported=True,
    sheet_roll_supported=False,
)


EDITION_CHOICES = [
    {"name": "20th Anniversary / World of Darkness", "value": "20th"},
    {"name": "5th Edition / 2024 Edition", "value": "5e"},
    {"name": "Custom", "value": "custom"},
]


def get_edition(key: str) -> Optional[EditionInfo]:
    return _EDITIONS.get((key or "").strip().lower())


def all_editions() -> List[EditionInfo]:
    return list(_EDITIONS.values())


def edition_help(edition: str) -> str:
    info = get_edition(edition)
    if not info:
        return f"Edition `{edition}` is not recognized."
    lines = [
        f"**{info.label}**",
        info.description,
        f"Roll systems: {', '.join(info.roll_systems)}",
        f"Default splats/species: {', '.join(info.default_splats) if info.default_splats else 'none'}",
    ]
    if info.character_sheet_supported:
        lines.append("Character sheets: supported")
    if info.sheet_roll_supported:
        lines.append("Sheet roll engine: available")
    return "\n".join(lines)
