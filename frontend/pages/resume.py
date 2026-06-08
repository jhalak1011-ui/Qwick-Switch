import streamlit as st
import requests
from frontend.helpers import load_sheet_data, API_BASE
from html import escape

def show():
    st.title("📄 Resume Analyzer")

    resume = st.file_uploader("Upload your resume (PDF only)", type=["pdf"])
    if st.button("Review Resume") and resume:
        with st.spinner("Analyzing resume..."):
            files = {"resume": (resume.name, resume, resume.type)}
            response = requests.post(f"{API_BASE}/resume-review", files=files)

        if response.status_code == 200:
            result = response.json()
            st.success("Feedback generated!")
            st.write(result.get("feedback", "No feedback available."))
        else:
            st.error(f"Error {response.status_code}: {response.text}")
