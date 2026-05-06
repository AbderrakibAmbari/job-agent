import streamlit as st
import sqlite3
import pandas as pd
import json
from datetime import datetime
from nodes.feedback_log import append_feedback
from nodes.tracker import (
    init_db, get_all_applications, get_matched_jobs,
    update_status, delete_application, update_matched_job_cover_letter,
    update_matched_job_company, update_matched_job_applied,
    get_applied_status, get_applied_statuses, save_application,
    get_not_matched_jobs,
)
import os

# ── Init ───────────────────────────────────────────
init_db()
DB_PATH  = "data/applications.db"
RUN_DATE = datetime.now().strftime("%Y-%m-%d")

# Cached DB reads — cleared explicitly before every st.rerun() that follows a write.
# TTL=300 is a safety net only; mutations always clear the cache first.
@st.cache_data(ttl=300)
def load_applications():
    return get_all_applications()

@st.cache_data(ttl=300)
def load_matched_jobs(date_filter: str, new_only: bool = False):
    return get_matched_jobs(date_filter, new_only=new_only)

@st.cache_data(ttl=300)
def load_not_matched_jobs(date_filter: str):
    return get_not_matched_jobs(date_filter)

st.set_page_config(
    page_title="Job Agent",
    page_icon="🤖",
    layout="wide"
)

# ── Load CV ────────────────────────────────────────
try:
    with open("my_cv.txt", "r", encoding="utf-8") as f:
        cv_text = f.read()
except:
    cv_text = ""

# ── Custom CSS ─────────────────────────────────────
st.markdown("""
<style>
    /* Sidebar background */
    [data-testid="stSidebar"] {
        background-color: #0f1117;
        border-right: 1px solid #1e2130;
    }

    /* Hide default radio styling */
    div[role="radiogroup"] label {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 12px 16px;
        margin: 4px 0;
        border-radius: 8px;
        cursor: pointer;
        transition: background 0.2s;
        font-size: 15px;
        font-weight: 500;
        color: #c9d1d9;
        width: 100%;
    }

    div[role="radiogroup"] label:hover {
        background-color: #1e2130;
        color: #ffffff;
    }

    div[role="radiogroup"] label[data-checked="true"] {
        background-color: #1e2130;
        color: #ffffff;
        border-left: 3px solid #4f8ef7;
    }

    div[role="radiogroup"] input {
        display: none;
    }

    /* Stats cards */
    .stat-card {
        background: #1e2130;
        border-radius: 10px;
        padding: 14px 16px;
        margin: 6px 0;
        border: 1px solid #2d3250;
    }
    .stat-label {
        font-size: 12px;
        color: #8b949e;
        margin-bottom: 4px;
    }
    .stat-value {
        font-size: 28px;
        font-weight: 700;
        color: #ffffff;
    }

    /* Region badge */
    .badge {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 600;
        margin: 2px;
    }
    .badge-nrw    { background: #1a3a5c; color: #58a6ff; }
    .badge-hessen { background: #1a3a2c; color: #3fb950; }
    .badge-saar   { background: #3a1a3a; color: #bc8cff; }
    .badge-rlp    { background: #3a2a1a; color: #f0883e; }
    .badge-other  { background: #2d2d2d; color: #8b949e; }

    /* Score bar */
    .score-bar-bg {
        background: #2d3250;
        border-radius: 4px;
        height: 6px;
        margin: 6px 0 12px 0;
    }
    .score-bar-fill {
        height: 6px;
        border-radius: 4px;
        background: linear-gradient(90deg, #4f8ef7, #3fb950);
    }

    /* Applied button */
    .applied-btn {
        background: #1a3a2c;
        color: #3fb950;
        border: 1px solid #3fb950;
        border-radius: 6px;
        padding: 6px 14px;
        font-size: 13px;
        cursor: pointer;
    }
    .not-applied-btn {
        background: #3a1a1a;
        color: #f85149;
        border: 1px solid #f85149;
        border-radius: 6px;
        padding: 6px 14px;
        font-size: 13px;
        cursor: pointer;
    }

    /* Divider */
    .sidebar-divider {
        border: none;
        border-top: 1px solid #1e2130;
        margin: 12px 0;
    }

    /* Job card link */
    a.apply-link {
        display: block;
        background: #1a3a5c;
        color: #58a6ff !important;
        text-decoration: none;
        padding: 10px 16px;
        border-radius: 8px;
        font-weight: 600;
        font-size: 15px;
        text-align: center;
        margin: 10px 0;
        border: 1px solid #2d4f7c;
    }
    a.apply-link:hover {
        background: #2d4f7c;
    }
</style>
""", unsafe_allow_html=True)

