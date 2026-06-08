# utils.py
import base64
import json
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import anthropic
import os
from dotenv import load_dotenv
from googleapiclient.discovery import build

load_dotenv("openaiapikey.env")
_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# DATA constants (per-sheet, not global ID)
DATA_RANGE = "Sheet1!A:F"        # Company | Role | Application date | Method | Status | Gmail ID
LAST_TS_CELL = "Sheet1!H1"       # store last processed internalDate (ms)
MAX_MSG = 100                    # how many message ids to fetch per run

# ----------------- small helpers -----------------
def _b64_to_text(d):
    if not d:
        return ""
    try:
        return base64.urlsafe_b64decode(d).decode("utf-8", errors="ignore")
    except:
        return ""


def extract_body(payload):
    # prefer text/plain, else try text/html -> strip tags
    if not payload:
        return ""
    if payload.get("mimeType", "").startswith("text/"):
        txt = _b64_to_text(payload.get("body", {}).get("data"))
        if txt:
            return re.sub(r"<[^>]+>", " ", txt) if payload["mimeType"] == "text/html" else txt
    for p in payload.get("parts", []) or []:
        if p.get("mimeType", "").startswith("text/plain"):
            t = _b64_to_text(p.get("body", {}).get("data"))
            if t:
                return t
    for p in payload.get("parts", []) or []:
        if p.get("mimeType", "").startswith("text/html"):
            t = _b64_to_text(p.get("body", {}).get("data"))
            if t:
                return re.sub(r"<[^>]+>", " ", t)
    # nested
    for p in payload.get("parts", []) or []:
        nested = extract_body(p)
        if nested:
            return nested
    return ""


def fmt_date(maybe_date_str, fallback_header):
    # try model-provided date first, else header. Return DD-MMM-YYYY
    for s in (maybe_date_str or "", fallback_header or ""):
        if not s:
            continue
        try:
            # try email date parser (handles many formats)
            dt = parsedate_to_datetime(s)
        except Exception:
            # try ISO-ish
            try:
                dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            except Exception:
                dt = None
        if dt:
            return dt.astimezone(timezone.utc).strftime("%d-%b-%Y")
    return ""  # unknown


def normalize(x):
    return (x or "").strip().lower()


def should_consider(subject, sender, body):
    sender_lower = (sender or "").lower()
    subject_lower = (subject or "").lower()
    body_preview = (body or "")[:600].lower()

    # hard block: invite-to-apply / job alert / recommendation emails (not real applications)
    block_kws = [
        "invite to apply", "job invite", "invited to apply", "jobs for you",
        "recommended jobs", "jobs you may like", "new job alert", "job alert",
        "you may be interested", "jobs matching", "similar jobs", "explore jobs",
        "apply now", "new jobs in", "top jobs", "jobs near you"
    ]
    if any(k in subject_lower for k in block_kws):
        return False

    # known job platforms — trust the sender domain alone
    job_platforms = ("linkedin", "naukri", "indeed", "glassdoor", "monster", "shine", "instahyre", "hirist", "foundit", "internshala")
    if any(p in sender_lower for p in job_platforms):
        # still block if it's a job alert from that platform
        if not any(k in subject_lower for k in block_kws):
            pass  # fall through to keyword checks below

    # strong subject-line signals (actual application events)
    strong_kws = [
        "application", "interview", "offer letter", "shortlisted", "selected",
        "rejected", "regret", "congratulations", "assessment", "next steps",
        "hiring", "position", "vacancy", "opening", "job offer", "we received your",
        "thank you for applying", "your application", "application received",
        "application update", "application status"
    ]
    if any(k in subject_lower for k in strong_kws):
        return True

    # weaker keywords — check subject + body preview only
    weak_kws = ["applied", "resume", "cv", "recruit", "hired"]
    combined = subject_lower + " " + body_preview
    return any(k in combined for k in weak_kws)


