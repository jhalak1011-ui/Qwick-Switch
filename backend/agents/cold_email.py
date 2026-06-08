import anthropic
import os
import re
import json
import PyPDF2
from docx import Document
from dotenv import load_dotenv

load_dotenv("openaiapikey.env")
_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def _extract_resume_text(path: str) -> str:
    if not path or not os.path.exists(path):
        return ""
    try:
        if path.lower().endswith(".pdf"):
            text = ""
            with open(path, "rb") as f:
                for page in PyPDF2.PdfReader(f).pages:
                    text += (page.extract_text() or "") + "\n"
            return text.strip()[:3000]
        if path.lower().endswith(".docx"):
            doc = Document(path)
            return "\n".join(p.text for p in doc.paragraphs).strip()[:3000]
    except Exception:
        pass
    return ""

_SYSTEM = """\
You are an expert at writing cold outreach emails for job seekers.
Write concise, personalized emails that feel human — not templated.

Return ONLY a JSON object with two keys:
- "subject": a short, specific subject line (under 10 words)
- "body": plain text email body (under 180 words)

Rules:
- Open with a specific, genuine hook about the company (not "I came across your company")
- Briefly connect the sender's background to the role/company
- Include the key highlight naturally if provided
- End with a single low-friction CTA (short call, quick chat, reply)
- No buzzwords, no fluff, no "I hope this email finds you well"
- Do NOT invent experience or skills not in the profile
- Return ONLY the raw JSON, no markdown, no code fences\
"""


def generate_cold_email(
    recipient_name: str,
    recipient_title: str,
    company: str,
    role: str,
    tone: str,
    highlight: str,
    profile: dict,
) -> dict:
    name = profile.get("name", "")
    title = profile.get("title", "")
    skills = ", ".join(profile.get("skills", []))
    desired_role = role or profile.get("desired_role", "")
    resume_text = _extract_resume_text(profile.get("resume_file", ""))

    user_msg = f"""\
Write a cold email with these details:

Sender: {name} | {title}
Skills: {skills}
Target role: {desired_role}
Target company: {company}
Recipient: {recipient_name or 'Hiring Manager'} ({recipient_title or 'Recruiter'})
Tone: {tone}
Key highlight: {highlight or 'none'}
"""
    if resume_text:
        user_msg += f"\nResume (use for relevant experience and achievements):\n{resume_text}"

    try:
        resp = _client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            system=_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = resp.content[0].text.strip()
        raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.I).strip()
        parsed = json.loads(raw)
        return {"subject": parsed.get("subject", ""), "body": parsed.get("body", "")}
    except Exception as e:
        return {"subject": "", "body": "", "error": str(e)}
