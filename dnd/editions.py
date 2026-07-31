from __future__ import annotations

from typing import Dict, List

D20_SPLATS: List[str] = [
    "vampire20th",
    "werewolf20th",
    "mage20th",
    "demon20th",
    "changeling20th",
    "wraith20th",
    "ghoul20th",
    "human20th",
]

V5_SPLATS: List[str] = [
    "vampire5th",
    "werewolf5th",
    "hunter5th",
    "ghoul5th",
    "human5th",
]

SPECIES_5E_2024: List[str] = [
    "dragonborn",
    "dwarf",
    "elf",
    "gnome",
    "half-elf",
    "half-orc",
    "halfling",
    "human",
    "tiefling",
]

EDITION_DEFAULTS: Dict[str, List[str]] = {
    "20th": D20_SPLATS,
    "5e": V5_SPLATS + SPECIES_5E_2024,
    "5th": V5_SPLATS + SPECIES_5E_2024,
    "2024": V5_SPLATS + SPECIES_5E_2024,
    "custom": [],
}

EDITION_LABELS: Dict[str, str] = {
    "20th": "20th Anniversary (World of Darkness)",
    "5e": "5th Edition / 2024 Edition",
    "5th": "5th Edition / 2024 Edition",
    "2024": "5th Edition / 2024 Edition",
    "custom": "Custom",
}
