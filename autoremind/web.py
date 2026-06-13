import io
import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import HTMLResponse

from autoremind.parser import (
    RenewalRecord,
    parse_renewals_file,
    filter_actionable_renewals,
    filter_skipped_renewals,
    parse_customer_name,
)
from autoremind.sms import format_message, send_reminder, DEFAULT_REMINDER_DAYS
from autoremind.tracker import ReminderTracker

app = FastAPI()


def get_base_url() -> str:
    url = os.environ.get("BASE_URL", "http://localhost:8000")
    return url.rstrip("/")

_last_actionable: list[RenewalRecord] = []
_last_skipped: list[RenewalRecord] = []


def get_db_path() -> Path:
    data_dir = Path(__file__).resolve().parent.parent / "data"
    data_dir.mkdir(exist_ok=True)
    return data_dir / "autoremind.db"


_tracker = ReminderTracker(db_path=get_db_path())

_BASE_CSS = """
  body { font-family: system-ui, sans-serif; max-width: 900px; margin: 40px auto; padding: 0 20px; }
  h1 { color: #1a365d; }
  table { border-collapse: collapse; width: 100%; margin: 12px 0; }
  th, td { border: 1px solid #e2e8f0; padding: 8px 12px; text-align: left; }
  th { background: #edf2f7; }
  form { background: #f7fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 24px; margin: 20px 0; }
  input[type=file] { margin: 12px 0; }
  button { background: #2b6cb0; color: white; border: none; padding: 10px 24px; border-radius: 4px; cursor: pointer; font-size: 16px; }
  button:hover { background: #2c5282; }
  a { color: #2b6cb0; margin-right: 16px; }
  nav { margin-bottom: 24px; }
  .count { color: #718096; }
"""

_NAV = '<nav><a href="/">Upload</a> <a href="/dashboard">Dashboard</a></nav>'


def _render_actionable_rows(records: list[RenewalRecord]) -> str:
    return "".join(
        f"<tr><td>{r.policy_number}</td><td>{r.customer_name}</td>"
        f"<td>{r.phone}</td><td>{r.make} {r.model}</td>"
        f"<td>{r.policy_expiry_date}</td></tr>\n"
        for r in records
    )


def _render_skipped_rows(records: list[RenewalRecord]) -> str:
    return "".join(
        f"<tr><td>{r.policy_number}</td><td>{r.customer_name}</td>"
        f"<td>invalid/missing</td></tr>\n"
        for r in records
    )


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(content=f"""<html><head>
<title>AutoRemind - Johnston Meier Insurance</title>
<style>{_BASE_CSS}</style>
</head><body>
<h1>AutoRemind</h1>
{_NAV}
<form action="/upload" method="post" enctype="multipart/form-data">
  <h3>Upload Renewal File</h3>
  <p>Select an Autolink export (.csv or .xlsx)</p>
  <input type="file" name="file" accept=".csv,.xlsx" required>
  <br><br>
  <button type="submit">Upload & Parse</button>
</form>
</body></html>""")


@app.post("/upload", response_class=HTMLResponse)
async def upload(file: UploadFile = File(...)):
    global _last_actionable, _last_skipped

    ext = Path(file.filename or "").suffix.lower()
    if ext not in (".csv", ".xlsx"):
        return HTMLResponse(content="Unsupported file format", status_code=400)

    content = await file.read()
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    records = parse_renewals_file(tmp_path)
    tmp_path.unlink(missing_ok=True)

    actionable = filter_actionable_renewals(records)
    skipped = filter_skipped_renewals(records)

    _last_actionable = actionable
    _last_skipped = skipped

    rows_html = _render_actionable_rows(actionable)

    skipped_html = _render_skipped_rows(skipped)

    return HTMLResponse(content=f"""<html><head>
<title>AutoRemind - Upload Results</title>
<style>{_BASE_CSS}</style>
</head><body>
<h1>AutoRemind</h1>
{_NAV}
<h2>Actionable Renewals <span class="count">({len(actionable)})</span></h2>
<table><tr><th>Policy</th><th>Name</th><th>Phone</th><th>Vehicle</th><th>Expiry</th></tr>
{rows_html}</table>
<form action="/send" method="post" style="margin: 20px 0;">
  <button type="submit">Send SMS to All ({len(actionable)})</button>
</form>
<h2>Skipped — Invalid Phone <span class="count">({len(skipped)})</span></h2>
<table><tr><th>Policy</th><th>Name</th><th>Phone</th></tr>
{skipped_html}</table>
</body></html>""")


