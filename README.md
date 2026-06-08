# QwickSwitch — AI Career Coach

An AI-powered job hunting assistant built with FastAPI and Streamlit. QwickSwitch automates the repetitive parts of job searching — tracking applications, tailoring CVs, writing cover letters, sending cold emails, and discovering new roles — all from one dashboard.

---

## Features

| Feature | Description |
|---|---|
| **Dashboard** | Live stats on applications, interviews, offers, daily streak, and India job market news |
| **Job Discovery** | AI matches open roles to your resume and desired skills |
| **Application Tracker** | Google Sheets-backed tracker with automatic Gmail scan to detect replies |
| **Career Assistant** | AI chatbot for career advice, interview prep, and resume Q&A |
| **Custom CV** | ATS keyword extraction from any JD, line-by-line diff, download tailored DOCX |
| **Cover Letter Maker** | Generates cover letters in your template format; exports DOCX + PDF |
| **Cold Email** | AI-drafted cold outreach emails sent directly via Gmail |
| **Resume Analyzer** | Scores your resume and gives structured feedback |
| **My Profile** | Central store for your resume, cover letter template, and personal details |

Guest mode is available — no Google account needed to explore the app.

---

## Tech Stack

**Backend**
- [FastAPI](https://fastapi.tiangolo.com/) + Uvicorn
- LangChain + LangGraph + Anthropic Claude
- Google APIs (Gmail, Sheets, Drive, OAuth 2.0)

**Frontend**
- [Streamlit](https://streamlit.io/) + streamlit-option-menu

**File handling**
- python-docx, PyMuPDF, pdf2image, pypandoc

**Deployment**
- Docker (separate containers for API and UI)
- Google Cloud Run via Cloud Build

---

## Project Structure

```
ai_career_coach/
├── backend/
│   ├── main.py              # FastAPI app, all API routes
│   ├── utils.py             # Gmail scan, sheet formatting helpers
│   ├── email_to_sheet.py    # Parses job emails into sheet rows
│   └── agents/
│       ├── chatbot.py
│       ├── cover_letter.py
│       ├── custom_cv.py
│       ├── cold_email.py
│       ├── resume_review.py
│       ├── resume_logic.py
│       ├── job_discovery_tool.py
│       ├── job_search_tool.py
│       └── career_question.py
├── frontend/
│   ├── app.py               # Streamlit entry point, login, sidebar nav
│   ├── helpers.py
│   └── pages/               # One file per page
├── assets/                  # Logo and UI images
├── Dockerfile.api
├── Dockerfile.ui
├── cloudbuild.yaml
└── requirements.txt
```

---

## Local Setup

### Prerequisites
- Python 3.10+
- A Google Cloud project with OAuth credentials (`credentials.json`)
- An Anthropic API key

### 1. Clone the repo

```bash
git clone https://github.com/jhalak1011-ui/Qwick-Switch.git
cd Qwick-Switch
```

### 2. Create a virtual environment

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Mac/Linux
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set up environment variables

Create a `claudeapikey.env` file:
```
ANTHROPIC_API_KEY=your_key_here
```

Create an `openaiapikey.env` file (if using OpenAI features):
```
OPENAI_API_KEY=your_key_here
```

Place your Google OAuth `credentials.json` in the project root.

### 5. Run the backend

```bash
uvicorn backend.main:app --port 8000 --reload
```

### 6. Run the frontend (separate terminal)

```bash
streamlit run frontend/app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

---

## Deployment (Google Cloud Run)

```bash
# Deploy both services
gcloud builds submit --config cloudbuild.yaml
```

Set the following environment variables on your Cloud Run services:
- `ANTHROPIC_API_KEY`
- `REDIRECT_URI` — your backend's `/oauth2callback` URL
- `STREAMLIT_URL` — your frontend's Cloud Run URL
- `FRONTEND_ORIGIN` — same as `STREAMLIT_URL`

---

## Environment Variables Reference

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Claude API key |
| `REDIRECT_URI` | `http://localhost:8001/oauth2callback` | Google OAuth callback URL |
| `STREAMLIT_URL` | `http://localhost:8501/` | Frontend URL |
| `FRONTEND_ORIGIN` | Cloud Run UI URL | Allowed CORS origin |
| `CLIENT_SECRETS_FILE` | `credentials.json` | Google OAuth client secrets path |

---

## Security Notes

- Never commit `credentials.json`, `*.env`, or the `tokens/` directory — all are in `.gitignore`
- User data (CVs, cover letters, profiles, database) is also excluded from version control
- The OAuth flow requires HTTPS in production; `OAUTHLIB_INSECURE_TRANSPORT=1` is set for local dev only