def parse_model_output(raw):
    if not raw:
        return None
    raw = raw.strip()
    # strip code fences
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.I).strip()
    try:
        return json.loads(raw)
    except Exception:
        # rescue first {...}
        m = re.search(r"(\{.*\})", raw, flags=re.S)
        if m:
            try:
                return json.loads(m.group(1))
            except:
                return None
    return None


# ---------------- LLM ----------------
_SYSTEM_PROMPT = """\
You are an email classifier for a job application tracker.

Analyze the email and return ONLY a JSON object with these exact keys:

- "Company": The hiring company's name. Extract from the email body or the sender's domain — NOT the recruiter's personal name. If the email was sent by LinkedIn/Naukri about a role at "Infosys", Company = "Infosys".
- "Role": The job title or position mentioned (e.g. "Software Engineer", "Data Analyst Intern").
- "Application date": Date formatted as DD-Mon-YYYY (e.g. "15-Jan-2025"). Use the Date header if the body doesn't specify one.
- "Method": How the application was submitted. Choose ONE of: "LinkedIn", "Naukri", "Indeed", "Glassdoor", "Internshala", "Company Website", "Referral", "Email", "Other".
- "Status": Current application status. Choose ONE of: "Applied", "Under Review", "Interview Scheduled", "Interview Done", "Offer", "Rejected", "Withdrawn".
- "IsJob": true if this email is clearly about a job application, recruitment, interview, or hiring process. false for newsletters, promotions, account alerts, or general career tips.

Rules:
- IsJob = true for: application confirmations, interview invites/reminders, offer letters, rejection/regret emails, recruiter outreach about a specific role, shortlisting notifications, assessment invites.
- IsJob = false for: "invite to apply" emails, job alerts, "jobs for you" / "recommended jobs" emails, job board newsletters, promotional emails, password resets, general career advice. These are NOT applications — the user hasn't applied yet.
- If a field cannot be determined, use empty string "".
- Return ONLY the raw JSON object. No explanation, no markdown, no code fences.\
"""

def call_llm(subject, sender, body, date):
    user_msg = (
        f"Subject: {subject}\n"
        f"From: {sender}\n"
        f"Date: {date}\n\n"
        f"Email body:\n{(body or '')[:2500]}"
    )
    try:
        resp = _client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}]
        )
        raw = resp.content[0].text
        parsed = parse_model_output(raw)
        if not parsed:
            return {"Company": "", "Role": "", "Application date": "", "Method": "", "Status": "", "IsJob": False}
        # normalise IsJob to bool in case model returns a string
        if isinstance(parsed.get("IsJob"), str):
            parsed["IsJob"] = parsed["IsJob"].lower() == "true"
        return parsed
    except Exception:
        return {"Company": "", "Role": "", "Application date": "", "Method": "", "Status": "", "IsJob": False}


# ---------------- Sheet formatting ----------------
HEADERS = ["Company", "Role", "Application Date", "Method", "Status", "Gmail ID"]

STATUS_COLORS = {
    "applied":              {"red": 0.878, "green": 0.937, "blue": 1.0},      # light blue
    "under review":         {"red": 1.0,   "green": 0.976, "blue": 0.769},    # light yellow
    "interview scheduled":  {"red": 1.0,   "green": 0.925, "blue": 0.78},     # light orange
    "interview done":       {"red": 1.0,   "green": 0.878, "blue": 0.706},    # deeper orange
    "offer":                {"red": 0.827, "green": 0.937, "blue": 0.827},    # light green
    "rejected":             {"red": 1.0,   "green": 0.859, "blue": 0.859},    # light red
    "withdrawn":            {"red": 0.937, "green": 0.937, "blue": 0.937},    # light grey
}

def _rgb(r, g, b):
    return {"red": r, "green": g, "blue": b}

