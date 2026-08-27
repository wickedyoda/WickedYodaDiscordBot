from __future__ import annotations

import secrets
from dataclasses import dataclass, field


@dataclass
class SheetRollResult:
    pool: int = 0
    difficulty: int = 6
    hunger: bool = False
    desperation: bool = False
    rage: bool = False
    modifier: int = 0
    successes: int = 0
    outcome: str = ""
    dice: list[int] = field(default_factory=list)


def roll_v5_die() -> int:
    return int(secrets.randbelow(10) + 1)


def build_sheet_pool(base: int, hunger: bool = False, modifier: int = 0, desperation: bool = False, rage: bool = False) -> int:
    pool = base + modifier
    if hunger:
        pool += 1
    if desperation:
        pool += 1
    if rage:
        pool += 1
    if pool < 0:
        return 0
    return pool


def roll_sheet_pool(
    pool: int, difficulty: int = 6, hunger: bool = False, modifier: int = 0, desperation: bool = False, rage: bool = False
) -> SheetRollResult:
    actual_pool = build_sheet_pool(pool, hunger=hunger, modifier=modifier, desperation=desperation, rage=rage)
    dice = [roll_v5_die() for _ in range(actual_pool)]
    successes = 0
    for d in dice:
        if d >= difficulty:
            successes += 1
        if d == 10:
            successes += 1
    result = SheetRollResult(
        pool=actual_pool, difficulty=difficulty, hunger=hunger, desperation=desperation, rage=rage, dice=dice, successes=successes
    )
    if successes >= difficulty:
        result.outcome = "Success"
    else:
        result.outcome = "Failure"
    if hunger and any(d == 1 for d in dice):
        result.outcome += " (Bestial Failure)"
    return result
