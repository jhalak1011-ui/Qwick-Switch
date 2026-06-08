import streamlit as st
import requests
from frontend.helpers import load_sheet_data, API_BASE
from html import escape

def show():
    st.markdown("<h1>💬 Career Chatbot</h1>", unsafe_allow_html=True)
    API_URL = f"{API_BASE}/chatbot"


    if "thread_id" not in st.session_state:
        st.session_state.thread_id = None

    # persistent uploader above input
    resume_upload = st.file_uploader("Upload your resume (optional)", type=["pdf", "docx"])

    # Chat input widget
    if prompt := st.chat_input("Ask me anything..."):
        data = {"message": prompt}
        if st.session_state.thread_id:
            data["thread_id"] = st.session_state.thread_id

        files = None
        if resume_upload is not None:
            files = {"resume": (resume_upload.name, resume_upload, resume_upload.type)}

        with st.spinner("AI is thinking..."):
            response = requests.post(API_URL, data=data, files=files)

        if response.status_code == 200:
            res = response.json()
            st.session_state.thread_id = res.get("thread_id")

            # Render chat directly from backend history
            for msg in res.get("history", []):
                with st.chat_message(msg["role"]):
                    st.write(msg["text"])
        else:
            st.error(f"Error {response.status_code}: {response.text}")