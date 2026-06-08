# helpers.py
import os
import streamlit as st
import requests
import pandas as pd
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("jobassist-ui")

# Use environment variable if present; otherwise default to localhost for local dev
API_BASE = os.getenv("API_BASE", "http://localhost:8001")
logger.info(f"Using API_BASE={API_BASE}")

def init_session():
    defaults = {
        "logged_in": False,
        "email": None,
        "name": None,
        "sheet_id": None,
        "sheet_url": None,
        "thread_id": None,
        "is_guest": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

def load_sheet_data(email):
    try:
        resp = requests.get(f"{API_BASE}/sheet-data", params={"email": email}, timeout=20)
        if resp.status_code != 200:
            return pd.DataFrame()
        rows = resp.json().get("rows", [])
        return pd.DataFrame(rows) if rows else pd.DataFrame()
    except Exception as e:
        st.error(f"Error fetching sheet: {e}")
        return pd.DataFrame()
