"""
Achievement badges system for WickedYoda bot.

Tracks user milestones and awards badges. Uses the existing SQLite DB
for persistence. Achievements are data-driven, making them easy to
add and configure.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


# Achievement definitions.
# trigger: the internal event that unlocks this badge
#   - "message_count": unlock when user sends N messages (uses member_activity data)
#   - "command_use": unlock when user uses a specific command N times
#   - "daily_streak": unlock for consecutive daily logins
#   - "cookie_balance": unlock when cookie balance reaches N
#   - "trivia_correct": unlock when user answers N trivia questions correctly
#   - "rps_win": unlock when user wins N RPS games
#   - "guess_win": unlock when user wins N guess games
#   - "birthday_set": unlock when user sets their birthday
#   - "roast_used": unlock when user uses /roastme N times
#   - "wisdom_asked": unlock when user asks for wisdom N times
#   - "gif_used": unlock when user uses /gif N times
#   - "compliment_given": unlock when user uses /compliment N times
#   - "trivia_played": unlock when user participates in N trivia rounds
#   - "eightball_used": unlock when user asks the magic 8-ball N times
#   - "roll_used": unlock when user rolls dice N times
#   - "meme_viewed": unlock when user views memes N times
#   - "cat_viewed": unlock when user views cat images N times
#   - "dadjoke_viewed": unlock when user tells themselves a dad joke N times

ACHIEVEMENTS: dict[str, dict] = {
    # Message activity achievements
    "chatty_cathy": {
        "title": "Chatty Cathy",
        "description": "Sent 100 messages in a managed server.",
        "emoji": "💬",
        "trigger": "message_count",
        "threshold": 100,
    },
    "conversationalist": {
        "title": "Conversationalist",
        "description": "Sent 1,000 messages in managed servers.",
        "emoji": "🗣️",
        "trigger": "message_count",
        "threshold": 1000,
    },
    "titan_of_talk": {
        "title": "Titan of Talk",
        "description": "Sent 5,000 messages in managed servers.",
        "emoji": "📢",
        "trigger": "message_count",
        "threshold": 5000,
    },
    # Command usage achievements
    "fortune_seeker": {
        "title": "Fortune Seeker",
        "description": "Asked for wisdom 25 times.",
        "emoji": "🔮",
        "trigger": "wisdom_asked",
        "threshold": 25,
    },
    "wisdom_master": {
        "title": "Wisdom Master",
        "description": "Asked for wisdom 100 times.",
        "emoji": "🧙",
        "trigger": "wisdom_asked",
        "threshold": 100,
    },
    "roast_survivor": {
        "title": "Roast Survivor",
        "description": "Used /roastme 25 times.",
        "emoji": "🔥",
        "trigger": "roast_used",
        "threshold": 25,
    },
    "compliment_master": {
        "title": "Compliment Master",
        "description": "Given 50 compliments via /compliment.",
        "emoji": "💝",
        "trigger": "compliment_given",
        "threshold": 50,
    },
    "gif_enthusiast": {
        "title": "GIF Enthusiast",
        "description": "Posted 25 reaction GIFs.",
        "emoji": "🎬",
        "trigger": "gif_used",
        "threshold": 25,
    },
    "meme_connoisseur": {
        "title": "Meme Connoisseur",
        "description": "Viewed 50 memes.",
        "emoji": "🤡",
        "trigger": "meme_viewed",
        "threshold": 50,
    },
    "cat_lover": {
        "title": "Cat Lover",
        "description": "Viewed 25 cat images.",
        "emoji": "🐱",
        "trigger": "cat_viewed",
        "threshold": 25,
    },
    "dad_joke_appreciator": {
        "title": "Dad Joke Appreciator",
        "description": "Read 50 dad jokes.",
        "emoji": "👴",
        "trigger": "dadjoke_viewed",
        "threshold": 50,
    },
    "dice_roller": {
        "title": "Dice Roller",
        "description": "Rolled dice 50 times.",
        "emoji": "🎲",
        "trigger": "roll_used",
        "threshold": 50,
    },
    "magic_eight_ball": {
        "title": "Magic 8-Ball Aficionado",
        "description": "Asked the 8-ball 50 questions.",
        "emoji": "🔮",
        "trigger": "eightball_used",
        "threshold": 50,
    },
    # Game achievements
    "trivia_night_champion": {
        "title": "Trivia Night Champion",
        "description": "Answered 10 trivia questions correctly.",
        "emoji": "🏆",
        "trigger": "trivia_correct",
        "threshold": 10,
    },
    "trivia_master": {
        "title": "Trivia Master",
        "description": "Answered 50 trivia questions correctly.",
        "emoji": "🎓",
        "trigger": "trivia_correct",
        "threshold": 50,
    },
    "rps_grandmaster": {
        "title": "RPS Grandmaster",
        "description": "Won 25 rock-paper-scissors games.",
        "emoji": "✊📄✂️",
        "trigger": "rps_win",
        "threshold": 25,
    },
    "number_guesser": {
        "title": "Number Guesser",
        "description": "Won 10 guessing games.",
        "emoji": "🔢",
        "trigger": "guess_win",
        "threshold": 10,
    },
    "trivia_participant": {
        "title": "Trivia Participant",
        "description": "Played in 25 trivia rounds.",
        "emoji": "📚",
        "trigger": "trivia_played",
        "threshold": 25,
    },
    # Cookie economy achievements
    "cookie_jar": {
        "title": "Cookie Jar",
        "description": "Accumulated 100 cookies.",
        "emoji": "🍪",
        "trigger": "cookie_balance",
        "threshold": 100,
    },
    "cookie_mogul": {
        "title": "Cookie Mogul",
        "description": "Accumulated 1,000 cookies.",
        "emoji": "💰",
        "trigger": "cookie_balance",
        "threshold": 1000,
    },
    "cookie_billionaire": {
        "title": "Cookie Billionaire",
        "description": "Accumulated 10,000 cookies.",
        "emoji": "🏦",
        "trigger": "cookie_balance",
        "threshold": 10000,
    },
    # Birthday achievements
    "birthday_star": {
        "title": "Birthday Star",
        "description": "Set your birthday.",
        "emoji": "🎂",
        "trigger": "birthday_set",
        "threshold": 1,
    },
    # Daily streak achievements
    "daily_grind": {
        "title": "Daily Grind",
        "description": "Claimed daily cookies 7 days in a row.",
        "emoji": "📅",
        "trigger": "daily_streak",
        "threshold": 7,
    },
    "cookie_climber": {
        "title": "Cookie Climber",
        "description": "Claimed daily cookies 30 days in a row.",
        "emoji": "📈",
        "trigger": "daily_streak",
        "threshold": 30,
    },
}


class AchievementStore:
    """Store and manage achievement unlocks in SQLite."""

    def __init__(self, db_path: str, lock: threading.Lock | None = None) -> None:
        self._db_path = db_path
        self._lock = lock or threading.Lock()
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _ensure_schema(self) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS achievements_unlocks (
                        guild_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        achievement_key TEXT NOT NULL,
                        unlocked_at TEXT NOT NULL,
                        PRIMARY KEY (guild_id, user_id, achievement_key)
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS achievement_progress (
                        guild_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        trigger_type TEXT NOT NULL,
                        count INTEGER NOT NULL DEFAULT 0,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (guild_id, user_id, trigger_type)
                    )
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_ach_progress_guild ON achievement_progress(guild_id, user_id)")
                conn.commit()

    def _now(self) -> str:
        return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

    def _increment_progress(self, guild_id: int, user_id: int, trigger_type: str, increment: int = 1) -> int:
        """Increment progress for a trigger type. Returns new count."""
        with self._lock:
            with self._connect() as conn:
                now = self._now()
                conn.execute(
                    """
                    INSERT INTO achievement_progress (guild_id, user_id, trigger_type, count, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(guild_id, user_id, trigger_type) DO UPDATE SET
                        count = count + excluded.count,
                        updated_at = excluded.updated_at
                    """,
                    (int(guild_id), int(user_id), trigger_type, increment, now),
                )
                conn.commit()
                row = conn.execute(
                    "SELECT count FROM achievement_progress WHERE guild_id=? AND user_id=? AND trigger_type=?",
                    (int(guild_id), int(user_id), trigger_type),
                ).fetchone()
                return int(row["count"]) if row else 0

    def _record_progress(self, guild_id: int, user_id: int, trigger_type: str, count: int) -> int:
        """Set absolute progress for a trigger type (e.g. for message_count from DB)."""
        with self._lock:
            with self._connect() as conn:
                now = self._now()
                conn.execute(
                    """
                    INSERT INTO achievement_progress (guild_id, user_id, trigger_type, count, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(guild_id, user_id, trigger_type) DO UPDATE SET
                        count = excluded.count,
                        updated_at = excluded.updated_at
                    """,
                    (int(guild_id), int(user_id), trigger_type, count, now),
                )
                conn.commit()
                return count

    def get_progress(self, guild_id: int, user_id: int, trigger_type: str) -> int:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT count FROM achievement_progress WHERE guild_id=? AND user_id=? AND trigger_type=?",
                    (int(guild_id), int(user_id), trigger_type),
                ).fetchone()
                return int(row["count"]) if row else 0

    def get_all_progress(self, guild_id: int, user_id: int) -> dict[str, int]:
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT trigger_type, count FROM achievement_progress WHERE guild_id=? AND user_id=?",
                    (int(guild_id), int(user_id)),
                ).fetchall()
                return {r["trigger_type"]: int(r["count"]) for r in rows}

    def _unlock_achievement(self, guild_id: int, user_id: int, achievement_key: str) -> bool:
        """Record an achievement unlock. Returns True if newly unlocked."""
        with self._lock:
            with self._connect() as conn:
                now = self._now()
                existing = conn.execute(
                    "SELECT 1 FROM achievements_unlocks WHERE guild_id=? AND user_id=? AND achievement_key=?",
                    (int(guild_id), int(user_id), achievement_key),
                ).fetchone()
                if existing:
                    return False
                conn.execute(
                    "INSERT INTO achievements_unlocks (guild_id, user_id, achievement_key, unlocked_at) VALUES (?, ?, ?, ?)",
                    (int(guild_id), int(user_id), achievement_key, now),
                )
                conn.commit()
                return True

    def record_event(self, guild_id: int, user_id: int, trigger_type: str, increment: int = 1) -> list[str]:
        """
        Record an achievement-triggering event and return list of newly unlocked achievement keys.
        Maps trigger_type to achievement triggers and checks thresholds.
        """
        new_count = self._increment_progress(guild_id, user_id, trigger_type, increment)
        unlocked: list[str] = []

        for key, ach in ACHIEVEMENTS.items():
            if ach["trigger"] == trigger_type and new_count >= ach["threshold"]:
                if self._unlock_achievement(guild_id, user_id, key):
                    unlocked.append(key)

        return unlocked

    def sync_message_activity(self, guild_id: int, user_id: int, message_count: int) -> list[str]:
        """Sync member message activity count and check achievements."""
        self._record_progress(guild_id, user_id, "message_count", message_count)
        new_count = message_count
        unlocked: list[str] = []

        for key, ach in ACHIEVEMENTS.items():
            if ach["trigger"] == "message_count" and new_count >= ach["threshold"]:
                if self._unlock_achievement(guild_id, user_id, key):
                    unlocked.append(key)

        return unlocked

    def set_cookie_balance(self, guild_id: int, user_id: int, balance: int) -> list[str]:
        """Sync cookie balance and check achievements."""
        unlocked: list[str] = []

        for key, ach in ACHIEVEMENTS.items():
            if ach["trigger"] == "cookie_balance" and balance >= ach["threshold"]:
                if self._unlock_achievement(guild_id, user_id, key):
                    unlocked.append(key)

        return unlocked

    def set_daily_streak(self, guild_id: int, user_id: int, streak: int) -> list[str]:
        """Set daily streak count and check achievements."""
        unlocked: list[str] = []

        for key, ach in ACHIEVEMENTS.items():
            if ach["trigger"] == "daily_streak" and streak >= ach["threshold"]:
                if self._unlock_achievement(guild_id, user_id, key):
                    unlocked.append(key)

        return unlocked

    def get_unlocked_achievements(self, guild_id: int, user_id: int) -> list[dict]:
        with self._lock:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """
                    SELECT a.achievement_key, a.unlocked_at
                    FROM achievements_unlocks a
                    WHERE a.guild_id=? AND a.user_id=?
                    ORDER BY a.unlocked_at DESC
                    """,
                    (int(guild_id), int(user_id)),
                ).fetchall()
                results = []
                for row in rows:
                    ach = ACHIEVEMENTS.get(row["achievement_key"], {})
                    results.append(
                        {
                            "key": row["achievement_key"],
                            "title": ach.get("title", row["achievement_key"]),
                            "description": ach.get("description", ""),
                            "emoji": ach.get("emoji", "🏅"),
                            "unlocked_at": row["unlocked_at"],
                        }
                    )
                return results

    def get_achievement_progress(self, guild_id: int, user_id: int) -> list[dict]:
        """Get progress for all achievements, including unlocked status."""
        user_progress = self.get_all_progress(guild_id, user_id)
        unlocked_keys = {a["key"] for a in self.get_unlocked_achievements(guild_id, user_id)}
        results = []

        for key, ach in ACHIEVEMENTS.items():
            trigger = ach["trigger"]
            threshold = ach["threshold"]
            current = user_progress.get(trigger, 0)
            is_unlocked = key in unlocked_keys
            results.append(
                {
                    "key": key,
                    "title": ach["title"],
                    "description": ach["description"],
                    "emoji": ach["emoji"],
                    "trigger": trigger,
                    "threshold": threshold,
                    "current": current,
                    "percent": min(int((current / threshold) * 100) if threshold > 0 else 0, 100),
                    "unlocked": is_unlocked,
                }
            )

        return results

    def get_leaderboard(self, guild_id: int, limit: int = 10) -> list[dict]:
        """Get top users by number of unlocked achievements."""
        with self._lock:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """
                    SELECT user_id, COUNT(*) as achievement_count
                    FROM achievements_unlocks
                    WHERE guild_id=?
                    GROUP BY user_id
                    ORDER BY achievement_count DESC, user_id ASC
                    LIMIT ?
                    """,
                    (int(guild_id), int(limit)),
                ).fetchall()
                return [{"user_id": int(r["user_id"]), "count": int(r["achievement_count"])} for r in rows]
