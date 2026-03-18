import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

DB_PATH = "data/applications.db"

# ── Page Config ────────────────────────────────────
st.set_page_config(
    page_title="Job Application Tracker",
    page_icon="🤖",
    layout="wide"
)

# ── Helper Functions ───────────────────────────────
def get_all_applications():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT * FROM applications ORDER BY date_applied DESC",
        conn
    )
    conn.close()
    return df

def update_status(app_id, new_status):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE applications SET status = ? WHERE id = ?",
        (new_status, app_id)
    )
    conn.commit()
    conn.close()

def delete_application(app_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM applications WHERE id = ?", (app_id,))
    conn.commit()
    conn.close()

# ── Status Colors ──────────────────────────────────
STATUS_COLORS = {
    "Pending Review": "⏳",
    "Sent":           "🔵",
    "Waiting":        "🟡",
    "Interview":      "🟢",
    "Rejected":       "🔴",
    "Offer":          "⭐"
}

STATUS_OPTIONS = ["Pending Review", "Sent", "Waiting", "Interview", "Rejected", "Offer"]

# ── Header ─────────────────────────────────────────
st.title("🤖 Job Application Tracker")
st.markdown("---")

# ── Load Data ──────────────────────────────────────
df = get_all_applications()

if df.empty:
    st.info("📭 No applications yet. Run `python main.py` to start applying!")
    st.stop()

# ── Stats Row ──────────────────────────────────────
col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.metric("📊 Total", len(df))
with col2:
    st.metric("🔵 Sent", len(df[df["status"] == "Sent"]))
with col3:
    st.metric("🟡 Waiting", len(df[df["status"] == "Waiting"]))
with col4:
    st.metric("🟢 Interview", len(df[df["status"] == "Interview"]))
with col5:
    st.metric("⭐ Offer", len(df[df["status"] == "Offer"]))

st.markdown("---")

# ── Filters ────────────────────────────────────────
col_f1, col_f2 = st.columns([1, 3])

with col_f1:
    filter_status = st.selectbox(
        "Filter by status",
        ["All"] + STATUS_OPTIONS
    )

with col_f2:
    search = st.text_input("🔍 Search company or role", "")

# Apply filters
filtered = df.copy()
if filter_status != "All":
    filtered = filtered[filtered["status"] == filter_status]
if search:
    mask = (
        filtered["company"].str.contains(search, case=False, na=False) |
        filtered["job_title"].str.contains(search, case=False, na=False)
    )
    filtered = filtered[mask]

st.markdown(f"**Showing {len(filtered)} application(s)**")
st.markdown("---")

# ── Application Cards ──────────────────────────────
for _, row in filtered.iterrows():
    status_icon = STATUS_COLORS.get(row["status"], "⚪")

    with st.expander(
        f"{status_icon} {row['company']} — {row['job_title']} | 📍 | 📅 {row['date_applied']}"
    ):
        col_info, col_actions = st.columns([2, 1])

        with col_info:
            st.markdown(f"**🏢 Company:** {row['company']}")
            st.markdown(f"**💼 Role:** {row['job_title']}")
            st.markdown(f"**🌐 Platform:** {row['platform']}")
            st.markdown(f"**📅 Applied:** {row['date_applied']}")
            st.markdown(f"**📌 Status:** {status_icon} {row['status']}")

            if row["job_url"]:
                st.markdown(f"**🔗 Link:** [Open job posting]({row['job_url']})")

        with col_actions:
            # Update status
            new_status = st.selectbox(
                "Update status",
                STATUS_OPTIONS,
                index=STATUS_OPTIONS.index(row["status"]) 
                      if row["status"] in STATUS_OPTIONS else 0,
                key=f"status_{row['id']}"
            )

            if st.button("💾 Save status", key=f"save_{row['id']}"):
                update_status(row["id"], new_status)
                st.success(f"Updated to: {new_status}")
                st.rerun()

            if st.button("🗑️ Delete", key=f"delete_{row['id']}"):
                delete_application(row["id"])
                st.warning("Application deleted.")
                st.rerun()

        # Cover letter
        if row["cover_letter"]:
            st.markdown("---")
            st.markdown("**📝 Cover Letter:**")
            st.text_area(
                "Cover Letter",
                value=row["cover_letter"],
                height=200,
                key=f"cl_{row['id']}",
                label_visibility="collapsed"
            )

# ── Footer ─────────────────────────────────────────
st.markdown("---")
st.markdown(
    "💡 Run `python main.py` in your terminal to scrape new jobs and add applications."
)