from __future__ import annotations

import secrets
from dataclasses import dataclass, field


@dataclass
class InitiativeCharacter:
    member_id: int
    display_name: str
    dex_wits: int
    modifier: int = 0
    extra_actions: int = 1
    roll: int = 0
    total: int = 0

    def compute(self) -> None:
        self.roll = int(secrets.randbelow(10) + 1)
        self.total = max(1, self.dex_wits + self.roll + self.modifier)


@dataclass
class InitiativeTracker:
    channel_id: int
    guild_id: int
    owner_id: int
    characters: list[InitiativeCharacter] = field(default_factory=list)
    phase: str = "roll"
    round: int = 1

    def ordered(self) -> list[InitiativeCharacter]:
        return sorted(self.characters, key=lambda x: (-x.total, x.member_id))
