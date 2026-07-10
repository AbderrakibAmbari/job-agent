import pytest

from dashboard import _esc, _safe_url


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
