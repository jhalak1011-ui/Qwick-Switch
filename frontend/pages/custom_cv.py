import streamlit as st
import requests
import json
from frontend.helpers import API_BASE


# ── helpers ────────────────────────────────────────────────────────────────────

def _ats_badge(score: int):
    if score >= 70:
        color, label = "#22c55e", "Strong"
    elif score >= 45:
        color, label = "#f59e0b", "Moderate"
    else:
        color, label = "#ef4444", "Weak"
    st.markdown(
        f"<span style='background:{color};color:white;padding:4px 12px;"
        f"border-radius:20px;font-weight:700;font-size:15px'>"
        f"ATS Match: {score}% — {label}</span>",
        unsafe_allow_html=True,
    )


def _reset():
    for k in ["cv_step", "cv_jd", "cv_resume_text", "cv_keywords",
              "cv_ats_before", "cv_selected", "cv_diffs",
              "cv_ats_after", "cv_approved", "cv_download_url", "cv_company"]:
        st.session_state.pop(k, None)


# ── main ───────────────────────────────────────────────────────────────────────

def show():
    st.markdown("## 📄 Custom CV Builder")
    email = st.session_state.get("email", "")
    step  = st.session_state.get("cv_step", 1)

    # progress bar
    st.markdown(
        f"""
        <div style='display:flex;gap:8px;margin-bottom:20px'>
          {''.join(
            f"<div style='flex:1;height:6px;border-radius:3px;"
            f"background:{'#7b2ff7' if i<=step else '#e5e7eb'}'></div>"
            for i in range(1, 5)
          )}
        </div>
        <p style='color:#888;font-size:13px;margin-top:-14px'>
          Step {step} of 4 —
          {['Paste Job Description','Review Keywords','Approve Changes','Download'][step-1]}
        </p>
        """,
        unsafe_allow_html=True,
    )

    # ── STEP 1: JD input ───────────────────────────────────────────────────────
    if step == 1:
        # check if DOCX CV is uploaded
        try:
            profile_resp = requests.get(
                f"{API_BASE}/profile", params={"email": email}, timeout=10
            )
            has_docx = bool(
                profile_resp.status_code == 200 and
                profile_resp.json().get("resume_docx_file")
            )
        except Exception:
            has_docx = False

        if not has_docx:
            st.warning(
                "⚠️ No DOCX CV found in your profile. Upload a `.docx` version of your CV "
                "in **My Profile** so the tailored output preserves your original formatting. "
                "Without it, a plain DOCX will be generated instead."
            )

        company = st.text_input("Company name", placeholder="Google", key="cv_company_input")
        jd = st.text_area("Paste the Job Description *", height=300,
                          placeholder="Paste the full JD here...")

        if st.button("Extract Keywords →", type="primary", use_container_width=True):
            if not jd.strip():
                st.error("Please paste the job description.")
            else:
                with st.spinner("Extracting keywords from JD..."):
                    try:
                        resp = requests.post(
                            f"{API_BASE}/cv/extract-keywords",
                            params={"email": email},
                            data={"jd_text": jd},
                            timeout=40,
                        )
                        if resp.status_code != 200:
                            st.error(f"Error: {resp.text}")
                        else:
                            data = resp.json()
                            st.session_state["cv_jd"]          = jd
                            st.session_state["cv_company"]     = company
                            st.session_state["cv_keywords"]    = data["keywords"]
                            st.session_state["cv_ats_before"]  = data["ats_before"]
                            st.session_state["cv_resume_text"] = data["resume_text"]
                            st.session_state["cv_step"]        = 2
                            st.rerun()
                    except Exception as e:
                        st.error(f"Could not connect to API: {e}")

    # ── STEP 2: Keyword review ─────────────────────────────────────────────────
    elif step == 2:
        keywords   = st.session_state["cv_keywords"]
        ats_before = st.session_state["cv_ats_before"]

        st.markdown("### Current ATS Score")
        _ats_badge(ats_before)
        st.caption("Select only keywords that genuinely reflect your experience.")
        st.markdown("---")

        CATEGORY_META = {
            "required":         ("🔴 Required Skills",     "Must-have qualifications"),
            "preferred":        ("🟡 Preferred Skills",    "Nice-to-have"),
            "responsibilities": ("🔵 Key Responsibilities","Core tasks in the role"),
            "industry_terms":   ("🟣 Industry Terms",      "Domain tools and terminology"),
        }

        selected = {}
        for cat, (title, subtitle) in CATEGORY_META.items():
            items = keywords.get(cat, [])
            if not items:
                continue
            st.markdown(f"**{title}** — *{subtitle}*")
            for item in items:
                kw   = item["keyword"]
                freq = item.get("frequency", 1)
                already = item.get("in_resume", False)
                badge = (
                    "<span style='background:#dcfce7;color:#166534;font-size:11px;"
                    "padding:1px 7px;border-radius:10px;margin-left:6px'>✓ in CV</span>"
                    if already else
                    "<span style='background:#fef9c3;color:#854d0e;font-size:11px;"
                    "padding:1px 7px;border-radius:10px;margin-left:6px'>missing</span>"
                )
                label_html = f"{kw} ×{freq}{badge}"
                col1, col2 = st.columns([0.05, 0.95])
                with col1:
                    checked = st.checkbox("", value=already, key=f"kw_{cat}_{kw}",
                                          label_visibility="collapsed")
                with col2:
                    st.markdown(label_html, unsafe_allow_html=True)
                if checked:
                    selected[kw] = True
            st.markdown("")

        col_back, col_next = st.columns([1, 2])
        with col_back:
            if st.button("← Back", use_container_width=True):
                _reset(); st.rerun()
        with col_next:
            if st.button("Tailor My CV →", type="primary", use_container_width=True):
                if not selected:
                    st.error("Select at least one keyword.")
                else:
                    st.session_state["cv_selected"] = list(selected.keys())
                    with st.spinner("Tailoring your CV — this takes ~15 seconds..."):
                        try:
                            resp = requests.post(
                                f"{API_BASE}/cv/tailor",
                                params={"email": email},
                                data={
                                    "jd_text":           st.session_state["cv_jd"],
                                    "selected_keywords": json.dumps(list(selected.keys())),
                                    "approved":          "{}",
                                    "company":           st.session_state.get("cv_company", ""),
                                },
                                timeout=90,
                            )
                            if resp.status_code != 200:
                                st.error(f"Error: {resp.text}")
                            else:
                                data = resp.json()
                                st.session_state["cv_diffs"]    = data["diffs"]
                                st.session_state["cv_ats_after"] = data["ats_after"]
                                st.session_state["cv_step"]     = 3
                                st.rerun()
                        except Exception as e:
                            st.error(f"Could not connect to API: {e}")

    # ── STEP 3: Diff review ────────────────────────────────────────────────────
    elif step == 3:
        diffs     = st.session_state["cv_diffs"]
        ats_before = st.session_state["cv_ats_before"]
        ats_after  = st.session_state["cv_ats_after"]

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**Before tailoring**")
            _ats_badge(ats_before)
        with col_b:
            st.markdown("**After tailoring**")
            _ats_badge(ats_after)

        st.markdown("---")
        st.markdown("### Review Changes")
        st.caption("Edit any field below. Approve each change — only what you confirm goes into the final CV.")

        approved = {}

        # Summary
        summary = diffs.get("summary", {})
        if summary:
            st.markdown("#### Professional Summary")
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Original**")
                st.text_area("", value=summary.get("original", ""), height=120,
                             key="orig_summary", disabled=True, label_visibility="collapsed")
            with col2:
                st.markdown("**Rewritten**")
                approved["summary"] = st.text_area(
                    "", value=summary.get("rewritten", ""), height=120,
                    key="edit_summary", label_visibility="collapsed"
                )
            st.markdown("")

        # Experience bullets
        exp_bullets = diffs.get("experience", [])
        if exp_bullets:
            st.markdown("#### Experience Bullets")
            for i, bullet in enumerate(exp_bullets):
                orig = bullet.get("original", "")
                rew  = bullet.get("rewritten", "")
                if orig == rew:
                    continue   # skip unchanged bullets
                with st.expander(f"Bullet {i+1}: {orig[:60]}...", expanded=(i < 3)):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown("**Original**")
                        st.text_area("", value=orig, height=100, disabled=True,
                                     key=f"orig_exp_{i}", label_visibility="collapsed")
                    with col2:
                        st.markdown("**Rewritten**")
                        approved[f"exp_{i}"] = st.text_area(
                            "", value=rew, height=100,
                            key=f"edit_exp_{i}", label_visibility="collapsed"
                        )

        # Skills
        skills = diffs.get("skills", {})
        if skills and skills.get("original") != skills.get("rewritten"):
            st.markdown("#### Skills")
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Original**")
                st.text_area("", value=skills.get("original", ""), height=80,
                             key="orig_skills", disabled=True, label_visibility="collapsed")
            with col2:
                st.markdown("**Rewritten**")
                approved["skills"] = st.text_area(
                    "", value=skills.get("rewritten", ""), height=80,
                    key="edit_skills", label_visibility="collapsed"
                )

        st.markdown("---")
        col_back, col_dl = st.columns([1, 2])
        with col_back:
            if st.button("← Back", use_container_width=True):
                st.session_state["cv_step"] = 2; st.rerun()
        with col_dl:
            if st.button("✅ Confirm & Build CV →", type="primary", use_container_width=True):
                st.session_state["cv_approved"] = approved
                with st.spinner("Building your tailored CV..."):
                    try:
                        resp = requests.post(
                            f"{API_BASE}/cv/tailor",
                            params={"email": email},
                            data={
                                "jd_text":           st.session_state["cv_jd"],
                                "selected_keywords": json.dumps(st.session_state["cv_selected"]),
                                "approved":          json.dumps(approved),
                                "company":           st.session_state.get("cv_company", ""),
                            },
                            timeout=90,
                        )
                        data = resp.json()
                        st.session_state["cv_download_url"] = data.get("download_url")
                        st.session_state["cv_step"] = 4
                        st.rerun()
                    except Exception as e:
                        st.error(f"Could not connect to API: {e}")

    # ── STEP 4: Download ───────────────────────────────────────────────────────
    elif step == 4:
        download_url = st.session_state.get("cv_download_url")
        ats_before   = st.session_state.get("cv_ats_before", 0)
        ats_after    = st.session_state.get("cv_ats_after", 0)
        kws_added    = st.session_state.get("cv_diffs", {}).get("keywords_added", [])

        st.success("✅ Your tailored CV is ready!")

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**Before**"); _ats_badge(ats_before)
        with col_b:
            st.markdown("**After**");  _ats_badge(ats_after)

        if kws_added:
            st.markdown(f"**Keywords added:** {', '.join(kws_added)}")

        st.markdown("")

        if download_url:
            file_resp = requests.get(f"{API_BASE}{download_url}", timeout=20)
            if file_resp.status_code == 200:
                filename = download_url.split("/")[-1]
                st.download_button(
                    label="⬇️ Download Tailored CV (.docx)",
                    data=file_resp.content,
                    file_name=filename,
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True,
                )
        else:
            st.warning("Download link unavailable.")

        st.markdown("")
        if st.button("🔄 Start Over", use_container_width=True):
            _reset(); st.rerun()
