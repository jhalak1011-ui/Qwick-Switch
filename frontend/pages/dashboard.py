import streamlit as st
import requests
from frontend.helpers import load_sheet_data, API_BASE
from html import escape

def show():
    if st.session_state.name:
        st.markdown(f"## 👋 Hi, {st.session_state.name}")
    elif st.session_state.email:
        st.markdown(f"## 👋 Hi, {st.session_state.email}")
    else:
        st.markdown("## 👋 Hi")

    st.write("Your personalized career cockpit 🚀")

    # Fetch data
    try:
        resp = requests.get(
            f"{API_BASE}/dashboard-summary",
            params={"email": st.session_state.email},
            timeout=30
        )
        data = resp.json() if resp.status_code == 200 else {}
    except Exception as e:
        st.error(f"❌ Could not connect to API: {e}")
        st.stop()

    stats = data.get("stats", {})
    recent = data.get("recent", [])
    progress = data.get("progress", {})
    insights = data.get("insights", [])
    gamification = data.get("gamification", {})

    # =============================
    # Custom CSS for cards & layout
    # =============================
    st.markdown("""
    <style>
        .kpi-card {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 15px;
            text-align: center;
            box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        }
        .kpi-number {
            font-size: 28px;
            font-weight: bold;
            margin-top: 10px;
            color: #4f46e5;
        }
        .kpi-label {
            font-size: 14px;
            color: #666;
        }
        .timeline-item {
            margin-bottom: 10px;
            padding: 10px;
            border-left: 3px solid #4f46e5;
            background: #fafafa;
            border-radius: 5px;
        }
        .insight-card {
            padding: 12px;
            border-radius: 10px;
            background: #ffffff;
            margin-bottom: 8px;
            border: 1px solid #eee;
        }
    </style>
    """, unsafe_allow_html=True)

    # --- KPI CARDS ---
    st.markdown("### 📊 At a Glance")
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(f"<div class='kpi-card'><div class='kpi-number'>{stats.get('applied',0)}</div><div class='kpi-label'>Jobs Applied</div></div>", unsafe_allow_html=True)
    with k2:
        st.markdown(f"<div class='kpi-card'><div class='kpi-number'>{stats.get('interviews',0)}</div><div class='kpi-label'>Interviews</div></div>", unsafe_allow_html=True)
    with k3:
        st.markdown(f"<div class='kpi-card'><div class='kpi-number'>{stats.get('offers',0)}</div><div class='kpi-label'>Offers</div></div>", unsafe_allow_html=True)
    with k4:
        st.markdown(f"<div class='kpi-card'><div class='kpi-number'>{stats.get('applied_today',0)}</div><div class='kpi-label'>Applied Today</div></div>", unsafe_allow_html=True)

    st.markdown("---")

    # --- Recent Activity & Gamification ---
    left, right = st.columns([1,1])

    with left:
        st.markdown("### 📅 Recent Activity")
        if recent:
            for r in recent:
                status = r.get("Status","Unknown")
                role = r.get("Role","N/A")
                company = r.get("Company","N/A")
                date = r.get("Date","N/A")
                st.markdown(f"<div class='timeline-item'><b>{status}</b> → {role} @ {company} ({date})</div>", unsafe_allow_html=True)
        else:
            st.info("No recent activity found.")


    import plotly.graph_objects as go

    with right:
        st.markdown("### 🎮 Today's Progress")
        if gamification:
            applied_today = gamification.get("applied_today", 0)
            daily_goal = 10
            percent = min(applied_today / daily_goal, 1.0) * 100
    
            st.success(gamification.get("message", ""))
            fig = go.Figure(go.Indicator(
                mode="gauge+number",
                value=applied_today,  # use count, not percent
                number={"suffix": "", "font": {"size": 22}},  # show raw number
                gauge={
                    "axis": {"range": [0, daily_goal], "tickfont": {"size": 10}},  # axis matches jobs goal
                    "bar": {"color": "#4f46e5", "thickness": 0.2},
                    "bgcolor": "white",
                    "borderwidth": 1,
                    "bordercolor": "lightgray",
                    "steps": [
                        {"range": [0, daily_goal*0.5], "color": "#f9f9f9"},
                        {"range": [daily_goal*0.5, daily_goal], "color": "#efefff"}
                    ],
                },
                title={"text": f"{applied_today}/{daily_goal} Jobs — {int(min(applied_today/daily_goal,1.0)*100)}%", "font": {"size": 14}}))
            fig.update_layout(
                height=180,
                margin=dict(t=10, b=10, l=10, r=10)
            )

    
            st.plotly_chart(fig, use_container_width=True)
    
        else:
            st.info("No gamification data available.")



    st.markdown("---")

    # --- Progress Charts ---
    st.markdown("### 📈 Progress Tracker")
    if progress:
        tab1, tab2 = st.tabs(["📅 Daily", "📆 Weekly"])
        with tab1:
            st.line_chart(progress.get("daily", {}))
        with tab2:
            st.bar_chart(progress.get("weekly", {}))
    else:
        st.info("No progress data available.")

    st.markdown("---")

    # --- Industry Insights ---
    st.markdown("### 🌍 Industry Insights")
    if insights:
        for item in insights:
            headline, url = item.get("headline",""), item.get("url","")
            st.markdown(f"<div class='insight-card'>🔗 <a href='{url}' target='_blank'>{headline}</a></div>", unsafe_allow_html=True)
    else:
        st.info("No insights available right now.")
