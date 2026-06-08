import streamlit as st
import requests
from frontend.helpers import API_BASE


def show():
    st.markdown("## 📧 Cold Email Outreach")
    st.write("Draft and send a personalized cold email using your profile.")

    email = st.session_state.get("email", "")
    is_guest = st.session_state.get("is_guest", False)

    if is_guest:
        st.warning("Guest mode — cold email sending is disabled. You can still generate a draft.")

    st.markdown("### Recipient Details")
    col1, col2 = st.columns(2)
    with col1:
        recipient_email = st.text_input("Recipient Email *", placeholder="hr@company.com")
        company = st.text_input("Company *", placeholder="Google")
        tone = st.selectbox("Tone", ["Professional", "Friendly", "Concise"])
    with col2:
        recipient_name = st.text_input("Recipient Name", placeholder="Sarah (optional)")
        recipient_title = st.text_input("Recipient Title", placeholder="HR Manager (optional)")
        role = st.text_input("Role You're Targeting", placeholder="Data Analyst (optional)")

    highlight = st.text_input(
        "Key Highlight to Mention",
        placeholder="e.g. I built a similar recommendation engine at my last internship (optional)"
    )

    st.markdown("---")

    if st.button("✨ Generate Draft", use_container_width=True):
        if not company:
            st.error("Company name is required.")
        else:
            with st.spinner("Generating your cold email..."):
                try:
                    resp = requests.post(
                        f"{API_BASE}/generate-cold-email",
                        params={"email": email},
                        data={
                            "recipient_name": recipient_name,
                            "recipient_title": recipient_title,
                            "company": company,
                            "role": role,
                            "tone": tone,
                            "highlight": highlight,
                        },
                        timeout=30,
                    )
                    result = resp.json()
                    if result.get("error"):
                        st.error(f"Generation failed: {result['error']}")
                    else:
                        st.session_state["cold_subject"] = result.get("subject", "")
                        st.session_state["cold_body"] = result.get("body", "")
                except Exception as e:
                    st.error(f"Could not connect to API: {e}")

    # Show editable draft if available
    if st.session_state.get("cold_subject") or st.session_state.get("cold_body"):
        st.markdown("### Review & Edit Draft")

        subject = st.text_input(
            "Subject",
            value=st.session_state.get("cold_subject", ""),
            key="edit_subject"
        )
        body = st.text_area(
            "Email Body",
            value=st.session_state.get("cold_body", ""),
            height=280,
            key="edit_body"
        )

        col_send, col_regen = st.columns([2, 1])
        with col_regen:
            if st.button("🔄 Regenerate", use_container_width=True):
                del st.session_state["cold_subject"]
                del st.session_state["cold_body"]
                st.rerun()

        with col_send:
            send_disabled = is_guest or not recipient_email
            if st.button("📤 Send Email", type="primary", use_container_width=True, disabled=send_disabled):
                if not recipient_email:
                    st.error("Enter the recipient email before sending.")
                else:
                    with st.spinner("Sending..."):
                        try:
                            send_resp = requests.post(
                                f"{API_BASE}/send-cold-email",
                                params={"email": email},
                                data={
                                    "recipient_email": recipient_email,
                                    "subject": subject,
                                    "body": body,
                                },
                                timeout=20,
                            )
                            if send_resp.status_code == 200:
                                st.success(f"✅ Email sent to {recipient_email}!")
                                del st.session_state["cold_subject"]
                                del st.session_state["cold_body"]
                            else:
                                st.error(f"Send failed: {send_resp.json().get('detail', 'Unknown error')}")
                        except Exception as e:
                            st.error(f"Could not connect to API: {e}")

        if is_guest:
            st.info("Sign in with Google to enable sending.")
