# main.py
import os
import json
import urllib.parse
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import requests
import feedparser
from fastapi import FastAPI, UploadFile, Form, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse
import uuid, shutil
from pathlib import Path
from types import SimpleNamespace

# Google / OAuth
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials as UserCredentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# === Agent modules (keep as-is if present) ===
from backend.agents.chatbot import chatbot_fn
from backend.agents.cold_email import generate_cold_email as _generate_cold_email
from backend.agents.custom_cv import (
    extract_resume_text, extract_keywords, tailor_cv,
    calculate_ats_score, build_cv_docx
)
from backend.agents.resume_review import review_resume
from backend.agents.cover_letter import cover_letter_fn, generate_cover_letter_body
from backend.agents.job_discovery_tool import job_discovery

# utils (must implement scan_emails(creds, spreadsheet_id) in utils.py)
from backend.utils import scan_emails as utils_scan_emails, format_sheet, apply_status_colors
import logging

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger(__name__)

# Allow insecure transport for local testing (DO NOT set in prod)
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

# ==== CONFIG (env overrides for deploy) ====
CLIENT_SECRETS_FILE = os.getenv("CLIENT_SECRETS_FILE", "credentials.json")
TOKEN_FILE = os.getenv("TOKEN_FILE", "token.json")
SHEET_ID_FILE = os.getenv("SHEET_ID_FILE", "sheet_id.json")

REDIRECT_URI = os.getenv("REDIRECT_URI", "http://localhost:8001/oauth2callback")
STREAMLIT_URL = os.getenv("STREAMLIT_URL", "http://localhost:8501/")


SCOPES = [
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]


# App
app = FastAPI()