def format_sheet(svc, spreadsheet_id):
    """Apply header styling, borders, frozen row, column widths, and status colours."""
    # get the real sheet id (integer, not the spreadsheet string id)
    meta = svc.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    sheet_id = meta["sheets"][0]["properties"]["sheetId"]

    col_widths = [160, 220, 130, 130, 160, 0]  # 0 = hide Gmail ID column visually

    requests = []

    # 1. Write header row values
    svc.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range="Sheet1!A1:F1",
        valueInputOption="RAW",
        body={"values": [HEADERS]}
    ).execute()

    # 2. Header row style: purple background, white bold text, center-aligned
    requests.append({
        "repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1,
                      "startColumnIndex": 0, "endColumnIndex": 6},
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": _rgb(0.482, 0.184, 0.969),  # #7b2ff7
                    "textFormat": {"foregroundColor": _rgb(1, 1, 1), "bold": True, "fontSize": 11},
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE",
                }
            },
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)"
        }
    })

    # 3. Freeze header row
    requests.append({
        "updateSheetProperties": {
            "properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}},
            "fields": "gridProperties.frozenRowCount"
        }
    })

    # 4. Column widths
    for col_idx, width in enumerate(col_widths):
        if width == 0:
            continue
        requests.append({
            "updateDimensionProperties": {
                "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                          "startIndex": col_idx, "endIndex": col_idx + 1},
                "properties": {"pixelSize": width},
                "fields": "pixelSize"
            }
        })

    # 5. Hide Gmail ID column (col F, index 5)
    requests.append({
        "updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                      "startIndex": 5, "endIndex": 6},
            "properties": {"hiddenByUser": True},
            "fields": "hiddenByUser"
        }
    })

    # 6. Borders on all data (A1:F1000)
    border_style = {"style": "SOLID", "width": 1, "color": _rgb(0.8, 0.8, 0.8)}
    requests.append({
        "updateBorders": {
            "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1000,
                      "startColumnIndex": 0, "endColumnIndex": 6},
            "top":    border_style,
            "bottom": border_style,
            "left":   border_style,
            "right":  border_style,
            "innerHorizontal": border_style,
            "innerVertical":   border_style,
        }
    })

    # 7. Data rows: font, alignment, row height
    requests.append({
        "repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 1000,
                      "startColumnIndex": 0, "endColumnIndex": 6},
            "cell": {
                "userEnteredFormat": {
                    "textFormat": {"fontSize": 10},
                    "verticalAlignment": "MIDDLE",
                    "wrapStrategy": "CLIP",
                }
            },
            "fields": "userEnteredFormat(textFormat,verticalAlignment,wrapStrategy)"
        }
    })

    # 8. Row height for all rows
    requests.append({
        "updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "ROWS",
                      "startIndex": 0, "endIndex": 1000},
            "properties": {"pixelSize": 28},
            "fields": "pixelSize"
        }
    })

    svc.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": requests}
    ).execute()


def apply_status_colors(svc, spreadsheet_id):
    """Re-colour all rows in the Status column (col E) based on their value."""
    meta = svc.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    sheet_id = meta["sheets"][0]["properties"]["sheetId"]

    rows = svc.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range="Sheet1!A2:E1000"
    ).execute().get("values", [])

    requests = []
    for i, row in enumerate(rows, start=1):   # start=1 → row index 1 (0-based) = sheet row 2
        status_val = (row[4] if len(row) > 4 else "").strip().lower()
        color = STATUS_COLORS.get(status_val, _rgb(1, 1, 1))  # white if unknown
        requests.append({
            "repeatCell": {
                "range": {"sheetId": sheet_id,
                          "startRowIndex": i, "endRowIndex": i + 1,
                          "startColumnIndex": 4, "endColumnIndex": 5},
                "cell": {"userEnteredFormat": {"backgroundColor": color}},
                "fields": "userEnteredFormat.backgroundColor"
            }
        })

    if requests:
        svc.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": requests}
        ).execute()


