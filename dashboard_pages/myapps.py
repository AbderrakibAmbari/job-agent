"""My Applications page renderer and its pure helpers."""

from datetime import datetime

import pandas as pd
import streamlit as st

from nodes.tracker import (
    default_followup_date,
    delete_application,
    get_due_followups,
    update_followup_date,
    update_status,
)

from dashboard_pages._shared import _esc, _safe_url


# ── My Applications: pure helpers (Plan 023) ───────
# Light-mode primary palette (soft tinted bg + saturated dark fg).
# Streamlit renders main content in light mode by default; the dark
# equivalents live in _MYAPPS_CSS as a prefers-color-scheme override.
_MYAPPS_STATUS_COLORS: dict[str, tuple[str, str]] = {
    "Pending Review": ("#f1f5f9", "#334155"),
    "Sent":           ("#dbeafe", "#1e40af"),
    "Waiting":        ("#fef3c7", "#92400e"),
    "Interview":      ("#ede9fe", "#5b21b6"),
    "Offer":          ("#d1fae5", "#065f46"),
    "Rejected":       ("#fee2e2", "#991b1b"),
}
_MYAPPS_STATUS_ORDER = ["Pending Review", "Sent", "Waiting", "Interview", "Offer", "Rejected"]
_MYAPPS_SORT_OPTIONS = ["Recently applied", "Oldest first", "Follow-up soonest", "Company A→Z"]
_MYAPPS_STATUS_SLUG = {
    "Pending Review": "pending",
    "Sent": "sent",
    "Waiting": "waiting",
    "Interview": "interview",
    "Offer": "offer",
    "Rejected": "rejected",
}


def _status_badge_html(status: str) -> str:
    """Render a status badge as an inline HTML span with the status palette.

    Falls back to the Pending Review palette for unknown statuses.
    The class hook lets _MYAPPS_CSS restyle the badge in dark mode.
    """
    bg, fg = _MYAPPS_STATUS_COLORS.get(status, _MYAPPS_STATUS_COLORS["Pending Review"])
    slug = _MYAPPS_STATUS_SLUG.get(status, "pending")
    return (
        f'<span class="myapps-badge myapps-badge-{slug}" '
        f'style="background:{bg}; color:{fg}; padding:2px 10px; '
        f'border-radius:12px; font-size:12px; font-weight:600; '
        f'white-space:nowrap;">{_esc(status)}</span>'
    )


# CSS block injected once by _render_myapps_page. Uses !important so
# @media dark-mode rules override the inline style= colors above.
_MYAPPS_CSS = """
<style>
.myapps-title { color:#0f172a; font-weight:600; }
.myapps-company { color:#334155; font-weight:600; }
.myapps-meta { color:#64748b; font-size:12px; }
.myapps-fu-meta { color:#b45309; font-size:12px; font-weight:600; }
.myapps-fu-banner {
  padding:12px 16px; margin:8px 0 6px 0;
  border-left:3px solid #d97706; background:#fef3c7;
  border-radius:6px; color:#78350f; font-weight:600;
}
@media (prefers-color-scheme: dark) {
  .myapps-title { color:#e6edf3 !important; }
  .myapps-company { color:#c9d1d9 !important; }
  .myapps-meta { color:#8b949e !important; }
  .myapps-fu-meta { color:#d29922 !important; }
  .myapps-fu-banner {
    background:#3a2e14 !important; border-left-color:#d29922 !important;
    color:#f0c674 !important;
  }
  .myapps-badge-pending  { background:#2d2d2d !important; color:#c9d1d9 !important; }
  .myapps-badge-sent     { background:#1a3a5c !important; color:#58a6ff !important; }
  .myapps-badge-waiting  { background:#3a2e14 !important; color:#d29922 !important; }
  .myapps-badge-interview{ background:#2a1a4a !important; color:#a78bfa !important; }
  .myapps-badge-offer    { background:#1a3a2c !important; color:#3fb950 !important; }
  .myapps-badge-rejected { background:#3a1a1a !important; color:#f85149 !important; }
}
</style>
"""


