import streamlit as st
import requests
from frontend.helpers import API_BASE

def show():
    st.markdown("## 👤 Your Profile")

    # --- Load existing profile (if any) ---
    profile_data = {}
    try:
        resp = requests.get(f"{API_BASE}/profile", params={"email": st.session_state.email}, timeout=20)
        if resp.status_code == 200:
            profile_data = resp.json()
    except Exception as e:
        st.warning(f"Could not load saved profile: {e}")

    with st.form("profile_form"):
        name = st.text_input("Full Name", value=profile_data.get("name", st.session_state.get("name", "")))
        email = st.text_input("Email", value=profile_data.get("email", st.session_state.get("email", "")))
        phone = st.text_input("Phone", value=profile_data.get("phone", ""))
        linkedin = st.text_input("LinkedIn", value=profile_data.get("linkedin", ""))
        github = st.text_input("GitHub", value=profile_data.get("github", ""))
        title = st.text_input("Current Title", value=profile_data.get("title", ""))
        skills = st.text_area("Skills (comma separated)", ", ".join(profile_data.get("skills", [])))
        desired_role = st.text_input("Desired Role", value=profile_data.get("desired_role", ""))
        preferred_location = st.text_input("Preferred Location", value=profile_data.get("preferred_location", ""))

        # --- Resume (PDF) ---
        if profile_data.get("resume_file"):
            st.markdown(f"📄 **Resume (PDF) uploaded:** `{profile_data['resume_file'].split(chr(92))[-1]}`")
        resume = st.file_uploader("Upload Resume — PDF", type=['pdf'])

        # --- Resume (DOCX) for Custom CV tailoring ---
        if profile_data.get("resume_docx_file"):
            st.markdown(f"📝 **Resume (DOCX) uploaded:** `{profile_data['resume_docx_file'].split(chr(92))[-1]}`")
        else:
            st.info("💡 Upload a DOCX version of your CV to enable in-place formatting in Custom CV Builder.")
        resume_docx = st.file_uploader("Upload Resume — DOCX (for Custom CV)", type=['docx'])

        # --- Cover Letter Template ---
        if profile_data.get("cover_letter_template"):
            st.markdown(f"📝 **Template already uploaded:** `{profile_data['cover_letter_template'].split('/')[-1]}`")
        template = st.file_uploader("Upload Cover Letter Template (.docx)", type=['docx'])

        submit = st.form_submit_button("Save Profile")

    if submit:
        files = {}
        if resume:
            files["resume"] = (resume.name, resume, resume.type)
        if resume_docx:
            files["resume_docx"] = (resume_docx.name, resume_docx, resume_docx.type)
        if template:
            files["template"] = (template.name, template, template.type)

        data = {
            "name": name,
            "email": email,
            "phone": phone,
            "linkedin": linkedin,
            "github": github,
            "title": title,
            "skills": skills,
            "desired_role": desired_role,
            "preferred_location": preferred_location,
        }

        try:
            resp = requests.post(
                f"{API_BASE}/profile",
                params={"email": st.session_state.email},
                data=data, files=files, timeout=60
            )
            if resp.status_code == 200:
                st.success("✅ Profile saved successfully!")
                # ✅ Refresh profile immediately
                st.session_state["profile"] = resp.json().get("profile", {})
            else:
                st.error(f"❌ Failed: {resp.text}")
        except Exception as e:
            st.error(f"API error: {e}")
