"""Tests for AR-5: Persistent DB and duplicate SMS prevention."""

import io
import csv
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


AUTOLINK_COLUMNS = [
    "CustomerName",
    "CustomerHomePhone",
    "PolicyExpiryDate",
    "PolicyNumber",
    "Make",
    "Model",
    "TransactionTypeDesc",
    "PolicyStatusDesc",
    "CustomerConsentYN",
    "DateRenewed",
]


def _make_csv_bytes(rows):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(AUTOLINK_COLUMNS)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue().encode()


@pytest.fixture
def clean_app_client(tmp_path):
    """TestClient with a fresh tracker DB to avoid cross-test contamination."""
    from autoremind import web
    from autoremind.tracker import ReminderTracker
    from starlette.testclient import TestClient

    original_tracker = web._tracker
    web._tracker = ReminderTracker(db_path=tmp_path / "test.db")
    yield TestClient(web.app)
    web._tracker = original_tracker


@pytest.fixture
def two_actionable_csv():
    expiry = date.today() + timedelta(days=20)
    return _make_csv_bytes([
        ["DOE JOHN", '="6041234567"', expiry.isoformat(), "POL-001", "Toyota", "Camry", "Renewal", "Active", "Y", ""],
        ["SMITH JANE", '="6049876543"', expiry.isoformat(), "POL-002", "Honda", "Civic", "Renewal", "Active", "Y", ""],
    ])


class TestPersistentDbPath:
    """AC: SQLite database is stored at a persistent project-relative path, not in the OS temp directory."""

    def test_db_path_not_in_temp_dir(self):
        from autoremind.web import get_db_path

        db_path = get_db_path()
        temp_dir = Path(tempfile.gettempdir()).resolve()
        assert not str(db_path.resolve()).startswith(str(temp_dir))

    def test_db_path_in_data_directory(self):
        from autoremind.web import get_db_path

        db_path = get_db_path()
        assert db_path.parent.name == "data"

    def test_db_path_named_autoremind_db(self):
        from autoremind.web import get_db_path

        db_path = get_db_path()
        assert db_path.name == "autoremind.db"


class TestDataDirectoryAutoCreation:
    """AC: The data/ directory is created automatically if it doesn't exist."""

    def test_data_directory_exists_after_get_db_path(self):
        from autoremind.web import get_db_path

        db_path = get_db_path()
        assert db_path.parent.exists()


class TestSendDeduplication:
    """AC: The /send endpoint checks the tracker before sending each SMS and skips any policy that was already sent a reminder."""

    @patch("autoremind.sms.Client")
    def test_first_send_delivers_all_messages(self, mock_twilio_cls, clean_app_client, two_actionable_csv):
        mock_client = MagicMock()
        mock_twilio_cls.return_value = mock_client

        clean_app_client.post("/upload", files={"file": ("renewals.csv", two_actionable_csv, "text/csv")})
        clean_app_client.post("/send")

        assert mock_client.messages.create.call_count == 2

    @patch("autoremind.sms.Client")
    def test_second_send_skips_already_sent(self, mock_twilio_cls, clean_app_client, two_actionable_csv):
        mock_client = MagicMock()
        mock_twilio_cls.return_value = mock_client

        clean_app_client.post("/upload", files={"file": ("renewals.csv", two_actionable_csv, "text/csv")})
        clean_app_client.post("/send")
        mock_client.messages.create.reset_mock()

        clean_app_client.post("/upload", files={"file": ("renewals.csv", two_actionable_csv, "text/csv")})
        clean_app_client.post("/send")

        assert mock_client.messages.create.call_count == 0

    @patch("autoremind.sms.Client")
    def test_skips_pre_recorded_policy(self, mock_twilio_cls, clean_app_client, two_actionable_csv):
        mock_client = MagicMock()
        mock_twilio_cls.return_value = mock_client

        from autoremind import web
        web._tracker.record_sent(policy_number="POL-001", phone="6041234567", reminder_days=30)

        clean_app_client.post("/upload", files={"file": ("renewals.csv", two_actionable_csv, "text/csv")})
        clean_app_client.post("/send")

        assert mock_client.messages.create.call_count == 1


class TestSendRecording:
    """AC: Each successful SMS send is recorded in the tracker database."""

    @patch("autoremind.sms.Client")
    def test_sent_messages_recorded_in_tracker(self, mock_twilio_cls, clean_app_client, two_actionable_csv):
        mock_client = MagicMock()
        mock_twilio_cls.return_value = mock_client

        clean_app_client.post("/upload", files={"file": ("renewals.csv", two_actionable_csv, "text/csv")})
        clean_app_client.post("/send")

        from autoremind import web
        assert web._tracker.was_policy_sent("POL-001")
        assert web._tracker.was_policy_sent("POL-002")


class TestSendResponseCounts:
    """AC: The /send response shows how many messages were sent vs. how many were skipped as duplicates."""

    @patch("autoremind.sms.Client")
    def test_response_shows_sent_count(self, mock_twilio_cls, clean_app_client, two_actionable_csv):
        mock_client = MagicMock()
        mock_twilio_cls.return_value = mock_client

        clean_app_client.post("/upload", files={"file": ("renewals.csv", two_actionable_csv, "text/csv")})
        resp = clean_app_client.post("/send")

        assert "Sent 2" in resp.text

    @patch("autoremind.sms.Client")
    def test_response_shows_skipped_count_on_resend(self, mock_twilio_cls, clean_app_client, two_actionable_csv):
        mock_client = MagicMock()
        mock_twilio_cls.return_value = mock_client

        clean_app_client.post("/upload", files={"file": ("renewals.csv", two_actionable_csv, "text/csv")})
        clean_app_client.post("/send")

        clean_app_client.post("/upload", files={"file": ("renewals.csv", two_actionable_csv, "text/csv")})
        resp = clean_app_client.post("/send")

        assert "Skipped 2" in resp.text

    @patch("autoremind.sms.Client")
    def test_response_shows_mixed_sent_and_skipped(self, mock_twilio_cls, clean_app_client):
        mock_client = MagicMock()
        mock_twilio_cls.return_value = mock_client

        expiry = date.today() + timedelta(days=20)
        csv_data = _make_csv_bytes([
            ["DOE JOHN", '="6041234567"', expiry.isoformat(), "POL-001", "Toyota", "Camry", "Renewal", "Active", "Y", ""],
            ["SMITH JANE", '="6049876543"', expiry.isoformat(), "POL-002", "Honda", "Civic", "Renewal", "Active", "Y", ""],
        ])

        from autoremind import web
        web._tracker.record_sent(policy_number="POL-001", phone="6041234567", reminder_days=30)

        clean_app_client.post("/upload", files={"file": ("renewals.csv", csv_data, "text/csv")})
        resp = clean_app_client.post("/send")

        assert "Sent 1" in resp.text
        assert "Skipped 1" in resp.text
