"""Tests for AR-3: CSV parsing and file-type auto-detection."""

import pytest
from datetime import date, timedelta
from pathlib import Path

from autoremind.parser import RenewalRecord


class TestCsvParsing:
    """AC: System parses .csv files into RenewalRecord objects using the same column mapping as .xlsx."""

    def test_csv_returns_renewal_records(self, sample_csv):
        from autoremind.parser import parse_renewals_csv

        records = parse_renewals_csv(sample_csv)
        assert isinstance(records, list)
        assert len(records) == 1
        assert isinstance(records[0], RenewalRecord)

    def test_csv_extracts_customer_name(self, sample_csv):
        from autoremind.parser import parse_renewals_csv

        records = parse_renewals_csv(sample_csv)
        assert records[0].customer_name == "DOE JOHN MICHAEL"

    def test_csv_extracts_phone(self, sample_csv):
        from autoremind.parser import parse_renewals_csv

        records = parse_renewals_csv(sample_csv)
        assert records[0].phone == "6041234567"

    def test_csv_extracts_policy_number(self, sample_csv):
        from autoremind.parser import parse_renewals_csv

        records = parse_renewals_csv(sample_csv)
        assert records[0].policy_number == "POL-001"

    def test_csv_extracts_vehicle_make_and_model(self, sample_csv):
        from autoremind.parser import parse_renewals_csv

        records = parse_renewals_csv(sample_csv)
        assert records[0].make == "Toyota"
        assert records[0].model == "Camry"

    def test_csv_extracts_expiry_date(self, sample_csv):
        from autoremind.parser import parse_renewals_csv

        records = parse_renewals_csv(sample_csv)
        assert records[0].policy_expiry_date is not None
        assert isinstance(records[0].policy_expiry_date, date)

    def test_csv_extracts_transaction_type(self, sample_csv):
        from autoremind.parser import parse_renewals_csv

        records = parse_renewals_csv(sample_csv)
        assert records[0].transaction_type == "Renewal"

    def test_csv_extracts_consent(self, sample_csv):
        from autoremind.parser import parse_renewals_csv

        records = parse_renewals_csv(sample_csv)
        assert records[0].consent == "Y"

    def test_csv_empty_date_renewed_is_none(self, sample_csv):
        from autoremind.parser import parse_renewals_csv

        records = parse_renewals_csv(sample_csv)
        assert records[0].date_renewed is None

    def test_csv_parses_multiple_rows(self, sample_csv_mixed):
        from autoremind.parser import parse_renewals_csv

        records = parse_renewals_csv(sample_csv_mixed)
        assert len(records) == 4

    def test_csv_handles_excel_escaped_phone(self, sample_csv):
        from autoremind.parser import parse_renewals_csv

        records = parse_renewals_csv(sample_csv)
        assert records[0].phone == "6041234567"


class TestFileTypeAutoDetection:
    """AC: Parser auto-detects file type by extension and routes to the correct reader."""

    def test_dispatches_xlsx(self, sample_xlsx):
        from autoremind.parser import parse_renewals_file

        records = parse_renewals_file(sample_xlsx)
        assert isinstance(records, list)
        assert len(records) == 1
        assert isinstance(records[0], RenewalRecord)

    def test_dispatches_csv(self, sample_csv):
        from autoremind.parser import parse_renewals_file

        records = parse_renewals_file(sample_csv)
        assert isinstance(records, list)
        assert len(records) == 1
        assert isinstance(records[0], RenewalRecord)

    def test_csv_and_xlsx_produce_same_fields(self, sample_xlsx, sample_csv):
        from autoremind.parser import parse_renewals_file

        xlsx_records = parse_renewals_file(sample_xlsx)
        csv_records = parse_renewals_file(sample_csv)
        assert xlsx_records[0].customer_name == csv_records[0].customer_name
        assert xlsx_records[0].phone == csv_records[0].phone
        assert xlsx_records[0].policy_number == csv_records[0].policy_number
        assert xlsx_records[0].make == csv_records[0].make
        assert xlsx_records[0].model == csv_records[0].model

    def test_rejects_unsupported_extension(self, tmp_path):
        from autoremind.parser import parse_renewals_file

        bad_file = tmp_path / "data.json"
        bad_file.write_text("{}")
        with pytest.raises(ValueError):
            parse_renewals_file(bad_file)
