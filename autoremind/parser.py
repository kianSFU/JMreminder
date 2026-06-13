import csv
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import openpyxl

logger = logging.getLogger(__name__)

EXPECTED_COLUMNS = [
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


@dataclass
class RenewalRecord:
    customer_name: str
    phone: Optional[str]
    policy_expiry_date: Optional[date]
    policy_number: str
    make: str
    model: str
    transaction_type: str
    policy_status: str
    consent: str
    date_renewed: Optional[date]


def clean_phone(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    raw = str(raw).strip()
    if not raw:
        return None
    # Strip Excel-escaped format: ="6041234567"
    raw = raw.replace('="', "").replace('"', "")
    # Strip formatting characters
    raw = re.sub(r"[\s\-\(\)\+]", "", raw)
    if not raw.isdigit():
        return None
    # Strip leading country code 1 for 11-digit numbers
    if len(raw) == 11 and raw.startswith("1"):
        raw = raw[1:]
    if len(raw) != 10:
        return None
    return raw


def parse_customer_name(full_name: str) -> Optional[str]:
    parts = full_name.strip().split()
    if len(parts) >= 2:
        return parts[1].capitalize()
    if len(parts) == 1:
        return parts[0].capitalize()
    return None


def _parse_date(value) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


def _build_record(row: dict) -> RenewalRecord:
    return RenewalRecord(
        customer_name=str(row.get("CustomerName") or ""),
        phone=clean_phone(row.get("CustomerHomePhone")),
        policy_expiry_date=_parse_date(row.get("PolicyExpiryDate")),
        policy_number=str(row.get("PolicyNumber") or ""),
        make=str(row.get("Make") or ""),
        model=str(row.get("Model") or ""),
        transaction_type=str(row.get("TransactionTypeDesc") or ""),
        policy_status=str(row.get("PolicyStatusDesc") or ""),
        consent=str(row.get("CustomerConsentYN") or ""),
        date_renewed=_parse_date(row.get("DateRenewed")),
    )


def parse_renewals(xlsx_path: Path) -> list[RenewalRecord]:
    wb = openpyxl.load_workbook(xlsx_path, read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    if not rows:
        return []

    header = [str(c) if c else "" for c in rows[0]]
    col_map = {name: idx for idx, name in enumerate(header)}

    def get(row, col):
        idx = col_map.get(col)
        if idx is None or idx >= len(row):
            return None
        return row[idx]

    records = []
    for row in rows[1:]:
        row_dict = {col: get(row, col) for col in EXPECTED_COLUMNS}
        records.append(_build_record(row_dict))

    return records


def parse_renewals_csv(csv_path: Path) -> list[RenewalRecord]:
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        return [_build_record(row) for row in reader]


def parse_renewals_file(file_path: Path) -> list[RenewalRecord]:
    file_path = Path(file_path)
    ext = file_path.suffix.lower()
    if ext == ".xlsx":
        return parse_renewals(file_path)
    if ext == ".csv":
        return parse_renewals_csv(file_path)
    raise ValueError(f"Unsupported file type: {ext}")


def _is_renewal_candidate(r: RenewalRecord) -> bool:
    return (
        r.transaction_type == "Renewal"
        and r.policy_status == "Active"
        and r.consent == "Y"
        and r.date_renewed is None
    )


def filter_actionable_renewals(records: list[RenewalRecord]) -> list[RenewalRecord]:
    actionable = []
    for r in records:
        if not _is_renewal_candidate(r):
            continue
        if not r.phone:
            logger.warning("Skipping %s — invalid or missing phone number", r.customer_name)
            continue
        actionable.append(r)
    return actionable


def filter_skipped_renewals(records: list[RenewalRecord]) -> list[RenewalRecord]:
    return [r for r in records if _is_renewal_candidate(r) and not r.phone]
