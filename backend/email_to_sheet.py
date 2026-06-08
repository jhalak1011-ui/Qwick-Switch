import os
from fastapi import FastAPI, HTTPException
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from datetime import datetime
import base64
import re
import json
from pathlib import Path

# ---------------- CONFIG ----------------
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/spreadsheets"
]

BASE_DIR = Path(__file__).resolve().parent.parent
TOKENS_DIR = BASE_DIR / "tokens"
SHEETS_DIR = BASE_DIR / "sheets"

app = FastAPI()

# ---------------- HELPERS ----------------
def email_key(email: str):
    return email.replace("@", "_at_").replace(".", "_dot_")

def load_creds(email: str):
    token_path = TOKENS_DIR / f"token_{email_key(email)}.json"
    if not token_path.exists():
        return None

    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json())
    return creds

def load_sheet_id(email: str):
    path = SHEETS_DIR / f"sheet_{email_key(email)}.json"
    if not path.exists():
        return None
    return json.load(open(path))["spreadsheet_id"]

# ---------------- CORE LOGIC ----------------
def scan_gmail_and_fill_sheet(creds, spreadsheet_id):
    gmail = build("gmail", "v1", credentials=creds)
    sheets = build("sheets", "v4", credentials=creds)

    query = (
        "subject:(application OR applied OR interview OR shortlisted OR offer)"
    )

    msgs = gmail.users().messages().list(userId="me", q=query, maxResults=20).execute()
    messages = msgs.get("messages", [])

    rows = []

    for msg in messages:
        m = gmail.users().messages().get(userId="me", id=msg["id"], format="metadata").execute()
        headers = {h["name"]: h["value"] for h in m["payload"]["headers"]}

        subject = headers.get("Subject", "")
        sender = headers.get("From", "")
        date = headers.get("Date", "")

        company = sender.split("<")[0].strip()
        role = subject

        rows.append([
            company,
            role,
            datetime.utcnow().strftime("%d-%b-%Y"),
            "Gmail",
            "Applied",
            msg["id"]
        ])

    if not rows:
        return {"added": 0}

    sheets.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range="Sheet1!A:F",
        valueInputOption="USER_ENTERED",
        body={"values": rows}
    ).execute()

    return {"added": len(rows)}

# ---------------- API ----------------
@app.post("/scan-and-fill")
def scan_and_fill(email: str):
    creds = load_creds(email)
    if not creds:
        raise HTTPException(401, "User not authenticated")

    sheet_id = load_sheet_id(email)
    if not sheet_id:
        raise HTTPException(400, "Google Sheet not found")

    result = scan_gmail_and_fill_sheet(creds, sheet_id)
    return {"status": "success", **result}
