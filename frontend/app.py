# app.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import requests
from frontend.helpers import init_session, API_BASE
from streamlit_option_menu import option_menu

# ------------------------
# Config
# ------------------------
st.set_page_config(page_title="QwickSwitch", page_icon="🧭", layout="wide")

st.markdown("""
<style>
[data-testid="stSidebarNav"] { display: none !important; }
</style>
""", unsafe_allow_html=True)

# ------------------------
# Init session
# ------------------------
init_session()


# --- put this near top of app.py, after init_session()  ---
import urllib.parse

# --- OAuth callback detection ---
params = st.query_params  # NEW API (dict-like)

if params.get("auth") == "failed":
    err = params.get("error", "")
    if isinstance(err, list):
        err = err[0] if err else ""
    try:
        decoded = urllib.parse.unquote_plus(err) if err else "Unknown error"
    except Exception:
        decoded = err
    st.error(f"Google sign-in failed: {decoded}")
    st.query_params.clear()
    st.rerun()

elif params.get("auth") == "success" and not st.session_state.get("logged_in"):
    email = params.get("email", "")
    name = params.get("name", email.split("@")[0] if email else "User")
    sheet_url = params.get("sheet_url", "")

    st.session_state.logged_in = True
    st.session_state.email = email
    st.session_state.name = urllib.parse.unquote_plus(name)
    st.session_state.is_guest = False

    if sheet_url:
        st.session_state.sheet_url = urllib.parse.unquote_plus(sheet_url)

    st.query_params.clear()
    st.rerun()



GUEST_EMAIL = "guest@demo.com"
GUEST_NAME = "Guest User"


# ------------------------
# Login Page (Streamlit only + minimal CSS for buttons)
# ------------------------
def render_login_page_streamlit():

    # ------------------ BUTTON COLORS (Purple theme) ------------------
    st.markdown("""
    <style>
    /* Main sign-in button (1st button inside the form) */
    div.stButton > button[kind="primary"] {
        background-color: #7b2ff7 !important;
        color: white !important;
        border-radius: 8px !important;
        padding: 8px 18px !important;
        border: none !important;
        font-weight: 600 !important;
    }

    /* Secondary button (Continue as Guest) */
    div.stButton > button[kind="secondary"] {
        background-color: white !important;
        color: #7b2ff7 !important;
        border: 2px solid #7b2ff7 !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
    }

    /* fallback selector for cases where Streamlit renders both as same kind */
    div.stButton:nth-of-type(1) button {
        background-color: #7b2ff7 !important;
        color: white !important;
        border-radius: 8px !important;
        padding: 8px 18px !important;
        border: none !important;
        font-weight: 600 !important;
    }

    div.stButton:nth-of-type(2) button {
        background-color: white !important;
        color: #7b2ff7 !important;
        border: 2px solid #7b2ff7 !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
    }

    /* center the login card on the right column */
    .css-1v3fvcr {
        padding-top: 18px;
    }
    </style>
    """, unsafe_allow_html=True)
    # ---------------------------------------------------------------

    # Two-column layout
    left_col, right_col = st.columns([1, 1])

    # LEFT SIDE
    with left_col:
        try:
            st.image("assets/logo_3.png", width=350)
        except:
            pass

        st.header("*Automate your job hunt. Faster insights, better matches.*")
        st.write("")
        st.write("- Auto Gmail sync & application tracker")
        st.write("- AI-powered job discovery")
        st.write("- Resume & cover letter helpers")
        st.write("")

    # RIGHT SIDE — Login Card
    with right_col:
        st.subheader("🔑 Welcome")
        st.write("Sign in to continue to QwickSwitch")

        with st.form("login_form_streamlit"):
            email = st.text_input("Email", placeholder="you@example.com")
            pwd = st.text_input("Password", placeholder="Enter your password", type="password")

            col1, col2 = st.columns([1, 1])
            with col1:
                submitted = st.form_submit_button("Sign in")
            with col2:
                guest_btn = st.form_submit_button("Continue as Guest")
                
        login_url = f"{API_BASE}/login"
        st.link_button("Sign in with Google", login_url, use_container_width=True)


    # ------------------------
    # Handle login logic
    # ------------------------
    if submitted:
        if email == "dalmiajhalak@gmail.com" and pwd == "123":
            st.session_state.logged_in = True
            st.session_state.email = email
            st.session_state.name = "Jhalak"
            st.success("✅ Login successful!")
            st.rerun()
        else:
            st.error("❌ Incorrect email or password")

    if guest_btn:
        st.session_state.logged_in = True
        st.session_state.email = GUEST_EMAIL
        st.session_state.name = GUEST_NAME
        st.session_state.is_guest = True
        st.success("✅ Continuing as Guest")
        st.rerun()