def _send_single_reminder(record: RenewalRecord, base_url: str) -> bool:
    """Returns True if sent, False if skipped as duplicate."""
    if _tracker.was_policy_sent(record.policy_number):
        return False
    first_name = parse_customer_name(record.customer_name) or record.customer_name
    tracking_url = f"{base_url}/click/{record.policy_number}"
    msg = format_message(
        first_name=first_name,
        make=record.make,
        model=record.model,
        expiry_date=record.policy_expiry_date,
        tracking_url=tracking_url,
    )
    send_reminder(phone=record.phone, message=msg)
    _tracker.record_sent(
        policy_number=record.policy_number,
        phone=record.phone,
        reminder_days=DEFAULT_REMINDER_DAYS[0],
        customer_name=record.customer_name,
        make=record.make,
        model=record.model,
        policy_expiry_date=str(record.policy_expiry_date) if record.policy_expiry_date else "",
    )
    return True


@app.post("/send", response_class=HTMLResponse)
async def send():
    base_url = get_base_url()
    results = [_send_single_reminder(r, base_url) for r in _last_actionable]
    sent_count = sum(results)
    skipped_count = len(results) - sent_count
    return HTMLResponse(content=f"""<html><head>
<title>AutoRemind - Send Results</title>
<style>{_BASE_CSS}</style>
</head><body>
<h1>AutoRemind</h1>
{_NAV}
<p>Sent {sent_count}. Skipped {skipped_count} duplicates.</p>
<a href="/">Upload</a> <a href="/dashboard">Dashboard</a>
</body></html>""")


@app.get("/click/{policy_number}", response_class=HTMLResponse)
async def click(policy_number: str):
    _tracker.record_click(policy_number=policy_number)
    return HTMLResponse(content=f"""<html><head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Johnston Meier Insurance — Renewal Confirmed</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 0; padding: 40px 20px; background: #f7fafc; color: #1a365d; }}
  .container {{ max-width: 480px; margin: 0 auto; background: white; border-radius: 8px; padding: 40px 32px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); text-align: center; }}
  h1 {{ font-size: 24px; margin-bottom: 8px; }}
  .subtitle {{ color: #4a5568; font-size: 14px; margin-bottom: 32px; }}
  p {{ color: #2d3748; line-height: 1.6; }}
</style>
</head><body>
<div class="container">
  <h1>Johnston Meier Insurance</h1>
  <p class="subtitle">Protecting what matters</p>
  <h2>Thank you!</h2>
  <p>Your broker will be in touch about your renewal.</p>
</div>
</body></html>""")


def _render_dashboard_rows(data: list[dict]) -> str:
    def _row(d: dict) -> str:
        vehicle = f"{d.get('make') or ''} {d.get('model') or ''}".strip()
        return (
            f"<tr><td>{d.get('policy_number', '')}</td>"
            f"<td>{d.get('customer_name') or ''}</td>"
            f"<td>{d.get('phone') or ''}</td>"
            f"<td>{vehicle}</td>"
            f"<td>{d.get('policy_expiry_date') or ''}</td>"
            f"<td>{d.get('clicked_at', '')}</td></tr>\n"
        )
    return "".join(_row(d) for d in data)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    data = _tracker.get_dashboard_data()
    rows_html = _render_dashboard_rows(data)
    return HTMLResponse(content=f"""<html><head>
<title>AutoRemind - Dashboard</title>
<style>{_BASE_CSS}</style>
</head><body>
<h1>AutoRemind</h1>
{_NAV}
<h2>Clicked Renewals</h2>
<table><tr><th>Policy</th><th>Name</th><th>Phone</th><th>Vehicle</th><th>Expiry</th><th>Clicked At</th></tr>
{rows_html}</table>
</body></html>""")
