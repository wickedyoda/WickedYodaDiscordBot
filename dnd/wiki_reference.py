from __future__ import annotations

WIKI_REFERENCE_URL = "https://share.google/aEG5ltpsiHwTaw2Zc"
WIKI_SUMMARY = (
    "Dungeons & Dragons is a fantasy tabletop role-playing game (TTRPG) originally created and designed by "
    "Gary Gygax and Dave Arneson. First published in 1974 by TSR; published by Wizards of the Coast since 1997. "
    "Derived from miniature wargames and Chainmail (1971). Recognized as the beginning of modern role-playing games."
)

ROOT_PAGE = "Dungeons & Dragons"
LEVEL2_PAGES: list[str] = [
    "Editions of Dungeons & Dragons",
    "Dungeons & Dragons 5th edition",
    "Dungeons & Dragons 4th edition",
    "Advanced Dungeons & Dragons 2nd edition",
    "Dungeons & Dragons 3rd edition",
    "Player's Handbook",
    "Dungeon Master's Guide",
    "Monster Manual",
    "Dragon (Dungeons & Dragons)",
    "Dwarf (Dungeons & Dragons)",
    "Elf (Dungeons & Dragons)",
    "Gnome (Dungeons & Dragons)",
    "Tiefling",
    "Halfling (Dungeons & Dragons)",
    "Half-elf",
    "Orc",
]

LEVEL3_PAGES: list[str] = [
    "Dungeons & Dragons 5th edition",
    "2024 revision of 5th Edition",
    "Dungeons & Dragons 4th edition",
    "Advanced Dungeons & Dragons 2nd edition",
    "Dungeons & Dragons 3rd edition",
    "Open Game License",
    "Dwarf (Dungeons & Dragons)",
    "Elf (Dungeons & Dragons)",
    "Gnome (Dungeons & Dragons)",
    "Tiefling",
    "Half-elf",
    "Player's Handbook",
]

LEVEL2_FALLBACK: dict[str, str] = {
    "Player's Handbook": "Core player rulebook for creating and advancing characters.",
    "Dungeon Master's Guide": "Rules for running campaigns and adjudicating play.",
    "Monster Manual": "Core bestiary for creatures and adversaries.",
}

LEVEL3_FALLBACK: dict[str, str] = {
    "Dungeons & Dragons 5th edition": "Current edition focusing on streamlined, accessible play.",
    "Dungeons & Dragons 4th edition": "Edition with defined roles and tactical combat.",
    "Advanced Dungeons & Dragons 2nd edition": "Classic edition with detailed campaign settings.",
    "Dungeons & Dragons 3rd edition": "Edition with the d20 System and open gaming license.",
    "Open Game License": "Open gaming rules framework published under Wizards of the Coast.",
}
