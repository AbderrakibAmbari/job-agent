import streamlit as st
import sqlite3
import pandas as pd
import json
from datetime import datetime
from nodes.tracker import (
    init_db, get_all_applications, get_matched_jobs,
    update_status, delete_application,
    update_matched_job_company, update_matched_job_applied,
    get_applied_status, get_applied_statuses, save_application,
    get_not_matched_jobs, get_scrape_dates,
    promote_not_matched_to_matched,
    get_due_followups, update_followup_date,  # Plan 009
    update_matched_job_rejection, get_rejection_row,  # Plan 013
    default_followup_date,  # Plan 021
)
from nodes.scrape_log_parser import (
    parse_scrape_log, platform_history, broken_platforms, top_terms_aggregated,
)
from streamlit_shortcuts import shortcut_button  # Plan 022 Phase E
import os
import html
from urllib.parse import urlparse


def _esc(value) -> str:
    """HTML-escape a value for safe interpolation into unsafe_allow_html blocks."""
    return html.escape("" if value is None else str(value), quote=True)


def _safe_url(value) -> str:
    """Return value only if it is an http(s) URL; empty string otherwise.

    Prevents javascript:/data:/file: URLs scraped from third-party boards
    from being placed into an href attribute.
    """
    if not value:
        return ""
    s = str(value).strip()
    try:
        parsed = urlparse(s)
    except ValueError:
        return ""
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return s
    return ""

# ── Init ───────────────────────────────────────────
init_db()
DB_PATH  = "data/applications.db"
RUN_DATE = datetime.now().strftime("%Y-%m-%d")

# Plan 022: V2 two-pane layout
_LEFT_RATIO = 1.2   # left-pane column width ratio for two-pane layout
_LEFT_PANE_HEIGHT = 750  # fixed height for scrollable left pane (px)
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


def render_date_chips(state_key: str, source: str, label: str, max_chips: int = 7) -> str:
    """Render a row of clickable scrape-day chips. Returns the selected YYYY-MM-DD string.
    Active day is highlighted green via the primary-button CSS override above.
    """
    run_dates = get_scrape_dates(source=source, limit=14)
    if state_key not in st.session_state:
        st.session_state[state_key] = (
            datetime.strptime(run_dates[0][0], "%Y-%m-%d").date()
            if run_dates else datetime.now().date()
        )

    if run_dates:
        st.markdown(f"**{label}**")
        chips = run_dates[:max_chips]
        cols = st.columns(len(chips))
        for i, (d_str, n) in enumerate(chips):
            d_obj = datetime.strptime(d_str, "%Y-%m-%d").date()
            is_active = (d_obj == st.session_state[state_key])
            with cols[i]:
                if st.button(
                    f"📅 {d_str[5:]}\n{n} jobs",
                    key=f"{state_key}_chip_{d_str}",
                    type="primary" if is_active else "secondary",
                    use_container_width=True,
                ):
                    st.session_state[state_key] = d_obj
                    st.rerun()

    return st.session_state[state_key].strftime("%Y-%m-%d")

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
    # West
    "nordrhein": ("NRW",     "badge-west"),
    "westfalen": ("NRW",     "badge-west"),
    "nrw":       ("NRW",     "badge-west"),
    "hessen":    ("Hessen",  "badge-west"),
    "rheinland": ("RLP",     "badge-west"),
    "pfalz":     ("RLP",     "badge-west"),
    "saarland":  ("Saar",    "badge-west"),
    # North
    "hamburg":        ("HH",  "badge-north"),
    "bremen":         ("HB",  "badge-north"),
    "niedersachsen":  ("NDS", "badge-north"),
    "schleswig":      ("SH",  "badge-north"),
    "holstein":       ("SH",  "badge-north"),
    # East
    "berlin":            ("Berlin", "badge-east"),
    "brandenburg":       ("BB",     "badge-east"),
    "mecklenburg":       ("MV",     "badge-east"),
    "vorpommern":        ("MV",     "badge-east"),
    "sachsen-anhalt":    ("ST",     "badge-east"),
    "sachsen anhalt":    ("ST",     "badge-east"),
    "thüringen":         ("TH",     "badge-east"),
    "sachsen":           ("SN",     "badge-east"),
    # South
    "bayern":           ("Bayern", "badge-south"),
    "münchen":          ("Bayern", "badge-south"),
    "baden-württemberg":("BaWü",   "badge-south"),
    "baden württemberg":("BaWü",   "badge-south"),
    "württemberg":      ("BaWü",   "badge-south"),
}

