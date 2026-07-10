"""Matcher tests (plan 020 phase 1)."""
import pytest

from nodes.gmail_matcher import (
    _extract_sender_domain,
    _slugify_company,
    match_message_to_application,
)


# ---------- _slugify_company ----------

@pytest.mark.parametrize("raw,expected", [
    ("Deutsche Bahn AG", "deutschebahn"),
    ("BMW Group", "bmwgroup"),
    ("thoughtworks", "thoughtworks"),
    ("SAP SE", "sap"),
    ("Bosch GmbH & Co. KG", "bosch"),
    ("", ""),
])
def test_slugify_company(raw, expected):
    assert _slugify_company(raw) == expected


# ---------- _extract_sender_domain ----------

@pytest.mark.parametrize("header,expected", [
    ("Careers Team <careers@bahn.de>", "bahn"),
    ("noreply@jobs.thoughtworks.com", "thoughtworks"),
    ("noreply@bmw-group.myworkday.com", "bmwgroup"),
    ("hr@sap.com", "sap"),
    ("<foo@company.co.uk>", "company"),
    ("", None),
    ("no-at-sign-here", None),
])
def test_extract_sender_domain(header, expected):
    assert _extract_sender_domain(header) == expected


# ---------- match_message_to_application ----------

def _app(**kw):
    base = {"id": 1, "company": "", "job_title": "", "job_url": "", "date_applied": "2026-01-01"}
    base.update(kw)
    return base


def _msg(**kw):
    base = {"from": "", "subject": "", "body": "", "date": "Wed, 15 Jan 2026 09:00:00 +0100"}
    base.update(kw)
    return base


def test_no_apps_returns_none():
    assert match_message_to_application(_msg(), []) == (None, [])


def test_single_signal_returns_none_with_signal_list():
    # Only company_domain matches — 1 signal, not enough
    msg = _msg(from_="hr@bahn.de", subject="Update", body="Hello")
    msg["from"] = msg.pop("from_")
    apps = [_app(company="Deutsche Bahn AG", job_title="Backend Engineer")]
    app_id, signals = match_message_to_application(msg, apps)
    assert app_id is None
    assert signals == ["company_domain"]


def test_two_signals_match_returns_app_id():
    msg = _msg(
        from_="hr@bahn.de",
        subject="Backend Engineer application update",
        body="Hello",
    )
    msg["from"] = msg.pop("from_")
    apps = [_app(id=42, company="Deutsche Bahn AG", job_title="Backend Engineer")]
    app_id, signals = match_message_to_application(msg, apps)
    assert app_id == 42
    assert set(signals) >= {"company_domain", "subject"}


def test_url_and_body_together_match():
    msg = _msg(
        from_="unknown@sender.io",
        subject="Follow-up",
        body="See the posting: https://example.com/job/backend-engineer  — a Backend Engineer role.",
    )
    msg["from"] = msg.pop("from_")
    apps = [_app(id=7, company="Nowhere", job_title="Backend Engineer",
                 job_url="https://example.com/job/backend-engineer")]
    app_id, signals = match_message_to_application(msg, apps)
    assert app_id == 7
    assert set(signals) >= {"body", "job_url"}


def test_tie_break_by_date_proximity():
    """Two apps at the same signal count — the one closer in date_applied wins."""
    msg = _msg(
        from_="hr@bahn.de",
        subject="Backend Engineer",
        body="",
        date="Wed, 15 Jan 2026 09:00:00 +0100",
    )
    msg["from"] = msg.pop("from_")
    # Both apps hit company_domain + subject.
    older = _app(id=1, company="Deutsche Bahn AG", job_title="Backend Engineer", date_applied="2025-06-01")
    newer = _app(id=2, company="Deutsche Bahn AG", job_title="Backend Engineer", date_applied="2026-01-10")
    app_id, _ = match_message_to_application(msg, [older, newer])
    assert app_id == 2  # newer one wins on proximity


def test_no_match_returns_none():
    msg = _msg(
        from_="newsletter@unrelated.com",
        subject="Newsletter",
        body="This week's jobs",
    )
    msg["from"] = msg.pop("from_")
    apps = [_app(id=1, company="Deutsche Bahn AG", job_title="Backend Engineer")]
    app_id, signals = match_message_to_application(msg, apps)
    assert app_id is None
    assert signals == []


def test_short_title_ignored_to_avoid_false_positives():
    """A 3-char job_title like 'ML' shouldn't count as a subject/body signal."""
    msg = _msg(from_="hr@company.de", subject="ML at scale — newsletter", body="ML jobs")
    msg["from"] = msg.pop("from_")
    apps = [_app(id=1, company="Company", job_title="ML")]
    app_id, signals = match_message_to_application(msg, apps)
    # company_domain matches, but subject and body should NOT because title is too short.
    assert app_id is None
    assert "subject" not in signals
    assert "body" not in signals


def test_gender_suffix_stripped_from_title():
    """job_title with (m/w/d) still matches subject without the suffix."""
    msg = _msg(
        from_="hr@bahn.de",
        subject="Ihre Bewerbung als Backend Engineer",
        body="",
    )
    msg["from"] = msg.pop("from_")
    apps = [_app(id=1, company="Deutsche Bahn AG", job_title="Backend Engineer (m/w/d)")]
    app_id, signals = match_message_to_application(msg, apps)
    assert app_id == 1
    assert set(signals) >= {"company_domain", "subject"}
