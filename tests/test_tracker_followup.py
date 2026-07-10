import gc
import os
import tempfile
import pytest
from datetime import date, timedelta

from nodes import tracker


def _safe_remove(path: str) -> None:
    """Windows-friendly cleanup: SQLite may hold a handle after GC."""
    gc.collect()
    try:
        os.remove(path)
    except OSError:
        pass


# ---------- _default_followup_date (pure) ----------

def test_default_followup_default_is_plus_7_days():
    assert tracker._default_followup_date("2026-07-02") == "2026-07-09"


def test_default_followup_crosses_month_boundary():
    assert tracker._default_followup_date("2026-06-28") == "2026-07-05"


def test_default_followup_crosses_year_boundary():
    assert tracker._default_followup_date("2026-12-30") == "2027-01-06"


def test_default_followup_custom_days():
    assert tracker._default_followup_date("2026-07-02", days=14) == "2026-07-16"


def test_default_followup_zero_days_returns_same_day():
    assert tracker._default_followup_date("2026-07-02", days=0) == "2026-07-02"


def test_default_followup_leap_year():
    # 2028 is a leap year; feb 22 + 7 days = feb 29
    assert tracker._default_followup_date("2028-02-22") == "2028-02-29"


def test_default_followup_invalid_input_raises():
    with pytest.raises(ValueError):
        tracker._default_followup_date("not-a-date")


# ---------- get_due_followups / update_followup_date (DB) ----------

@pytest.fixture
def temp_db(monkeypatch):
    """Point DB_PATH at a fresh temp file and init_db it."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(tracker, "DB_PATH", path)
    tracker.init_db()
    yield path
    _safe_remove(path)


def test_get_due_followups_returns_only_sent_and_waiting(temp_db):
    tracker.save_application("Acme", "Junior Dev", "LinkedIn", "", "https://x/1")
    tracker.save_application("Beta", "Backend", "XING", "", "https://x/2")
    tracker.save_application("Gamma", "Frontend", "Indeed", "", "https://x/3")
    # Move Beta to Rejected — shouldn't show up
    rows = tracker.get_all_applications()
    beta_id = [r[0] for r in rows if r[1] == "Beta"][0]
    tracker.update_status(beta_id, "Rejected")
    # Force everyone's follow-up to today
    today = date.today().strftime("%Y-%m-%d")
    for r in tracker.get_all_applications():
        tracker.update_followup_date(r[0], today)

    due = tracker.get_due_followups()
    companies = [r[1] for r in due]
    assert "Acme" in companies
    assert "Gamma" in companies
    assert "Beta" not in companies


def test_get_due_followups_excludes_future_dates(temp_db):
    tracker.save_application("Future", "Role", "LinkedIn", "", "https://x/f")
    row = tracker.get_all_applications()[0]
    future = (date.today() + timedelta(days=30)).strftime("%Y-%m-%d")
    tracker.update_followup_date(row[0], future)
    assert tracker.get_due_followups() == []


def test_get_due_followups_includes_overdue(temp_db):
    tracker.save_application("Overdue", "Role", "LinkedIn", "", "https://x/o")
    row = tracker.get_all_applications()[0]
    past = (date.today() - timedelta(days=14)).strftime("%Y-%m-%d")
    tracker.update_followup_date(row[0], past)
    due = tracker.get_due_followups()
    assert len(due) == 1
    assert due[0][1] == "Overdue"


def test_get_due_followups_orders_by_follow_up_date_asc(temp_db):
    tracker.save_application("A", "R", "L", "", "https://x/a")
    tracker.save_application("B", "R", "L", "", "https://x/b")
    a_id, b_id = [r[0] for r in tracker.get_all_applications()]
    tracker.update_followup_date(a_id, "2026-07-01")
    tracker.update_followup_date(b_id, "2026-06-20")
    due = tracker.get_due_followups(today_str="2026-07-10")
    assert [r[1] for r in due] == ["B", "A"]


def test_update_followup_date_persists(temp_db):
    tracker.save_application("Acme", "Role", "LinkedIn", "", "https://x/u")
    row = tracker.get_all_applications()[0]
    tracker.update_followup_date(row[0], "2027-01-15")
    row = tracker.get_all_applications()[0]
    assert row[8] == "2027-01-15"  # follow_up_date column


def test_save_application_default_followup_is_plus_7_days(temp_db):
    tracker.save_application("Acme", "Role", "LinkedIn", "", "https://x/s")
    row = tracker.get_all_applications()[0]
    d_applied = date.fromisoformat(row[4])
    d_followup = date.fromisoformat(row[8])
    assert (d_followup - d_applied).days == 7
