"""Tests for AR-1: SMS reminder sending, message content, and timing configuration."""

import pytest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

from autoremind.sms import send_reminder, format_message, get_due_reminders
from autoremind.parser import parse_renewals, filter_actionable_renewals


class TestMessageFormatting:
    """AC: SMS message includes client first name, vehicle info, and renewal date."""

    def test_includes_first_name(self):
        msg = format_message(
            first_name="John",
            make="Toyota",
            model="Camry",
            expiry_date=date(2026, 7, 15),
        )
        assert "John" in msg

    def test_includes_vehicle_make(self):
        msg = format_message(
            first_name="John",
            make="Toyota",
            model="Camry",
            expiry_date=date(2026, 7, 15),
        )
        assert "Toyota" in msg

    def test_includes_vehicle_model(self):
        msg = format_message(
            first_name="John",
            make="Toyota",
            model="Camry",
            expiry_date=date(2026, 7, 15),
        )
        assert "Camry" in msg

    def test_includes_renewal_date(self):
        msg = format_message(
            first_name="John",
            make="Toyota",
            model="Camry",
            expiry_date=date(2026, 7, 15),
        )
        assert "July" in msg or "2026-07-15" in msg or "07/15" in msg

    def test_returns_string(self):
        msg = format_message(
            first_name="Jane",
            make="Honda",
            model="Civic",
            expiry_date=date(2026, 8, 1),
        )
        assert isinstance(msg, str)
        assert len(msg) > 0


class TestReminderTiming:
    """AC: SMS reminder timing is configurable (30, 14, 3 days before expiry)."""

    def test_default_intervals(self):
        from autoremind.sms import DEFAULT_REMINDER_DAYS

        assert 30 in DEFAULT_REMINDER_DAYS
        assert 14 in DEFAULT_REMINDER_DAYS
        assert 3 in DEFAULT_REMINDER_DAYS

    def test_due_at_30_days(self, sample_xlsx_multiple_valid):
        records = parse_renewals(sample_xlsx_multiple_valid)
        actionable = filter_actionable_renewals(records)
        due = get_due_reminders(actionable, reminder_days=[30])
        policy_numbers = [r.policy_number for r in due]
        assert "POL-200" in policy_numbers

    def test_due_at_14_days(self, sample_xlsx_multiple_valid):
        records = parse_renewals(sample_xlsx_multiple_valid)
        actionable = filter_actionable_renewals(records)
        due = get_due_reminders(actionable, reminder_days=[14])
        policy_numbers = [r.policy_number for r in due]
        assert "POL-201" in policy_numbers

    def test_due_at_3_days(self, sample_xlsx_multiple_valid):
        records = parse_renewals(sample_xlsx_multiple_valid)
        actionable = filter_actionable_renewals(records)
        due = get_due_reminders(actionable, reminder_days=[3])
        policy_numbers = [r.policy_number for r in due]
        assert "POL-202" in policy_numbers

    def test_not_due_at_60_days(self, sample_xlsx_multiple_valid):
        records = parse_renewals(sample_xlsx_multiple_valid)
        actionable = filter_actionable_renewals(records)
        due = get_due_reminders(actionable, reminder_days=[30, 14, 3])
        policy_numbers = [r.policy_number for r in due]
        assert "POL-203" not in policy_numbers

    def test_custom_intervals(self, sample_xlsx_multiple_valid):
        records = parse_renewals(sample_xlsx_multiple_valid)
        actionable = filter_actionable_renewals(records)
        due = get_due_reminders(actionable, reminder_days=[60])
        policy_numbers = [r.policy_number for r in due]
        assert "POL-203" in policy_numbers


class TestSmsSending:
    """AC: SMS sending via Twilio (mocked — never send real SMS in tests)."""

    @patch("autoremind.sms.Client")
    def test_calls_twilio_create(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        send_reminder(phone="6041234567", message="Hi John, your renewal is coming up.")
        mock_client.messages.create.assert_called_once()

    @patch("autoremind.sms.Client")
    def test_sends_to_correct_phone(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        send_reminder(phone="6041234567", message="Test message")
        call_kwargs = mock_client.messages.create.call_args
        assert "6041234567" in str(call_kwargs)

    @patch("autoremind.sms.Client")
    def test_sends_correct_body(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        send_reminder(phone="6041234567", message="Renewal reminder for John")
        call_kwargs = mock_client.messages.create.call_args
        assert "Renewal reminder for John" in str(call_kwargs)


class TestMessageWithTrackingLink:
    """AC (AR-3): SMS includes a unique tracking link per client."""

    def test_message_includes_link(self):
        msg = format_message(
            first_name="John",
            make="Toyota",
            model="Camry",
            expiry_date=date(2026, 7, 15),
            tracking_url="https://example.com/click/POL-001",
        )
        assert "https://example.com/click/POL-001" in msg

    def test_link_is_unique_per_policy(self):
        msg1 = format_message(
            first_name="John",
            make="Toyota",
            model="Camry",
            expiry_date=date(2026, 7, 15),
            tracking_url="https://example.com/click/POL-001",
        )
        msg2 = format_message(
            first_name="Jane",
            make="Honda",
            model="Civic",
            expiry_date=date(2026, 7, 15),
            tracking_url="https://example.com/click/POL-002",
        )
        assert "POL-001" in msg1
        assert "POL-002" in msg2
        assert "POL-001" not in msg2

    def test_message_still_includes_client_name_and_date(self):
        msg = format_message(
            first_name="Sarah",
            make="Hyundai",
            model="Tucson",
            expiry_date=date(2026, 8, 10),
            tracking_url="https://example.com/click/POL-100",
        )
        assert "Sarah" in msg
        assert "Hyundai" in msg
        assert "Tucson" in msg
