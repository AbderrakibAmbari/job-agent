"""Shared helpers used across dashboard pages."""

import html
from datetime import datetime
from urllib.parse import urlparse

import streamlit as st

from nodes.tracker import get_scrape_dates


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


# ── V2/Not Matched shared visual helpers ──────────
# Consumed by both dashboard_pages.matches_v2._render_job_detail_right and
# dashboard.py's Not Matched page, so they live here rather than in either
# page module. REGION_BADGE is a private detail of get_region_badge.
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