# ── Status config ──────────────────────────────────
STATUS_OPTIONS = [
    "Pending Review", "Sent", "Waiting",
    "Interview", "Rejected", "Offer"
]
STATUS_COLORS = {
    "Pending Review": "⏳",
    "Sent":           "🔵",
    "Waiting":        "🟡",
    "Interview":      "🟢",
    "Rejected":       "🔴",
    "Offer":          "⭐"
}

REGION_BADGE = {
    "nordrhein": ("NRW", "badge-nrw"),
    "westfalen": ("NRW", "badge-nrw"),
    "nrw":       ("NRW", "badge-nrw"),
    "hessen":    ("Hessen", "badge-hessen"),
    "saarland":  ("Saarland", "badge-saar"),
    "rheinland": ("RLP", "badge-rlp"),
    "pfalz":     ("RLP", "badge-rlp"),
    "thüringen": ("TH", "badge-other"),
    "niedersachsen": ("NDS", "badge-other"),
    "bremen":    ("HB", "badge-other"),
    "hamburg":   ("HH", "badge-other"),
    "sachsen":   ("SN", "badge-other"),
}

def get_region_badge(location: str) -> str:
    loc_lower = location.lower()
    for key, (label, css) in REGION_BADGE.items():
        if key in loc_lower:
            return f'<span class="badge {css}">{label}</span>'
    return f'<span class="badge badge-other">{location[:15]}</span>'

def classify_job_type(title: str) -> str:
    t = title.lower()
    if "werkstudent" in t or "working student" in t:
        return "Werkstudent"
    if "praktikum" in t or "praktikant" in t or "intern" in t:
        return "Praktikum"
    return "Fulltime"

def get_score_color(score: int) -> str:
    if score >= 85: return "#3fb950"
    if score >= 70: return "#f0883e"
    return "#f85149"

