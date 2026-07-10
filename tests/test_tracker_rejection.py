import gc
import os
import tempfile
import sqlite3

import pytest

from nodes import tracker


def _safe_remove(path):
    """Windows-friendly cleanup: SQLite may hold a handle after GC."""
    gc.collect()
    try:
        os.remove(path)
    except OSError:
        pass


@pytest.fixture
def temp_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(tracker, "DB_PATH", path)
    tracker.init_db()
    yield path
    _safe_remove(path)


def _seed_job(url: str = "https://x/1") -> int:
    tracker.save_matched_jobs([{
        "title": "Junior Backend", "company": "Acme", "location": "Bochum",
        "platform": "LinkedIn", "url": url, "score": 75,
        "recommendation": "Good Match", "match_reasons": [], "missing": [],
        "contract_type": "Full-time", "work_mode": "Hybrid",
        "link_status": "alive", "job_category": "Backend",
    }])
    with sqlite3.connect(tracker.DB_PATH) as conn:
        row = conn.execute(
            "SELECT id FROM matched_jobs WHERE job_url = ?", (url,)
        ).fetchone()
    return row[0]


def test_init_db_idempotent(temp_db):
    tracker.init_db()
    tracker.init_db()


def test_schema_has_new_rejection_columns(temp_db):
    cols = [r[1] for r in sqlite3.connect(temp_db).execute(
        "PRAGMA table_info(matched_jobs)"
    )]
    assert "rejection_reason" in cols
    assert "rejection_note" in cols


def test_update_rejection_sets_applied_and_reason(temp_db):
    job_id = _seed_job()
    tracker.update_matched_job_rejection(job_id, "wrong-tech", "Java stack only")

    assert tracker.get_applied_status(job_id) == 2
    assert tracker.get_rejection_row(job_id) == ("wrong-tech", "Java stack only")


def test_update_rejection_note_defaults_to_empty(temp_db):
    job_id = _seed_job()
    tracker.update_matched_job_rejection(job_id, "wrong-location")
    assert tracker.get_rejection_row(job_id) == ("wrong-location", "")


def test_update_rejection_overwrites_previous(temp_db):
    job_id = _seed_job()
    tracker.update_matched_job_rejection(job_id, "wrong-tech", "first")
    tracker.update_matched_job_rejection(job_id, "wrong-location", "second")
    assert tracker.get_rejection_row(job_id) == ("wrong-location", "second")


def test_get_rejection_row_returns_none_for_missing_job(temp_db):
    assert tracker.get_rejection_row(999) is None


def test_get_rejection_row_returns_empties_for_unrejected(temp_db):
    job_id = _seed_job()
    assert tracker.get_rejection_row(job_id) == ("", "")


def test_get_rejection_reason_counts_aggregates(temp_db):
    id1 = _seed_job(url="https://x/1")
    id2 = _seed_job(url="https://x/2")
    id3 = _seed_job(url="https://x/3")
    tracker.update_matched_job_rejection(id1, "wrong-tech")
    tracker.update_matched_job_rejection(id2, "wrong-tech")
    tracker.update_matched_job_rejection(id3, "wrong-location")

    counts = dict(tracker.get_rejection_reason_counts())
    assert counts == {"wrong-tech": 2, "wrong-location": 1}


def test_get_rejection_reason_counts_excludes_unrejected(temp_db):
    id1 = _seed_job(url="https://x/1")
    _seed_job(url="https://x/2")  # never rejected
    tracker.update_matched_job_rejection(id1, "wrong-tech")

    assert tracker.get_rejection_reason_counts() == [("wrong-tech", 1)]


def test_get_rejection_reason_counts_excludes_empty_reasons(temp_db):
    id1 = _seed_job(url="https://x/1")
    id2 = _seed_job(url="https://x/2")
    tracker.update_matched_job_rejection(id1, "")   # blank — excluded
    tracker.update_matched_job_rejection(id2, "wrong-tech")

    assert tracker.get_rejection_reason_counts() == [("wrong-tech", 1)]


def test_soft_validation_stores_unknown_reason_verbatim(temp_db):
    """Unknown reasons are stored, not rejected — dropdown drift shouldn't lose data."""
    job_id = _seed_job()
    tracker.update_matched_job_rejection(job_id, "brand-new-reason-2027")
    assert tracker.get_rejection_row(job_id) == ("brand-new-reason-2027", "")
