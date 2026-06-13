"""Tests for AR-1: Autolink .xlsx parsing, phone cleaning, name parsing, and renewal filtering."""

import pytest

from autoremind.parser import (
    parse_renewals,
    clean_phone,
    parse_customer_name,
    filter_actionable_renewals,
)


class TestXlsxParsing:
    """AC: System parses Autolink .xlsx renewal exports extracting all required fields."""

    def test_extracts_customer_name(self, sample_xlsx):
        records = parse_renewals(sample_xlsx)
        assert records[0].customer_name == "DOE JOHN MICHAEL"

    def test_extracts_phone_number(self, sample_xlsx):
        records = parse_renewals(sample_xlsx)
        assert records[0].phone == "6041234567"

    def test_extracts_policy_expiry_date(self, sample_xlsx):
        records = parse_renewals(sample_xlsx)
        assert records[0].policy_expiry_date is not None

    def test_extracts_policy_number(self, sample_xlsx):
        records = parse_renewals(sample_xlsx)
        assert records[0].policy_number == "POL-001"

    def test_extracts_vehicle_make(self, sample_xlsx):
        records = parse_renewals(sample_xlsx)
        assert records[0].make == "Toyota"

    def test_extracts_vehicle_model(self, sample_xlsx):
        records = parse_renewals(sample_xlsx)
        assert records[0].model == "Camry"

    def test_extracts_transaction_type(self, sample_xlsx):
        records = parse_renewals(sample_xlsx)
        assert records[0].transaction_type == "Renewal"

    def test_extracts_consent_status(self, sample_xlsx):
        records = parse_renewals(sample_xlsx)
        assert records[0].consent == "Y"

    def test_extracts_policy_status(self, sample_xlsx):
        records = parse_renewals(sample_xlsx)
        assert records[0].policy_status == "Active"

    def test_returns_list_of_records(self, sample_xlsx):
        records = parse_renewals(sample_xlsx)
        assert isinstance(records, list)
        assert len(records) == 1


class TestPhoneCleaning:
    """AC: Phone numbers cleaned from Excel-escaped format and validated as 10-digit Canadian."""

    def test_cleans_excel_escaped_format(self):
        assert clean_phone('="6041234567"') == "6041234567"

    def test_passes_plain_10_digit(self):
        assert clean_phone("6041234567") == "6041234567"

    def test_strips_dashes(self):
        assert clean_phone("604-123-4567") == "6041234567"

    def test_strips_spaces(self):
        assert clean_phone("604 123 4567") == "6041234567"

    def test_strips_parentheses_and_dashes(self):
        assert clean_phone("(604) 123-4567") == "6041234567"

    def test_handles_leading_country_code_1(self):
        assert clean_phone("16041234567") == "6041234567"

    def test_rejects_too_short(self):
        assert clean_phone("604123") is None

    def test_rejects_non_numeric(self):
        assert clean_phone("abcdefghij") is None

    def test_rejects_empty_string(self):
        assert clean_phone("") is None

    def test_rejects_none(self):
        assert clean_phone(None) is None


class TestCustomerNameParsing:
    """Name format: LASTNAME FIRSTNAME MIDDLENAME — extract first name for SMS."""

    def test_extracts_first_from_three_part(self):
        assert parse_customer_name("DOE JOHN MICHAEL") == "John"

    def test_extracts_first_from_two_part(self):
        assert parse_customer_name("DOE JANE") == "Jane"

    def test_handles_single_name(self):
        result = parse_customer_name("DOE")
        assert result is not None

    def test_capitalizes_properly(self):
        assert parse_customer_name("SMITH SARAH") == "Sarah"


class TestRenewalFiltering:
    """AC: Only Renewal + Active + no DateRenewed selected; invalid phone/consent skipped."""

    def test_includes_valid_active_renewal(self, sample_xlsx):
        records = parse_renewals(sample_xlsx)
        actionable = filter_actionable_renewals(records)
        assert len(actionable) == 1

    def test_excludes_non_renewal_transaction(self, sample_xlsx_mixed):
        records = parse_renewals(sample_xlsx_mixed)
        actionable = filter_actionable_renewals(records)
        types = [r.transaction_type for r in actionable]
        assert "New Business" not in types

    def test_excludes_already_renewed(self, sample_xlsx_mixed):
        records = parse_renewals(sample_xlsx_mixed)
        actionable = filter_actionable_renewals(records)
        for r in actionable:
            assert r.date_renewed is None

    def test_excludes_inactive_policies(self, sample_xlsx_mixed):
        records = parse_renewals(sample_xlsx_mixed)
        actionable = filter_actionable_renewals(records)
        for r in actionable:
            assert r.policy_status == "Active"

    def test_only_one_actionable_in_mixed(self, sample_xlsx_mixed):
        records = parse_renewals(sample_xlsx_mixed)
        actionable = filter_actionable_renewals(records)
        assert len(actionable) == 1
        assert actionable[0].policy_number == "POL-001"


class TestSkipInvalidPhones:
    """AC: Clients without a valid phone number are skipped and logged."""

    def test_skips_record_with_empty_phone(self, sample_xlsx_no_phone):
        records = parse_renewals(sample_xlsx_no_phone)
        actionable = filter_actionable_renewals(records)
        assert len(actionable) == 0

    def test_logs_skipped_invalid_phone(self, sample_xlsx_no_phone, caplog):
        import logging

        with caplog.at_level(logging.WARNING):
            records = parse_renewals(sample_xlsx_no_phone)
            filter_actionable_renewals(records)
        assert any("skip" in msg.lower() or "invalid" in msg.lower() for msg in caplog.messages)


class TestConsentFiltering:
    """AC: Clients without CustomerConsentYN = 'Y' are flagged/skipped (CASL compliance)."""

    def test_includes_consented_clients(self, sample_xlsx):
        records = parse_renewals(sample_xlsx)
        actionable = filter_actionable_renewals(records)
        assert len(actionable) == 1
        assert actionable[0].consent == "Y"

    def test_skips_non_consented_clients(self, sample_xlsx_no_consent):
        records = parse_renewals(sample_xlsx_no_consent)
        actionable = filter_actionable_renewals(records)
        assert len(actionable) == 0


class TestFileReload:
    """AC: Broker can load a new .xlsx file to refresh the renewal list."""

    def test_parses_different_file(self, sample_xlsx, sample_xlsx_updated):
        records1 = parse_renewals(sample_xlsx)
        records2 = parse_renewals(sample_xlsx_updated)
        assert records1[0].policy_number == "POL-001"
        assert records2[0].policy_number == "POL-100"

    def test_updated_file_has_different_count(self, sample_xlsx, sample_xlsx_updated):
        records1 = parse_renewals(sample_xlsx)
        records2 = parse_renewals(sample_xlsx_updated)
        assert len(records1) == 1
        assert len(records2) == 2