# ══════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════
with st.sidebar:
    st.markdown("""
    <div style="padding: 20px 0 10px 0;">
        <div style="font-size:22px; font-weight:700; color:#fff;">
            🤖 Job Agent
        </div>
        <div style="font-size:12px; color:#8b949e; margin-top:4px;">
            AI-powered job search
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<hr class="sidebar-divider">', unsafe_allow_html=True)

    # Navigation
    apps      = load_applications()
    matched   = load_matched_jobs(RUN_DATE)
    page      = st.radio(
        "nav",
        ["📊  My Applications", "🔍  Today's Matches", "❌  Not Matched"],
        label_visibility="collapsed"
    )

    st.markdown('<hr class="sidebar-divider">', unsafe_allow_html=True)

    # Stats
    st.markdown("""
    <div style="font-size:11px; text-transform:uppercase;
                letter-spacing:1px; color:#8b949e; padding: 0 4px 8px 4px;">
        Quick Stats
    </div>
    """, unsafe_allow_html=True)

    n_fulltime    = sum(1 for j in matched if classify_job_type(j[1]) == "Fulltime")
    n_werkstudent = sum(1 for j in matched if classify_job_type(j[1]) == "Werkstudent")
    n_praktikum   = sum(1 for j in matched if classify_job_type(j[1]) == "Praktikum")

    st.markdown(f"""
    <div class="stat-card">
        <div class="stat-label">Total Applications</div>
        <div class="stat-value">{len(apps)}</div>
    </div>
    <div class="stat-card">
        <div class="stat-label">Today's Matches</div>
        <div class="stat-value">{len(matched)}</div>
    </div>
    <div class="stat-card">
        <div class="stat-label">💼 Fulltime</div>
        <div class="stat-value">{n_fulltime}</div>
    </div>
    <div class="stat-card">
        <div class="stat-label">🎓 Werkstudent</div>
        <div class="stat-value">{n_werkstudent}</div>
    </div>
    <div class="stat-card">
        <div class="stat-label">📚 Praktikum</div>
        <div class="stat-value">{n_praktikum}</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<hr class="sidebar-divider">', unsafe_allow_html=True)

    st.markdown(f"""
    <div style="font-size:12px; color:#8b949e; padding: 4px;">
        📅 {RUN_DATE}
    </div>
    <div style="font-size:11px; color:#444d56; padding: 4px; margin-top:4px;">
        Run <code>python main.py</code><br>to scrape new jobs
    </div>
    """, unsafe_allow_html=True)

# ══════════════════════════════════════════════════
# PAGE 1 — MY APPLICATIONS
# ══════════════════════════════════════════════════
if page == "📊  My Applications":

    st.title("📊 My Applications")
    st.markdown("---")

    col1, col2, col3, col4, col5 = st.columns(5)
    df_apps = pd.DataFrame(apps, columns=[
        "id", "company", "job_title", "platform",
        "date_applied", "status", "cover_letter",
        "job_url", "follow_up_date"
    ]) if apps else pd.DataFrame()

    with col1: st.metric("📊 Total",     len(df_apps))
    with col2: st.metric("🔵 Sent",      len(df_apps[df_apps["status"] == "Sent"])      if not df_apps.empty else 0)
    with col3: st.metric("🟡 Waiting",   len(df_apps[df_apps["status"] == "Waiting"])   if not df_apps.empty else 0)
    with col4: st.metric("🟢 Interview", len(df_apps[df_apps["status"] == "Interview"]) if not df_apps.empty else 0)
    with col5: st.metric("⭐ Offer",     len(df_apps[df_apps["status"] == "Offer"])     if not df_apps.empty else 0)

    st.markdown("---")

    if df_apps.empty:
        st.info("📭 No applications yet. Run `python main.py` to start!")
    else:
        col_f1, col_f2 = st.columns([1, 3])
        with col_f1:
            filter_status = st.selectbox("Filter by status", ["All"] + STATUS_OPTIONS)
        with col_f2:
            search = st.text_input("🔍 Search company or role", "")

        filtered = df_apps.copy()
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

        for _, row in filtered.iterrows():
            icon = STATUS_COLORS.get(row["status"], "⚪")
            with st.expander(
                f"{icon} {row['company']} — {row['job_title']} | 📅 {row['date_applied']}"
            ):
                col_info, col_actions = st.columns([2, 1])
                with col_info:
                    st.markdown(f"**🏢 Company:** {row['company']}")
                    st.markdown(f"**💼 Role:** {row['job_title']}")
                    st.markdown(f"**🌐 Platform:** {row['platform']}")
                    st.markdown(f"**📅 Applied:** {row['date_applied']}")
                    st.markdown(f"**📌 Status:** {icon} {row['status']}")
                    if row["job_url"]:
                        st.markdown(f"**🔗 Link:** [Open job posting]({row['job_url']})")

                with col_actions:
                    new_status = st.selectbox(
                        "Update status", STATUS_OPTIONS,
                        index=STATUS_OPTIONS.index(row["status"])
                              if row["status"] in STATUS_OPTIONS else 0,
                        key=f"status_{row['id']}"
                    )
                    if st.button("💾 Save", key=f"save_{row['id']}"):
                        update_status(row["id"], new_status)
                        st.cache_data.clear()
                        st.success(f"Updated to: {new_status}")
                        st.rerun()
                    if st.button("🗑️ Delete", key=f"del_{row['id']}"):
                        delete_application(row["id"])
                        st.cache_data.clear()
                        st.warning("Deleted.")
                        st.rerun()

                if row["cover_letter"]:
                    st.markdown("---")
                    st.markdown("**📝 Cover Letter:**")
                    st.text_area("Cover Letter", value=row["cover_letter"], height=200,
                                 key=f"cl_{row['id']}", label_visibility="collapsed")

# ══════════════════════════════════════════════════
# PAGE 2 — TODAY'S MATCHES
# ══════════════════════════════════════════════════
elif page == "🔍  Today's Matches":

    st.title("🔍 Today's Matched Jobs")
    st.markdown(f"📅 {RUN_DATE}")
    st.markdown("---")

    col_d1, col_d2, _ = st.columns([1, 1, 2])
    with col_d1:
        selected_date = st.date_input("View matches from", value=datetime.now())
    with col_d2:
        new_only = st.checkbox("New jobs only (not seen before)", value=True)
    selected_date_str = selected_date.strftime("%Y-%m-%d")

    matched = load_matched_jobs(selected_date_str, new_only=new_only)

    if not matched:
        st.info(f"📭 No matched jobs for {selected_date_str}. Run `python main.py` to scrape!")
    else:
        # Category filter (job_category is column index 17)
        all_cats = sorted(set((j[17] if len(j) > 17 and j[17] else "Other") for j in matched))
        if len(all_cats) > 1:
            sel_cats = st.multiselect(
                "Filter by category",
                options=all_cats,
                default=all_cats,
                key="cat_filter",
            )
            if sel_cats:
                matched = [j for j in matched if (j[17] if len(j) > 17 and j[17] else "Other") in sel_cats]

        # Fetch all applied flags in one query instead of one per job
        applied_map = get_applied_statuses([j[0] for j in matched])

        # Summary row
        total     = len(matched)
        applied_n = sum(1 for j in matched if applied_map.get(j[0], 0) == 1)
        jobs_by_type = {
            "Fulltime":    [j for j in matched if classify_job_type(j[1]) == "Fulltime"],
            "Werkstudent": [j for j in matched if classify_job_type(j[1]) == "Werkstudent"],
            "Praktikum":   [j for j in matched if classify_job_type(j[1]) == "Praktikum"],
        }

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("📋 Total", total)
        c2.metric("💼 Fulltime",    len(jobs_by_type["Fulltime"]))
        c3.metric("🎓 Werkstudent", len(jobs_by_type["Werkstudent"]))
        c4.metric("📚 Praktikum",   len(jobs_by_type["Praktikum"]))
        c5.metric("✅ Applied", applied_n)

        st.markdown("---")

        tab_ft, tab_ws, tab_pk = st.tabs([
            f"💼 Fulltime ({len(jobs_by_type['Fulltime'])})",
            f"🎓 Werkstudent ({len(jobs_by_type['Werkstudent'])})",
            f"📚 Praktikum ({len(jobs_by_type['Praktikum'])})",
        ])

        def render_jobs(job_list):
            if not job_list:
                st.info("No jobs in this category yet.")
                return
            for job in job_list:
                (job_id, job_title, company, location, platform,
                 job_url, match_score, recommendation, match_reasons,
                 missing, contract_type, work_mode, link_status,
                 cover_letter, date_found, applied, all_urls_raw, *_) = job
                try:
                    platform_links = json.loads(all_urls_raw or "[]")
                except Exception:
                    platform_links = []
                if not platform_links and job_url:
                    platform_links = [{"platform": platform, "url": job_url}]

                score_color   = get_score_color(match_score)
                region_badge  = get_region_badge(location)
                apply_state   = applied_map.get(job_id, 0)
                if apply_state == 1:
                    applied_icon = "✅ Applied"
                elif apply_state == 2:
                    applied_icon = "❌ Not Applying"
                else:
                    applied_icon = "📋 Unreviewed"

                with st.expander(
                    f"{applied_icon} | {match_score}% — {job_title} @ {company} | {location}"
                ):
                    col_left, col_right = st.columns([2, 1])

                    with col_left:
                        st.markdown(f"""
                        <div style="margin-bottom:4px;">
                            <span style="font-size:22px; font-weight:700;
                                         color:{score_color};">{match_score}%</span>
                            <span style="color:#8b949e; font-size:13px;
                                         margin-left:8px;">{recommendation}</span>
                        </div>
                        <div class="score-bar-bg">
                            <div class="score-bar-fill" style="width:{match_score}%;
                                 background: {score_color};"></div>
                        </div>
                        """, unsafe_allow_html=True)

                        st.markdown(
                            f"📍 {region_badge} &nbsp; "
                            f'<span style="color:#8b949e; font-size:13px;">{location}</span>',
                            unsafe_allow_html=True
                        )

                        new_company = st.text_input(
                            "🏢 Company",
                            value=company if company != "Unknown" else "",
                            placeholder="Type company name...",
                            key=f"company_{job_id}"
                        )
                        if new_company and new_company != company:
                            if st.button("💾 Save company", key=f"save_company_{job_id}"):
                                update_matched_job_company(job_id, new_company)
                                st.cache_data.clear()
                                st.success(f"Updated to: {new_company}")
                                st.rerun()
                        st.markdown(f"**💼 Role:** {job_title}")
                        st.markdown(f"**🌐 Work Mode:** {work_mode}")
                        st.markdown(f"**📄 Contract:** {contract_type}")
                        st.markdown(f"**📡 Platform:** {platform}")

                        if link_status == "active":
                            st.success("🔗 Job link is active")
                        elif link_status == "expired":
                            st.error("❌ Job link expired")
                        else:
                            st.warning("⚠️ Manual review needed")

                        if platform_links:
                            for pl in platform_links:
                                pl_name = pl.get("platform", "Apply")
                                pl_url  = pl.get("url", "")
                                if pl_url:
                                    st.markdown(
                                        f'<a href="{pl_url}" target="_blank" class="apply-link">'
                                        f'👉 Apply on {pl_name}</a>',
                                        unsafe_allow_html=True
                                    )

                        if match_reasons:
                            st.markdown("**✅ Why you fit:**")
                            for r in match_reasons.split(" | "):
                                if r.strip():
                                    st.markdown(f"  • {r}")

                        if missing:
                            st.markdown("**⚠️ Gaps:**")
                            for m in missing.split(" | "):
                                if m.strip():
                                    st.markdown(f"  • {m}")

                    with col_right:
                        st.markdown("### 📋 Actions")

                        st.markdown("**Application Status:**")
                        btn_col1, btn_col2 = st.columns(2)

                        with btn_col1:
                            if st.button(
                                "✅ Applied",
                                key=f"applied_{job_id}",
                                type="primary" if apply_state != 1 else "secondary"
                            ):
                                update_matched_job_applied(job_id, 1)
                                save_application(
                                    company=company,
                                    job_title=job_title,
                                    platform=platform,
                                    cover_letter=cover_letter if cover_letter else "",
                                    job_url=job_url if job_url else ""
                                )
                                st.cache_data.clear()
                                st.success("Marked as Applied!")
                                st.rerun()

                        with btn_col2:
                            if st.button(
                                "❌ Not Applying",
                                key=f"notapplied_{job_id}",
                                type="primary" if apply_state != 2 else "secondary"
                            ):
                                update_matched_job_applied(job_id, 2)
                                st.cache_data.clear()
                                st.rerun()

                    st.markdown("---")
                    with st.expander("📋 Log feedback for this job"):
                        fb_c1, fb_c2 = st.columns([1, 2])
                        with fb_c1:
                            fb_result = st.selectbox(
                                "Outcome",
                                ["applied", "not_interested", "link_broken",
                                 "needs_review", "saved_for_later"],
                                key=f"fb_result_{job_id}"
                            )
                        with fb_c2:
                            fb_action = st.text_input(
                                "Action needed (optional)",
                                key=f"fb_action_{job_id}"
                            )
                        if st.button("Log feedback", key=f"fb_btn_{job_id}"):
                            append_feedback(company, job_title, platform, fb_result, fb_action)
                            st.success("Logged!")

        with tab_ft:
            render_jobs(jobs_by_type["Fulltime"])
        with tab_ws:
            render_jobs(jobs_by_type["Werkstudent"])
        with tab_pk:
            render_jobs(jobs_by_type["Praktikum"])

# ══════════════════════════════════════════════════
# PAGE 3 — NOT MATCHED
# ══════════════════════════════════════════════════
elif page == "❌  Not Matched":

    st.title("❌ Not Matched Jobs")
    st.markdown("Jobs the AI scored but fell below the match threshold. Review these — some may still be worth applying to.")
    st.markdown("---")

    col_d1, _ = st.columns([1, 3])
    with col_d1:
        nm_date = st.date_input("View from date", value=datetime.now(), key="nm_date")
    nm_date_str = nm_date.strftime("%Y-%m-%d")

    not_matched = load_not_matched_jobs(nm_date_str)

    if not not_matched:
        st.info(f"📭 No not-matched jobs for {nm_date_str}. Run a scrape first.")
    else:
        st.markdown(f"**{len(not_matched)} jobs below threshold on {nm_date_str}**")
        st.markdown("---")

        for row in not_matched:
            (nm_id, nm_title, nm_company, nm_location, nm_platform,
             nm_url, nm_score, nm_recommendation, nm_reasons,
             nm_missing, nm_contract, nm_work_mode, nm_date_found) = row

            score_color  = get_score_color(nm_score)
            region_badge = get_region_badge(nm_location)

            with st.expander(
                f"{nm_score}% [{nm_recommendation}] — {nm_title} @ {nm_company} | {nm_location}"
            ):
                col_left, col_right = st.columns([3, 1])

                with col_left:
                    st.markdown(f"""
                    <div style="margin-bottom:4px;">
                        <span style="font-size:22px; font-weight:700;
                                     color:{score_color};">{nm_score}%</span>
                        <span style="color:#8b949e; font-size:13px;
                                     margin-left:8px;">{nm_recommendation}</span>
                    </div>
                    <div class="score-bar-bg">
                        <div class="score-bar-fill" style="width:{nm_score}%;
                             background:{score_color};"></div>
                    </div>
                    """, unsafe_allow_html=True)

                    st.markdown(
                        f"📍 {region_badge} &nbsp; "
                        f'<span style="color:#8b949e; font-size:13px;">{nm_location}</span>',
                        unsafe_allow_html=True
                    )
                    st.markdown(f"**💼 Role:** {nm_title}")
                    st.markdown(f"**🏢 Company:** {nm_company}")
                    st.markdown(f"**🌐 Work Mode:** {nm_work_mode}  |  **📄 Contract:** {nm_contract}")
                    st.markdown(f"**📡 Platform:** {nm_platform}")

                    if nm_reasons:
                        st.markdown("**✅ Partial match:**")
                        for r in nm_reasons.split(" | "):
                            if r.strip():
                                st.markdown(f"  • {r}")

                    if nm_missing:
                        st.markdown("**⚠️ Why it didn't match:**")
                        for m in nm_missing.split(" | "):
                            if m.strip():
                                st.markdown(f"  • {m}")

                with col_right:
                    if nm_url:
                        st.markdown(
                            f'<a href="{nm_url}" target="_blank" class="apply-link">'
                            f'👉 View on {nm_platform}</a>',
                            unsafe_allow_html=True
                        )

st.markdown("---")
st.caption("🤖 Job Agent — powered by Claude AI & LangGraph")