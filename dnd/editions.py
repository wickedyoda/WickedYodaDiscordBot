from __future__ import annotations

from typing import Dict, List

D20_SPLATS: List[str] = [
    "vampire20th",
    "werewolf",
    "mage",
    "demon",
    "changeling",
    "wraith",
    "ghoul",
    "human",
]

V5_SPLATS: List[str] = [
    "vampire5th",
    "werewolf5th",
    "hunter5th",
    "ghoul5th",
    "human5th",
]

EDITION_DEFAULTS: Dict[str, List[str]] = {
    "20th": D20_SPLATS,
    "5e": V5_SPLATS,
    "5th": V5_SPLATS,
    "2024": V5_SPLATS,
    "custom": [],
}

EDITION_LABELS: Dict[str, str] = {
    "20th": "20th Anniversary (World of Darkness)",
    "5e": "5th Edition / 2024 Edition",
    "5th": "5th Edition / 2024 Edition",
    "2024": "5th Edition / 2024 Edition",
    "custom": "Custom",
}
