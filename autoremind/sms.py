import os
from datetime import date
from typing import Optional

from twilio.rest import Client

from autoremind.parser import RenewalRecord, parse_customer_name

DEFAULT_REMINDER_DAYS = [30, 14, 3]


def format_message(first_name: str, make: str, model: str, expiry_date: date) -> str:
    date_str = expiry_date.strftime("%B %d, %Y")
    return (
        f"Hi {first_name}, your ICBC policy for your {make} {model} "
        f"is up for renewal on {date_str}. "
        f"Please contact Johnston Meier Insurance to renew."
    )


def get_due_reminders(
    records: list[RenewalRecord],
    reminder_days: Optional[list[int]] = None,
) -> list[RenewalRecord]:
    if reminder_days is None:
        reminder_days = DEFAULT_REMINDER_DAYS
    today = date.today()
    due = []
    for r in records:
        if r.policy_expiry_date is None:
            continue
        days_until = (r.policy_expiry_date - today).days
        if days_until in reminder_days:
            due.append(r)
    return due


def send_reminder(phone: str, message: str) -> None:
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    from_number = os.environ.get("TWILIO_FROM_NUMBER", "")

    client = Client(account_sid, auth_token)
    client.messages.create(
        body=message,
        from_=from_number,
        to=f"+1{phone}",
    )
