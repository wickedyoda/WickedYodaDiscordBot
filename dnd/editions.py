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
    sheet_roll_supported: bool = False
    proxy_supported: bool = True
    xp_supported: bool = True
    reward_supported: bool = True
    splat_metadata: Dict[str, Dict[str, str]] = field(default_factory=dict)


WIKI_REFERENCE_URL = "https://share.google/aEG5ltpsiHwTaw2Zc"
WIKI_SUMMARY = "Dungeons & Dragons is a fantasy tabletop role-playing game (TTRPG) originally created and designed by Gary Gygax and Dave Arneson. First published in 1974 by TSR; published by Wizards of the Coast since 1997. Derived from miniature wargames and Chainmail (1971). Recognized as the beginning of modern role-playing games."


_EDITIONS: Dict[str, EditionInfo] = {}


def _register(
    key: str,
    label: str,
    default_splats: List[str],
    description: str,
    roll_systems: List[str],
    character_sheet_supported: bool,
    sheet_roll_supported: bool = False,
    proxy_supported: bool = True,
    xp_supported: bool = True,
    reward_supported: bool = True,
    splat_metadata: Optional[Dict[str, Dict[str, str]]] = None,
) -> None:
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
        splat_metadata=splat_metadata or {},
    )
    _EDITIONS[key] = info


_SPLATS_20TH = {
    "vampire20th": {"name": "Vampire", "version": "20th", "slug": "vampire20th"},
    "ghoul20th": {"name": "Ghoul", "version": "20th", "slug": "ghoul20th"},
    "human20th": {"name": "Human", "version": "20th", "slug": "human20th"},
    "werewolf20th": {"name": "Werewolf", "version": "20th", "slug": "werewolf20th"},
    "changeling20th": {"name": "Changeling", "version": "20th", "slug": "changeling20th"},
    "mage20th": {"name": "Mage", "version": "20th", "slug": "mage20th"},
    "wraith20th": {"name": "Wraith", "version": "20th", "slug": "wraith20th"},
    "demon20th": {"name": "Demon", "version": "20th", "slug": "demon20th"},
}

_SPLATS_5TH = {
    "vampire5th": {"name": "Vampire", "version": "5th", "slug": "vampire5th", "sheetSlug": "v5"},
    "hunter5th": {"name": "Hunter", "version": "5th", "slug": "hunter5th", "sheetSlug": "h5"},
    "werewolf5th": {"name": "Werewolf", "version": "5th", "slug": "werewolf5th", "sheetSlug": "w5"},
    "human5th": {"name": "Human", "version": "5th", "slug": "human5th", "sheetSlug": "human5"},
    "ghoul5th": {"name": "Ghoul", "version": "5th", "slug": "ghoul5th", "sheetSlug": "ghoul5"},
}

_SPECIES_5E_2024 = [
    {"name": "Dragonborn", "slug": "dragonborn"},
    {"name": "Dwarf", "slug": "dwarf"},
    {"name": "Elf", "slug": "elf"},
    {"name": "Gnome", "slug": "gnome"},
    {"name": "Half-Elf", "slug": "half-elf"},
    {"name": "Half-Orc", "slug": "half-orc"},
    {"name": "Halfling", "slug": "halfling"},
    {"name": "Human", "slug": "human"},
    {"name": "Tiefling", "slug": "tiefling"},
]

_register(
    key="20th",
    label="20th Anniversary (World of Darkness)",
    default_splats=list(_SPLATS_20TH.keys()),
    description="Classic World of Darkness 20th Anniversary rules with splat-based character types.",
    roll_systems=["20th"],
    character_sheet_supported=True,
    sheet_roll_supported=False,
    splat_metadata=_SPLATS_20TH,
)

_register(
    key="5e",
    label="5th Edition / 2024 Edition",
    default_splats=list(_SPLATS_5TH.keys()) + [s["slug"] for s in _SPECIES_5E_2024],
    description="D&D 5th/2024 edition rules with core races and WoD 5th splat support.",
    roll_systems=["5e", "5th", "2024"],
    character_sheet_supported=True,
    sheet_roll_supported=True,
    splat_metadata={**_SPLATS_5TH, **{s["slug"]: {"name": s["name"], "version": "5e", "slug": s["slug"]} for s in _SPECIES_5E_2024}},
)

_register(
    key="5th",
    label="5th Edition / 2024 Edition",
    default_splats=list(_SPLATS_5TH.keys()) + [s["slug"] for s in _SPECIES_5E_2024],
    description="D&D 5th/2024 edition rules with core races and WoD 5th splat support.",
    roll_systems=["5e", "5th", "2024"],
    character_sheet_supported=True,
    sheet_roll_supported=True,
    splat_metadata={**_SPLATS_5TH, **{s["slug"]: {"name": s["name"], "version": "5th", "slug": s["slug"]} for s in _SPECIES_5E_2024}},
)

_register(
    key="2024",
    label="5th Edition / 2024 Edition",
    default_splats=list(_SPLATS_5TH.keys()) + [s["slug"] for s in _SPECIES_5E_2024],
    description="D&D 5th/2024 edition rules with core races and WoD 5th splat support.",
    roll_systems=["5e", "5th", "2024"],
    character_sheet_supported=True,
    sheet_roll_supported=True,
    splat_metadata={**_SPLATS_5TH, **{s["slug"]: {"name": s["name"], "version": "2024", "slug": s["slug"]} for s in _SPECIES_5E_2024}},
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


def splat_label(splat: str) -> str:
    edition = _edition_for_splat(splat)
    if not edition:
        return splat
    meta = edition.splat_metadata.get(splat)
    if not meta:
        return splat
    return meta.get("name", splat)


def is_splat_allowed(edition_key: str, splat: str) -> bool:
    edition = get_edition(edition_key)
    if not edition:
        return False
    return splat in edition.default_splats


def _edition_for_splat(splat: str) -> Optional[EditionInfo]:
    for edition in _EDITIONS.values():
        if splat in edition.default_splats:
            return edition
    return None
