"""Tests for AR-3: Web UI — file upload, renewals dashboard, click tracking, and confirmation page."""

import io
import csv
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import openpyxl

from autoremind.parser import RenewalRecord


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


def _make_xlsx_bytes(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(AUTOLINK_COLUMNS)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture
def app_client():
    from autoremind.web import app
    from starlette.testclient import TestClient

    return TestClient(app)


@pytest.fixture
def csv_upload_bytes():
    expiry = date.today() + timedelta(days=20)
    return _make_csv_bytes([
        ["DOE JOHN", '="6041234567"', expiry.isoformat(), "POL-001", "Toyota", "Camry", "Renewal", "Active", "Y", ""],
        ["WONG SAM", "", expiry.isoformat(), "POL-002", "BMW", "X3", "Renewal", "Active", "Y", ""],
    ])


@pytest.fixture
def xlsx_upload_bytes():
    expiry = date.today() + timedelta(days=20)
    return _make_xlsx_bytes([
        ["DOE JOHN", '="6041234567"', expiry, "POL-001", "Toyota", "Camry", "Renewal", "Active", "Y", None],
    ])


class TestFileUpload:
    """AC: Web UI allows broker to upload a renewal file (.csv or .xlsx)."""

    def test_upload_csv_returns_success(self, app_client, csv_upload_bytes):
        resp = app_client.post(
            "/upload",
            files={"file": ("renewals.csv", csv_upload_bytes, "text/csv")},
        )
        assert resp.status_code == 200

    def test_upload_xlsx_returns_success(self, app_client, xlsx_upload_bytes):
        resp = app_client.post(
            "/upload",
            files={"file": ("renewals.xlsx", xlsx_upload_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert resp.status_code == 200

    def test_upload_rejects_unsupported_format(self, app_client):
        resp = app_client.post(
            "/upload",
            files={"file": ("data.json", b'{"key": "val"}', "application/json")},
        )
        assert resp.status_code in (400, 422)


class TestActionableRenewalsDisplay:
    """AC: UI displays a table of actionable renewals after upload (Renewal + Active + consented + valid phone + not yet renewed)."""

    def test_response_contains_actionable_records(self, app_client, csv_upload_bytes):
        resp = app_client.post(
            "/upload",
            files={"file": ("renewals.csv", csv_upload_bytes, "text/csv")},
        )
        body = resp.text
        assert "POL-001" in body

    def test_response_excludes_non_actionable(self, app_client):
        expiry = date.today() + timedelta(days=20)
        data = _make_csv_bytes([
            ["SMITH JANE", '="6049876543"', expiry.isoformat(), "POL-010", "Honda", "Civic", "New Business", "Active", "Y", ""],
        ])
        resp = app_client.post(
            "/upload",
            files={"file": ("renewals.csv", data, "text/csv")},
        )
        body = resp.text
        assert "POL-010" not in body or "non-actionable" in body.lower() or "skipped" in body.lower()


class TestInvalidPhoneSeparation:
    """AC: Clients with invalid/missing phone numbers are skipped and displayed separately in the UI."""

    def test_invalid_phone_clients_shown_separately(self, app_client, csv_upload_bytes):
        resp = app_client.post(
            "/upload",
            files={"file": ("renewals.csv", csv_upload_bytes, "text/csv")},
        )
        body = resp.text
        assert "POL-002" in body


class TestSmsBroadcast:
    """AC: System sends SMS to all actionable clients with a personalized message including a unique click link."""

    @patch("autoremind.sms.Client")
    def test_send_endpoint_triggers_sms(self, mock_twilio_cls, app_client, csv_upload_bytes):
        mock_client = MagicMock()
        mock_twilio_cls.return_value = mock_client
        app_client.post(
            "/upload",
            files={"file": ("renewals.csv", csv_upload_bytes, "text/csv")},
        )
        resp = app_client.post("/send")
        assert resp.status_code == 200


class TestClickConfirmationPage:
    """AC: When a client clicks the renewal link, they see a confirmation page."""

    def test_click_endpoint_returns_confirmation(self, app_client):
        resp = app_client.get("/click/POL-001")
        assert resp.status_code == 200
        body = resp.text.lower()
        assert "thank" in body or "confirm" in body or "broker" in body

    def test_click_endpoint_accepts_any_policy(self, app_client):
        resp = app_client.get("/click/POL-999")
        assert resp.status_code == 200


class TestClickTracking:
    """AC: Click endpoint records the client's response (policy number, timestamp) in the tracker database."""

    def test_click_records_in_database(self, app_client):
        app_client.get("/click/POL-001")
        from autoremind.tracker import ReminderTracker

        resp = app_client.get("/dashboard")
        body = resp.text
        assert "POL-001" in body


class TestBrokerDashboard:
    """AC: Broker dashboard shows a list of clients who clicked the renewal link."""

    def test_dashboard_endpoint_exists(self, app_client):
        resp = app_client.get("/dashboard")
        assert resp.status_code == 200

    def test_dashboard_shows_clicked_clients(self, app_client):
        app_client.get("/click/POL-050")
        resp = app_client.get("/dashboard")
        body = resp.text
        assert "POL-050" in body

    def test_dashboard_does_not_show_unclicked(self, app_client):
        resp = app_client.get("/dashboard")
        body = resp.text
        assert "POL-NEVER-CLICKED" not in body
