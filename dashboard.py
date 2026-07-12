import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
from nodes.tracker import (
    init_db, get_all_applications, get_matched_jobs,
    get_applied_status, get_applied_statuses,
    get_not_matched_jobs, get_scrape_dates,
    promote_not_matched_to_matched,
)
from nodes.scrape_log_parser import (
    parse_scrape_log, platform_history, broken_platforms, top_terms_aggregated,
)
import os

from dashboard_pages._shared import (
    _esc,
    _safe_url,
    get_region_badge,
    get_score_color,
    render_date_chips,
)
from dashboard_pages.myapps import _render_myapps_page
from dashboard_pages.matches_v2 import _render_matches_v2


# ── Init ───────────────────────────────────────────
init_db()
DB_PATH  = "data/applications.db"
RUN_DATE = datetime.now().strftime("%Y-%m-%d")

# Plan 022: V2 two-pane layout — session-state init lives here so both the
# router and _render_matches_v2 can read the key unconditionally.
if "v2_selected_job_id" not in st.session_state:
    st.session_state["v2_selected_job_id"] = None

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

@st.cache_data(ttl=60)
def load_scrape_runs():
    """Read the scrape log fresh at most once a minute."""
    return parse_scrape_log()

@st.cache_data(ttl=300)
def load_due_followups():
    return get_due_followups()

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

    /* Region badge — 4 macro-region colors for all 16 Bundesländer */
    .badge {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 600;
        margin: 2px;
    }
    .badge-west   { background: #1a3a5c; color: #58a6ff; }  /* NRW, Hessen, RLP, Saar */
    .badge-north  { background: #143a3a; color: #56d4d4; }  /* HH, HB, NDS, SH */
    .badge-east   { background: #2a1a4a; color: #a78bfa; }  /* BE, BB, MV, SN, ST, TH */
    .badge-south  { background: #1a3a2c; color: #3fb950; }  /* BY, BW */
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

    /* Active scrape-day chip (primary button override) */
    .stButton > button[kind="primary"] {
        background-color: #1a3a2c !important;
        color: #3fb950 !important;
        border: 1px solid #3fb950 !important;
    }
    .stButton > button[kind="primary"]:hover {
        background-color: #25513c !important;
        color: #ffffff !important;
    }
</style>
""", unsafe_allow_html=True)


# ── Status config ──────────────────────────────────
# STATUS_OPTIONS moved to dashboard_pages/myapps.py (Plan 027 Step 4).
# STATUS_COLORS below is currently unused; kept in place for a future cleanup.
STATUS_COLORS = {
    "Pending Review": "⏳",
    "Sent":           "🔵",
    "Waiting":        "🟡",
    "Interview":      "🟢",
    "Rejected":       "🔴",
    "Offer":          "⭐"
}


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
        [
            "📊  My Applications",
            "🔍  Today's Matches",
            "❌  Not Matched",
            "📈  Scrape Health",
        ],
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

    st.markdown(f"""
    <div class="stat-card">
        <div class="stat-label">Total Applications</div>
        <div class="stat-value">{len(apps)}</div>
    </div>
    <div class="stat-card">
        <div class="stat-label">Today's Matches</div>
        <div class="stat-value">{len(matched)}</div>
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
    _render_myapps_page(apps)

# ══════════════════════════════════════════════════
# PAGE 2 — TODAY'S MATCHES
# ══════════════════════════════════════════════════
elif page == "🔍  Today's Matches":

    st.title("Today's Matched Jobs")
    st.markdown("---")

    selected_date_str = render_date_chips(
        state_key="td_selected_date",
        source="matched",
        label="Pick a scrape day (active day highlighted):",
    )
    new_only = st.checkbox("New jobs only (not seen before)", value=True)

    matched = load_matched_jobs(selected_date_str, new_only=new_only)

    if not matched:
        st.info(f"📭 No matched jobs for {selected_date_str}. Run `python main.py` to scrape!")
    else:
        # Fetch all applied flags in one query instead of one per job
        applied_map = get_applied_statuses([j[0] for j in matched])

        # Summary row
        total       = len(matched)
        applied_n   = sum(1 for j in matched if applied_map.get(j[0], 0) == 1)
        skipped_n   = sum(1 for j in matched if applied_map.get(j[0], 0) == 2)
        unreviewed  = total - applied_n - skipped_n

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total",       total)
        c2.metric("Unreviewed",  unreviewed)
        c3.metric("Applied",     applied_n)
        c4.metric("Skipped",     skipped_n)

        st.markdown("---")

        _render_matches_v2(matched, applied_map, selected_date_str)

# ══════════════════════════════════════════════════
# PAGE 3 — NOT MATCHED
# ══════════════════════════════════════════════════
elif page == "❌  Not Matched":

    st.title("Not Matched Jobs")
    st.caption("Jobs the AI scored but fell below the match threshold. Some may still be worth a look.")
    st.markdown("---")

    nm_date_str = render_date_chips(
        state_key="nm_selected_date",
        source="not_matched",
        label="Pick a scrape day (active day highlighted):",
    )

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
                                     margin-left:8px;">{_esc(nm_recommendation)}</span>
                    </div>
                    <div class="score-bar-bg">
                        <div class="score-bar-fill" style="width:{nm_score}%;
                             background:{score_color};"></div>
                    </div>
                    """, unsafe_allow_html=True)

                    st.markdown(
                        f"{region_badge} &nbsp; "
                        f'<span style="color:#8b949e; font-size:13px;">{_esc(nm_location)}</span>',
                        unsafe_allow_html=True
                    )
                    st.markdown(f"**Role** &nbsp; {_esc(nm_title)}", unsafe_allow_html=True)
                    st.markdown(f"**Company** &nbsp; {_esc(nm_company)}", unsafe_allow_html=True)
                    st.markdown(f"**Work Mode** &nbsp; {_esc(nm_work_mode)} &nbsp;&nbsp;·&nbsp;&nbsp; **Contract** &nbsp; {_esc(nm_contract)}", unsafe_allow_html=True)
                    st.markdown(f"**Platform** &nbsp; {_esc(nm_platform)}", unsafe_allow_html=True)

                    if nm_reasons:
                        st.markdown("**Partial match**")
                        for r in nm_reasons.split(" | "):
                            if r.strip():
                                st.markdown(f"  • {r}")

                    if nm_missing:
                        st.markdown("**Why it didn't match**")
                        for m in nm_missing.split(" | "):
                            if m.strip():
                                st.markdown(f"  • {m}")

                with col_right:
                    if nm_url:
                        safe = _safe_url(nm_url)
                        if safe:
                            st.markdown(
                                f'<a href="{_esc(safe)}" target="_blank" class="apply-link">'
                                f'View on {_esc(nm_platform)}</a>',
                                unsafe_allow_html=True
                            )

                    if st.button(
                        "Move to Matched",
                        key=f"promote_{nm_id}",
                        type="primary",
                        use_container_width=True,
                    ):
                        promote_not_matched_to_matched(nm_id)
                        st.cache_data.clear()
                        st.success("Moved to Matched — open the Today's Matches tab to mark Applied / Not Applying.")
                        st.rerun()

# ══════════════════════════════════════════════════
# PAGE 4 — SCRAPE HEALTH
# ══════════════════════════════════════════════════
elif page == "📈  Scrape Health":

    st.title("Scrape Source Health")
    st.markdown("Per-platform yield from the last runs, parsed from `data/scrape_log.txt`.")
    st.markdown("---")

    runs = load_scrape_runs()

    if not runs:
        st.info("📭 No scrape summaries yet. Run `python main.py` first.")
    else:
        # ── Broken-platform alert ────────────────────────
        broken = broken_platforms(runs, streak=3)
        if broken:
            names = ", ".join(_esc(b) for b in broken)
            st.markdown(
                '<style>'
                '.scrape-warn { padding:10px 14px; margin-bottom:12px; '
                'border-left:3px solid #dc2626; background:#fef2f2; '
                'border-radius:4px; color:#7f1d1d; }'
                '.scrape-warn code { background:#fde68a; color:#7c2d12; '
                'padding:1px 6px; border-radius:3px; }'
                '@media (prefers-color-scheme: dark) {'
                '  .scrape-warn { background:#3d0f10 !important; '
                '    border-left-color:#f85149 !important; color:#fecaca !important; }'
                '  .scrape-warn code { background:#3a1a1a !important; '
                '    color:#fbbf24 !important; }'
                '}'
                '</style>'
                f'<div class="scrape-warn">'
                f'⚠️ <strong>{len(broken)} platform(s) added zero jobs across the last 3 runs:</strong> {names}. '
                f'Likely bot-block or broken selectors. See <code>plans/015-diagnose-silent-scraper-failures.md</code>.'
                f'</div>',
                unsafe_allow_html=True,
            )

        # ── Per-platform yield table ──────────────────────
        st.subheader("Recent runs")
        num_runs = st.slider("How many recent runs to show", 3, 20, min(10, len(runs)))
        window = runs[-num_runs:]

        platforms = sorted({p for r in window for p in r["platforms"]})
        rows = []
        for run in window:
            row = {"Timestamp": run["timestamp"]}
            for p in platforms:
                row[p] = run["platforms"].get(p, {}).get("added", None)
            row["TOTAL"] = (run.get("total") or {}).get("added", None)
            rows.append(row)

        df = pd.DataFrame(rows)
        # newest at the top
        df = df.iloc[::-1].reset_index(drop=True)

        def _highlight_zero(v):
            # Streamlit dataframe renders in light theme; use a red-50/red-700
            # tint with strong contrast so zero-yield cells jump out at a glance.
            if v == 0:
                return "background-color:#fef2f2; color:#b91c1c; font-weight:600;"
            return ""

        styled = df.style.applymap(_highlight_zero, subset=platforms)
        st.dataframe(styled, use_container_width=True, hide_index=True)

        # ── Top terms aggregated ──────────────────────────
        st.subheader("Top search terms (aggregated across window)")
        top = top_terms_aggregated(window, limit=15)
        if top:
            top_df = pd.DataFrame(top, columns=["Term", "Jobs added"])
            st.dataframe(top_df, use_container_width=True, hide_index=True)
        else:
            st.info("No top-terms line found in the recent runs.")

st.markdown("---")
st.caption("🤖 Job Agent — powered by Claude AI & LangGraph")