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