def get_region_badge(location: str) -> str:
    loc_lower = location.lower()
    for key, (label, css) in REGION_BADGE.items():
        if key in loc_lower:
            return f'<span class="badge {css}">{label}</span>'
    return f'<span class="badge badge-other">{_esc(location[:15])}</span>'

def get_score_color(score: int) -> str:
    if score >= 85: return "#3fb950"
    if score >= 70: return "#f0883e"
    return "#f85149"


# ══════════════════════════════════════════════════
# PLAN 022 — V2 TWO-PANE LAYOUT
# ══════════════════════════════════════════════════

def _render_job_row_compact(job, applied_map: dict, is_selected: bool) -> bool:
    """Render one compact job row in the left pane. Returns True if clicked."""
    job_id, job_title, company, location = job[0], job[1], job[2], job[3]
    match_score = job[6]
    apply_state = applied_map.get(job_id, 0)

    icon = "✅" if apply_state == 1 else ("❌" if apply_state == 2 else "📋")

    # Two lines: header (score + title) and sub (company · location)
    title = (job_title or "")[:60]
    label = f"{icon} {match_score}%  ·  {title}"
    sub = f"{(company or '')[:32]} · {(location or '')[:22]}"

    clicked = st.button(
        label,
        key=f"v2_row_{job_id}",
        use_container_width=True,
        type="primary" if is_selected else "secondary",
        help=sub,
    )
    return clicked


def _auto_advance(current_job_id: int, all_jobs: list, applied_map: dict):
    """Move selection to the next unreviewed job after an action.

    Mutates st.session_state["v2_selected_job_id"]. Called before st.rerun()
    so the next render lands on the right job. applied_map reflects the
    state BEFORE the write, so the current job's state is still 0 in the
    map — we skip it by id comparison, not by state.
    """
    ids = [j[0] for j in all_jobs]
    try:
        idx = ids.index(current_job_id)
    except ValueError:
        return
    for j in all_jobs[idx + 1:]:
        if applied_map.get(j[0], 0) == 0:
            st.session_state["v2_selected_job_id"] = j[0]
            return
    for j in all_jobs[:idx]:
        if applied_map.get(j[0], 0) == 0:
            st.session_state["v2_selected_job_id"] = j[0]
            return
    # All reviewed — stay on current job.


