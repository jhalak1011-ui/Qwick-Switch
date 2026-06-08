import os
import json
import requests
import fitz
from docx import Document
from typing import Dict, List, Any
from dotenv import load_dotenv
import anthropic
from fastapi import UploadFile
import tempfile, shutil

# === Load API keys from .env ===
load_dotenv("openaiapikey.env")
_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

RAPIDAPI_KEY = "9fe97cb47emshb1f0b54fe226cc3p1ffa2fjsnb1956fa0e501"  # move to env in prod
JSEARCH_URL = "https://jsearch.p.rapidapi.com/search"

# ================= Resume Extraction =================
def extract_text_from_resume(file_path: str) -> str:
    if not file_path or not os.path.exists(file_path):
        return ""
    if file_path.lower().endswith(".docx"):
        doc = Document(file_path)
        return "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
    elif file_path.lower().endswith(".pdf"):
        text = ""
        pdf = fitz.open(file_path)
        for page in pdf:
            text += page.get_text()
        return text.strip()
    else:
        raise ValueError("Unsupported file format. Please upload .docx or .pdf")

# ================= JD Scoring with LLM =================
def _score_with_llm(resume_text: str, jd: str) -> Dict[str, Any]:
    if not jd.strip():
        print("⚠️ JD is empty")
        return {"overall_score": 0, "missing_skills": []}
    if not resume_text.strip():
        print("⚠️ Resume is empty")
        return {"overall_score": 0, "missing_skills": []}

    prompt = f"""
Compare the resume with the job description.
Return ONLY valid JSON in this format:
{{
  "overall_score": <integer 0-100>,
  "missing_skills": ["skill1","skill2"]
}}

Resume (excerpt):
{resume_text[:1500]}

Job Description (excerpt):
{jd[:1500]}
"""

    try:
        resp = _client.messages.create(model="claude-sonnet-4-6", max_tokens=512, messages=[{"role": "user", "content": prompt}])
        content = resp.content[0].text
        print("🔍 LLM RAW RESPONSE:", content)

        # try parsing JSON
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            import re
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                parsed = json.loads(match.group())
            else:
                print("⚠️ No valid JSON found in response")
                return {"overall_score": 0, "missing_skills": []}

        return {
            "overall_score": int(parsed.get("overall_score", 0)),
            "missing_skills": parsed.get("missing_skills", [])
        }

    except Exception as e:
        print("❌ Error in _score_with_llm:", e)
        return {"overall_score": 0, "missing_skills": []}

# ================= JSearch API =================
def _call_jsearch(skill: str, location: str, experience_required: str, max_results: int = 10) -> List[Dict[str, Any]]:
    params = {
        "query": f"{skill} jobs in {location}",
        "page": "1",
        "num_pages": "1",
        "country": "India",
        "date_posted": "all"
    }
    if experience_required:
        params["experience_required"] = experience_required.upper()

    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": "jsearch.p.rapidapi.com"
    }

    r = requests.get(JSEARCH_URL, headers=headers, params=params, timeout=20)
    r.raise_for_status()
    data = r.json().get("data", []) or []
    return data[:max_results]

# ================= Job Discovery =================
from typing import Dict, Any, List
from fastapi import UploadFile
import os

def job_discovery(skill: str, location: str, experience_level: str, resume_file) -> Dict[str, Any]:
    """
    Returns JSON:
    {
      "jobs": [ {title, company, location, link, score, missing_skills, description}, ... ],
      "error": null_or_message
    }
    """
    try:
        if not skill or not location:
            return {"jobs": [], "error": "⚠️ skill and location are required."}

        # Extract resume text
        resume_path = getattr(resume_file, "name", "") or ""
        resume_text = extract_text_from_resume(resume_path)
        print(f"📄 Resume length: {len(resume_text)} chars")

        # Fetch jobs
        try:
            raw_jobs = _call_jsearch(skill, location, experience_level, max_results=10)
        except requests.HTTPError as e:
            return {"jobs": [], "error": f"Job API error: {e}"}
        except Exception as e:
            return {"jobs": [], "error": f"Job API request failed: {e}"}

        if not raw_jobs:
            return {"jobs": [], "error": "No jobs found."}

        out = []
        for job in raw_jobs:
            jd = job.get("job_description") or job.get("snippet") or ""

            # Guarantee a fallback description
            if not jd.strip():
                jd = f"{job.get('job_title', 'Job')} at {job.get('employer_name', 'Company')}"

            # Trim very long descriptions to 500 chars
            jd_preview = jd[:500] + "..." if len(jd) > 500 else jd

            print("🔎 JOB TITLE:", job.get("job_title"))
            print("JD SAMPLE:", jd_preview[:200])

            # Score resume vs JD
            score_data = (
                _score_with_llm(resume_text, jd)
                if resume_text else {"overall_score": 0, "missing_skills": []}
            )
            print("SCORE RESULT:", score_data)

            out.append({
                "title": job.get("job_title") or "N/A",
                "company": job.get("employer_name") or "N/A",
                "location": job.get("job_city") or job.get("job_state") or location,
                "link": job.get("job_apply_link") or job.get("job_google_link") or "#",
                "score": score_data.get("overall_score", 0),
                "missing_skills": score_data.get("missing_skills", []),
                "description": jd_preview  # ✅ always present, trimmed
            })

        # Sort by score desc
        out.sort(key=lambda x: x["score"], reverse=True)
        return {"jobs": out, "error": None}

    except Exception as e:
        return {"jobs": [], "error": f"Unexpected error: {e}"}
