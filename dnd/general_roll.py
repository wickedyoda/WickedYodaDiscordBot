from __future__ import annotations

import secrets
from dataclasses import dataclass, field


@dataclass
class DiceSet:
    sides: int = 0
    dice: int = 0
    results: list[int] = field(default_factory=list)


def roll_one(sides: int) -> int:
    sides = max(1, min(int(sides), 500))
    return int(secrets.randbelow(sides) + 1)


def roll_many(dice: int, sides: int) -> DiceSet:
    result = DiceSet(sides=int(sides), dice=int(dice))
    result.results = [roll_one(sides) for _ in range(result.dice)]
    return result


def parse_sets(
    set1: str | None = None, set2: str | None = None, set3: str | None = None, set4: str | None = None, set5: str | None = None
) -> dict[int, DiceSet]:
    import re

    raw = [s for s in [set1, set2, set3, set4, set5] if s]
    sets: dict[int, DiceSet] = {}
    for item in raw:
        item = item.strip()
        if not item:
            continue
        match = re.fullmatch(r"(\d+)\s*d\s*(\d+)", item, re.IGNORECASE)
        if not match:
            raise ValueError(f"Invalid dice set format: {item}")
        dice_count = int(match.group(1))
        sides = int(match.group(2))
        if dice_count > 50 or sides > 500 or dice_count < 1 or sides < 1:
            raise ValueError("Dice out of bounds for a set.")
        if sides in sets:
            sets[sides].dice += dice_count
        else:
            sets[sides] = DiceSet(sides=sides, dice=dice_count)
    return sets


def build_general_embed(
    sets: dict[int, DiceSet],
    modifier: int | None,
    difficulty: int | None,
    notes: str | None,
    author_name: str,
    author_icon: str | None = None,
) -> dict:
    total = 0
    fields = []
    for s in sets.values():
        s.results = [roll_one(s.sides) for _ in range(s.dice)]
        total += sum(s.results)
        preview = " ".join(str(x) for x in s.results)
        fields.append(
            {
                "name": f"{s.dice}d{s.sides}",
                "value": f"```css\n{preview}\n```",
                "inline": True,
            }
        )
    if modifier:
        total += int(modifier)
        fields.append({"name": "Modifier", "value": f"```css\n{modifier}\n```", "inline": True})
    if notes:
        fields.append({"name": "Notes", "value": notes, "inline": False})

    result_value = f"Total of {total}"
    color = 0x000000
    if difficulty:
        if total < int(difficulty):
            result_value += f" vs diff {difficulty}\nMissing {int(difficulty) - total}\n```ansi\nFailed\n```"
            color = 0xCD0E0E
        else:
            result_value += f" vs diff {difficulty}\nMargin of {total - int(difficulty)}\n```ansi\nPassed\n```"
            color = 0x66FF33

    fields.append({"name": "Result", "value": result_value, "inline": False})
    fields.append(
        {
            "name": "\u200b",
            "value": "[Website](https://realmofdarkness.app/) | [Commands](https://realmofdarkness.app/20th/commands/) | [Patreon](https://www.patreon.com/MiraiMiki)",
            "inline": False,
        }
    )

    embed: dict = {
        "title": "General Roll",
        "color": color,
        "fields": fields,
        "url": "https://realmofdarkness.app/",
    }
    if author_name:
        embed["author"] = {"name": author_name}
    if author_icon:
        embed["author"]["icon_url"] = author_icon
    return embed