# -------------------------
# CORS - allow your front-end domain(s)
# -------------------------
allowed_origins = [
    os.getenv("FRONTEND_ORIGIN", "https://jobassist-ui-ua6pbx6pna-uc.a.run.app"),
    "http://localhost:8501",
    "http://localhost:3000",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------
# Files & directories
# -------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
TOKENS_DIR = BASE_DIR / "tokens"
SHEETS_DIR = BASE_DIR / "sheets"
PROFILE_DIR = BASE_DIR / "profiles"
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "cover_outputs"

for d in [TOKENS_DIR, SHEETS_DIR, PROFILE_DIR, UPLOAD_DIR, OUTPUT_DIR]:
    d.mkdir(exist_ok=True)

# ------------------------
# Guest/demo constants & helpers
# ------------------------
GUEST_EMAIL = "guest@demo.com"

today = datetime.utcnow().strftime("%d-%b-%Y")

GUEST_SHEET_ROWS = [
    ["Company", "Role", "Application Date", "Method", "Status", "Gmail ID"],
    ["Acme Corp", "Junior Data Analyst", today, "LinkedIn", "Applied", "guest-1"],
    ["Cloudify", "SRE Trainee", today, "LinkedIn", "Applied", "guest-5"],
    ["FinEdge", "Business Analyst", (datetime.utcnow() - timedelta(days=8)).strftime("%d-%b-%Y"), "Company Website", "In Progress", "guest-2"],
    ["GreenTech", "ML Intern", (datetime.utcnow() - timedelta(days=12)).strftime("%d-%b-%Y"), "Referral", "Interview Scheduled", "guest-3"],
    ["RetailX", "Product Analyst", (datetime.utcnow() - timedelta(days=16)).strftime("%d-%b-%Y"), "Naukri", "Offer", "guest-4"],
]

GUEST_PROFILE = {
    "user_id": GUEST_EMAIL,
    "name": "Guest User",
    "email": GUEST_EMAIL,
    "phone": None,
    "linkedin": None,
    "github": None,
    "title": "Product / Data aspirant",
    "skills": ["python", "sql", "excel"],
    "desired_role": "Analyst",
    "preferred_location": "Remote / India",
    "resume_file": None,
    "cover_letter_template": None,
    "last_updated": datetime.utcnow().isoformat()
}

def _guest_rows_as_json():
    headers = GUEST_SHEET_ROWS[0]
    rows = [dict(zip(headers, r + [""] * (len(headers) - len(r)))) for r in GUEST_SHEET_ROWS[1:]]
    return {"rows": rows}

def _guest_df():
    headers = GUEST_SHEET_ROWS[0]
    rows = [r + [""] * (len(headers) - len(r)) for r in GUEST_SHEET_ROWS[1:]]
    return pd.DataFrame(rows, columns=headers)

# -------------------------
# Helpers: token / sheet id (single-user helpers)
# -------------------------
def _safe_email_key(email: str) -> str:
    return email.replace("@", "_at_").replace(".", "_dot_")

from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleAuthRequest

def email_key(email: str) -> str:
    return email.lower().replace("@", "_at_").replace(".", "_dot_")

def save_user_token(email: str, creds: Credentials):
    path = TOKENS_DIR / f"token_{email_key(email)}.json"
    path.write_text(creds.to_json())
    LOG.info("✅ Token saved at %s", path)

def load_user_token(email: str):
    path = TOKENS_DIR / f"token_{email_key(email)}.json"

    if not path.exists():
        LOG.info("❌ No token file for %s", email)
        return None

    try:
        creds = Credentials.from_authorized_user_file(str(path), SCOPES)
    except Exception:
        path.unlink(missing_ok=True)
        return None

    if creds.expired:
        if not creds.refresh_token:
            path.unlink(missing_ok=True)
            return None
        try:
            creds.refresh(GoogleAuthRequest())
            save_user_token(email, creds)
        except RefreshError:
            path.unlink(missing_ok=True)
            return None

    return creds



def save_user_sheet(email: str, sheet_id: str):
    key = _safe_email_key(email)
    with open(SHEETS_DIR / f"sheet_{key}.json", "w") as f:
        json.dump({"spreadsheet_id": sheet_id}, f)

def load_user_sheet(email: str) -> Optional[str]:
    key = _safe_email_key(email)
    sheet_file = SHEETS_DIR / f"sheet_{key}.json"
    if not sheet_file.exists():
        return None
    return json.load(open(sheet_file))["spreadsheet_id"]

def _get_user_id(request: Request) -> str:
    email = request.query_params.get("email")
    if not email:
        raise HTTPException(status_code=401, detail="User email missing")
    return email

# -------------------------
# utility: validate credentials.json redirect URIs vs REDIRECT_URI (clear helpful error)
# -------------------------
def _validate_client_secrets():
    if not Path(CLIENT_SECRETS_FILE).exists():
        return "Missing client secrets file: " + CLIENT_SECRETS_FILE
    try:
        cfg = json.load(open(CLIENT_SECRETS_FILE))
        # Common layout: cfg["web"]["redirect_uris"] or cfg["installed"]
        web = cfg.get("web") or cfg.get("installed")
        if not web:
            return "credentials.json missing 'web' or 'installed' section"
        allowed = web.get("redirect_uris", [])
        if REDIRECT_URI not in allowed:
            return f"REDIRECT_URI mismatch. REDIRECT_URI={REDIRECT_URI} not found in credentials.json redirect_uris: {allowed}"
        return None
    except Exception as e:
        return f"Error reading client secrets: {e}"

# -------------------------
# OAuth endpoints
# -------------------------
_pending_flows: dict = {}  # state -> Flow, persists between /login and /oauth2callback

@app.get("/login")
def login():
    bad = _validate_client_secrets()
    if bad:
        qs = {"auth": "failed", "error": urllib.parse.quote_plus(bad)}
        return RedirectResponse(STREAMLIT_URL.rstrip("/") + "/?" + urllib.parse.urlencode(qs, quote_via=urllib.parse.quote_plus))

    try:
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE, scopes=SCOPES, redirect_uri=REDIRECT_URI
        )
        auth_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent"
        )
        _pending_flows[state] = flow
        return RedirectResponse(auth_url)
    except Exception as e:
        qs = {"auth": "failed", "error": urllib.parse.quote_plus(f"Failed creating OAuth flow: {e}")}
        return RedirectResponse(STREAMLIT_URL.rstrip("/") + "/?" + urllib.parse.urlencode(qs, quote_via=urllib.parse.quote_plus))