def _render_job_detail_right(job: tuple, applied_map: dict, all_jobs: list):
    """Render the right-pane detail view for the selected job."""
    import streamlit.components.v1 as components

    (job_id, job_title, company, location, platform,
     job_url, match_score, recommendation, match_reasons,
     missing, contract_type, work_mode, link_status,
     _cover, date_found, applied, all_urls_raw, job_category,
     rejection_reason, rejection_note) = job

    try:
        platform_links = json.loads(all_urls_raw or "[]")
    except Exception:
        platform_links = []
    if not platform_links and job_url:
        platform_links = [{"platform": platform, "url": job_url}]

    score_color = get_score_color(match_score)
    region_badge = get_region_badge(location)
    apply_state = applied_map.get(job_id, 0)

    # ── Header ──
    st.markdown(
        f"<div style='margin-bottom:2px;'>"
        f"<span style='font-size:26px; font-weight:700; color:{score_color};'>"
        f"{match_score}%</span> &nbsp;"
        f"<span style='color:#8b949e; font-size:14px;'>{_esc(recommendation)}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.markdown(f"### {_esc(job_title)}", unsafe_allow_html=True)
    st.markdown(
        f"{region_badge} &nbsp; "
        f'<span style="color:#8b949e; font-size:13px;">{_esc(location)}</span>',
        unsafe_allow_html=True,
    )

    # ── Score bar ──
    st.markdown(
        f'<div class="score-bar-bg">'
        f'<div class="score-bar-fill" style="width:{match_score}%; background:{score_color};"></div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Metadata row ──
    meta_cols = st.columns(4)
    meta_cols[0].markdown(f"**Company**  \n{_esc(company)}", unsafe_allow_html=True)
    meta_cols[1].markdown(f"**Mode**  \n{_esc(work_mode)}", unsafe_allow_html=True)
    meta_cols[2].markdown(f"**Contract**  \n{_esc(contract_type)}", unsafe_allow_html=True)
    meta_cols[3].markdown(f"**Category**  \n{_esc(job_category)}", unsafe_allow_html=True)

    # ── Inline company edit (preserved from v1) ──
    new_company = st.text_input(
        "Company name (edit if wrong)",
        value=company if company != "Unknown" else "",
        placeholder="Type company name...",
        key=f"v2_company_{job_id}",
    )
    if new_company and new_company != company:
        if st.button("Save company", key=f"v2_save_company_{job_id}"):
            update_matched_job_company(job_id, new_company)
            st.cache_data.clear()
            st.success(f"Updated to: {new_company}")
            st.rerun()

    # ── Link status indicator ──
    if link_status == "active":
        st.success("Job link is active")
    elif link_status == "expired":
        st.error("Job link expired")
    else:
        st.warning("Manual review needed")

    st.markdown("---")

    # ── Reasons + gaps side by side ──
    reason_col, gap_col = st.columns(2)
    with reason_col:
        if match_reasons:
            st.markdown("**Why you fit**")
            for r in match_reasons.split(" | "):
                if r.strip():
                    st.markdown(f"  • {r}")
    with gap_col:
        if missing:
            st.markdown("**Gaps**")
            for m in missing.split(" | "):
                if m.strip():
                    st.markdown(f"  • {m}")

    st.markdown("---")

    # ── Action buttons ──
    # Shortcuts: a = Applied · n = Not-Applying quick (reason=other) · → = skip
    # `n` cannot open a popover programmatically in Streamlit — it commits with
    # reason="other" as a fast-path. Use the popover mouse-click for specific reasons.
    st.markdown("**Triage**  ·  `a` Applied  ·  `n` skip w/ reason=other  ·  `→` next")
    btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 0.6])

    with btn_col1:
        if shortcut_button(
            "✅ Applied",
            shortcut="a",
            hint=False,
            key=f"v2_applied_{job_id}",
            type="primary" if apply_state != 1 else "secondary",
            use_container_width=True,
        ):
            update_matched_job_applied(job_id, 1)
            save_application(
                company=company,
                job_title=job_title,
                platform=platform,
                cover_letter="",
                job_url=job_url if job_url else "",
            )
            st.cache_data.clear()
            _auto_advance(job_id, all_jobs, applied_map)
            st.rerun()

    with btn_col2:
        with st.popover("❌ Not Applying", use_container_width=True):
            st.markdown("**Why skip this job?**")
            reason = st.selectbox(
                "Reason",
                [
                    "not-tech", "wrong-tech", "wrong-seniority",
                    "wrong-location", "wrong-contract",
                    "employer-mismatch", "already-applied-elsewhere",
                    "link-broken", "other",
                ],
                key=f"v2_rej_reason_{job_id}",
            )
            note = st.text_input(
                "Note (optional)",
                key=f"v2_rej_note_{job_id}",
                placeholder="e.g. Angular-only shop, no Vue",
            )
            if st.button("Save reason", key=f"v2_rej_save_{job_id}"):
                update_matched_job_rejection(job_id, reason, note)
                st.cache_data.clear()
                _auto_advance(job_id, all_jobs, applied_map)
                st.rerun()

    with btn_col3:
        if shortcut_button(
            "→",
            shortcut="arrowright",
            hint=False,
            key=f"v2_next_{job_id}",
            use_container_width=True,
            help="Skip to next unreviewed",
        ):
            _auto_advance(job_id, all_jobs, applied_map)
            st.rerun()

    # `n` shortcut: quick-reject with reason=other, no note. A Streamlit
    # popover cannot be opened programmatically, so `n` fires a fast-path
    # commit. Users who want a specific reason click the popover instead.
    if shortcut_button(
        "⏭ Skip w/o reason",
        shortcut="n",
        hint=False,
        key=f"v2_n_quick_{job_id}",
        type="secondary",
        use_container_width=True,
    ):
        update_matched_job_rejection(job_id, "other", "")
        st.cache_data.clear()
        _auto_advance(job_id, all_jobs, applied_map)
        st.rerun()

    if apply_state == 2:
        existing = get_rejection_row(job_id) or ("", "")
        if existing[0]:
            st.caption(
                f"↳ {_esc(existing[0])}"
                + (f" — {_esc(existing[1])}" if existing[1] else "")
            )
        else:
            st.caption("↳ (legacy — no reason captured)")

    st.markdown("---")

    # ── Platform links ──
    if platform_links:
        for pl in platform_links:
            pl_name = pl.get("platform", "Apply")
            pl_url = _safe_url(pl.get("url", ""))
            if pl_url:
                st.markdown(
                    f'<a href="{_esc(pl_url)}" target="_blank" class="apply-link">'
                    f'Open on {_esc(pl_name)} ↗</a>',
                    unsafe_allow_html=True,
                )

    # ── Inline iframe ──
    primary_url = _safe_url(job_url or "")
    if primary_url:
        st.markdown("**Job posting (inline preview)**")
        st.caption(
            "If the frame is blank, the board blocks embedding — use a link above."
        )
        components.html(
            f'<iframe src="{_esc(primary_url)}" '
            f'width="100%" height="600" '
            f'style="border:1px solid #2d3250; border-radius:6px;" '
            f'sandbox="allow-scripts allow-same-origin allow-forms">'
            f'</iframe>',
            height=620,
            scrolling=False,
        )


