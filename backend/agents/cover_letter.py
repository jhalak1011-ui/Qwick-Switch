import anthropic
import os
import PyPDF2
from docx import Document
from docx2pdf import convert
from dotenv import load_dotenv

load_dotenv("openaiapikey.env")
_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def extract_text_from_pdf(pdf_path):
    """Extracts raw text from a PDF resume."""
    text = ""
    with open(pdf_path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            text += page.extract_text() + "\n"
    return text.strip()


def generate_cover_letter_body(job_description, resume_text, tone="professional"):
    """Generates a tailored cover letter body only (no header)."""

    system_prompt = f"""
    You are an expert career coach and cover letter writer.
    Write only the body of a cover letter.
    Tone: {tone}.
    Constraints:
    - Use ONLY information from the resume provided. Do NOT invent skills or jobs.
    - Tailor it to the job description.
    - Mention the company naturally in the letter.
    - Do not include greeting, closing signature, or formatting outside plain text.
    """

    response = _client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=system_prompt,
        messages=[
            {"role": "user", "content": f"Resume:\n{resume_text}\n\nJob Description:\n{job_description}"}
        ]
    )
    return response.content[0].text.strip()


def cover_letter_fn(template_path, resume_pdf, job_description, output_docx="cover_letter.docx", output_pdf="cover_letter.pdf"):
    """Replaces placeholder in a DOCX template with the generated cover letter body."""
    resume_text = extract_text_from_pdf(resume_pdf)

    cover_letter_text = generate_cover_letter_body(job_description, resume_text, tone="startup-casual")

    doc = Document(template_path)

    for p in doc.paragraphs:
        if "[COVER_LETTER_BODY]" in p.text:
            p.text = p.text.replace("[COVER_LETTER_BODY]", cover_letter_text)

    doc.save(output_docx)
    try:
        convert(output_docx, output_pdf)
    except Exception:
        output_pdf = None

    return output_docx, output_pdf
