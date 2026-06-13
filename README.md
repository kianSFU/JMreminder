# AutoRemind

SMS renewal reminder system for Johnston Meier Insurance. Parses Autolink renewal exports, sends SMS reminders to clients via Twilio, and tracks click confirmations.

## Setup

### 1. Install dependencies

```bash
pip install openpyxl twilio fastapi uvicorn python-multipart jinja2 httpx
```

### 2. Configure environment variables

```bash
export TWILIO_ACCOUNT_SID="your_account_sid"
export TWILIO_AUTH_TOKEN="your_auth_token"
export TWILIO_FROM_NUMBER="+1XXXXXXXXXX"
```

### 3. Run the web app

```bash
cd JMreminder
python -m uvicorn autoremind.web:app --reload --port 8000
```

Open http://localhost:8000 in your browser.

### 4. Usage

1. Export a renewal list from Autolink as `.csv` or `.xlsx`
2. Upload the file at http://localhost:8000
3. Review the actionable renewals table
4. Click "Send SMS to All" to send reminders
5. Monitor client clicks at http://localhost:8000/dashboard

## Running tests

```bash
pip install pytest
python -m pytest -v
```