def _render_matches_v2(job_list, applied_map: dict, date_str: str):
    """V2 two-pane triage view — left = compact list, right = detail (Phase C)."""
    # Auto-select first unreviewed job on first load
    if st.session_state["v2_selected_job_id"] is None and job_list:
        for j in job_list:
            if applied_map.get(j[0], 0) == 0:
                st.session_state["v2_selected_job_id"] = j[0]
                break
        if st.session_state["v2_selected_job_id"] is None:
            st.session_state["v2_selected_job_id"] = job_list[0][0]

    left, right = st.columns([_LEFT_RATIO, 2])

    # ── Left pane ──
    with left:
        reviewed = sum(1 for j in job_list if applied_map.get(j[0], 0) != 0)
        st.caption(f"**{reviewed} of {len(job_list)} reviewed**  ·  {date_str}")
        st.markdown("---")

        with st.container(height=_LEFT_PANE_HEIGHT):
            for job in job_list:
                job_id = job[0]
                is_selected = (st.session_state["v2_selected_job_id"] == job_id)
                if _render_job_row_compact(job, applied_map, is_selected):
                    st.session_state["v2_selected_job_id"] = job_id
                    st.rerun()

    # ── Right pane ──
    with right:
        sel_id = st.session_state.get("v2_selected_job_id")
        if sel_id is None:
            st.info("Select a job from the list to view details.")
        else:
            sel_job = next((j for j in job_list if j[0] == sel_id), None)
            if sel_job is None:
                st.warning("Selected job not found in current list.")
            else:
                _render_job_detail_right(sel_job, applied_map, job_list)


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

    # Plan 022: V2 layout toggle — removed after operator sign-off
    v2_layout = st.checkbox("V2 layout (two-pane)", value=True, key="v2_layout")

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

    st.title("My Applications")
    st.markdown("---")

    # ── Follow-up due (Plan 009) ──────────────────────
    due = load_due_followups()
    if due:
        st.markdown(
            f'<div style="padding:10px 14px; margin-bottom:12px; '
            f'border-left:3px solid #d29922; background:#332b00; '
            f'border-radius:4px; color:#e6e6e6;">'
            f'🔔 <strong>{len(due)} follow-up{"s" if len(due) > 1 else ""} due</strong> '
            f'— applications waiting on a reply past their follow-up date.'
            f'</div>',
            unsafe_allow_html=True,
        )
        with st.expander(f"Show {len(due)} due follow-up(s)", expanded=False):
            for r in due:
                app_id, company, job_title, platform, date_applied, status, _cover, job_url, follow_up = r
                days_since = (
                    datetime.now().date() - datetime.strptime(date_applied, "%Y-%m-%d").date()
                ).days if date_applied else 0

                fu_cols = st.columns([3, 1, 1, 1, 1])
                with fu_cols[0]:
                    safe = _safe_url(job_url) if job_url else ""
                    link_html = (
                        f' <a href="{safe}" target="_blank" style="color:#58a6ff; '
                        f'font-size:12px; text-decoration:none;">↗</a>'
                        if safe else ""
                    )
                    st.markdown(
                        f"**{_esc(company)}** — {_esc(job_title)}  "
                        f"<span style='color:#8b949e;font-size:12px;'>"
                        f"({days_since}d ago · {_esc(status)}){link_html}"
                        f"</span>",
                        unsafe_allow_html=True,
                    )
                with fu_cols[1]:
                    if st.button("Interview", key=f"fu_int_{app_id}"):
                        update_status(app_id, "Interview")
                        st.cache_data.clear()
                        st.rerun()
                with fu_cols[2]:
                    if st.button("Rejected", key=f"fu_rej_{app_id}"):
                        update_status(app_id, "Rejected")
                        st.cache_data.clear()
                        st.rerun()
                with fu_cols[3]:
                    if st.button("Snooze +7d", key=f"fu_snz_{app_id}"):
                        today = datetime.now().strftime("%Y-%m-%d")
                        update_followup_date(app_id, default_followup_date(today))
                        st.cache_data.clear()
                        st.rerun()
                with fu_cols[4]:
                    st.markdown(
                        f"<span style='color:#8b949e;font-size:11px;'>due {_esc(follow_up)}</span>",
                        unsafe_allow_html=True,
                    )
        st.markdown("---")

    col1, col2, col3, col4, col5 = st.columns(5)
    df_apps = pd.DataFrame(apps, columns=[
        "id", "company", "job_title", "platform",
        "date_applied", "status", "cover_letter",
        "job_url", "follow_up_date"
    ]) if apps else pd.DataFrame()

    with col1: st.metric("Total",     len(df_apps))
    with col2: st.metric("Sent",      len(df_apps[df_apps["status"] == "Sent"])      if not df_apps.empty else 0)
    with col3: st.metric("Waiting",   len(df_apps[df_apps["status"] == "Waiting"])   if not df_apps.empty else 0)
    with col4: st.metric("Interview", len(df_apps[df_apps["status"] == "Interview"]) if not df_apps.empty else 0)
    with col5: st.metric("Offer",     len(df_apps[df_apps["status"] == "Offer"])     if not df_apps.empty else 0)

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
                    st.markdown(f"**Company** &nbsp; {_esc(row['company'])}", unsafe_allow_html=True)
                    st.markdown(f"**Role** &nbsp; {_esc(row['job_title'])}", unsafe_allow_html=True)
                    st.markdown(f"**Platform** &nbsp; {_esc(row['platform'])}", unsafe_allow_html=True)
                    st.markdown(f"**Applied** &nbsp; {_esc(row['date_applied'])}", unsafe_allow_html=True)
                    st.markdown(f"**Status** &nbsp; {icon} {_esc(row['status'])}", unsafe_allow_html=True)
                    safe = _safe_url(row["job_url"])
                    if safe:
                        st.markdown(f"**Link** &nbsp; [Open job posting]({safe})", unsafe_allow_html=True)

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

                    # ── Follow-up date (Plan 009) ──
                    fu_col1, fu_col2 = st.columns([3, 1])
                    with fu_col1:
                        new_fu = st.date_input(
                            "Follow-up date",
                            value=(
                                datetime.strptime(row["follow_up_date"], "%Y-%m-%d").date()
                                if row["follow_up_date"] else datetime.now().date()
                            ),
                            key=f"fu_date_{row['id']}",
                        )
                    with fu_col2:
                        st.markdown("<br>", unsafe_allow_html=True)
                        if st.button("Save follow-up", key=f"fu_save_{row['id']}"):
                            update_followup_date(row["id"], new_fu.strftime("%Y-%m-%d"))
                            st.cache_data.clear()
                            st.success(f"Follow-up set to {new_fu}")
                            st.rerun()

                if row["cover_letter"]:
                    st.markdown("---")
                    st.markdown("**Cover Letter**")
                    st.text_area("Cover Letter", value=row["cover_letter"], height=200,
                                 key=f"cl_{row['id']}", label_visibility="collapsed")

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

        def render_jobs(job_list):
            if not job_list:
                st.info("No jobs in this category yet.")
                return
            for job in job_list:
                (job_id, job_title, company, location, platform,
                 job_url, match_score, recommendation, match_reasons,
                 missing, contract_type, work_mode, link_status,
                 _unused_cover_letter, date_found, applied, all_urls_raw, *_) = job
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
                                         margin-left:8px;">{_esc(recommendation)}</span>
                        </div>
                        <div class="score-bar-bg">
                            <div class="score-bar-fill" style="width:{match_score}%;
                                 background: {score_color};"></div>
                        </div>
                        """, unsafe_allow_html=True)

                        st.markdown(
                            f"{region_badge} &nbsp; "
                            f'<span style="color:#8b949e; font-size:13px;">{_esc(location)}</span>',
                            unsafe_allow_html=True
                        )

                        new_company = st.text_input(
                            "Company",
                            value=company if company != "Unknown" else "",
                            placeholder="Type company name...",
                            key=f"company_{job_id}"
                        )
                        if new_company and new_company != company:
                            if st.button("Save company", key=f"save_company_{job_id}"):
                                update_matched_job_company(job_id, new_company)
                                st.cache_data.clear()
                                st.success(f"Updated to: {new_company}")
                                st.rerun()
                        st.markdown(f"**Role** &nbsp; {_esc(job_title)}", unsafe_allow_html=True)
                        st.markdown(f"**Work Mode** &nbsp; {_esc(work_mode)}", unsafe_allow_html=True)
                        st.markdown(f"**Contract** &nbsp; {_esc(contract_type)}", unsafe_allow_html=True)
                        st.markdown(f"**Platform** &nbsp; {_esc(platform)}", unsafe_allow_html=True)

                        if link_status == "active":
                            st.success("Job link is active")
                        elif link_status == "expired":
                            st.error("Job link expired")
                        else:
                            st.warning("Manual review needed")

                        if platform_links:
                            for pl in platform_links:
                                pl_name = pl.get("platform", "Apply")
                                pl_url  = _safe_url(pl.get("url", ""))
                                if pl_url:
                                    st.markdown(
                                        f'<a href="{_esc(pl_url)}" target="_blank" class="apply-link">'
                                        f'Apply on {_esc(pl_name)}</a>',
                                        unsafe_allow_html=True
                                    )

                        if match_reasons:
                            st.markdown("**Why you fit**")
                            for r in match_reasons.split(" | "):
                                if r.strip():
                                    st.markdown(f"  • {r}")

                        if missing:
                            st.markdown("**Gaps**")
                            for m in missing.split(" | "):
                                if m.strip():
                                    st.markdown(f"  • {m}")

                    with col_right:
                        st.markdown("### Actions")

                        st.markdown("**Application Status**")
                        btn_col1, btn_col2 = st.columns(2)

                        with btn_col1:
                            if st.button(
                                "Applied",
                                key=f"applied_{job_id}",
                                type="primary" if apply_state != 1 else "secondary"
                            ):
                                update_matched_job_applied(job_id, 1)
                                save_application(
                                    company=company,
                                    job_title=job_title,
                                    platform=platform,
                                    cover_letter="",
                                    job_url=job_url if job_url else ""
                                )
                                st.cache_data.clear()
                                st.success("Marked as Applied!")
                                st.rerun()

                        with btn_col2:
                            # Plan 013: reason capture on Not Applying
                            with st.popover(
                                "Not Applying",
                                use_container_width=True,
                            ):
                                st.markdown("**Why skip this job?**")
                                reason = st.selectbox(
                                    "Reason",
                                    [
                                        "not-tech",
                                        "wrong-tech",
                                        "wrong-seniority",
                                        "wrong-location",
                                        "wrong-contract",
                                        "employer-mismatch",
                                        "already-applied-elsewhere",
                                        "link-broken",
                                        "other",
                                    ],
                                    key=f"rej_reason_{job_id}",
                                )
                                note = st.text_input(
                                    "Note (optional)",
                                    key=f"rej_note_{job_id}",
                                    placeholder="e.g. Angular-only shop, no Vue",
                                )
                                if st.button("Save reason", key=f"rej_save_{job_id}"):
                                    update_matched_job_rejection(job_id, reason, note)
                                    st.cache_data.clear()
                                    st.rerun()

                            if apply_state == 2:
                                existing = get_rejection_row(job_id) or ("", "")
                                if existing[0]:
                                    st.caption(f"↳ {_esc(existing[0])}"
                                               + (f" — {_esc(existing[1])}" if existing[1] else ""))
                                else:
                                    st.caption("↳ (legacy — no reason captured)")

        if st.session_state.get("v2_layout", True):
            _render_matches_v2(matched, applied_map, selected_date_str)
        else:
            render_jobs(matched)

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
                f'<div style="padding:10px 14px; margin-bottom:12px; '
                f'border-left:3px solid #f85149; background:#3d0f10; '
                f'border-radius:4px; color:#e6e6e6;">'
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
            if v == 0:
                return "background-color:#3d0f10; color:#f85149;"
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