# ------------------------
# Simple Login Wrapper
# ------------------------
def simple_login():
    if st.session_state.get("logged_in", False):
        return
    render_login_page_streamlit()
    st.stop()


# ------------------------
# Run Login Flow
# ------------------------
simple_login()

# ------------------------
# Sidebar
# ------------------------
with st.sidebar:
    try:
        st.image("assets/logo_3.png", width=250)
    except:
        pass

    # Inject purple styling for option menu (active + hover + icons)
    st.markdown(
        """
        <style>
        /* Sidebar purple active item and hover */
        div[data-testid="stSidebar"] .nav-link.active {
            background-color: #7b2ff7 !important;
            color: #ffffff !important;
            border-radius: 8px;
            padding-left: 12px;
            padding-right: 12px;
        }
        div[data-testid="stSidebar"] .nav-link.active svg {
            fill: #ffffff !important;
        }
        div[data-testid="stSidebar"] .nav-link:hover {
            background-color: rgba(123,47,247,0.08) !important;
            color: #111827 !important;
            border-radius: 8px;
        }
        /* ensure icons are purple when not active */
        div[data-testid="stSidebar"] .nav-link svg {
            fill: #7b2ff7 !important;
        }
        /* text for non-active items */
        div[data-testid="stSidebar"] .nav-link {
            color: #111827 !important;
            font-weight: 500 !important;
        }
        /* small padding tweak so items look balanced */
        div[data-testid="stSidebar"] .nav-link {
            padding-top: 10px !important;
            padding-bottom: 10px !important;
        }
        /* remove default pink highlight override if exists */
        .css-1d391kg {
            background-color: transparent !important;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    name = st.session_state.get("name", "User")
    email = st.session_state.get("email", "")
    is_guest = st.session_state.get("is_guest", False)

    # Gmail Sync
    if is_guest or email == GUEST_EMAIL:
        st.info("Guest mode — Gmail features disabled.")
    else:
        try:
            resp = requests.get(
                f"{API_BASE}/connect-gmail",
                params={"email": email},
                allow_redirects=False,
                timeout=10
            )
            if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("application/json"):
                data = resp.json()
                if data.get("status") == "success":
                    st.success("✅ Gmail synced automatically")
                    if data.get("sheet_url"):
                        st.session_state.sheet_url = data["sheet_url"]
                else:
                    st.warning("⚠️ Gmail sync response: " + str(data))
            elif resp.status_code in (302, 307):
                auth_url = resp.headers.get("location")
                st.warning("⚠️ Gmail not connected. [Click here to connect Gmail](" + auth_url + ")")
            else:
                st.error(f"❌ Gmail sync failed: {resp.text}")
        except Exception as e:
            st.error(f"⚠️ Auto-sync error: {e}")

    # Sheet link
    if st.session_state.get("sheet_url"):
        st.markdown(f"📄 **Google Sheet:** [Open here]({st.session_state.sheet_url})")
    else:
        st.write("Guest mode: No Google Sheet connected." if is_guest else "No Google Sheet connected.")

    # Navigation
    selected = option_menu(
           menu_title=None,
            options=[
                "Dashboard",
                "Job Discovery",
                "Application Tracker",
                "Career Assistant",
                "Cold Email",
                "Custom CV",
                "Cover Letter Maker",
                "Resume Analyzer",
                "My Profile"
            ],
            icons=[
                "speedometer2", "search", "card-checklist",
                "robot", "envelope-paper", "file-earmark-person",
                "file-earmark-text", "clipboard-data", "person"
            ],
            menu_icon="cast",
            default_index=0,
            orientation="vertical",
            styles={
                "container": {"padding": "0px", "background-color": "transparent"},
                "icon": {"color": "#7b2ff7", "font-size": "20px"},
                "nav-link": {
                    "font-size": "16px",
                    "text-align": "left",
                    "margin": "0px",
                    "padding": "12px 14px",
                    "color": "#111827"
                },
                "nav-link-selected": {
                    "background-color": "#7b2ff7",
                    "color": "white"
                }
            }
        )
    st.markdown("---")
    if st.button("🚪 Logout"):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()


# ------------------------
# Route Main Pages
# ------------------------
from frontend.pages import dashboard, jobs, tracker, chatbot, profile, cover_letter, resume, cold_email, custom_cv

if selected == "Dashboard":
    dashboard.show()
elif selected == "Job Discovery":
    jobs.show()
elif selected == "Application Tracker":
    tracker.show()
elif selected == "Career Assistant":
    chatbot.show()
elif selected == "Cold Email":
    cold_email.show()
elif selected == "Custom CV":
    custom_cv.show()
elif selected == "Cover Letter Maker":
    cover_letter.show()
elif selected == "Resume Analyzer":
    resume.show()
elif selected == "My Profile":
    profile.show()
