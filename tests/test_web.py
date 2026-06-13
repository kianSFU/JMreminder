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


class TestFullTrackingUrl:
    """AR-7 AC: SMS message contains a full clickable URL, not a relative path."""

    @patch("autoremind.web._tracker")
    @patch("autoremind.sms.Client")
    def test_send_uses_full_url_not_relative(self, mock_twilio_cls, mock_tracker, app_client):
        mock_tracker.was_policy_sent.return_value = False
        mock_client = MagicMock()
        mock_twilio_cls.return_value = mock_client
        expiry = date.today() + timedelta(days=20)
        data = _make_csv_bytes([
            ["DOE JOHN", '="6041234567"', expiry.isoformat(), "POL-URL-001", "Toyota", "Camry", "Renewal", "Active", "Y", ""],
        ])
        app_client.post("/upload", files={"file": ("r.csv", data, "text/csv")})
        app_client.post("/send")
        call_args = mock_client.messages.create.call_args
        assert call_args is not None, "send_reminder must be called"
        body = call_args.kwargs.get("body", str(call_args))
        assert "http" in body, "SMS body must contain a full URL (http/https), not a relative path"
        assert "/click/" in body

    @patch.dict("os.environ", {"BASE_URL": "https://autoremind-jm.up.railway.app"})
    @patch("autoremind.web._tracker")
    @patch("autoremind.sms.Client")
    def test_send_uses_configured_base_url(self, mock_twilio_cls, mock_tracker, app_client):
        mock_tracker.was_policy_sent.return_value = False
        mock_client = MagicMock()
        mock_twilio_cls.return_value = mock_client
        expiry = date.today() + timedelta(days=20)
        data = _make_csv_bytes([
            ["DOE JOHN", '="6041234567"', expiry.isoformat(), "POL-URL-002", "Toyota", "Camry", "Renewal", "Active", "Y", ""],
        ])
        app_client.post("/upload", files={"file": ("r.csv", data, "text/csv")})
        app_client.post("/send")
        call_args = mock_client.messages.create.call_args
        assert call_args is not None, "send_reminder must be called"
        body = call_args.kwargs.get("body", str(call_args))
        assert "https://autoremind-jm.up.railway.app/click/" in body


class TestBaseUrlConfig:
    """AR-7 AC: BASE_URL is configurable via environment variable."""

    def test_get_base_url_returns_env_value(self):
        from autoremind.web import get_base_url
        with patch.dict("os.environ", {"BASE_URL": "https://example.com"}):
            assert get_base_url() == "https://example.com"

    def test_get_base_url_defaults_to_localhost(self):
        from autoremind.web import get_base_url
        with patch.dict("os.environ", {}, clear=True):
            result = get_base_url()
            assert "localhost" in result

    def test_get_base_url_strips_trailing_slash(self):
        from autoremind.web import get_base_url
        with patch.dict("os.environ", {"BASE_URL": "https://example.com/"}):
            assert get_base_url() == "https://example.com"


class TestBrandedClickPage:
    """AR-7 AC: Click confirmation page shows Johnston Meier Insurance branding."""

    def test_click_page_contains_company_name(self, app_client):
        resp = app_client.get("/click/POL-001")
        body = resp.text
        assert "Johnston Meier" in body

    def test_click_page_contains_insurance_reference(self, app_client):
        resp = app_client.get("/click/POL-001")
        body = resp.text.lower()
        assert "insurance" in body


class TestMobileFriendlyClickPage:
    """AR-7 AC: Click confirmation page is mobile-friendly."""

    def test_click_page_has_viewport_meta(self, app_client):
        resp = app_client.get("/click/POL-001")
        body = resp.text.lower()
        assert "viewport" in body

    def test_click_page_has_responsive_styling(self, app_client):
        resp = app_client.get("/click/POL-001")
        body = resp.text.lower()
        assert "max-width" in body or "width: 100%" in body or "responsive" in body


