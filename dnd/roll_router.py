from __future__ import annotations

from typing import Any

from dnd import editions
from dnd.roll_20th import roll_pool as roll_20th_pool
from dnd.roll_5th import build_sheet_pool, roll_sheet_pool


class RollError(Exception):
    pass


def route_roll(edition: str, system: str, pool: int = 1, difficulty: int = 6, modifier: int = 0, **kwargs: Any) -> dict:
    edition_info = editions.get_edition(edition)
    if not edition_info:
        raise RollError(f"Unsupported edition: {edition}")
    allowed = edition_info.roll_systems or []
    canonical = system.lower()
    target = next((s for s in allowed if s.lower() == canonical), None)
    if target is None and not allowed:
        target = canonical
    elif target is None:
        raise RollError(f"System '{system}' not available for {edition_info.label}")

    if target in ("5e", "5th", "custom"):
        actual_pool = build_sheet_pool(base=pool, modifier=modifier, hunger=bool(kwargs.get("hunger")))
        result = roll_sheet_pool(pool=actual_pool, difficulty=difficulty, hunger=bool(kwargs.get("hunger")))
        return {
            "edition": edition,
            "system": target,
            "pool": result.pool,
            "difficulty": result.difficulty,
            "successes": result.successes,
            "outcome": result.outcome,
            "dice": result.dice,
        }

    if target == "20th":
        result = roll_20th_pool(
            count=pool,
            difficulty=difficulty,
            nightmare=int(kwargs.get("nightmare", 0)),
            willpower=int(kwargs.get("willpower", 0)),
        )
        dice = result.black_dice + result.nightmare_dice
        return {
            "edition": edition,
            "system": target,
            "pool": result.pool,
            "difficulty": result.difficulty,
            "successes": result.successes,
            "outcome": result.outcome,
            "dice": dice,
        }

    raise RollError(f"Unhandled roll system: {target}")
