from __future__ import annotations

import secrets
from dataclasses import dataclass, field


@dataclass
class RollResults20th:
    pool: int = 0
    difficulty: int = 2
    willpower: bool = False
    mod: int = 0
    spec: str = ""
    cancel_ones: bool = False
    nightmare: int = 0
    black_dice: list[int] = field(default_factory=list)
    nightmare_dice: list[int] = field(default_factory=list)

    successes: int = 0
    outcome: str = ""
    color: int = 0x000000

    def compute(self) -> None:
        success_count = 0
        botches = 0
        for d in self.black_dice:
            if d == 1 and not self.cancel_ones:
                botches += 1
            elif d >= self.difficulty:
                success_count += 1
        for d in self.nightmare_dice:
            if d == 10:
                success_count += 1
            elif d >= self.difficulty:
                success_count += 1
            elif d == 1 and not self.cancel_ones:
                botches += 1

        if self.spec:
            success_count += 1

        success_count += self.mod
        if self.willpower:
            success_count += 1

        if success_count <= 0 and botches > 0:
            self.outcome = "Botch"
            self.color = 0x7A0000
            self.successes = 0
            return

        if success_count >= self.difficulty:
            extra = success_count - self.difficulty
            if extra >= 5:
                self.outcome = f"Exceptional Success ({extra} extra)"
                self.color = 0x0A5C0A
            else:
                self.outcome = "Success"
                self.color = 0x155815
        else:
            self.outcome = "Failure"
            self.color = 0xB03030

        self.successes = success_count


def _emoji_for(die: int, diff: int, nightmare: bool = False) -> str:
    if nightmare:
        if die == 10:
            return "💜"
        return "💢"
    if die == 10:
        return "⭐"
    if die == 1:
        return "💀"
    if die >= diff:
        return "✅"
    return "❌"


def format_dice_emojis(roll: RollResults20th) -> str:
    parts: list[str] = []
    for d in roll.black_dice:
        parts.append(_emoji_for(d, roll.difficulty, False))
    if roll.nightmare_dice:
        parts.append("—")
    for d in roll.nightmare_dice:
        parts.append(_emoji_for(d, roll.difficulty, True))
    return " ".join(parts) if parts else "—"


def build_dice_embed(
    roll: RollResults20th, author_name: str, author_icon: str | None = None, character_name: str | None = None, notes: str | None = None
) -> dict:
    title = f"Pool {roll.pool} | Diff {roll.difficulty}"
    if roll.nightmare:
        title += f" | Nightmare {roll.nightmare}"
    if roll.willpower:
        title += " | WP"
    if roll.mod:
        title += f" | Mod {roll.mod}"
    if roll.spec:
        title += " | Spec"
    if roll.cancel_ones:
        title += " | No Botch"

    fields = []
    if character_name:
        fields.append({"name": "Character", "value": character_name, "inline": False})
    if roll.black_dice:
        fields.append({"name": "Dice", "value": " ".join(str(x) for x in sorted(roll.black_dice)), "inline": True})
    if roll.nightmare_dice:
        fields.append({"name": "Nightmare", "value": " ".join(str(x) for x in sorted(roll.nightmare_dice)), "inline": True})
    if roll.spec:
        fields.append({"name": "Specialty", "value": roll.spec, "inline": True})
    if roll.mod:
        fields.append({"name": "Modifier", "value": str(roll.mod), "inline": True})
    if notes:
        fields.append({"name": "Notes", "value": notes, "inline": False})

    fields.append({"name": "Result", "value": f"{roll.successes} successes | {roll.outcome}", "inline": False})
    fields.append(
        {
            "name": "\u200b",
            "value": "[Commands](https://www.patreon.com/MiraiMiki)",
            "inline": False,
        }
    )

    embed: dict = {
        "title": title,
        "description": format_dice_emojis(roll),
        "color": roll.color,
        "fields": fields,
        "url": "https://www.patreon.com/MiraiMiki",
    }
    if author_name:
        embed["author"] = {"name": author_name}
    if author_icon:
        embed["author"]["icon_url"] = author_icon

    return embed


def parse_20th_pool(value: object) -> int:
    text = str(value or "").strip()
    if not text:
        raise ValueError("Pool must be provided.")
    if not text.isdigit():
        raise ValueError("Pool must be a positive integer.")
    result = int(text)
    if result < 1 or result > 50:
        raise ValueError("Pool must be between 1 and 50.")
    return result


def parse_difficulty(value: object) -> int:
    text = str(value or "").strip()
    if not text:
        raise ValueError("Difficulty must be provided.")
    if not text.isdigit():
        raise ValueError("Difficulty must be an integer.")
    result = int(text)
    if result < 2 or result > 10:
        raise ValueError("Difficulty must be between 2 and 10.")
    return result


def roll_d20() -> int:
    return int(secrets.randbelow(10) + 1)


def roll_pool(count: int, difficulty: int, nightmare: int = 0, willpower: int = 0) -> RollResults20th:
    if nightmare + willpower > count:
        raise ValueError("Nightmare and willpower dice cannot exceed pool size.")
    pool = max(1, count)
    regular_dice = pool - nightmare - willpower
    black: list[int] = [roll_d20() for _ in range(regular_dice)]
    nightmare_dice: list[int] = [roll_d20() for _ in range(nightmare)]
    willpower_dice: list[int] = [roll_d20() for _ in range(willpower)]
    results = RollResults20th(pool=pool, difficulty=difficulty, black_dice=black, nightmare_dice=nightmare_dice + willpower_dice)
    results.compute()
    return results