@app.get("/oauth2callback")
def oauth2callback(request: Request):
    try:
        state = request.query_params.get("state")
        flow = _pending_flows.pop(state, None)
        if flow is None:
            flow = Flow.from_client_secrets_file(
                CLIENT_SECRETS_FILE, scopes=SCOPES, redirect_uri=REDIRECT_URI
            )

        # Cloud Run terminates TLS; internal URL may be http:// — force https
        auth_response = str(request.url)
        if auth_response.startswith("http://") and "localhost" not in auth_response:
            auth_response = "https://" + auth_response[7:]
        flow.fetch_token(authorization_response=auth_response)
        creds = flow.credentials

        # 🔹 OpenID userinfo (modern + correct)
        resp = requests.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {creds.token}"},
            timeout=10,
        )
        resp.raise_for_status()
        userinfo = resp.json()

        email = userinfo["email"]
        name = userinfo.get("name", email.split("@")[0])

        save_user_token(email, creds)

        # 🔹 Create or load Google Sheet
        sheet_id = load_user_sheet(email)
        if not sheet_id:
            sheets_svc = build("sheets", "v4", credentials=creds)
            sheet = sheets_svc.spreadsheets().create(
                body={"properties": {"title": f"Job Tracker - {email}"}},
                fields="spreadsheetId",
            ).execute()
            sheet_id = sheet["spreadsheetId"]
            save_user_sheet(email, sheet_id)
            format_sheet(sheets_svc, sheet_id)

        sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"

        # 🔹 Redirect back to Streamlit
        qs = {
            "auth": "success",
            "email": email,
            "name": name,
            "sheet_url": sheet_url,
        }

        redirect_url = (
            STREAMLIT_URL.rstrip("/")
            + "/?"
            + urllib.parse.urlencode(qs, quote_via=urllib.parse.quote_plus)
        )

        return RedirectResponse(redirect_url)

    except Exception as e:
        LOG.exception("OAuth failed")
        return RedirectResponse(
            STREAMLIT_URL
            + "/?auth=failed&error="
            + urllib.parse.quote_plus(str(e))
        )




# -------------------------
# Scan emails endpoint
# -------------------------
@app.get("/format-sheet")
def format_sheet_endpoint(email: str):
    if email == GUEST_EMAIL:
        return {"status": "skipped", "reason": "guest mode"}
    creds = load_user_token(email)
    sheet_id = load_user_sheet(email)
    if not creds or not sheet_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    svc = build("sheets", "v4", credentials=creds)
    format_sheet(svc, sheet_id)
    apply_status_colors(svc, sheet_id)
    return {"status": "ok", "sheet_id": sheet_id}


@app.get("/scan_emails")
def scan_emails_endpoint(email: str):
    if email == GUEST_EMAIL:
        return {"msg": "guest_mode", "report": {}}

    creds = load_user_token(email)
    sheet_id = load_user_sheet(email)
    if not creds or not sheet_id:
        raise HTTPException(status_code=401, detail="Not authenticated for this user.")
    return utils_scan_emails(creds, spreadsheet_id=sheet_id)

@app.get("/connect-gmail")
def connect_gmail(email: str):
    if email == GUEST_EMAIL:
        return {"status": "success", "guest": True}

    creds = load_user_token(email)
    sheet_id = load_user_sheet(email)

    if creds and sheet_id:
        return {
            "status": "success",
            "sheet_url": f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"
        }

    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent"
    )
    return RedirectResponse(auth_url)

# -------------------------
# Sheet data endpoint (for front-end / dashboard if needed)
# -------------------------
@app.get("/sheet-data")
def sheet_data_endpoint(email: str):
    if email == GUEST_EMAIL:
        return _guest_rows_as_json()

    creds = load_user_token(email)
    sheet_id = load_user_sheet(email)
    if not creds or not sheet_id:
        raise HTTPException(status_code=401, detail="Not authenticated for this user.")

    sheets = build("sheets", "v4", credentials=creds)
    resp = sheets.spreadsheets().values().get(
        spreadsheetId=sheet_id, range="Sheet1!A1:F1000"
    ).execute()
    values = resp.get("values", [])

    if not values or len(values) <= 1:
        return {"rows": []}

    headers = values[0]
    rows = [
        dict(zip(headers, row + [""] * (len(headers) - len(row))))
        for row in values[1:]
    ]
    return {"rows": rows}