def _apply_filters(apps: list, filters: dict) -> list:
    """Filter + sort an application list (list of dicts). Pure — safe to test.

    `filters` keys: status ("All" or one of _MYAPPS_STATUS_ORDER),
    search (case-insensitive substring on company/title),
    platform ("All" or platform name),
    sort (one of _MYAPPS_SORT_OPTIONS).
    """
    out = list(apps)
    status = filters.get("status", "All")
    if status and status != "All":
        out = [a for a in out if a.get("status") == status]
    search = (filters.get("search") or "").strip().lower()
    if search:
        out = [
            a for a in out
            if search in (a.get("company") or "").lower()
            or search in (a.get("job_title") or "").lower()
        ]
    platform = filters.get("platform", "All")
    if platform and platform != "All":
        out = [a for a in out if (a.get("platform") or "") == platform]

    sort = filters.get("sort", _MYAPPS_SORT_OPTIONS[0])
    if sort == "Recently applied":
        out.sort(key=lambda a: a.get("date_applied") or "", reverse=True)
    elif sort == "Oldest first":
        out.sort(key=lambda a: a.get("date_applied") or "")
    elif sort == "Follow-up soonest":
        out.sort(key=lambda a: a.get("follow_up_date") or "9999-12-31")
    elif sort == "Company A→Z":
        out.sort(key=lambda a: (a.get("company") or "").lower())
    return out


# ── Status config ──────────────────────────────────
STATUS_OPTIONS = [
    "Pending Review", "Sent", "Waiting",
    "Interview", "Rejected", "Offer"
]


_APP_COLS = [
    "id", "company", "job_title", "platform", "date_applied",
    "status", "cover_letter", "job_url", "follow_up_date",
]


def _row_to_dict(row) -> dict:
    return {col: row[i] if i < len(row) else None for i, col in enumerate(_APP_COLS)}


def _on_status_change(app_id: int) -> None:
    new_status = st.session_state.get(f"myapps_status_{app_id}")
    if not new_status:
        return
    update_status(app_id, new_status)
    st.cache_data.clear()


def _on_followup_change(app_id: int) -> None:
    val = st.session_state.get(f"myapps_followup_{app_id}")
    if not val:
        return
    update_followup_date(app_id, val.strftime("%Y-%m-%d"))
    st.cache_data.clear()


def _quick_flip_status(app_id: int, new_status: str) -> None:
    update_status(app_id, new_status)
    st.session_state.pop(f"myapps_status_{app_id}", None)
    st.cache_data.clear()


def _quick_snooze(app_id: int, days: int = 7) -> None:
    today = datetime.now().strftime("%Y-%m-%d")
    update_followup_date(app_id, default_followup_date(today, days))
    st.session_state.pop(f"myapps_followup_{app_id}", None)
    st.cache_data.clear()


def _render_myapps_toolbar(apps: list) -> dict:
    """Filter chips + search + platform + sort + CSV export. Returns filters dict."""
    status_counts = {s: 0 for s in _MYAPPS_STATUS_ORDER}
    platforms = set()
    for a in apps:
        s = a.get("status")
        if s in status_counts:
            status_counts[s] += 1
        p = a.get("platform")
        if p:
            platforms.add(p)

    chip_labels = [f"All  {len(apps)}"] + [f"{s}  {status_counts[s]}" for s in _MYAPPS_STATUS_ORDER]
    label_to_status = {chip_labels[0]: "All"}
    for s, label in zip(_MYAPPS_STATUS_ORDER, chip_labels[1:]):
        label_to_status[label] = s

    default_label = st.session_state.get("myapps_status_chip") or chip_labels[0]
    if default_label not in chip_labels:
        default_label = chip_labels[0]

    chip = st.segmented_control(
        "Filter by status",
        options=chip_labels,
        default=default_label,
        key="myapps_status_chip",
        label_visibility="collapsed",
    ) or default_label
    status = label_to_status.get(chip, "All")

    c_search, c_platform, c_sort, c_export = st.columns([3, 2, 2, 1])
    with c_search:
        search = st.text_input(
            "Search",
            key="myapps_search",
            placeholder="🔎 Search company or role",
            label_visibility="collapsed",
        )
    with c_platform:
        platform_options = ["All"] + sorted(platforms)
        platform = st.selectbox(
            "Platform",
            platform_options,
            key="myapps_platform_filter",
            label_visibility="collapsed",
        )
    with c_sort:
        sort = st.selectbox(
            "Sort",
            _MYAPPS_SORT_OPTIONS,
            key="myapps_sort",
            label_visibility="collapsed",
        )
    with c_export:
        preview_filters = {"status": status, "search": search, "platform": platform, "sort": sort}
        preview = _apply_filters(apps, preview_filters)
        csv_bytes = pd.DataFrame(preview).to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇ CSV",
            data=csv_bytes,
            file_name=f"applications-{datetime.now().strftime('%Y-%m-%d')}.csv",
            mime="text/csv",
            use_container_width=True,
            key="myapps_export_csv",
        )

    return {"status": status, "search": search, "platform": platform, "sort": sort}


