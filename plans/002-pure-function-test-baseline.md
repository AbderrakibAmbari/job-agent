# Plan 002: Establish a pytest baseline covering the pure-function logic

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**:
> `git diff --stat 29244f6..HEAD -- nodes/tracker.py nodes/analyzer.py nodes/scraper.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: LOW
- **Depends on**: none
- **Category**: tests
- **Planned at**: commit `29244f6`, 2026-06-30

## Why this matters

This repo has **zero** project tests today (`tests/` does not exist, no
`pytest.ini`, no `pyproject.toml`; `python -c "import pytest"` is the only
way to know pytest is even installed). Several pure functions encode the
business rules the rest of the agent depends on — and they are exactly the
kind of regex-heavy, branchy code that drifts silently when edited:

- `nodes/tracker._title_company_key` — the dedup key used both at scrape
  time (`main.py:84-86`) and in the SQLite store. Drift between this and
  `nodes/scraper._title_key` is already a known concern.
- `nodes/analyzer._quick_reject` — the pre-LLM filter. Every false positive
  here costs Anthropic credit; every false negative pollutes the matched
  list.
- `nodes/analyzer._apply_experience_cap` — the score-cap rules.
- `nodes/scraper.extract_city` — parses German location strings.
- `nodes/scraper.deduplicate` — cross-platform dedup.

After this plan: `pytest` runs as a verification gate (used by every
subsequent refactor plan), and a non-trivial subset of the business logic
is locked in by test cases derived from real examples seen in the existing
job logs.

## Current state

In-scope files (read-only — tests should target their pure functions):

- `nodes/tracker.py` lines 14-39 — `_GENDER_RE`, `_COMPANY_SUFFIX_RE`,
  `_norm_title`, `_norm_company`, `_title_company_key`. Excerpt:

  ```python
  _GENDER_RE = re.compile(
      r'\s*\(m/w/d\)|\s*\(w/m/d\)|\s*\(m/f/d\)|\s*\(m/w/x\)|\s*\(w/m/x\)|\s*\(all genders\)',
      re.IGNORECASE,
  )
  _COMPANY_SUFFIX_RE = re.compile(
      r'\b(GmbH\s*&\s*Co\.?\s*KG|GmbH|AG|SE|Ltd\.?|LLC|Inc\.?|KG|e\.V\.|gGmbH|plc)\b',
      re.IGNORECASE,
  )
  def _norm_title(title): return _GENDER_RE.sub('', title or '').lower().strip()
  def _norm_company(company):
      c = _COMPANY_SUFFIX_RE.sub('', company or '').lower()
      return re.sub(r'\s+', ' ', c).strip()
  def _title_company_key(title, company):
      t = _norm_title(title); c = _norm_company(company)
      if c and c not in ('unknown', '', 'n/a'): return f"{t}|{c}"
      return t
  ```

- `nodes/analyzer.py` lines 42-110 — `_apply_experience_cap` and its
  associated regexes (`_JUNIOR_KEYWORDS`, `_PARTTIME_HARD`,
  `_VOLLZEIT_OR_ENTRY`, `_EXPERIENCE_HARD`, `_SAP_TITLE`,
  `_TRAINEE_PROGRAM`).

- `nodes/analyzer.py` lines 280-337 — `_quick_reject` and
  `_SENIOR_TITLE`/`_JUNIOR_TITLE`/`_NON_TECH_TITLE`/`_EXPERIENCE_EXTREME`/
  `_GERMANY_LOCATION`.

- `nodes/scraper.py` lines 143-217 — `extract_city`, `_url_key`,
  `_title_key`, `deduplicate`.

These functions are all pure (no DB, no network, no LLM). They can be
imported and called directly from a test.

**Existing test infrastructure**: none. `requirements.txt` does not declare
`pytest`. There is no `tests/` directory. There is no CI.

**Python version**: README states 3.11+. Type syntax in
`nodes/tracker.py:279` (`-> str | None`) confirms 3.10+ is fine.

## Commands you will need

| Purpose                  | Command                              | Expected on success            |
|--------------------------|--------------------------------------|--------------------------------|
| Install pytest           | `pip install pytest`                 | exit 0                         |
| Run all tests            | `pytest -q`                          | exit 0, all pass               |
| Run a single test file   | `pytest -q tests/test_tracker.py`    | exit 0                         |
| Run tests verbosely      | `pytest -v`                          | exit 0                         |

## Scope

**In scope** (the only files you should create or modify):

- `tests/__init__.py` (create — empty)
- `tests/test_tracker_keys.py` (create)
- `tests/test_analyzer_filters.py` (create)
- `tests/test_scraper_helpers.py` (create)
- `requirements.txt` (modify — add `pytest` line, alphabetical position)
- `pytest.ini` (create) — minimal config so `pytest` from the repo root just
  works.

**Out of scope** (do NOT touch — these are the systems under test):

- `nodes/tracker.py`, `nodes/analyzer.py`, `nodes/scraper.py`,
  `nodes/validator.py`, `nodes/pipeline.py`, `dashboard.py`, `main.py`,
  `run_daily.py`, `cleanup_duplicates.py`.
- Any change to existing function signatures or behavior. If a test reveals
  a bug, document it as a TODO comment in the test, mark it `xfail`, and
  STOP — do not fix the production code in this plan.

## Git workflow

- Branch: `advisor/002-test-baseline`.
- One commit per test file is fine; final commit adds `pytest.ini` +
  `requirements.txt` change.
- Commit message style observed in `git log`: short imperative subject,
  no body required. Example: `add unit tests for tracker dedup keys`.
- Do NOT push or open a PR unless the operator asks.

## Steps

### Step 1: Add pytest to the project

1. Append `pytest` to `requirements.txt` in alphabetical position
   (between `pyee==13.0.1` and `python-dateutil==2.9.0.post0`).
   No version pin needed — use the latest. The line should be exactly:
   ```
   pytest
   ```

2. Install it locally:
   ```
   pip install pytest
   ```

3. Create `pytest.ini` in the repo root:
   ```ini
   [pytest]
   testpaths = tests
   python_files = test_*.py
   addopts = -ra --tb=short
   ```

**Verify**:
```
pytest --version
```
→ prints a pytest version, exit 0.

```
pytest -q
```
→ "no tests ran" (exit code 5 is acceptable here — we have not added any
tests yet). If the command errors out for any other reason, STOP and report.

### Step 2: Create the `tests/` package

1. Create `tests/__init__.py` as an empty file.
2. Make sure the repo root is on `sys.path` when pytest runs. Adding
   `tests/conftest.py` with the following content does this without
   touching production code:

   ```python
   import sys
   from pathlib import Path

   sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
   ```

**Verify**:
```
pytest -q
```
→ still "no tests ran" (exit 5), no import errors.

### Step 3: Tests for `nodes/tracker._title_company_key`

Create `tests/test_tracker_keys.py`. Cover at minimum these cases (use
parametrize where natural):

- `_norm_title` strips `(m/w/d)`, `(w/m/d)`, `(m/f/d)`, `(m/w/x)`,
  `(w/m/x)`, `(all genders)` case-insensitively, and lowercases the result.
  E.g. `_norm_title("Junior Dev (m/w/d)") == "junior dev"`.
- `_norm_title` collapses whitespace via `.strip()` (no whitespace
  normalization beyond `strip`).
- `_norm_company` strips legal suffixes: `GmbH`, `AG`, `SE`, `Ltd`, `LLC`,
  `Inc`, `KG`, `e.V.`, `gGmbH`, `plc`, and the compound `GmbH & Co. KG`.
  E.g. `_norm_company("Acme GmbH") == "acme"` and
  `_norm_company("Acme GmbH & Co. KG") == "acme"`.
- `_norm_company` collapses internal whitespace to single space.
- `_title_company_key`:
  - Includes company when known: `_title_company_key("Junior Dev", "Acme GmbH") == "junior dev|acme"`.
  - Drops company when "Unknown" / empty / "n/a" (case-insensitive):
    `_title_company_key("Junior Dev", "Unknown") == "junior dev"`.
  - Merges across same-title different-suffix companies:
    `_title_company_key("Junior Dev (m/w/d)", "Acme GmbH")` ==
    `_title_company_key("Junior Dev (w/m/d)", "Acme AG")`.

Import as: `from nodes.tracker import _title_company_key, _norm_title, _norm_company`.

**Verify**:
```
pytest -q tests/test_tracker_keys.py
```
→ all pass, exit 0.

### Step 4: Tests for `nodes/analyzer._quick_reject` and `_apply_experience_cap`

Create `tests/test_analyzer_filters.py`. Cover:

For `_quick_reject(job)` returning a reason string or `None`:

- Part-time keywords reject (Werkstudent, Praktikum, Teilzeit, Minijob,
  Midijob, Aushilfe, `geringfügig`, `520 €`, `538 €`, `450 €`). One assertion
  per keyword via parametrize. Example:
  `_quick_reject({"title": "Werkstudent Backend", "description": ""}) is not None`.
- Senior titles reject UNLESS a junior counter-indicator is also present:
  - `{"title": "Senior Backend Developer"}` → rejection reason mentions
    "Senior/Lead".
  - `{"title": "Senior Trainee Programme"}` → returns `None` (trainee
    counter-indicator wins).
- Non-tech titles reject (Vertrieb, Sales, Recruiter, Buchhalter, Logistik).
- 5+ years experience reject:
  `{"title": "Junior Backend", "description": "5+ Jahre Erfahrung"}` →
  rejection mentions "5+ years".
- Location outside Germany rejects when not remote:
  `{"title": "Junior Backend", "location": "Zürich"}` → rejection mentions
  the location.
- Location remote anywhere passes:
  `{"title": "Junior Backend", "location": "Remote"}` → returns `None`.

For `_apply_experience_cap(job)` (called *after* the LLM scored, modifies
`job` in place):

- Part-time hard-reject sets score=0 even when LLM gave high:
  `_apply_experience_cap({"title": "Werkstudent Junior", "description": "", "score": 90})["score"] == 0`.
- 3+ years requirement caps score at 40:
  `{"title": "Junior", "description": "3 Jahre Erfahrung", "score": 80}` →
  score becomes 40.
- No-junior/no-Vollzeit indicator caps score at 60:
  `{"title": "Backend Developer", "description": "", "score": 85}` → 60.
- Vollzeit keyword exempts the 60 cap:
  `{"title": "Backend Developer", "description": "Vollzeit Festanstellung", "score": 85}` → 85 (no cap).
- SAP role caps at 55 when title matches SAP and category is SAP/ERP:
  `{"title": "SAP Consultant", "description": "", "score": 90, "job_category": "SAP/ERP"}` → 55.
- Trainee SAP roles exempt the SAP cap:
  `{"title": "SAP Trainee", "description": "", "score": 90, "job_category": "SAP/ERP"}` → not capped to 55.

**Verify**:
```
pytest -q tests/test_analyzer_filters.py
```
→ all pass, exit 0.

### Step 5: Tests for `nodes/scraper.extract_city` and `deduplicate`

Create `tests/test_scraper_helpers.py`. Cover:

For `extract_city(location: str) -> str`:

- Postcode + city: `extract_city("44801 Bochum") == "Bochum"`.
- City + region with comma: `extract_city("Bochum, NRW") == "Bochum"`.
- Empty / None-like: `extract_city("") == "Unknown"`, `extract_city(None) == "Unknown"`.
- Trailing district `gebiet`: `extract_city("Ruhrgebiet") == "Ruhr"`.
- Parens stripped: `extract_city("Bochum (44801)") == "Bochum"`.

For `_url_key(url)`:

- Strips query string: `_url_key("https://X.de/job/1?utm=ad") == "https://x.de/job/1"`.
- Strips trailing slash: `_url_key("https://X.de/job/1/") == "https://x.de/job/1"`.
- Empty/None: `_url_key("") == ""`, `_url_key(None) == ""`.

For `deduplicate(jobs: list) -> list`:

- Two jobs with identical normalized URL → deduplicated to one entry,
  but the second platform URL is merged into the surviving entry's
  `urls` list.
- Two jobs with same title+company, different URLs, different platforms →
  merged into one entry with two URLs in `urls`.
- "Unknown" company is upgraded to a real company when the second copy
  has one.

Use small fixture-style dicts inline; you do NOT need to call any real
scraper.

**Verify**:
```
pytest -q tests/test_scraper_helpers.py
```
→ all pass, exit 0.

### Step 6: Full test-suite run

```
pytest -v
```

**Expected**: all three new test files run, all tests pass, no warnings
escalate to errors. Count: should be roughly 30–50 tests total
(parametrize generates many).

### Step 7: Verify no production code was modified

```
git diff --stat 29244f6..HEAD -- nodes/ main.py run_daily.py dashboard.py cleanup_duplicates.py
```

**Expected**: empty output — only files under `tests/`, plus
`requirements.txt` and `pytest.ini`, should appear in the full diff.

## Test plan

This plan IS the test plan. Done criteria below are the verification gate.

## Done criteria

ALL must hold:

- [ ] `pytest --version` exits 0.
- [ ] `pytest -q` exits 0 and runs at least 30 tests.
- [ ] `tests/test_tracker_keys.py`, `tests/test_analyzer_filters.py`,
      `tests/test_scraper_helpers.py`, `tests/conftest.py`,
      `tests/__init__.py`, and `pytest.ini` all exist.
- [ ] `requirements.txt` contains a `pytest` line.
- [ ] `git diff --stat 29244f6..HEAD -- nodes/ main.py run_daily.py dashboard.py cleanup_duplicates.py`
      is empty.
- [ ] `plans/README.md` status row updated to DONE.

## STOP conditions

Stop and report (do not improvise) if:

- The drift check shows `nodes/tracker.py`, `nodes/analyzer.py`, or
  `nodes/scraper.py` changed since `29244f6` — verify the excerpts in
  "Current state" still match before continuing.
- Any test fails because the production function behaves differently from
  the expected case (i.e. you found a bug). Mark the test `@pytest.mark.xfail`
  with a clear `reason="..."` string and STOP — fixing the bug is
  out-of-scope for this plan.
- You find yourself wanting to add imports to `nodes/*.py` to make a function
  testable (e.g. moving an inline `from nodes.tracker import ...` to module
  scope). That's a refactor, not a test plan. STOP and report.

## Maintenance notes

For the human/agent who owns this code after the change lands:

- These tests are the verification gate for future refactor plans
  (specifically plan 005, which collapses `main.py` into `run_pipeline()`).
  Keeping them green is the safety net.
- Add a test alongside any change to regex constants in
  `nodes/analyzer.py` or `nodes/tracker.py` — these are exactly the spots
  that drift undetected.
- A CI step `pytest -q` can be added later (e.g. in a GitHub Action) when
  the repo grows beyond personal use. For now, the operator runs it
  manually before merging.
- Coverage targets: this baseline does NOT aim to cover scraper internals
  (Playwright/network), validator (network), tracker DB writes, or the
  LLM-calling code. Those need integration tests with mocks/fixtures —
  deferred.
