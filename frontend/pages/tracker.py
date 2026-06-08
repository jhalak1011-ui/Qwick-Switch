import streamlit as st
import requests
import pandas as pd
from frontend.helpers import load_sheet_data, API_BASE
from html import escape

def show():
    st.markdown("## 📊 Application Tracker")
    st.write("Your Gmail applications are automatically synced after login 🚀")
    col1, col2 ,col3= st.columns([2, 1, 1])

    # ✅ Load sheet data
    sheet_df = load_sheet_data(st.session_state.email)

    if sheet_df.empty:
        st.info("⚠️ No applications found yet. Try refreshing below 👇")
        st.write("DEBUG: No rows returned from /sheet-data API")
    else:
        # ✅ Standardize columns
        expected_cols = ["Company", "Role", "Date", "Method", "Status", "Gmail ID"]
        for col in expected_cols:
            if col not in sheet_df.columns:
                sheet_df[col] = ""
        #left, right = st.columns([1,1])
        # ----------------------
        # 🔍 Filters
        # ----------------------
        with col1:
            # ✅ Show Google Sheet link if available
            if st.session_state.get("sheet_url"):
                st.markdown(f"📄 **Google Sheet:** [Open here]({st.session_state.sheet_url})")

        with col2:
            with st.expander("🔍 Filters", expanded=False):
                company_filter = st.multiselect("Filter by Company", options=sheet_df["Company"].unique())
                role_filter = st.multiselect("Filter by Role", options=sheet_df["Role"].unique())
                status_filter = st.multiselect("Filter by Status", options=sheet_df["Status"].unique())
                method_filter = st.multiselect("Filter by Method", options=sheet_df["Method"].unique())
    
            # Apply filters
            df = sheet_df.copy()
            if company_filter:
                df = df[df["Company"].isin(company_filter)]
            if role_filter:
                df = df[df["Role"].isin(role_filter)]
            if status_filter:
                df = df[df["Status"].isin(status_filter)]
            if method_filter:
                df = df[df["Method"].isin(method_filter)]

        # ----------------------
        # ↕️ Sort Options
        # ----------------------
        with col3: 
            with st.expander("↕️ Sort Options", expanded=False):
                sort_col = st.selectbox("Sort by", options=df.columns, index=list(df.columns).index("Date") if "Date" in df.columns else 0)
                sort_order = st.radio("Order", ["Ascending", "Descending"], horizontal=True)
            
            # Special handling if sorting by Date
            if sort_col == "Date":
                df["Date"] = pd.to_datetime(df["Date"], format="%d-%b-%Y", errors="coerce")
                df = df.sort_values(by="Date", ascending=(sort_order == "Ascending"))
            else:
                df = df.sort_values(by=sort_col, ascending=(sort_order == "Ascending"))


        # ✅ Show applications
        st.markdown("### Recent Applications")
        for _, row in df.tail(1000).iterrows():  # show last 100 (after filter + sort)
            company = escape(str(row["Company"]))
            role = escape(str(row["Role"]))
            date = escape(str(row["Date"]))
            method = escape(str(row["Method"]))
            status = escape(str(row["Status"]))
            gmail_id = escape(str(row["Gmail ID"]))

            emoji = "📄"
            if "Interview" in status:
                emoji = "🎤"
            elif "Offer" in status:
                emoji = "🏆"
            elif "Reject" in status:
                emoji = "❌"

            st.markdown(f"""
            <div style='border:1px solid #ddd; padding:12px; border-radius:10px; margin-bottom:10px; background:#fafafa;'>
                <div style='display:flex; justify-content:space-between;'>
                    <div>
                        <b>{emoji} {role}</b> @ {company}  
                        <div style='font-size:15px; color:#666;'>Applied on {date} via {method}</div>
                    </div>
                    <div style='font-weight:600; color:#4f46e5;'>{status}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

    # ✅ Refresh button
    if st.button("🔄 Refresh Applications"):
        with st.spinner("Fetching latest emails..."):
            try:
                response = requests.get(
                    f"{API_BASE}/scan_emails",
                    params={"email": st.session_state.email},
                    timeout=120
                )
                if response.status_code == 200:
                    st.success("✅ Gmail synced successfully! Refreshing data...")
                else:
                    st.error(f"❌ Sync failed: {response.text}")
            except Exception as e:
                st.error(f"❌ Sync failed: {e}")
        st.rerun()
