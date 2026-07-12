"""Today's Matches (V2 two-pane) renderer and helpers."""

import json

import streamlit as st
from streamlit_shortcuts import shortcut_button

from nodes.tracker import (
    get_rejection_row,
    save_application,
    update_matched_job_applied,
    update_matched_job_company,
    update_matched_job_rejection,
)

from dashboard_pages._shared import (
    _esc,
    _safe_url,
    get_region_badge,
    get_score_color,
)


# ── V2 layout constants ────────────────────────────
_LEFT_RATIO = 1.2   # left-pane column width ratio for two-pane layout
_LEFT_PANE_HEIGHT = 750  # fixed height for scrollable left pane (px)


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
