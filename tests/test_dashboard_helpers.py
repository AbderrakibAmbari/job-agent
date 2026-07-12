import pytest

from dashboard_pages._shared import _esc, _safe_url
from dashboard_pages.myapps import (
    _status_badge_html,
    _apply_filters,
    _MYAPPS_STATUS_COLORS,
)


# ---------- _esc ----------

def test_esc_escapes_script_tag():
    assert _esc("<script>") == "&lt;script&gt;"


def test_esc_none_returns_empty_string():
    assert _esc(None) == ""


def test_esc_int_stringifies():
    assert _esc(42) == "42"


# ---------- _safe_url ----------

def test_safe_url_allows_https():
    assert _safe_url("https://x.de/j") == "https://x.de/j"


def test_safe_url_allows_http():
    assert _safe_url("http://x.de/j") == "http://x.de/j"


def test_safe_url_rejects_javascript_scheme():
    assert _safe_url("javascript:alert(1)") == ""


def test_safe_url_rejects_data_scheme():
    assert _safe_url("data:text/html,foo") == ""


def test_safe_url_empty_string_returns_empty():
    assert _safe_url("") == ""


def test_safe_url_none_returns_empty():
    assert _safe_url(None) == ""


def test_safe_url_rejects_bare_text():
    assert _safe_url("not a url") == ""


def test_safe_url_rejects_scheme_relative():
    # No scheme → rejected even if it looks host-like.
    assert _safe_url("//cdn.example.com/x") == ""


# ---------- _auto_advance (Plan 022) ----------
#
# `_auto_advance` mutates `st.session_state` and needs a Streamlit runtime.
# The pure implementation is mirrored here for testing; keep the two in sync.

def _auto_advance_pure(current_id, all_ids, unreviewed_ids):
    """Return the next unreviewed id after current, wrapping around, or None."""
    try:
        idx = all_ids.index(current_id)
    except ValueError:
        return None
    for i in all_ids[idx + 1:]:
        if i in unreviewed_ids:
            return i
    for i in all_ids[:idx]:
        if i in unreviewed_ids:
            return i
    return None


def test_auto_advance_finds_next():
    assert _auto_advance_pure(2, [1, 2, 3, 4], {3, 4}) == 3


def test_auto_advance_wraps_around():
    assert _auto_advance_pure(4, [1, 2, 3, 4], {1, 2}) == 1


def test_auto_advance_all_reviewed():
    assert _auto_advance_pure(2, [1, 2, 3], set()) is None


def test_auto_advance_unknown_id():
    assert _auto_advance_pure(99, [1, 2, 3], {1}) is None


# ---------- _status_badge_html (Plan 023) ----------

def test_status_badge_html_contains_status_text():
    html = _status_badge_html("Interview")
    assert "Interview" in html
    assert html.startswith("<span")


def test_status_badge_html_uses_matching_palette():
    html = _status_badge_html("Offer")
    bg, fg = _MYAPPS_STATUS_COLORS["Offer"]
    assert bg in html
    assert fg in html


def test_status_badge_html_escapes_status():
    html = _status_badge_html("<script>x</script>")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_status_badge_html_unknown_status_falls_back_to_pending():
    unknown_html = _status_badge_html("Ghosted")
    pending_bg, pending_fg = _MYAPPS_STATUS_COLORS["Pending Review"]
    assert pending_bg in unknown_html
    assert pending_fg in unknown_html
    # Status text still rendered even though it's unknown.
    assert "Ghosted" in unknown_html


# ---------- _apply_filters (Plan 023) ----------

def _mkapp(**kw):
    base = {
        "id": 1, "company": "Foo", "job_title": "Backend Engineer",
        "platform": "LinkedIn", "date_applied": "2026-01-01",
        "status": "Sent", "follow_up_date": "2026-01-08",
    }
    base.update(kw)
    return base


def test_apply_filters_status_all_returns_all():
    apps = [_mkapp(id=1), _mkapp(id=2, status="Interview")]
    out = _apply_filters(apps, {"status": "All", "sort": "Recently applied"})
    assert {a["id"] for a in out} == {1, 2}


def test_apply_filters_status_filters():
    apps = [_mkapp(id=1, status="Sent"), _mkapp(id=2, status="Interview")]
    out = _apply_filters(apps, {"status": "Interview"})
    assert [a["id"] for a in out] == [2]


def test_apply_filters_search_matches_company_case_insensitive():
    apps = [_mkapp(id=1, company="SAP SE"), _mkapp(id=2, company="Bosch")]
    out = _apply_filters(apps, {"search": "sap"})
    assert [a["id"] for a in out] == [1]


def test_apply_filters_search_matches_title_case_insensitive():
    apps = [_mkapp(id=1, job_title="Data Engineer"), _mkapp(id=2, job_title="ML Ops")]
    out = _apply_filters(apps, {"search": "DATA"})
    assert [a["id"] for a in out] == [1]


def test_apply_filters_platform_filters():
    apps = [_mkapp(id=1, platform="LinkedIn"), _mkapp(id=2, platform="XING")]
    out = _apply_filters(apps, {"platform": "XING"})
    assert [a["id"] for a in out] == [2]


def test_apply_filters_sort_recently_applied():
    apps = [
        _mkapp(id=1, date_applied="2025-06-01"),
        _mkapp(id=2, date_applied="2026-05-01"),
        _mkapp(id=3, date_applied="2026-01-01"),
    ]
    out = _apply_filters(apps, {"sort": "Recently applied"})
    assert [a["id"] for a in out] == [2, 3, 1]


def test_apply_filters_sort_oldest_first():
    apps = [
        _mkapp(id=1, date_applied="2025-06-01"),
        _mkapp(id=2, date_applied="2026-05-01"),
    ]
    out = _apply_filters(apps, {"sort": "Oldest first"})
    assert [a["id"] for a in out] == [1, 2]


def test_apply_filters_sort_followup_soonest_puts_none_last():
    apps = [
        _mkapp(id=1, follow_up_date=None),
        _mkapp(id=2, follow_up_date="2026-02-01"),
        _mkapp(id=3, follow_up_date="2026-01-01"),
    ]
    out = _apply_filters(apps, {"sort": "Follow-up soonest"})
    assert [a["id"] for a in out] == [3, 2, 1]


def test_apply_filters_sort_company_az():
    apps = [
        _mkapp(id=1, company="Zalando"),
        _mkapp(id=2, company="alphabet"),
        _mkapp(id=3, company="Bosch"),
    ]
    out = _apply_filters(apps, {"sort": "Company A→Z"})
    assert [a["id"] for a in out] == [2, 3, 1]


def test_apply_filters_empty_search_no_op():
    apps = [_mkapp(id=1), _mkapp(id=2)]
    out = _apply_filters(apps, {"search": "   "})
    assert len(out) == 2