# -------------------------
# Helper used by dashboard_summary to load sheet data as DataFrame
# -------------------------
def load_sheet_data():
    creds = load_token_creds()
    sheet_info = load_sheet_id()
    if not creds or not sheet_info or not sheet_info.get("spreadsheet_id"):
        return pd.DataFrame()

    try:
        sheets = build("sheets", "v4", credentials=creds)
        resp = sheets.spreadsheets().values().get(spreadsheetId=sheet_info["spreadsheet_id"], range="Sheet1!A:F").execute()
        values = resp.get("values", [])
        if not values or len(values) == 0:
            return pd.DataFrame()
        headers = values[0]
        data_rows = values[1:]
        norm_rows = [row + [""] * (len(headers) - len(row)) for row in data_rows]
        df = pd.DataFrame(norm_rows, columns=headers)
        return df
    except Exception:
        return pd.DataFrame()

# -------------------------
# Dashboard summary endpoint (with guest support)
# -------------------------
@app.get("/dashboard-summary")
async def dashboard_summary(email: str):
    if email == GUEST_EMAIL:
        df = _guest_df()
    else:
        creds = load_user_token(email)
        sheet_id = load_user_sheet(email)
        if not creds or not sheet_id:
            raise HTTPException(status_code=401, detail="Not authenticated for this user.")

        sheets = build("sheets", "v4", credentials=creds)
        resp = sheets.spreadsheets().values().get(
            spreadsheetId=sheet_id, range="Sheet1!A1:F1000"
        ).execute()
        values = resp.get("values", [])

        if not values or len(values) <= 1:
            df = pd.DataFrame()
        else:
            headers = values[0]
            rows = [row + [""] * (len(headers) - len(row)) for row in values[1:]]
            df = pd.DataFrame(rows, columns=headers)

    today = datetime.today().date()
    applied_today, recent = 0, []
    stats, progress, streak = {}, {"daily": {}, "weekly": {}}, 0

    # normalise date column name (sheet header may be "Date" or "Application Date")
    if not df.empty:
        if "Application Date" in df.columns and "Date" not in df.columns:
            df = df.rename(columns={"Application Date": "Date"})

    if not df.empty and "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        applied_today = int((df["Date"].dt.date == today).sum())
        stats = {
            "applied": len(df),
            "interviews": int((df["Status"].str.contains("Interview|In Progress", case=False, na=False)).sum())
            if "Status" in df.columns else 0,
            "offers": int((df["Status"] == "Offer").sum())
            if "Status" in df.columns else 0,
            "applied_today": applied_today,
        }
        recent = df.tail(3).to_dict(orient="records")

        for i in range(7):
            day = today - timedelta(days=i)
            if "Date" in df.columns:
                progress["daily"][str(day)] = int((df["Date"].dt.date == day).sum())
        for i in range(4):
            start, end = today - timedelta(days=i*7), today - timedelta(days=(i*7+6))
            if "Date" in df.columns:
                progress["weekly"][f"Week-{i+1}"] = int(
                    df[(df["Date"].dt.date <= start) & (df["Date"].dt.date >= end)].shape[0]
                )

        for i in range(7):
            day = today - timedelta(days=i)
            if "Date" in df.columns and int((df["Date"].dt.date == day).sum()) > 0:
                streak += 1
            else:
                break

    resume_feedback = {"score": "7.5/10","strengths": ["Good technical skills"],"improvements": ["Add measurable achievements"]}

    try:
        feed = feedparser.parse(
            requests.get("https://news.google.com/rss/search?q=india+job+market+OR+hiring+OR+recruitment+OR+unemployment+OR+AI&hl=en-IN&gl=IN&ceid=IN:en").text
        )
        insights = [{"headline": e.title, "url": e.link} for e in feed.entries[:5]]
    except Exception:
        insights = [{"headline": "⚠️ Unable to fetch news", "url": ""}]

    gamification = {
        "applied_today": applied_today,
        "jobs_left_today": max(10 - applied_today, 0),
        "streak": streak,
        "message": f"🔥 {streak}-day streak | {applied_today} jobs today, {max(10 - applied_today, 0)} left for goal 10"
    }

    return {
        "stats": stats,
        "recent": recent,
        "progress": progress,
        "resume_feedback": resume_feedback,
        "insights": insights,
        "gamification": gamification,
    }

# ------------------------
# Chatbot
# ------------------------
@app.post("/chatbot")
async def chatbot(message: str = Form(...), thread_id: str = Form(None), resume: UploadFile | None = File(None)):
    response, thread_id, history = chatbot_fn(message, thread_id, resume)
    return {"response": response, "thread_id": thread_id, "history": history}

