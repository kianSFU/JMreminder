import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional


class ReminderTracker:
    def __init__(self, db_path: Path):
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS sent_reminders (
                policy_number TEXT NOT NULL,
                phone TEXT NOT NULL,
                reminder_days INTEGER NOT NULL,
                sent_at TEXT NOT NULL,
                customer_name TEXT,
                make TEXT,
                model TEXT,
                policy_expiry_date TEXT,
                PRIMARY KEY (policy_number, reminder_days)
            )"""
        )
        self._migrate_sent_reminders()
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS clicks (
                policy_number TEXT NOT NULL,
                clicked_at TEXT NOT NULL
            )"""
        )
        self._conn.commit()

    def _migrate_sent_reminders(self) -> None:
        cols = {row[1] for row in self._conn.execute("PRAGMA table_info(sent_reminders)").fetchall()}
        for col in ("customer_name", "make", "model", "policy_expiry_date"):
            if col not in cols:
                self._conn.execute(f"ALTER TABLE sent_reminders ADD COLUMN {col} TEXT")
        self._conn.commit()

    def record_sent(
        self,
        policy_number: str,
        phone: str,
        reminder_days: int,
        customer_name: str = "",
        make: str = "",
        model: str = "",
        policy_expiry_date: str = "",
    ) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO sent_reminders (policy_number, phone, reminder_days, sent_at, customer_name, make, model, policy_expiry_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (policy_number, phone, reminder_days, datetime.now().isoformat(), customer_name, make, model, policy_expiry_date),
        )
        self._conn.commit()

    def was_sent(self, policy_number: str, reminder_days: int) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM sent_reminders WHERE policy_number = ? AND reminder_days = ?",
            (policy_number, reminder_days),
        ).fetchone()
        return row is not None

    def was_policy_sent(self, policy_number: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM sent_reminders WHERE policy_number = ?",
            (policy_number,),
        ).fetchone()
        return row is not None

    def get_record(self, policy_number: str, reminder_days: int) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT policy_number, phone, reminder_days, sent_at, customer_name, make, model, policy_expiry_date FROM sent_reminders WHERE policy_number = ? AND reminder_days = ?",
            (policy_number, reminder_days),
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def record_click(self, policy_number: str) -> None:
        self._conn.execute(
            "INSERT INTO clicks (policy_number, clicked_at) VALUES (?, ?)",
            (policy_number, datetime.now().isoformat()),
        )
        self._conn.commit()

    def get_clicks(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT policy_number, clicked_at FROM clicks ORDER BY clicked_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_dashboard_data(self) -> list[dict]:
        rows = self._conn.execute(
            """SELECT c.policy_number, s.customer_name, s.phone, s.make, s.model, s.policy_expiry_date, c.clicked_at
               FROM clicks c
               LEFT JOIN sent_reminders s ON c.policy_number = s.policy_number
               ORDER BY c.clicked_at DESC"""
        ).fetchall()
        return [dict(r) for r in rows]
