import streamlit as st
import requests
from frontend.helpers import API_BASE

API = f"{API_BASE}/discover-jobs"

def show():
    st.title("🔎 Job Discovery")

    # --- Inline search inputs ---
    col1, col2, col3, col4 = st.columns([3, 2, 2, 1])

    with col1:
        skills = st.text_input("Skills", placeholder="python, fastapi, ml")

    with col2:
        location = st.text_input("Location", placeholder="Bengaluru / Remote")

    with col3:
        experience_level = st.selectbox(
            "Experience Level",
            ["entry_level", "mid_level", "senior_level"],
            index=1
        )

    search_clicked = col4.button("Search")

    # --- Search Logic ---
    if search_clicked:
        if not skills.strip() or not location.strip() or not experience_level.strip():
            st.error("⚠️ Please enter skills, location, and experience level.")
            st.stop()

        with st.spinner("🔎 Finding best-matched jobs..."):
            data = {
                "skill": skills,
                "location": location,
                "experience_level": experience_level,
            }
            try:
                resp = requests.post(
                    API,
                    params={"email": st.session_state.email},  # remove if backend doesn’t need email
                    data=data,
                    timeout=120,
                )
                resp.raise_for_status()
            except Exception as e:
                st.error(f"❌ Request failed: {e}")
                st.stop()

        payload = resp.json()
        if payload.get("error"):
            st.error(f"❌ Server error: {payload.get('error')}")
        else:
            jobs = payload.get("jobs", [])
            if not jobs:
                st.info("No jobs found.")
            else:
                st.markdown(f"### 🎯 {len(jobs)} jobs found")

                # --- Card CSS (only once) ---
                st.markdown(
                    """
                    <style>
                
                    .apply-btn {
                        display: inline-block;
                        margin-top: 8px;
                        padding: 8px 14px;
                        background-color: #2E86AB;
                        color: white !important;
                        text-decoration: none;
                        border-radius: 8px;
                        font-size: 14px;
                        font-weight: 600;
                    }
                    .apply-btn:hover {
                        background-color: #1b5d7a;
                    }
                    </style>
                    """,
                    unsafe_allow_html=True
                )

                # --- Job cards ---
                for job in jobs:
                    score = job.get("score", 0)
                    description = job.get("description") or "No description available"


                    # Header row
                    cols = st.columns([6, 2])
                    with cols[0]:
                        st.markdown(f"### {job.get('title', 'N/A')}")
                        st.caption(f"{job.get('company', 'N/A')} • {job.get('location', 'N/A')}")
                    with cols[1]:
                        st.markdown(f"**{score}%**")
                        st.caption("match")

                    # Description
                    with st.expander("📄 Job Description"):
                        st.write(description)

                    # Footer
                    st.markdown(
                        f"""
                        <div style="margin-top:8px;color:#333">
                            <b>Missing skills:</b> {', '.join(job.get('missing_skills', [])) or 'None'}
                        </div>
                        <a class="apply-btn" href="{job.get('link', '#')}" target="_blank">Apply Now</a>
                        """,
                        unsafe_allow_html=True
                    )

                    st.markdown("</div>", unsafe_allow_html=True)
