"""Tests for AR-1: Reminder tracking to prevent duplicate messages."""

import pytest
from datetime import date, timedelta

from autoremind.tracker import ReminderTracker


class TestReminderTracking:
    """AC: System tracks which reminders have been sent to prevent duplicate messages."""

    @pytest.fixture
    def tracker(self, tmp_path):
        return ReminderTracker(db_path=tmp_path / "reminders.db")

    def test_records_sent_reminder(self, tracker):
        tracker.record_sent(
            policy_number="POL-001",
            phone="6041234567",
            reminder_days=30,
        )
        assert tracker.was_sent(policy_number="POL-001", reminder_days=30)

    def test_unsent_reminder_returns_false(self, tracker):
        assert not tracker.was_sent(policy_number="POL-001", reminder_days=30)

    def test_prevents_duplicate_at_same_interval(self, tracker):
        tracker.record_sent(policy_number="POL-001", phone="6041234567", reminder_days=30)
        assert tracker.was_sent(policy_number="POL-001", reminder_days=30)

    def test_allows_different_interval_for_same_policy(self, tracker):
        tracker.record_sent(policy_number="POL-001", phone="6041234567", reminder_days=30)
        assert not tracker.was_sent(policy_number="POL-001", reminder_days=14)

    def test_allows_same_interval_for_different_policy(self, tracker):
        tracker.record_sent(policy_number="POL-001", phone="6041234567", reminder_days=30)
        assert not tracker.was_sent(policy_number="POL-002", reminder_days=30)

    def test_stores_timestamp(self, tracker):
        tracker.record_sent(policy_number="POL-001", phone="6041234567", reminder_days=30)
        record = tracker.get_record(policy_number="POL-001", reminder_days=30)
        assert record is not None
        assert record["sent_at"] is not None

    def test_persists_across_instances(self, tmp_path):
        db = tmp_path / "reminders.db"
        tracker1 = ReminderTracker(db_path=db)
        tracker1.record_sent(policy_number="POL-001", phone="6041234567", reminder_days=30)

        tracker2 = ReminderTracker(db_path=db)
        assert tracker2.was_sent(policy_number="POL-001", reminder_days=30)


class TestClickTracking:
    """AC (AR-3): Click endpoint records client response (policy number, timestamp) in tracker."""

    @pytest.fixture
    def tracker(self, tmp_path):
        return ReminderTracker(db_path=tmp_path / "reminders.db")

    def test_records_click(self, tracker):
        tracker.record_click(policy_number="POL-001")
        clicks = tracker.get_clicks()
        policy_numbers = [c["policy_number"] for c in clicks]
        assert "POL-001" in policy_numbers

    def test_click_stores_timestamp(self, tracker):
        tracker.record_click(policy_number="POL-001")
        clicks = tracker.get_clicks()
        assert clicks[0]["clicked_at"] is not None

    def test_get_clicks_returns_empty_when_none(self, tracker):
        clicks = tracker.get_clicks()
        assert clicks == []

    def test_multiple_clicks_recorded(self, tracker):
        tracker.record_click(policy_number="POL-001")
        tracker.record_click(policy_number="POL-002")
        clicks = tracker.get_clicks()
        assert len(clicks) == 2

    def test_duplicate_click_does_not_error(self, tracker):
        tracker.record_click(policy_number="POL-001")
        tracker.record_click(policy_number="POL-001")
        clicks = tracker.get_clicks()
        assert any(c["policy_number"] == "POL-001" for c in clicks)