# ------------------------
# Resume Review
# ------------------------
@app.post("/resume-review")
async def resume_review_endpoint(resume: UploadFile = File(...)):
    return await review_resume(resume)

# ------------------------
# Profile Save (fixed server-side)
# ------------------------
@app.post("/profile")
async def save_profile(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(None),
    linkedin: str = Form(None),
    github: str = Form(None),
    title: str = Form(None),
    skills: str = Form(None),  # comma-separated
    desired_role: str = Form(None),
    preferred_location: str = Form(None),
    resume: UploadFile = File(None),
    resume_docx: UploadFile = File(None),
    template: UploadFile = File(None),
):
    user_id = _get_user_id(request)

    user_upload_dir = UPLOAD_DIR / _safe_email_key(user_id)
    user_upload_dir.mkdir(parents=True, exist_ok=True)

    profile_path = PROFILE_DIR / f"{_safe_email_key(user_id)}.json"
    profile = {
        "user_id": user_id,
        "name": name,
        "email": email,
        "phone": phone,
        "linkedin": linkedin,
        "github": github,
        "title": title,
        "skills": [s.strip() for s in (skills or "").split(",") if s.strip()],
        "desired_role": desired_role,
        "preferred_location": preferred_location,
        "resume_file": None,
        "resume_docx_file": None,
        "cover_letter_template": None,
        "last_updated": datetime.utcnow().isoformat()
    }

    if resume:
        resume_path = user_upload_dir / f"resume_{uuid.uuid4().hex}_{resume.filename}"
        with open(resume_path, "wb") as f:
            shutil.copyfileobj(resume.file, f)
        profile["resume_file"] = str(resume_path)

    if resume_docx:
        docx_path = user_upload_dir / f"resume_docx_{uuid.uuid4().hex}_{resume_docx.filename}"
        with open(docx_path, "wb") as f:
            shutil.copyfileobj(resume_docx.file, f)
        profile["resume_docx_file"] = str(docx_path)

    if template:
        template_path = user_upload_dir / f"template_{uuid.uuid4().hex}_{template.filename}"
        with open(template_path, "wb") as f:
            shutil.copyfileobj(template.file, f)
        profile["cover_letter_template"] = str(template_path)

    with open(profile_path, "w") as f:
        json.dump(profile, f, indent=2)

    return {"status": "success", "profile": profile}

@app.get("/profile")
async def get_profile(request: Request):
    user_id = _get_user_id(request)
    if user_id == GUEST_EMAIL:
        return GUEST_PROFILE

    profile_path = PROFILE_DIR / f"{_safe_email_key(user_id)}.json"
    if not profile_path.exists():
        return {"error": f"No profile found for {user_id}"}
    with open(profile_path, "r") as f:
        profile = json.load(f)
    return profile

# ------------------------
# Cover Letter Generator
# ------------------------
def _save_upload(upload: UploadFile, dest_dir: Path) -> Path:
    dest = dest_dir / f"{uuid.uuid4().hex}_{upload.filename}"
    with dest.open("wb") as f:
        shutil.copyfileobj(upload.file, f)
    try: upload.file.seek(0)
    except: pass
    return dest

