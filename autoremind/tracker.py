import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional


class ReminderTracker:
    def __init__(self, db_path: Path):
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS sent_reminders (
                policy_number TEXT NOT NULL,
                phone TEXT NOT NULL,
                reminder_days INTEGER NOT NULL,
                sent_at TEXT NOT NULL,
                PRIMARY KEY (policy_number, reminder_days)
            )"""
        )
        self._conn.commit()

    def record_sent(self, policy_number: str, phone: str, reminder_days: int) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO sent_reminders (policy_number, phone, reminder_days, sent_at) VALUES (?, ?, ?, ?)",
            (policy_number, phone, reminder_days, datetime.now().isoformat()),
        )
        self._conn.commit()

    def was_sent(self, policy_number: str, reminder_days: int) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM sent_reminders WHERE policy_number = ? AND reminder_days = ?",
            (policy_number, reminder_days),
        ).fetchone()
        return row is not None

    def get_record(self, policy_number: str, reminder_days: int) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT policy_number, phone, reminder_days, sent_at FROM sent_reminders WHERE policy_number = ? AND reminder_days = ?",
            (policy_number, reminder_days),
        ).fetchone()
        if row is None:
            return None
        return dict(row)
