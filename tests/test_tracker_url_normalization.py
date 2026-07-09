"""Unit + integration tests for URL canonicalization at write time."""
import gc
import os
import sqlite3
import tempfile
from unittest.mock import patch

import pytest

from nodes.tracker import _normalize_url


def _safe_remove(path: str) -> None:
    """Windows-friendly cleanup: SQLite may hold a handle after GC."""
    gc.collect()
    try:
        os.remove(path)
    except OSError:
        # File will be reclaimed with tmp dir; safe to ignore on Windows.
        pass


# -------- unit tests: _normalize_url --------

@pytest.mark.parametrize("raw,expected", [
    ("https://de.linkedin.com/jobs/view/foo-123?position=1&trackingId=abc",
     "https://de.linkedin.com/jobs/view/foo-123"),
    ("https://de.linkedin.com/jobs/view/foo-123",
     "https://de.linkedin.com/jobs/view/foo-123"),
    ("https://example.com/x/",
     "https://example.com/x"),
    ("HTTPS://EXAMPLE.COM/PATH",
     "https://example.com/path"),
    ("", ""),
    (None, ""),
])
def test_normalize_url_cases(raw, expected):
    assert _normalize_url(raw) == expected


def test_normalize_url_is_idempotent():
    u = "https://de.linkedin.com/jobs/view/foo-4408296319"
    assert _normalize_url(_normalize_url(u)) == u


# -------- integration tests against a fresh temp DB --------

@pytest.fixture()
def temp_db(monkeypatch):
    """Point tracker at a temp DB, initialize schema, yield, cleanup."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr("nodes.tracker.DB_PATH", path)
    from nodes.tracker import init_db
    init_db()
    yield path
    _safe_remove(path)


def test_save_application_stores_canonical_url(temp_db):
    from nodes.tracker import save_application
    raw = "https://xing.com/jobs/foo-123?utm=x"
    save_application("Acme", "Backend Dev", "XING", "", raw)
    with sqlite3.connect(temp_db) as con:
        row = con.execute("SELECT job_url FROM applications").fetchone()
        assert row[0] == "https://xing.com/jobs/foo-123"


def test_save_application_dedupes_across_url_variants(temp_db):
    from nodes.tracker import save_application
    save_application("Acme", "Backend Dev", "LI", "",
                     "https://li.com/jobs/view/foo-123?position=1&refId=A")
    save_application("Acme", "Backend Dev", "LI", "",
                     "https://li.com/jobs/view/foo-123?position=7&refId=B")
    with sqlite3.connect(temp_db) as con:
        n = con.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
        assert n == 1


def test_applications_url_unique_index_blocks_raw_duplicates(temp_db):
    from nodes.tracker import save_application
    save_application("Acme", "Backend Dev", "LI", "",
                     "https://li.com/jobs/view/foo-123?a=1")
    # Bypass save_application and try raw INSERT with same canonical URL
    with sqlite3.connect(temp_db) as con:
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(
                "INSERT INTO applications (job_url) VALUES (?)",
                ("https://li.com/jobs/view/foo-123",)
            )


def test_save_matched_jobs_canonicalizes(temp_db):
    from nodes.tracker import save_matched_jobs
    save_matched_jobs([{
        "title": "Backend", "company": "Acme", "location": "Bochum",
        "platform": "LI", "url": "https://li.com/jobs/view/x-99?trackingId=q",
        "score": 80, "recommendation": "APPLY",
        "match_reasons": [], "missing": [],
        "contract_type": "", "work_mode": "", "link_status": "alive",
    }])
    with sqlite3.connect(temp_db) as con:
        url = con.execute("SELECT job_url FROM matched_jobs").fetchone()[0]
        assert url == "https://li.com/jobs/view/x-99"


def test_save_matched_jobs_second_variant_is_dedup(temp_db):
    from nodes.tracker import save_matched_jobs
    for tid in ("a", "b"):
        save_matched_jobs([{
            "title": "Backend", "company": "Acme", "location": "Bochum",
            "platform": "LI", "url": f"https://li.com/jobs/view/x-99?trackingId={tid}",
            "score": 80, "recommendation": "APPLY",
            "match_reasons": [], "missing": [],
            "contract_type": "", "work_mode": "", "link_status": "alive",
        }])
    with sqlite3.connect(temp_db) as con:
        n = con.execute("SELECT COUNT(*) FROM matched_jobs").fetchone()[0]
        assert n == 1


def test_backfill_dedupes_pre_existing_raw_urls():
    """Simulate an old DB with two rows that differ only in query params.
    After init_db (which runs backfill), only one should remain."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    # Insert two "old" rows with only query-param variation, NO unique index yet.
    # Tables need the columns init_db()'s index creation references (date_found,
    # match_score) since CREATE TABLE IF NOT EXISTS is a no-op on existing tables.
    with sqlite3.connect(path) as con:
        con.execute("CREATE TABLE applications (id INTEGER PRIMARY KEY AUTOINCREMENT, job_url TEXT)")
        con.execute(
            "CREATE TABLE matched_jobs "
            "(id INTEGER PRIMARY KEY AUTOINCREMENT, job_url TEXT, "
            "date_found TEXT, match_score INTEGER)"
        )
        con.execute(
            "CREATE TABLE not_matched_jobs "
            "(id INTEGER PRIMARY KEY AUTOINCREMENT, job_url TEXT)"
        )
        con.execute("INSERT INTO not_matched_jobs (job_url) VALUES (?)",
                    ("https://li.com/jobs/view/x-1?a=1",))
        con.execute("INSERT INTO not_matched_jobs (job_url) VALUES (?)",
                    ("https://li.com/jobs/view/x-1?a=2",))
        con.commit()
    # Now point tracker at this DB and run init_db
    import importlib
    import nodes.tracker as tracker
    orig = tracker.DB_PATH
    tracker.DB_PATH = path
    try:
        tracker.init_db()
        with sqlite3.connect(path) as con:
            n = con.execute("SELECT COUNT(*) FROM not_matched_jobs").fetchone()[0]
            assert n == 1, f"expected 1 row after backfill, got {n}"
            url = con.execute("SELECT job_url FROM not_matched_jobs").fetchone()[0]
            assert url == "https://li.com/jobs/view/x-1", f"expected canonical url, got {url}"
    finally:
        tracker.DB_PATH = orig
        _safe_remove(path)
