# Plan 017 — Canonical URL at write time + `applications` UNIQUE index

**Planned at commit**: `59b4be3` (main)
**Category**: Correctness — DB integrity
**Effort**: M
**Risk**: LOW–MEDIUM (schema-touching migration; recoverable via backup)
**Dependencies**: plan 016 (one-shot dedup — must be DONE first so migration doesn't hit collisions on old dupes; already applied to real DB)

## Why this matters

Every daily scrape re-visits the same LinkedIn postings under URLs that vary only in tracking params:

```
https://de.linkedin.com/jobs/view/typo3-developer-w-m-d-at-schaffrath%C2%AE-4408296319?position=1&pageNum=0&refId=<HASH-A>&trackingId=<HASH-B>
https://de.linkedin.com/jobs/view/typo3-developer-w-m-d-at-schaffrath%C2%AE-4408296319?position=3&pageNum=0&refId=<HASH-C>&trackingId=<HASH-D>
```

The `UNIQUE INDEX ... ON not_matched_jobs(job_url)` treats these as distinct. Result: the same posting re-inserts every scrape day, and plan 016 had to hand-clean 24 dupes.

A pre-INSERT filter exists (`nodes/pipeline.py:39-40`) using `_url_key()` from `nodes/scraper.py:137-139` which correctly canonicalizes URLs at READ time. But INSERTs still store the raw URL, so the UNIQUE index can't defend against the same job appearing twice in one scrape batch (multiple search terms hitting the same posting) or a stale in-memory set.

A separate gap: the `applications` table has NO UNIQUE index on `job_url` at all. Plan 016 found and removed one duplicate there.

## What this plan does

1. Store the **canonical URL** (query-stripped, trailing-slash-stripped, lowercased) in `job_url` at INSERT time across all four write paths.
2. Backfill existing rows so their `job_url` values are canonical.
3. Add a partial UNIQUE index on `applications.job_url` — matching the pattern already used on `matched_jobs` and `not_matched_jobs`.
4. Keep `all_urls` (matched_jobs JSON column) using the raw URLs — it's the audit trail of original hits per platform.

## Environment

- Windows 11, bash shell, Python 3.14 venv at `C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe`
- Verification gate: `"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -m pytest -q` — baseline 143 passed as of `59b4be3`

## Drift check (do first)

```bash
git rev-parse --short HEAD
"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -m pytest -q 2>&1 | tail -3
```

Expected: HEAD is `59b4be3` (or a descendant with plan 012 merged). Test suite ≥ 143 passed, 0 failed.

Also verify the DB is post-plan-016 (dedup applied):

```bash
"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -c "
import sqlite3
con = sqlite3.connect('data/applications.db')
cur = con.cursor()
for t in ('applications', 'matched_jobs', 'not_matched_jobs'):
    n = cur.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
    print(f'{t}: {n}')
"
```

Expected: `applications: 138`, `matched_jobs: 777`, `not_matched_jobs: 2921`.

If any of those differ, STOP — plan 016 wasn't applied, or the DB has drifted. Do not proceed until plan 016 is DONE against the current DB.

## Files in scope
- `nodes/tracker.py` — add `_normalize_url` + backfill + UNIQUE index + wire into all INSERTs
- `nodes/pipeline.py` — simplify `_url_key` usage (URLs in DB are now canonical, no runtime strip needed there)
- `tests/test_tracker_url_normalization.py` — NEW file, unit + integration tests
- `plans/README.md` — status flip after execution

## Files explicitly out of scope
- `nodes/scraper.py` — leave `_url_key` alone (still useful for per-batch dedup)
- `nodes/analyzer.py`, `dashboard.py`, `run_daily.py` — no touches
- `nodes/validator.py` — do not touch URL-alive checks
- Any other `.db` file or scrape log

## Current-state excerpts

### `nodes/tracker.py:1-11` (imports)
```python
import re
import sqlite3
import json
import shutil
import glob
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)
DB_PATH = "data/applications.db"
```

### `nodes/tracker.py:161-182` (save_application — no dedup on job_url alone, no UNIQUE constraint)
```python
def save_application(company: str, job_title: str, platform: str,
                     cover_letter: str, job_url: str) -> None:
    with _conn() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT id FROM applications
            WHERE job_url = ? OR (company = ? AND job_title = ?)
        """, (job_url, company, job_title))
        if c.fetchone():
            return
        c.execute("""
            INSERT INTO applications
            (company, job_title, platform, date_applied,
             cover_letter, job_url, follow_up_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            company, job_title, platform,
            datetime.now().strftime("%Y-%m-%d"),
            cover_letter, job_url,
            datetime.now().strftime("%Y-%m-%d"),
        ))
        conn.commit()
```

### `nodes/tracker.py:185-244` (save_matched_jobs — writes raw `job.get("url", "").strip()`)
The relevant lines: `job.get("url", "").strip()` used at both `INSERT` (line 207) and the merge-lookup (line 226). Both must be replaced by `_normalize_url(job.get("url", ""))`.

### `nodes/tracker.py:247-276` (save_not_matched_jobs — writes raw `job.get("url", "").strip()`)
Line 264.

### `nodes/tracker.py:294-335` (promote_not_matched_to_matched — writes `(job_url or "").strip()`)
Line 327.

### `nodes/tracker.py:391-403` (get_known_urls — normalises at READ time; can be simplified after backfill)
```python
def get_known_urls() -> set:
    """Return normalised URLs of every job already in matched_jobs or not_matched_jobs."""
    with _conn() as conn:
        matched = conn.execute(
            "SELECT job_url FROM matched_jobs WHERE job_url IS NOT NULL AND job_url != ''"
        ).fetchall()
        not_matched = conn.execute(
            "SELECT job_url FROM not_matched_jobs WHERE job_url IS NOT NULL AND job_url != ''"
        ).fetchall()
    urls = set()
    for (url,) in matched + not_matched:
        urls.add(url.split("?")[0].rstrip("/").lower())
    return urls
```

### `nodes/scraper.py:137-139` (existing canonical form — keep in place, reference from tracker)
```python
def _url_key(url: str) -> str:
    """Normalise a URL for dedup: strip query params, trailing slash, lowercase."""
    return url.split("?")[0].rstrip("/").lower() if url else ""
```

### `nodes/pipeline.py:39-40` (pre-scrape filter)
```python
known_urls = get_known_urls()
after_url = [j for j in alive if _url_key(j.get("url", "")) not in known_urls]
```

## Steps

### Step 1 — Add `_normalize_url` in `tracker.py`

Insert after `_title_company_key()` (around line 40), before `_conn()`:

```python
def _normalize_url(url: str) -> str:
    """Canonical form used for storage + UNIQUE index.

    Strips query string, trailing slash, and lowercases. Idempotent —
    safe to call on already-canonical URLs. Must stay in sync with
    `nodes.scraper._url_key`.
    """
    return url.split("?")[0].rstrip("/").lower() if url else ""
```

**Do not import `_url_key` from `nodes.scraper`** — creating a `tracker → scraper` import risks a circular dep (scraper.py may need tracker at some point). Duplicate the 1-line function; add a comment on both sides.

Verify:
```bash
"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -c "
from nodes.tracker import _normalize_url
assert _normalize_url('https://de.linkedin.com/jobs/view/foo-123?position=1&trackingId=abc') == 'https://de.linkedin.com/jobs/view/foo-123'
assert _normalize_url('') == ''
assert _normalize_url(None) == ''
assert _normalize_url('https://example.com/x/') == 'https://example.com/x'
# idempotence
u = 'https://de.linkedin.com/jobs/view/foo-123'
assert _normalize_url(_normalize_url(u)) == u
print('normalize_url OK')
"
```

Expected output: `normalize_url OK`.

### Step 2 — Wire into all four write paths in `tracker.py`

Replace every occurrence of raw URL usage in INSERTs with `_normalize_url(...)`. The list:

1. `save_application` (line 168): `job_url` in SELECT and INSERT — pass through `_normalize_url` once and use the result in both.
2. `save_matched_jobs` (lines 207, 226): `job.get("url", "").strip()` — replace with `_normalize_url(job.get("url", ""))`. Do it once above the loop body: `raw_url = job.get("url", ""); norm_url = _normalize_url(raw_url)`. Use `norm_url` in the INSERT and the merge-lookup SELECT. The `all_urls` JSON should continue to store the raw URL per platform (audit trail).
3. `save_not_matched_jobs` (line 264): replace with `_normalize_url(job.get("url", ""))`.
4. `promote_not_matched_to_matched` (line 327): replace with `_normalize_url(job_url or "")`.

Also update `save_application`'s guard clause so it dedupes against the canonical URL:

```python
def save_application(company: str, job_title: str, platform: str,
                     cover_letter: str, job_url: str) -> None:
    norm_url = _normalize_url(job_url)
    with _conn() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT id FROM applications
            WHERE job_url = ? OR (company = ? AND job_title = ?)
        """, (norm_url, company, job_title))
        if c.fetchone():
            return
        c.execute("""
            INSERT INTO applications
            (company, job_title, platform, date_applied,
             cover_letter, job_url, follow_up_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            company, job_title, platform,
            datetime.now().strftime("%Y-%m-%d"),
            cover_letter, norm_url,
            datetime.now().strftime("%Y-%m-%d"),
        ))
        conn.commit()
```

### Step 3 — Backfill migration inside `init_db()`

Add a new function `_backfill_normalize_urls(conn)` and call it from `init_db()` AFTER the schema-migration `try/except` block and BEFORE the index creation.

```python
def _backfill_normalize_urls(conn):
    """One-shot: rewrite job_url in all three tables to canonical form.
    Idempotent — subsequent runs find already-canonical URLs and no-op.
    Collisions are impossible if plan 016 was applied; if any occur (e.g.
    fresh DB with unexpected data), the earliest id wins and later dupes
    are deleted.
    """
    cur = conn.cursor()
    for table in ("applications", "matched_jobs", "not_matched_jobs"):
        rows = cur.execute(
            f"SELECT id, job_url FROM {table} "
            f"WHERE job_url IS NOT NULL AND job_url != ''"
        ).fetchall()
        # Build a normalized-URL → surviving-id map (keep earliest id per group)
        keeper = {}
        to_delete = []
        for rid, url in rows:
            norm = _normalize_url(url)
            if not norm:
                continue
            if norm in keeper:
                to_delete.append(rid)
            else:
                keeper[norm] = rid
        # Delete late-arriving collisions
        if to_delete:
            cur.executemany(
                f"DELETE FROM {table} WHERE id = ?",
                [(rid,) for rid in to_delete],
            )
            logger.info(
                "Backfill: dropped %d URL collisions from %s", len(to_delete), table
            )
        # Now UPDATE only rows whose stored URL differs from canonical
        updated = 0
        for norm, rid in keeper.items():
            cur.execute(
                f"UPDATE {table} SET job_url = ? WHERE id = ? AND job_url != ?",
                (norm, rid, norm),
            )
            if cur.rowcount:
                updated += 1
        if updated:
            logger.info(
                "Backfill: normalized %d URLs in %s", updated, table
            )
    conn.commit()
```

Wire it into `init_db()` right after the `matched_jobs` schema-migration `try/except` block and before the CREATE UNIQUE INDEX statements:

```python
        # Safe column migrations
        for col, definition in [
            ("applied",       "INTEGER DEFAULT 0"),
            ("all_urls",      "TEXT DEFAULT '[]'"),
            ("job_category",  "TEXT DEFAULT 'Other'"),
        ]:
            try:
                c.execute(f"ALTER TABLE matched_jobs ADD COLUMN {col} {definition}")
            except Exception:
                pass

        # --- BEGIN plan 017 additions ---
        _backfill_normalize_urls(conn)

        c.execute("""
            CREATE TABLE IF NOT EXISTS not_matched_jobs (
                ...
```

Wait — `not_matched_jobs`'s CREATE TABLE is a few lines below and the backfill needs the table to exist. Reorder:

The correct placement is AFTER all three `CREATE TABLE IF NOT EXISTS` statements (applications, matched_jobs, not_matched_jobs), AFTER the safe column migrations, but BEFORE any UNIQUE INDEX creation on the tables the migration touches. That way the migration runs on the full schema, and the UNIQUE indexes are then created (or re-created) safely on canonical data.

Also add the new UNIQUE index on `applications.job_url`:

```python
        c.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_applications_url
            ON applications(job_url)
            WHERE job_url IS NOT NULL AND job_url != ''
        """)
```

Place it alongside the other index creations.

### Step 4 — Simplify `get_known_urls`

Since DB URLs are now canonical after backfill, `get_known_urls` no longer needs to normalize at read time. Change the return-set construction to:

```python
    urls = set()
    for (url,) in matched + not_matched:
        urls.add(url)  # already canonical
    return urls
```

This is a defensive simplification, not a functional change — since `_url_key(canonical) == canonical`, the old behaviour still works. Delete the `url.split("?")[0].rstrip("/").lower()` line and replace with `url`.

Add a one-line comment above: `# URLs stored canonical since plan 017; no runtime normalization needed`.

### Step 5 — Verify migration on a copy of the real DB

Run `init_db()` from the repo root — this triggers the backfill against the real DB. **Back up first:**

```bash
cp data/applications.db data/applications.db.bak.plan017
"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -c "
from nodes.tracker import init_db
init_db()
print('init_db done')
"
```

Then verify:
```bash
"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -c "
import sqlite3
con = sqlite3.connect('data/applications.db')
cur = con.cursor()

# Post-migration counts
for t in ('applications', 'matched_jobs', 'not_matched_jobs'):
    n = cur.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
    print(f'{t}: {n}')

# No URLs contain '?' anymore
for t in ('applications', 'matched_jobs', 'not_matched_jobs'):
    n = cur.execute(f\"SELECT COUNT(*) FROM {t} WHERE job_url LIKE '%?%'\").fetchone()[0]
    print(f'{t} URLs with query string remaining: {n}')

# No trailing slashes
for t in ('applications', 'matched_jobs', 'not_matched_jobs'):
    n = cur.execute(f\"SELECT COUNT(*) FROM {t} WHERE job_url LIKE '%/'\").fetchone()[0]
    print(f'{t} URLs with trailing slash remaining: {n}')

# UNIQUE index exists on applications
row = cur.execute(\"\"\"
    SELECT name FROM sqlite_master
    WHERE type='index' AND tbl_name='applications' AND sql LIKE '%UNIQUE%'
\"\"\").fetchone()
print(f'applications UNIQUE URL index: {row[0] if row else \"MISSING\"}')

# Attempt duplicate insert — should raise IntegrityError
try:
    cur.execute(
        \"INSERT INTO applications (job_url) SELECT job_url FROM applications LIMIT 1\"
    )
    print('DUPLICATE INSERT UNEXPECTEDLY SUCCEEDED — FAIL')
except sqlite3.IntegrityError:
    print('duplicate insert correctly rejected — OK')
"
```

**Expected:**
- `applications: 138`, `matched_jobs: 777`, `not_matched_jobs: 2921` (unchanged from plan 016)
- All three "URLs with query string remaining" → `0`
- All three "URLs with trailing slash remaining" → `0`
- `applications UNIQUE URL index: idx_applications_url`
- `duplicate insert correctly rejected — OK`

If counts changed (someone added rows since plan 016), that's fine — the important checks are the zero query strings and the successful UNIQUE rejection. If either fails, STOP and report.

Do NOT commit the migrated DB. This step is validation only. The real DB will re-migrate when the pipeline starts (idempotent — no-op the second time).

### Step 6 — Tests

Create `tests/test_tracker_url_normalization.py`:

```python
"""Unit + integration tests for URL canonicalization at write time."""
import os
import sqlite3
import tempfile
from unittest.mock import patch

import pytest

from nodes.tracker import _normalize_url


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
    os.remove(path)


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
    # Insert two "old" rows with only query-param variation, NO unique index yet
    with sqlite3.connect(path) as con:
        con.execute("CREATE TABLE applications (id INTEGER PRIMARY KEY AUTOINCREMENT, job_url TEXT)")
        con.execute("CREATE TABLE matched_jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, job_url TEXT)")
        con.execute("CREATE TABLE not_matched_jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, job_url TEXT)")
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
        os.remove(path)
```

Run:
```bash
"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -m pytest tests/test_tracker_url_normalization.py -q
```

Expected: **11 passed** (7 parametrized `_normalize_url` cases counted as separate + 5 integration + 1 idempotence + 1 backfill = 14 test items; count may vary by parametrize count. Check that all pass and nothing fails.)

### Step 7 — Full suite gate

```bash
"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -m pytest -q 2>&1 | tail -3
```

Expected: existing tests all still pass. New tests all pass. Baseline was 143 → after this plan, ≥ 154 (143 + 11).

If any pre-existing test breaks, STOP. The most likely offender is a test that hits `save_application` or `save_matched_jobs` with a raw URL and asserts the exact stored value — such tests need updating to expect the canonical form.

### Step 8 — Commit + README

Commit format matches plan 014's pattern:
```
Plan 017: canonicalize URL at write time + applications UNIQUE index
```

Update `plans/README.md` row 017 to:
```
| 017  | Canonical URL at write time + `applications` UNIQUE index          | P2       | M      | LOW  | 016        | DONE — `_normalize_url` wired into 4 write paths; backfill migration idempotent; UNIQUE partial index on `applications.job_url`; N new tests; suite Kp/0xf/0f (commit <SHA>). |
```

Where `N` is the number of new tests and `K` is the resulting total, `<SHA>` is the final commit SHA (amend once to insert per plan 014/012 pattern).

Also add a new row for 017 in the `Recommended order for plans 009–015` section — actually rename that heading to `Recommended order for plans 009–017` or add a note that 017 is a strict dependent of 016. Keep numbering monotonic.

## Done criteria (machine-checkable)

1. `pytest -q` exits 0 with count ≥ 154.
2. `SELECT COUNT(*) FROM applications WHERE job_url LIKE '%?%'` returns 0.
3. `SELECT COUNT(*) FROM matched_jobs WHERE job_url LIKE '%?%'` returns 0.
4. `SELECT COUNT(*) FROM not_matched_jobs WHERE job_url LIKE '%?%'` returns 0.
5. `SELECT name FROM sqlite_master WHERE tbl_name='applications' AND sql LIKE '%UNIQUE%'` returns exactly one row named `idx_applications_url`.
6. A raw `INSERT INTO applications (job_url) VALUES (<canonical URL already present>)` raises `IntegrityError`.
7. `plans/README.md` row 017 status is `DONE — ...`.

## STOP conditions

- **Drift**: HEAD isn't `59b4be3` or a descendant, or the DB counts don't match plan-016's post-state.
- **Backfill count mismatch**: after `_backfill_normalize_urls`, the row-count of any table drops by more than 0 (implies the plan-016 dedup was incomplete or the DB has drifted). Post-backfill: `applications: 138`, `matched_jobs: 777`, `not_matched_jobs: 2921` exactly.
- **UNIQUE index rejection fails**: the sanity test at end of Step 5 doesn't raise `IntegrityError`.
- **Pre-existing tests break** and the fix requires touching files outside "in scope."
- **`_url_key` in scraper.py diverges** from `_normalize_url` — if you find yourself wanting to change scraper.py's function, STOP and report.

STOP means: don't push through, report the exact observation and roll back your changes.

## Test plan (recap)

- **New test file**: `tests/test_tracker_url_normalization.py`
- **Pattern to follow**: `tests/test_analyzer_filters.py` (existing parametrize + monkeypatch style)
- **What each test covers**:
  - Unit: `_normalize_url` on various inputs (parametrized, incl. None/empty)
  - Idempotence: `_normalize_url` called twice = same
  - Integration: `save_application` stores canonical URL, dedupes cross-variant
  - Integration: `save_matched_jobs` canonicalizes + dedupes
  - Migration: backfill on a synthetic pre-migration DB collapses dupes
  - Constraint: raw INSERT of duplicate canonical URL raises IntegrityError

## Maintenance note

- If a new scraper is added that produces URLs with meaningful path-level uniqueness (e.g. `linkedin.com/jobs/view/foo/apply` vs `.../foo` are distinct), revisit `_normalize_url` — the current version treats them the same after query strip if paths differ, which is fine. Only issue would be a scraper that puts the job ID in a query param (e.g. `?jobId=123`); such a URL would collapse to the site root after normalization. If that happens, STOP and design a per-platform normalizer.
- `nodes.scraper._url_key` and `nodes.tracker._normalize_url` are intentionally duplicated to avoid a circular import. Both are one-liners; if you change one, change the other and add a matching test in both `test_analyzer_filters.py` (if any) and `test_tracker_url_normalization.py`.
- The backfill in `init_db()` runs on every process start. Cost is O(rows) — ~4k rows takes <100ms on this box. If the DB grows past ~1M rows, gate the backfill behind a schema-version flag.