# ---------------- Sheets helpers (refactored to accept spreadsheet_id) ----------------
def load_sheet_map(svc, spreadsheet_id):
    """
    Return (rows, exact_mapping, company_mapping).
    exact_mapping:   (company, role) -> row_index (1-based)
    company_mapping: company -> row_index of the most recent row for that company
    """
    rows = svc.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=DATA_RANGE).execute().get("values", [])
    exact_mapping = {}
    company_mapping = {}
    for i, r in enumerate(rows, start=1):
        comp = normalize(r[0]) if len(r) > 0 else ""
        role = normalize(r[1]) if len(r) > 1 else ""
        if comp:
            exact_mapping[(comp, role)] = i
            company_mapping[comp] = i  # last row wins (most recent status)
    return rows, exact_mapping, company_mapping


def get_last_ts(svc, spreadsheet_id):
    try:
        v = svc.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=LAST_TS_CELL).execute().get("values", [])
        return int(v[0][0]) if v else 0
    except:
        return 0


def set_last_ts(svc, spreadsheet_id, ts):
    svc.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=LAST_TS_CELL,
        valueInputOption="RAW",
        body={"values": [[str(int(ts))]]}
    ).execute()


# ---------------- main pipeline (now accepts spreadsheet_id) ----------------
# DEBUG-friendly scan_emails (replace existing scan_emails in utils.py)
def scan_emails(creds, spreadsheet_id, debug=True):
    """
    Debug version: scans Gmail, appends/updates spreadsheet, and returns
    a detailed report of messages processed so you can see why rows weren't added.
    """
    gmail = build("gmail", "v1", credentials=creds)
    sheets = build("sheets", "v4", credentials=creds)

    last_ts = get_last_ts(sheets, spreadsheet_id)
    rows, mapping, company_mapping = load_sheet_map(sheets, spreadsheet_id)

    # fetch job-related message ids using Gmail search query
    JOB_QUERY = (
        "subject:(application OR applied OR interview OR shortlisted OR offer OR "
        "selected OR rejected OR regret OR congratulations OR assessment OR hiring OR "
        "\"thank you for applying\" OR \"your application\" OR \"next steps\") "
        "OR from:(linkedin.com OR naukri.com OR indeed.com OR glassdoor.com OR "
        "internshala.com OR shine.com OR foundit.in OR instahyre.com)"
    )
    msgs = []
    page_token = None
    while len(msgs) < MAX_MSG:
        resp = gmail.users().messages().list(
            userId="me",
            q=JOB_QUERY,
            maxResults=min(100, MAX_MSG - len(msgs)),
            pageToken=page_token
        ).execute()
        msgs.extend(resp.get("messages", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    report = {"checked": 0, "skipped_old_ts": 0, "skipped_filter": 0, "skipped_not_job": 0,
              "updated": [], "appended": [], "errors": [], "samples": []}

    if not msgs:
        return {"msg": "no messages", "report": report}

    to_append = []
    updated_rows = {}
    max_ts = last_ts

    # limit to first 200 messages for debug safety
    for item in msgs:
        try:
            mid = item["id"]
            m = gmail.users().messages().get(userId="me", id=mid, format="full").execute()
            internal = int(m.get("internalDate", "0"))
            report["checked"] += 1
            if internal <= last_ts:
                report["skipped_old_ts"] += 1
                report["samples"].append({"id": mid, "reason": "old_internalDate", "internal": internal})
                continue
            if internal > max_ts:
                max_ts = internal

            payload = m.get("payload", {})
            headers = {h["name"].lower(): h["value"] for h in payload.get("headers", []) or []}
            subject = headers.get("subject", "")
            sender = headers.get("from", "")
            date_hdr = headers.get("date", "")
            body = extract_body(payload)

            # quick sample of what we saw (first few)
            if len(report["samples"]) < 5:
                report["samples"].append({"id": mid, "subject": subject, "from": sender, "internal": internal})

            if not should_consider(subject, sender, body):
                report["skipped_filter"] += 1
                # keep reason for debugging
                report.setdefault("skipped_filter_examples", []).append({"id": mid, "subject": subject, "from": sender})
                continue

            parsed = call_llm(subject, sender, body, date_hdr)
            if not parsed or not parsed.get("IsJob"):
                report["skipped_not_job"] += 1
                report.setdefault("skipped_not_job_examples", []).append({"id": mid, "subject": subject, "parsed": parsed})
                continue

            comp = parsed.get("Company", "") or ""
            role = parsed.get("Role", "") or ""
            status = parsed.get("Status") or "Applied"
            app_date = fmt_date(parsed.get("Application date", ""), date_hdr)
            method = parsed.get("Method") or ("Linkedin" if "linkedin" in (sender or "").lower() else "Website")

            # Change 1: skip rows with no company name
            if not comp.strip():
                report.setdefault("skipped_blank_company", []).append({"id": mid, "subject": subject})
                continue

            comp_key = normalize(comp)
            exact_key = (comp_key, normalize(role))

            if exact_key in mapping:
                # exact (company, role) match — update full row
                row_idx = mapping[exact_key]
                vals = [[comp, role, app_date, method, status, mid]]
                rng = f"Sheet1!A{row_idx}:F{row_idx}"
                try:
                    sheets.spreadsheets().values().update(spreadsheetId=spreadsheet_id, range=rng, valueInputOption="RAW", body={"values": vals}).execute()
                    updated_rows[exact_key] = row_idx
                    report["updated"].append({"id": mid, "company": comp, "role": role, "row": row_idx, "match": "exact"})
                except Exception as e:
                    report["errors"].append({"id": mid, "when": "update", "error": str(e)})

            elif comp_key in company_mapping:
                # Change 2: company-only match — same company, different stage email
                # only update Status (col E) and Gmail ID (col F) to avoid overwriting role
                row_idx = company_mapping[comp_key]
                rng_status = f"Sheet1!E{row_idx}:F{row_idx}"
                try:
                    sheets.spreadsheets().values().update(spreadsheetId=spreadsheet_id, range=rng_status, valueInputOption="RAW", body={"values": [[status, mid]]}).execute()
                    updated_rows[exact_key] = row_idx
                    report["updated"].append({"id": mid, "company": comp, "role": role, "row": row_idx, "match": "company_only"})
                except Exception as e:
                    report["errors"].append({"id": mid, "when": "status_update", "error": str(e)})

            else:
                to_append.append([comp, role, app_date, method, status, mid])
                mapping[exact_key] = len(rows) + len(to_append)
                company_mapping[comp_key] = len(rows) + len(to_append)
                report["appended"].append({"id": mid, "company": comp, "role": role})

        except Exception as e:
            report["errors"].append({"id": item.get("id"), "error": str(e)})

    # perform append
    if to_append:
        try:
            sheets.spreadsheets().values().append(spreadsheetId=spreadsheet_id, range=DATA_RANGE, valueInputOption="RAW", body={"values": to_append}).execute()
        except Exception as e:
            report["errors"].append({"when": "append", "error": str(e)})

    if max_ts:
        try:
            set_last_ts(sheets, spreadsheet_id, max_ts)
        except Exception as e:
            report["errors"].append({"when": "set_last_ts", "error": str(e)})

    # include a summary count
    report["summary"] = {
        "checked": report["checked"],
        "appended": len(report["appended"]),
        "updated": len(report["updated"]),
        "skipped_old_ts": report["skipped_old_ts"],
        "skipped_filter": report["skipped_filter"],
        "skipped_not_job": report["skipped_not_job"],
        "errors": len(report["errors"])
    }
    # re-colour status column after any changes
    if report["appended"] or report["updated"]:
        try:
            apply_status_colors(sheets, spreadsheet_id)
        except Exception:
            pass

    return {"msg": "debug run complete", "report": report}
