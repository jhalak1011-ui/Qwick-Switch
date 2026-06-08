import streamlit as st
import requests
from frontend.helpers import API_BASE

def show():
    st.title("📝 Cover Letter Generator")

    # -----------------------------
    # Upload files (stored in session)
    # -----------------------------
    st.subheader("📄 Upload Resume")
    resume_file = st.file_uploader(
        "Upload your resume",
        type=["pdf", "docx"],
        key="guest_resume"
    )

    st.subheader("📝 Upload Cover Letter Template")
    template_file = st.file_uploader(
        "Upload cover letter template",
        type=["docx"],
        key="guest_template"
    )

    if resume_file:
        st.session_state.guest_resume_file = resume_file

    if template_file:
        st.session_state.guest_template_file = template_file

    resume = st.session_state.get("guest_resume_file")
    template = st.session_state.get("guest_template_file")

    # -----------------------------
    # Cover letter form
    # -----------------------------
    with st.form("cover_form"):
        if not resume or not template:
            st.warning("⚠️ Upload resume & cover letter template above to continue.")
        else:
            st.success("✅ Resume & template loaded for this session")

        tone = st.selectbox(
            "Tone",
            ["professional", "startup-casual", "enthusiastic", "concise"],
            index=0
        )

        job_description = st.text_area(
            "Job Description (paste the JD here)",
            height=250
        )

        submit = st.form_submit_button("Generate Cover Letter")

    # -----------------------------
    # Submit
    # -----------------------------
    if submit:
        if not resume or not template:
            st.error("⚠️ Please upload resume and template first.")
            return

        if not job_description.strip():
            st.error("⚠️ Paste the job description.")
            return

        with st.spinner("Generating cover letter..."):
            try:
                resp = requests.post(
                    f"{API_BASE}/generate-cover-letter",
                    params={"email": st.session_state.email},
                    data={
                        "job_description": job_description,
                        "tone": tone
                    },
                    files={
                        "resume": (resume.name, resume.getvalue(), resume.type),
                        "template": (template.name, template.getvalue(), template.type)
                    },
                    timeout=120
                )
            except Exception as e:
                st.error(f"❌ Failed to contact API: {e}")
                return

        if resp.status_code != 200:
            st.error(f"API error {resp.status_code}: {resp.text}")
            return

        result = resp.json()
        st.success("🎉 Cover letter generated successfully!")

        if result.get("docx"):
            r = requests.get(API_BASE + result["docx"])
            if r.status_code == 200:
                st.download_button(
                    "⬇️ Download DOCX",
                    data=r.content,
                    file_name="cover_letter.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )

        if result.get("pdf"):
            r2 = requests.get(API_BASE + result["pdf"])
            if r2.status_code == 200:
                st.download_button(
                    "⬇️ Download PDF",
                    data=r2.content,
                    file_name="cover_letter.pdf",
                    mime="application/pdf"
                )