def _render_followup_section(due_apps: list) -> None:
    show_key = "myapps_show_followups"
    if show_key not in st.session_state:
        st.session_state[show_key] = True

    header_col, toggle_col = st.columns([5, 1])
    with header_col:
        st.markdown(
            f'<div class="myapps-fu-banner">'
            f'🔔 {len(due_apps)} follow-up{"s" if len(due_apps) > 1 else ""} due'
            f'</div>',
            unsafe_allow_html=True,
        )
    with toggle_col:
        st.markdown('<div style="margin-top:14px;"></div>', unsafe_allow_html=True)
        label = "Hide" if st.session_state[show_key] else "Show"
        if st.button(label, key="myapps_toggle_followups", use_container_width=True):
            st.session_state[show_key] = not st.session_state[show_key]
            st.rerun()

    if st.session_state[show_key]:
        for app in due_apps:
            _render_followup_card(app)


def _render_followup_card(app: dict) -> None:
    app_id = app["id"]
    date_applied = app.get("date_applied") or ""
    try:
        days_ago = (datetime.now().date() - datetime.strptime(date_applied, "%Y-%m-%d").date()).days
    except (ValueError, TypeError):
        days_ago = 0

    with st.container(border=True):
        head, badge = st.columns([4, 1])
        with head:
            st.markdown(
                f"<div class='myapps-fu-meta' style='margin-bottom:4px;'>"
                f"⏰ {days_ago}d ago · applied {_esc(date_applied)}"
                f"</div>"
                f"<div class='myapps-title' style='font-size:16px;'>"
                f"{_esc(app.get('job_title') or '')}"
                f" <span class='myapps-meta' style='font-size:14px; font-weight:400;'>"
                f"@ {_esc(app.get('company') or '')}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
        with badge:
            st.markdown(
                f"<div style='text-align:right; margin-top:2px;'>"
                f"{_status_badge_html(app.get('status') or '')}</div>",
                unsafe_allow_html=True,
            )

        b1, b2, b3, b4 = st.columns([1, 1, 1, 1])
        with b1:
            if st.button("✓ Interview", key=f"myapps_fu_int_{app_id}", use_container_width=True):
                _quick_flip_status(app_id, "Interview")
                st.rerun()
        with b2:
            if st.button("✗ Rejected", key=f"myapps_fu_rej_{app_id}", use_container_width=True):
                _quick_flip_status(app_id, "Rejected")
                st.rerun()
        with b3:
            if st.button("⏰ Snooze +7d", key=f"myapps_fu_snz_{app_id}", use_container_width=True):
                _quick_snooze(app_id, 7)
                st.rerun()
        with b4:
            safe = _safe_url(app.get("job_url"))
            if safe:
                st.link_button("Open ↗", safe, use_container_width=True)
            else:
                st.markdown("<div style='height:38px;'></div>", unsafe_allow_html=True)


def _render_app_card(app: dict) -> None:
    app_id = app["id"]
    status = app.get("status") or ""
    with st.container(border=True):
        head, actions = st.columns([3, 2])
        with head:
            st.markdown(
                f"<div style='margin-bottom:6px;'>"
                f"{_status_badge_html(status)}"
                f" <span class='myapps-company' style='margin-left:8px; font-size:14px;'>"
                f"{_esc(app.get('company') or '')}</span>"
                f" <span class='myapps-meta' style='margin-left:8px;'>"
                f"· applied {_esc(app.get('date_applied') or '')}</span>"
                f"</div>"
                f"<div class='myapps-title' style='font-size:15px; margin-bottom:6px;'>"
                f"{_esc(app.get('job_title') or '')}"
                f"</div>",
                unsafe_allow_html=True,
            )
            meta = []
            if app.get("platform"):
                meta.append(_esc(app["platform"]))
            if app.get("follow_up_date"):
                meta.append(f"follow-up: {_esc(app['follow_up_date'])}")
            if meta:
                st.markdown(
                    f"<div class='myapps-meta'>{'  ·  '.join(meta)}</div>",
                    unsafe_allow_html=True,
                )

        with actions:
            a1, a2, a3, a4 = st.columns([2, 2, 1, 1])
            with a1:
                status_key = f"myapps_status_{app_id}"
                if status_key not in st.session_state:
                    st.session_state[status_key] = (
                        status if status in STATUS_OPTIONS else STATUS_OPTIONS[0]
                    )
                st.selectbox(
                    "Status",
                    STATUS_OPTIONS,
                    key=status_key,
                    on_change=_on_status_change,
                    args=(app_id,),
                    label_visibility="collapsed",
                )
            with a2:
                fu_key = f"myapps_followup_{app_id}"
                if fu_key not in st.session_state:
                    fu_val = app.get("follow_up_date")
                    try:
                        st.session_state[fu_key] = (
                            datetime.strptime(fu_val, "%Y-%m-%d").date()
                            if fu_val else datetime.now().date()
                        )
                    except (ValueError, TypeError):
                        st.session_state[fu_key] = datetime.now().date()
                st.date_input(
                    "Follow-up",
                    key=fu_key,
                    on_change=_on_followup_change,
                    args=(app_id,),
                    label_visibility="collapsed",
                )
            with a3:
                safe = _safe_url(app.get("job_url"))
                if safe:
                    st.link_button("🔗", safe, use_container_width=True)
                else:
                    st.markdown("<div style='height:38px;'></div>", unsafe_allow_html=True)
            with a4:
                with st.popover("⋯", use_container_width=True):
                    if app.get("cover_letter"):
                        with st.expander("Cover letter", expanded=False):
                            st.text_area(
                                "Cover letter body",
                                value=app["cover_letter"],
                                height=180,
                                key=f"myapps_cl_{app_id}",
                                label_visibility="collapsed",
                            )
                    else:
                        st.caption("No cover letter saved.")

                    confirm_key = f"myapps_delete_confirm_{app_id}"
                    if st.session_state.get(confirm_key):
                        st.warning("Delete this application?")
                        d1, d2 = st.columns(2)
                        with d1:
                            if st.button(
                                "Yes, delete",
                                key=f"myapps_del_yes_{app_id}",
                                use_container_width=True,
                                type="primary",
                            ):
                                delete_application(app_id)
                                st.session_state[confirm_key] = False
                                st.cache_data.clear()
                                st.rerun()
                        with d2:
                            if st.button(
                                "Cancel",
                                key=f"myapps_del_no_{app_id}",
                                use_container_width=True,
                            ):
                                st.session_state[confirm_key] = False
                                st.rerun()
                    else:
                        if st.button(
                            "🗑️ Delete application",
                            key=f"myapps_del_ask_{app_id}",
                            use_container_width=True,
                        ):
                            st.session_state[confirm_key] = True
                            st.rerun()


def _render_myapps_page(raw_apps: list) -> None:
    st.markdown(_MYAPPS_CSS, unsafe_allow_html=True)
    st.title("My Applications")

    apps = [_row_to_dict(r) for r in (raw_apps or [])]

    if not apps:
        st.info("📭 No applications yet. Run `python main.py` to start!")
        return

    filters = _render_myapps_toolbar(apps)

    due_rows = get_due_followups()
    if due_rows:
        due_apps = [_row_to_dict(r) for r in due_rows]
        _render_followup_section(due_apps)

    filtered = _apply_filters(apps, filters)

    st.markdown(
        f'<div style="margin: 24px 0 10px 0; font-size:11px; '
        f'color:#8b949e; text-transform:uppercase; letter-spacing:1px;">'
        f'{len(filtered)} of {len(apps)} applications'
        f'</div>',
        unsafe_allow_html=True,
    )

    if not filtered:
        st.info("Nothing matches these filters. Try clearing search or picking a different status chip.")
        return

    for app in filtered:
        _render_app_card(app)