@app.post("/generate-cover-letter")
async def generate_cover_letter_endpoint(
    request: Request,
    job_description: str = Form(...),
    tone: str = Form("professional"),
    template: Optional[UploadFile] = File(None),
    resume: Optional[UploadFile] = File(None),
):
    user_id = _get_user_id(request)

    # --------------------
    # ✅ GUEST FLOW
    # --------------------
    if user_id == GUEST_EMAIL:
        if not resume or not template:
            raise HTTPException(
                status_code=400,
                detail="Guest users must upload both resume and template."
            )

        resume_path = str(_save_upload(resume, UPLOAD_DIR))
        template_path = str(_save_upload(template, UPLOAD_DIR))

        out_base = uuid.uuid4().hex
        out_docx = OUTPUT_DIR / f"{out_base}.docx"
        out_pdf = OUTPUT_DIR / f"{out_base}.pdf"

        cover_letter_fn(
            template_path,
            resume_path,
            job_description,
            output_docx=str(out_docx),
            output_pdf=str(out_pdf)
        )

        return {
            "mode": "guest",
            "docx": f"/download/{out_docx.name}",
            "pdf": f"/download/{out_pdf.name}"
        }

    # --------------------
    # ✅ LOGGED-IN USER FLOW (unchanged)
    # --------------------
    profile_path = PROFILE_DIR / f"{_safe_email_key(user_id)}.json"
    if not profile_path.exists():
        raise HTTPException(
            status_code=400,
            detail="Profile not found. Please upload files in Profile page."
        )

    profile = json.load(open(profile_path))

    resume_path = None
    template_path = None

    if resume:
        resume_path = str(_save_upload(resume, UPLOAD_DIR))
    elif profile.get("resume_file"):
        resume_path = profile["resume_file"]

    if template:
        template_path = str(_save_upload(template, UPLOAD_DIR))
    elif profile.get("cover_letter_template"):
        template_path = profile["cover_letter_template"]

    if not resume_path or not template_path:
        raise HTTPException(status_code=400, detail="Missing resume or template.")

    out_base = uuid.uuid4().hex
    out_docx, out_pdf = OUTPUT_DIR / f"{out_base}.docx", OUTPUT_DIR / f"{out_base}.pdf"

    _, pdf_result = cover_letter_fn(
        template_path,
        resume_path,
        job_description,
        output_docx=str(out_docx),
        output_pdf=str(out_pdf)
    )

    return {
        "docx": f"/download/{out_docx.name}",
        "pdf": f"/download/{out_pdf.name}" if pdf_result else None
    }

@app.get("/generate-body")
async def generate_body_endpoint(job_description: str, resume_text: str, tone: str = "professional"):
    return {"body": generate_cover_letter_body(job_description, resume_text, tone=tone)}

@app.get("/download/{filename}")
async def download_file(filename: str):
    safe_path = OUTPUT_DIR / filename
    if not safe_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    media_type = "application/pdf" if filename.lower().endswith(".pdf") else \
                 "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return FileResponse(path=str(safe_path), filename=filename, media_type=media_type)

# ------------------------
# Job Discovery (with guest demo)
# ------------------------
# ------------------------
# Cold Email
# ------------------------
@app.post("/generate-cold-email")
async def generate_cold_email_endpoint(
    request: Request,
    recipient_name: str = Form(""),
    recipient_title: str = Form(""),
    company: str = Form(...),
    role: str = Form(""),
    tone: str = Form("Professional"),
    highlight: str = Form(""),
):
    user_id = _get_user_id(request)
    profile_path = PROFILE_DIR / f"{_safe_email_key(user_id)}.json"
    profile = json.load(open(profile_path)) if profile_path.exists() else {}
    result = _generate_cold_email(recipient_name, recipient_title, company, role, tone, highlight, profile)
    return result


