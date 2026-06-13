import csv
from pathlib import Path

import pytest
import openpyxl
from datetime import date, timedelta


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


def _create_xlsx(path, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(AUTOLINK_COLUMNS)
    for row in rows:
        ws.append(row)
    wb.save(path)
    return path


@pytest.fixture
def sample_xlsx(tmp_path):
    """Single valid renewal record — active, consented, valid phone, not yet renewed."""
    expiry = date.today() + timedelta(days=20)
    return _create_xlsx(
        tmp_path / "renewals.xlsx",
        [
            [
                "DOE JOHN MICHAEL",
                '="6041234567"',
                expiry,
                "POL-001",
                "Toyota",
                "Camry",
                "Renewal",
                "Active",
                "Y",
                None,
            ],
        ],
    )


@pytest.fixture
def sample_xlsx_mixed(tmp_path):
    """Multiple records with varying transaction types, statuses, and renewal states."""
    expiry = date.today() + timedelta(days=20)
    return _create_xlsx(
        tmp_path / "renewals_mixed.xlsx",
        [
            # Valid actionable renewal
            ["DOE JOHN", '="6041234567"', expiry, "POL-001", "Toyota", "Camry", "Renewal", "Active", "Y", None],
            # Non-renewal transaction type
            ["SMITH JANE", '="6049876543"', expiry, "POL-002", "Honda", "Civic", "New Business", "Active", "Y", None],
            # Already renewed
            ["LEE ALEX", '="7781112222"', expiry, "POL-003", "Ford", "Focus", "Renewal", "Active", "Y", date.today()],
            # Inactive policy
            ["WONG SAM", '="6045556666"', expiry, "POL-004", "BMW", "X3", "Renewal", "Cancelled", "Y", None],
        ],
    )


@pytest.fixture
def sample_xlsx_no_phone(tmp_path):
    """Record with missing/invalid phone number."""
    expiry = date.today() + timedelta(days=20)
    return _create_xlsx(
        tmp_path / "renewals_no_phone.xlsx",
        [
            ["DOE JOHN", "", expiry, "POL-010", "Toyota", "Camry", "Renewal", "Active", "Y", None],
        ],
    )


@pytest.fixture
def sample_xlsx_no_consent(tmp_path):
    """Record without customer consent."""
    expiry = date.today() + timedelta(days=20)
    return _create_xlsx(
        tmp_path / "renewals_no_consent.xlsx",
        [
            ["DOE JOHN", '="6041234567"', expiry, "POL-020", "Toyota", "Camry", "Renewal", "Active", "N", None],
        ],
    )


@pytest.fixture
def sample_xlsx_updated(tmp_path):
    """Different data set to test file reload."""
    expiry = date.today() + timedelta(days=15)
    return _create_xlsx(
        tmp_path / "renewals_updated.xlsx",
        [
            ["PARK SARAH", '="7789998888"', expiry, "POL-100", "Hyundai", "Tucson", "Renewal", "Active", "Y", None],
            ["KIM DAVID", '="6047776655"', expiry, "POL-101", "Kia", "Sportage", "Renewal", "Active", "Y", None],
        ],
    )


@pytest.fixture
def sample_xlsx_multiple_valid(tmp_path):
    """Multiple actionable renewals at different expiry dates for timing tests."""
    return _create_xlsx(
        tmp_path / "renewals_timing.xlsx",
        [
            ["DOE JOHN", '="6041234567"', date.today() + timedelta(days=30), "POL-200", "Toyota", "Camry", "Renewal", "Active", "Y", None],
            ["SMITH JANE", '="6049876543"', date.today() + timedelta(days=14), "POL-201", "Honda", "Civic", "Renewal", "Active", "Y", None],
            ["LEE ALEX", '="7781112222"', date.today() + timedelta(days=3), "POL-202", "Ford", "Focus", "Renewal", "Active", "Y", None],
            ["WONG SAM", '="6045556666"', date.today() + timedelta(days=60), "POL-203", "BMW", "X3", "Renewal", "Active", "Y", None],
        ],
    )


def _create_csv(path, rows):
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(AUTOLINK_COLUMNS)
        for row in rows:
            writer.writerow(row)
    return path


@pytest.fixture
def sample_csv(tmp_path):
    """Single valid renewal record as CSV — mirrors sample_xlsx."""
    expiry = date.today() + timedelta(days=20)
    return _create_csv(
        tmp_path / "renewals.csv",
        [
            [
                "DOE JOHN MICHAEL",
                '="6041234567"',
                expiry.isoformat(),
                "POL-001",
                "Toyota",
                "Camry",
                "Renewal",
                "Active",
                "Y",
                "",
            ],
        ],
    )


@pytest.fixture
def sample_csv_mixed(tmp_path):
    """Multiple CSV records with varying states — mirrors sample_xlsx_mixed."""
    expiry = date.today() + timedelta(days=20)
    return _create_csv(
        tmp_path / "renewals_mixed.csv",
        [
            ["DOE JOHN", '="6041234567"', expiry.isoformat(), "POL-001", "Toyota", "Camry", "Renewal", "Active", "Y", ""],
            ["SMITH JANE", '="6049876543"', expiry.isoformat(), "POL-002", "Honda", "Civic", "New Business", "Active", "Y", ""],
            ["LEE ALEX", '="7781112222"', expiry.isoformat(), "POL-003", "Ford", "Focus", "Renewal", "Active", "Y", date.today().isoformat()],
            ["WONG SAM", "", expiry.isoformat(), "POL-004", "BMW", "X3", "Renewal", "Active", "Y", ""],
        ],
    )
