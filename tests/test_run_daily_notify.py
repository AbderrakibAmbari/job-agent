import pytest

from run_daily import (
    _select_strong_matches,
    _format_notification_body,
    _notify_strong_matches,
    STRONG_MATCH_THRESHOLD,
)


def test_select_strong_matches_filters_below_threshold():
    picks = _select_strong_matches([
        {"title": "a", "company": "c1", "score": 90},
        {"title": "b", "company": "c2", "score": 70},
        {"title": "c", "company": "c3", "score": 85},
    ])
    assert [p["title"] for p in picks] == ["a", "c"]


def test_select_strong_matches_sorts_desc_and_caps_at_five():
    jobs = [{"title": f"j{i}", "company": "c", "score": 85 + i} for i in range(10)]
    picks = _select_strong_matches(jobs)
    assert len(picks) == 5
    scores = [p["score"] for p in picks]
    assert scores == sorted(scores, reverse=True)


def test_select_strong_matches_empty_input_returns_empty():
    assert _select_strong_matches([]) == []
    assert _select_strong_matches(None) == []


def test_select_strong_matches_respects_custom_threshold():
    jobs = [{"title": "a", "score": 60}, {"title": "b", "score": 80}]
    picks = _select_strong_matches(jobs, threshold=50)
    assert [p["title"] for p in picks] == ["b", "a"]


def test_select_strong_matches_missing_score_treats_as_zero():
    picks = _select_strong_matches([{"title": "a", "company": "c"}])
    assert picks == []


def test_format_body_contains_score_title_company():
    body = _format_notification_body([
        {"title": "Backend Dev", "company": "Acme", "score": 88},
    ])
    assert "88" in body
    assert "Backend Dev" in body
    assert "Acme" in body


def test_notify_returns_zero_when_no_strong_matches(monkeypatch):
    # Ensure winotify is never imported when no strong matches — proves early return
    monkeypatch.setitem(__import__("sys").modules, "winotify", None)
    n = _notify_strong_matches([{"title": "a", "score": 60}])
    assert n == 0


def test_notify_returns_count_when_toast_call_stubbed(monkeypatch):
    """Stub the winotify.Notification so we can assert count without raising a real toast."""
    class _StubNotification:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
        def set_audio(self, *args, **kwargs):
            pass
        def show(self):
            pass

    class _StubAudio:
        Default = "default"

    stub_module = type("m", (), {"Notification": _StubNotification, "audio": _StubAudio})
    monkeypatch.setitem(__import__("sys").modules, "winotify", stub_module)

    n = _notify_strong_matches([
        {"title": "a", "company": "c", "score": 90},
        {"title": "b", "company": "c", "score": 88},
    ])
    assert n == 2


def test_strong_match_threshold_default_is_85():
    assert STRONG_MATCH_THRESHOLD == 85
