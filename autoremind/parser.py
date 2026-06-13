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
    return None


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
        phone_raw = get(row, "CustomerHomePhone")
        phone = clean_phone(phone_raw)

        expiry_date = _parse_date(get(row, "PolicyExpiryDate"))
        date_renewed = _parse_date(get(row, "DateRenewed"))

        records.append(RenewalRecord(
            customer_name=str(get(row, "CustomerName") or ""),
            phone=phone,
            policy_expiry_date=expiry_date,
            policy_number=str(get(row, "PolicyNumber") or ""),
            make=str(get(row, "Make") or ""),
            model=str(get(row, "Model") or ""),
            transaction_type=str(get(row, "TransactionTypeDesc") or ""),
            policy_status=str(get(row, "PolicyStatusDesc") or ""),
            consent=str(get(row, "CustomerConsentYN") or ""),
            date_renewed=date_renewed,
        ))

    return records


def filter_actionable_renewals(records: list[RenewalRecord]) -> list[RenewalRecord]:
    actionable = []
    for r in records:
        if r.transaction_type != "Renewal":
            continue
        if r.policy_status != "Active":
            continue
        if r.date_renewed is not None:
            continue
        if r.consent != "Y":
            continue
        if not r.phone:
            logger.warning("Skipping %s — invalid or missing phone number", r.customer_name)
            continue
        actionable.append(r)
    return actionable
