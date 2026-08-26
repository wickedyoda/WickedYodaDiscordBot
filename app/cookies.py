"""
Cookie economy system for WickedYoda bot.

Provides a simple SQLite-backed currency (cookies) that users can:
- Check balance (`/balance`)
- Claim daily cookies (`/daily`)
- Gift cookies to friends (`/gift @user <amount>`)
- Gamble via coin flip or RPS (`/gamble coinflip <amount>`, `/gamble rps <amount>`)

Tables:
  cookie_balances (guild_id, user_id, balance, updated_at)
  cookie_transactions (id, guild_id, user_id, amount, source, created_at)
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime


class CookieStore:
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
                    CREATE TABLE IF NOT EXISTS cookie_balances (
                        guild_id INTEGER NOT NULL,
                        user_id  INTEGER NOT NULL,
                        balance  INTEGER NOT NULL DEFAULT 0,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (guild_id, user_id)
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS cookie_transactions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        guild_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        amount INTEGER NOT NULL,
                        source TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS cookie_daily_claims (
                        guild_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        claimed_at TEXT NOT NULL,
                        PRIMARY KEY (guild_id, user_id)
                    )
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_cookie_tx_guild_user ON cookie_transactions(guild_id, user_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_cookie_daily_guild_user ON cookie_daily_claims(guild_id, user_id)")
                conn.commit()

    def _now(self) -> str:
        return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

    def get_balance(self, guild_id: int, user_id: int) -> int:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT balance FROM cookie_balances WHERE guild_id=? AND user_id=?",
                    (int(guild_id), int(user_id)),
                ).fetchone()
                return int(row["balance"]) if row else 0

    def get_top_balances(self, guild_id: int, limit: int = 10) -> list[dict]:
        with self._lock:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """
                    SELECT user_id, balance FROM cookie_balances
                    WHERE guild_id=? ORDER BY balance DESC, updated_at ASC
                    LIMIT ?
                    """,
                    (int(guild_id), int(limit)),
                ).fetchall()
                return [{"user_id": int(r["user_id"]), "balance": int(r["balance"])} for r in rows]

    def _adjust_balance(self, guild_id: int, user_id: int, delta: int, source: str) -> int:
        """Atomically adjust a user's balance. Returns new balance. Delta can be negative."""
        with self._lock:
            with self._connect() as conn:
                now = self._now()
                conn.execute(
                    """
                    INSERT INTO cookie_balances (guild_id, user_id, balance, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(guild_id, user_id) DO UPDATE SET
                        balance = balance + excluded.balance,
                        updated_at = excluded.updated_at
                    """,
                    (int(guild_id), int(user_id), int(delta), now),
                )
                conn.execute(
                    "INSERT INTO cookie_transactions (guild_id, user_id, amount, source, created_at) VALUES (?, ?, ?, ?, ?)",
                    (int(guild_id), int(user_id), int(delta), source, now),
                )
                conn.commit()
                row = conn.execute(
                    "SELECT balance FROM cookie_balances WHERE guild_id=? AND user_id=?",
                    (int(guild_id), int(user_id)),
                ).fetchone()
                return int(row["balance"]) if row else 0

    def set_balance(self, guild_id: int, user_id: int, amount: int, source: str) -> int:
        """Set an absolute balance (use with caution — mainly for admin)."""
        return self._adjust_balance(guild_id, user_id, amount, source)

    def add_cookies(self, guild_id: int, user_id: int, amount: int, source: str) -> int:
        amount = max(0, int(amount))
        if amount == 0:
            return self.get_balance(guild_id, user_id)
        return self._adjust_balance(guild_id, user_id, amount, source)

    def remove_cookies(self, guild_id: int, user_id: int, amount: int, source: str) -> int:
        amount = min(int(amount), self.get_balance(guild_id, user_id))
        if amount <= 0:
            return self.get_balance(guild_id, user_id)
        return self._adjust_balance(guild_id, user_id, -amount, source)

    def can_claim_daily(self, guild_id: int, user_id: int) -> bool:
        """Check if 24h have passed since last daily claim."""
        with self._lock:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT claimed_at FROM cookie_daily_claims WHERE guild_id=? AND user_id=? AND claimed_at > ?",
                    (
                        int(guild_id),
                        int(user_id),
                        (datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")),
                    ),
                ).fetchone()
                # Actually compare properly
                row = conn.execute(
                    "SELECT claimed_at FROM cookie_daily_claims WHERE guild_id=? AND user_id=?",
                    (int(guild_id), int(user_id)),
                ).fetchone()
                if row is None:
                    return True
                last_claim = datetime.strptime(row["claimed_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
                return (datetime.now(UTC) - last_claim).total_seconds() >= 86400

    def claim_daily(self, guild_id: int, user_id: int, amount: int) -> int:
        """Claim daily cookies. Returns new balance, or -1 if not eligible."""
        if not self.can_claim_daily(guild_id, user_id):
            return -1
        with self._lock:
            with self._connect() as conn:
                now = self._now()
                conn.execute(
                    """
                    INSERT INTO cookie_daily_claims (guild_id, user_id, claimed_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(guild_id, user_id) DO UPDATE SET
                        claimed_at = excluded.claimed_at
                    """,
                    (int(guild_id), int(user_id), now),
                )
                conn.commit()
        return self.add_cookies(guild_id, user_id, amount, "daily")

    def get_transaction_history(self, guild_id: int, user_id: int, limit: int = 20) -> list[dict]:
        with self._lock:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """
                    SELECT amount, source, created_at FROM cookie_transactions
                    WHERE guild_id=? AND user_id=?
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (int(guild_id), int(user_id), int(limit)),
                ).fetchall()
                return [{"amount": int(r["amount"]), "source": r["source"], "created_at": r["created_at"]} for r in rows]
