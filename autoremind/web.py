import io
import tempfile
from pathlib import Path

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

    rows_html = ""
    for r in actionable:
        rows_html += (
            f"<tr><td>{r.policy_number}</td><td>{r.customer_name}</td>"
            f"<td>{r.phone}</td><td>{r.make} {r.model}</td>"
            f"<td>{r.policy_expiry_date}</td></tr>\n"
        )

    skipped_html = ""
    for r in skipped:
        skipped_html += (
            f"<tr><td>{r.policy_number}</td><td>{r.customer_name}</td>"
            f"<td>invalid/missing</td></tr>\n"
        )

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


@app.post("/send", response_class=HTMLResponse)
async def send():
    sent_count = 0
    skipped_count = 0
    for r in _last_actionable:
        if _tracker.was_policy_sent(r.policy_number):
            skipped_count += 1
            continue
        first_name = parse_customer_name(r.customer_name) or r.customer_name
        tracking_url = f"/click/{r.policy_number}"
        msg = format_message(
            first_name=first_name,
            make=r.make,
            model=r.model,
            expiry_date=r.policy_expiry_date,
            tracking_url=tracking_url,
        )
        send_reminder(phone=r.phone, message=msg)
        _tracker.record_sent(policy_number=r.policy_number, phone=r.phone, reminder_days=DEFAULT_REMINDER_DAYS[0])
        sent_count += 1
    return HTMLResponse(content=f"<html><body>Sent {sent_count}. Skipped {skipped_count} duplicates.</body></html>")


@app.get("/click/{policy_number}", response_class=HTMLResponse)
async def click(policy_number: str):
    _tracker.record_click(policy_number=policy_number)
    return HTMLResponse(
        content=f"<html><body><h1>Thank you!</h1><p>Your broker will be in touch about your renewal.</p></body></html>"
    )


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    clicks = _tracker.get_clicks()
    rows_html = ""
    for c in clicks:
        rows_html += f"<tr><td>{c['policy_number']}</td><td>{c['clicked_at']}</td></tr>\n"
    return HTMLResponse(content=f"""<html><body>
<h2>Clicked Renewals</h2>
<table>{rows_html}</table>
</body></html>""")