@app.post("/send-cold-email")
async def send_cold_email_endpoint(
    request: Request,
    recipient_email: str = Form(...),
    subject: str = Form(...),
    body: str = Form(...),
):
    user_id = _get_user_id(request)
    if user_id == GUEST_EMAIL:
        raise HTTPException(status_code=403, detail="Guest users cannot send emails.")

    creds = load_user_token(user_id)
    if not creds:
        raise HTTPException(status_code=401, detail="Gmail not connected.")

    try:
        import base64, mimetypes
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from email.mime.base import MIMEBase
        from email import encoders

        msg = MIMEMultipart()
        msg["to"] = recipient_email
        msg["subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        # attach resume from profile if it exists
        profile_path = PROFILE_DIR / f"{_safe_email_key(user_id)}.json"
        if profile_path.exists():
            profile = json.load(open(profile_path))
            resume_file = profile.get("resume_file")
            if resume_file and Path(resume_file).exists():
                mime_type, _ = mimetypes.guess_type(resume_file)
                main_type, sub_type = (mime_type or "application/octet-stream").split("/", 1)
                with open(resume_file, "rb") as f:
                    part = MIMEBase(main_type, sub_type)
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f'attachment; filename="{Path(resume_file).name}"'
                )
                msg.attach(part)

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        gmail = build("gmail", "v1", credentials=creds)
        gmail.users().messages().send(userId="me", body={"raw": raw}).execute()
        return {"status": "sent"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Send failed: {e}")


# ------------------------
# Custom CV
# ------------------------
CV_VERSIONS_DIR = BASE_DIR / "cv_versions"
CV_VERSIONS_DIR.mkdir(exist_ok=True)

@app.post("/cv/extract-keywords")
async def cv_extract_keywords(
    request: Request,
    jd_text: str = Form(...),
):
    user_id = _get_user_id(request)
    profile_path = PROFILE_DIR / f"{_safe_email_key(user_id)}.json"
    profile = json.load(open(profile_path)) if profile_path.exists() else {}
    resume_text = extract_resume_text(profile.get("resume_file", ""))
    keywords = extract_keywords(jd_text, resume_text)
    # flatten all keywords for ATS score
    all_kws = [
        item["keyword"]
        for cat in ["required", "preferred", "responsibilities", "industry_terms"]
        for item in keywords.get(cat, [])
    ]
    ats_before = calculate_ats_score(resume_text, all_kws)
    return {"keywords": keywords, "ats_before": ats_before, "resume_text": resume_text}


@app.post("/cv/tailor")
async def cv_tailor(
    request: Request,
    jd_text: str = Form(...),
    selected_keywords: str = Form(...),   # JSON-encoded list
    approved: str = Form("{}"),           # JSON-encoded approval dict
    company: str = Form(""),
):
    user_id = _get_user_id(request)
    profile_path = PROFILE_DIR / f"{_safe_email_key(user_id)}.json"
    profile = json.load(open(profile_path)) if profile_path.exists() else {}
    resume_text = extract_resume_text(profile.get("resume_file", ""))

    kws = json.loads(selected_keywords)
    approved_dict = json.loads(approved)

    diffs = tailor_cv(resume_text, kws, jd_text)
    if diffs.get("error"):
        raise HTTPException(status_code=500, detail=diffs["error"])

    # ATS score on rewritten text (flatten approved/rewritten content)
    rewritten_text = " ".join([
        approved_dict.get("summary") or (diffs.get("summary") or {}).get("rewritten", ""),
        " ".join(
            approved_dict.get(f"exp_{i}") or b.get("rewritten", "")
            for i, b in enumerate(diffs.get("experience", []))
        ),
        approved_dict.get("skills") or (diffs.get("skills") or {}).get("rewritten", ""),
    ])
    ats_after = calculate_ats_score(rewritten_text, kws)

    # if approved dict provided, also build the DOCX
    download_url = None
    if approved_dict:
        label = company.strip().replace(" ", "_") or "tailored"
        from datetime import date
        filename = f"CV_{label}_{date.today().strftime('%d%b%Y')}.docx"
        out_path = CV_VERSIONS_DIR / filename
        build_cv_docx(diffs, approved_dict, profile, str(out_path))
        download_url = f"/cv/download/{filename}"

    return {"diffs": diffs, "ats_after": ats_after, "download_url": download_url}


@app.get("/cv/download/{filename}")
async def download_cv(filename: str):
    safe_path = CV_VERSIONS_DIR / filename
    if not safe_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        path=str(safe_path),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


@app.post("/discover-jobs")
async def discover_jobs_endpoint(
    request: Request,
    skill: str = Form(...),
    location: str = Form(...),
    experience_level: str = Form(...),
    max_results: int = Form(10),
):
    try:
        user_id = _get_user_id(request)

        if user_id == GUEST_EMAIL:
            demo_jobs = [
                {"title": "Junior Data Analyst - Acme Corp", "company": "Acme Corp", "location": "Remote", "score": 0.85},
                {"title": "Business Analyst - FinEdge", "company": "FinEdge", "location": "Bengaluru", "score": 0.78},
                {"title": "ML Intern - GreenTech", "company": "GreenTech", "location": "Pune", "score": 0.72},
            ]
            return {"jobs": demo_jobs, "error": None}

        profile_path = PROFILE_DIR / f"{_safe_email_key(user_id)}.json"
        if not profile_path.exists():
            return {"jobs": [], "error": "⚠️ No profile found for this user"}

        profile = json.load(open(profile_path))
        resume_file = profile.get("resume_file")

        if not resume_file or not os.path.exists(resume_file):
            return {"jobs": [], "error": "⚠️ Resume not uploaded in profile"}

        resume_obj = SimpleNamespace(name=str(resume_file))
        result = job_discovery(skill, location, experience_level, resume_obj)

        if result.get("error"):
            return {"jobs": [], "error": result["error"]}
        return {"jobs": result["jobs"], "error": None}

    except Exception as e:
        return {"jobs": [], "error": str(e)}