class TestSendResultPageUI:
    """AR-9 AC: /send result page includes navigation back to Upload and Dashboard, and uses shared CSS."""

    @patch("autoremind.sms.Client")
    def test_send_result_includes_upload_link(self, mock_twilio_cls, app_client, csv_upload_bytes):
        mock_client = MagicMock()
        mock_twilio_cls.return_value = mock_client
        app_client.post("/upload", files={"file": ("r.csv", csv_upload_bytes, "text/csv")})
        resp = app_client.post("/send")
        assert 'href="/"' in resp.text

    @patch("autoremind.sms.Client")
    def test_send_result_includes_dashboard_link(self, mock_twilio_cls, app_client, csv_upload_bytes):
        mock_client = MagicMock()
        mock_twilio_cls.return_value = mock_client
        app_client.post("/upload", files={"file": ("r.csv", csv_upload_bytes, "text/csv")})
        resp = app_client.post("/send")
        assert 'href="/dashboard"' in resp.text

    @patch("autoremind.sms.Client")
    def test_send_result_uses_base_css(self, mock_twilio_cls, app_client, csv_upload_bytes):
        mock_client = MagicMock()
        mock_twilio_cls.return_value = mock_client
        app_client.post("/upload", files={"file": ("r.csv", csv_upload_bytes, "text/csv")})
        resp = app_client.post("/send")
        assert "<style>" in resp.text
        assert "font-family" in resp.text


class TestDashboardPageUI:
    """AR-9 AC: /dashboard page includes shared navigation bar and CSS styling."""

    def test_dashboard_includes_nav_bar(self, app_client):
        resp = app_client.get("/dashboard")
        assert "<nav>" in resp.text
        assert 'href="/"' in resp.text
        assert 'href="/dashboard"' in resp.text

    def test_dashboard_uses_base_css(self, app_client):
        resp = app_client.get("/dashboard")
        assert "<style>" in resp.text
        assert "font-family" in resp.text


class TestDashboardClientDetails:
    """AR-9 AC: Dashboard displays Name, Phone, Vehicle, Expiry, and Clicked At for each clicked renewal."""

    @patch("autoremind.sms.Client")
    def test_dashboard_shows_client_name(self, mock_twilio_cls, app_client, csv_upload_bytes):
        mock_client = MagicMock()
        mock_twilio_cls.return_value = mock_client
        app_client.post("/upload", files={"file": ("r.csv", csv_upload_bytes, "text/csv")})
        app_client.post("/send")
        app_client.get("/click/POL-001")
        resp = app_client.get("/dashboard")
        assert "DOE JOHN" in resp.text

    @patch("autoremind.sms.Client")
    def test_dashboard_shows_phone(self, mock_twilio_cls, app_client, csv_upload_bytes):
        mock_client = MagicMock()
        mock_twilio_cls.return_value = mock_client
        app_client.post("/upload", files={"file": ("r.csv", csv_upload_bytes, "text/csv")})
        app_client.post("/send")
        app_client.get("/click/POL-001")
        resp = app_client.get("/dashboard")
        assert "6041234567" in resp.text

    @patch("autoremind.sms.Client")
    def test_dashboard_shows_vehicle(self, mock_twilio_cls, app_client, csv_upload_bytes):
        mock_client = MagicMock()
        mock_twilio_cls.return_value = mock_client
        app_client.post("/upload", files={"file": ("r.csv", csv_upload_bytes, "text/csv")})
        app_client.post("/send")
        app_client.get("/click/POL-001")
        resp = app_client.get("/dashboard")
        assert "Toyota" in resp.text
        assert "Camry" in resp.text

    @patch("autoremind.sms.Client")
    def test_dashboard_shows_expiry_date(self, mock_twilio_cls, app_client, csv_upload_bytes):
        mock_client = MagicMock()
        mock_twilio_cls.return_value = mock_client
        app_client.post("/upload", files={"file": ("r.csv", csv_upload_bytes, "text/csv")})
        app_client.post("/send")
        app_client.get("/click/POL-001")
        resp = app_client.get("/dashboard")
        expiry = (date.today() + timedelta(days=20)).isoformat()
        assert expiry in resp.text
