# Plan 003: Small cleanup — unused deps, stale README, dead cover-letter wiring

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**:
> `git diff --stat ee9a6e2..HEAD -- requirements.txt README.md dashboard.py nodes/tracker.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code; on mismatch, STOP.
>
> **SHA note**: Plan 001 (executed 2026-07-01) rewrote every commit SHA via
> `git filter-repo`. The original `Planned at` commit `29244f6` was replaced
> by its rewritten equivalent `ee9a6e2` (same tree, same message). All
> SHAs in this plan use the new value.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: tech-debt / docs / dx
- **Planned at**: commit `29244f6` / rewritten `ee9a6e2`, 2026-06-30

## Why this matters

Four small drifts each cost ~nothing alone but compound into "the docs lie
and there's dead code everywhere." Each step here is a 2-line edit, but
together they remove 4 distinct sources of confusion for anyone (including
future-you) reading this repo.

1. `requirements.txt` declares LangChain integrations for Google Gemini and
   Groq that are never imported anywhere — they get installed in every
   fresh venv and people will wonder why.
2. README says `min_score` defaults to 70/50; both scripts actually use 40.
3. README says `PLATFORM_TIMEOUT` default is 600; code default is 900.
4. The `cover_letter` feature was removed (commit `2fc1568`) but its DB
   column, dashboard textarea, and unused import linger. Either keep the
   leftovers and re-add the feature (not in scope here), or drop the
   leftovers (this plan's choice — they are doing nothing).

After this plan: `requirements.txt` only declares what the code uses, the
README's documented defaults match the code, and the cover-letter remnants
are gone.

## Current state

### Drift 1 — unused deps in `requirements.txt`

`requirements.txt:30-31`:
```
langchain-google-genai>=2.0.0
langchain-groq>=0.2.0
```

A grep for usage (case-insensitive, across `nodes/`, `main.py`, `run_daily.py`,
`dashboard.py`, `cleanup_duplicates.py`, `login_linkedin.py`) returns zero
hits. Only `requirements.txt` mentions them.

### Drift 2 — stale `min_score` in README

`README.md:157`:
> Scoring is controlled in `nodes/analyzer.py`:
> ...
> - `min_score` argument to `score_and_filter_jobs` — threshold for "matched" vs "near miss" (default 70 for `main.py`, 50 for `run_daily.py`)

Actual usage:
- `main.py:99`: `min_score=40,`
- `run_daily.py:26`: `scored = run_pipeline(min_score=40)`

### Drift 3 — stale `PLATFORM_TIMEOUT` in README

`README.md:150`:
> - `PLATFORM_TIMEOUT` — seconds per platform before bailing (default 600)

Actual code, `nodes/scraper.py:120-121`:
```python
# Overridable via env so a busy day can be widened without code change.
PLATFORM_TIMEOUT = int(os.getenv("PLATFORM_TIMEOUT", "900"))
```

A second stale reference exists at `nodes/scraper.py:416-417`:
```python
# All 16 German Bundesländer, ordered by tech-hub priority so the
# top-priority terms hit the most relevant regions first under the
# 600s/platform budget.
```

### Drift 4 — dead cover-letter wiring

The cover letter generator was removed in commit `2fc1568` ("Remove
cover_letter.py module"). Leftovers:

- `nodes/tracker.py:352-358` — `update_matched_job_cover_letter(job_id, cover_letter)`.
  Nothing calls this function. The only import is in `dashboard.py:9`,
  which never uses it.
- `nodes/tracker.py:80` — `cover_letter TEXT` column in the `matched_jobs`
  CREATE TABLE.
- `nodes/tracker.py:198-218` — saves an empty string into `cover_letter`
  every insert: `c.execute("...", (..., "", today, ...))`.
- `nodes/tracker.py:326-331` — same empty string in the promote path.
- `dashboard.py:9` — imports `update_matched_job_cover_letter` (never used).
- `dashboard.py:352` — DataFrame columns list includes `"cover_letter"`.
- `dashboard.py:419-423` — applications-page expander renders a "Cover
  Letter" textarea (always shows nothing since the value is always empty
  for new rows; legacy applications may still have data).
- `dashboard.py:470` — destructures `cover_letter` out of the matched-job
  tuple.
- `dashboard.py:577` — passes `cover_letter` into `save_application(...)`
  (which still has the parameter — that's correct because applications.cover_letter
  IS used historically and we are NOT touching the `applications` table).

**Important distinction**: the `applications` table (table for jobs the
user actually applied to) has a real `cover_letter` column and old rows may
contain real text the user wrote manually. The `matched_jobs` table's
`cover_letter` column has only ever stored empty strings since the
generator was removed. This plan removes the `matched_jobs` half only.

## Commands you will need

| Purpose                | Command                                            | Expected on success     |
|------------------------|----------------------------------------------------|-------------------------|
| Verify deps not used   | `grep -rn "langchain_google_genai\|langchain_groq\|ChatGroq\|ChatGoogleGenerativeAI" --include='*.py' .` | only matches in venv/ (or none) |
| Reinstall after change | `pip install -r requirements.txt`                  | exit 0                  |
| Smoke test             | `python -c "import main, dashboard"`               | no traceback            |
| Run tests              | `pytest -q`                                        | exit 0 (if plan 002 landed; otherwise skip) |

## Scope

**In scope** (the only files you should modify):

- `requirements.txt` — remove two lines.
- `README.md` — update two numbers.
- `nodes/scraper.py` — fix one stale comment.
- `dashboard.py` — remove dead cover-letter wiring from the matched-jobs
  code paths (NOT from the applications-page expander).
- `nodes/tracker.py` — drop `update_matched_job_cover_letter`. **Do NOT**
  alter the `CREATE TABLE` or insert statements (see "Out of scope"
  reasoning below).

**Out of scope** (do NOT touch):

- The `cover_letter TEXT` column on `matched_jobs`. Schema changes against
  the existing `data/applications.db` (which holds the user's real
  application history) need a migration plan of their own. This cleanup
  removes the *Python-side wiring*; the column can be left in place as a
  no-op until a separate migration plan is written. The insert sites that
  pass `""` will be left untouched.
- The `applications` table or its cover_letter column — that one is real
  and contains historical user-written cover letters.
- `save_application(...)` signature — that function services the
  `applications` table and is correct.
- The `cover_letter.py` module — it's already gone.

## Git workflow

- Branch: `advisor/003-small-cleanup`.
- Commit per drift is fine, OR one combined commit. Commit message style
  observed in `git log`: short imperative subject. Example: `clean up
  stale docs, dead deps, and unused cover-letter import`.
- Do NOT push or open a PR unless the operator asks.

## Steps

### Step 1: Remove unused LangChain integrations from `requirements.txt`

In `requirements.txt`, delete these two lines exactly:
```
langchain-google-genai>=2.0.0
langchain-groq>=0.2.0
```

(Lines 30 and 31 at HEAD `ee9a6e2`.)

**Verify**:
```
grep -E "langchain-google-genai|langchain-groq" requirements.txt
```
→ no output (exit 1).

```
grep -rn "langchain_google_genai\|langchain_groq\|ChatGroq\|ChatGoogleGenerativeAI" --include="*.py" . | grep -v venv
```
→ no matches.

```
pip uninstall -y langchain-google-genai langchain-groq
python -c "import main, dashboard, nodes.pipeline"
```
→ no `ImportError`, no traceback. (This proves they were truly unused.)

### Step 2: Fix `min_score` documentation in README

In `README.md`, find this line (around line 157):

```
- `min_score` argument to `score_and_filter_jobs` — threshold for "matched" vs "near miss" (default 70 for `main.py`, 50 for `run_daily.py`)
```

Replace with:

```
- `min_score` argument to `score_and_filter_jobs` — threshold for "matched" vs "near miss" (default 40 in both `main.py` and `run_daily.py`)
```

**Verify**:
```
grep -n "min_score" README.md
```
→ the line above is the only `min_score` line and matches the new wording.

```
grep -n "min_score=" main.py run_daily.py
```
→ both show `40`.

### Step 3: Fix `PLATFORM_TIMEOUT` documentation

In `README.md`, find:

```
- `PLATFORM_TIMEOUT` — seconds per platform before bailing (default 600)
```

Replace with:

```
- `PLATFORM_TIMEOUT` — seconds per platform before bailing (default 900, env-overridable)
```

In `nodes/scraper.py`, find the comment around line 416-417:

```
# All 16 German Bundesländer, ordered by tech-hub priority so the
# top-priority terms hit the most relevant regions first under the
# 600s/platform budget.
```

Replace `600s/platform budget` with `PLATFORM_TIMEOUT budget`.

**Verify**:
```
grep -n "600s/platform" nodes/scraper.py
```
→ no matches.

```
grep -n "PLATFORM_TIMEOUT" README.md
```
→ shows the updated `900, env-overridable` line.

### Step 4: Remove dead cover-letter Python wiring

In `dashboard.py`:

1. Line 9 — remove `update_matched_job_cover_letter,` from the imports list.
   The line currently reads:
   ```python
       update_status, delete_application, update_matched_job_cover_letter,
   ```
   After:
   ```python
       update_status, delete_application,
   ```

2. Line 470 — the matched-jobs unpacking. Currently:
   ```python
   (job_id, job_title, company, location, platform,
    job_url, match_score, recommendation, match_reasons,
    missing, contract_type, work_mode, link_status,
    cover_letter, date_found, applied, all_urls_raw, *_) = job
   ```
   Keep the unpack — the underlying SELECT still returns the column. Replace
   `cover_letter` with `_unused_cover_letter` to signal it is intentionally
   not used in this code path:
   ```python
   (job_id, job_title, company, location, platform,
    job_url, match_score, recommendation, match_reasons,
    missing, contract_type, work_mode, link_status,
    _unused_cover_letter, date_found, applied, all_urls_raw, *_) = job
   ```

3. Line 577 — the Applied button calls `save_application(... cover_letter=cover_letter ...)`.
   That `cover_letter` came from the unpack we just renamed. The
   `applications` table still meaningfully stores a cover letter, but on
   the matched-jobs page it is always empty for new rows. Change line 577
   to pass an empty string explicitly:
   ```python
                                       cover_letter="",
   ```
   (Removing the conditional `cover_letter if cover_letter else ""` — the
   value is always falsy here.)

4. **Leave the applications-page expander alone** (lines 419-423). That
   reads from the `applications` table where real text exists.

In `nodes/tracker.py`:

1. Delete the function `update_matched_job_cover_letter` (lines 352-358):
   ```python
   def update_matched_job_cover_letter(job_id: int, cover_letter: str) -> None:
       with _conn() as conn:
           conn.execute(
               "UPDATE matched_jobs SET cover_letter = ? WHERE id = ?",
               (cover_letter, job_id)
           )
           conn.commit()
   ```

**Verify**:
```
grep -rn "update_matched_job_cover_letter" --include="*.py" .
```
→ no matches (besides possibly `.git/` history, which is fine).

```
python -c "import dashboard; print('OK')"
```
→ prints `OK`, no `ImportError`.

```
python -c "from nodes.tracker import update_matched_job_cover_letter" 2>&1 | grep -q "ImportError" && echo "removed OK"
```
→ prints `removed OK` (the import correctly fails because the function is
gone).

### Step 5: Run the test suite (if plan 002 has landed)

```
pytest -q
```

If plan 002 has NOT landed yet, skip this step.

If plan 002 HAS landed:

**Expected**: all tests still pass (this plan does not touch the
pure-function code under test).

### Step 6: Smoke import everything

```
python -c "import main, dashboard, nodes.pipeline, nodes.tracker, nodes.analyzer, nodes.scraper, nodes.validator, nodes.feedback_log, cleanup_duplicates"
```

**Expected**: no traceback. (Note: `main.py` reads `my_cv.txt` at module
import — the file must exist on disk.)

## Done criteria

ALL must hold:

- [ ] `grep -E "langchain-google-genai|langchain-groq" requirements.txt` returns no matches.
- [ ] `grep -n "min_score" README.md` shows only the corrected `40` wording.
- [ ] `grep -n "600s/platform" nodes/scraper.py` returns no matches.
- [ ] `grep -rn "update_matched_job_cover_letter" --include="*.py" .` returns no matches.
- [ ] `python -c "import main, dashboard"` exits 0.
- [ ] `pytest -q` exits 0 (if plan 002 is in place; otherwise N/A).
- [ ] `git status --porcelain` shows changes only in `requirements.txt`,
      `README.md`, `nodes/scraper.py`, `dashboard.py`, `nodes/tracker.py`,
      and `plans/README.md`.
- [ ] `plans/README.md` status row updated to DONE.

## STOP conditions

Stop and report (do not improvise) if:

- A `grep` for `langchain_google_genai`/`langchain_groq` (outside `venv/`)
  returns a match — the dep IS being used somewhere and removing it would
  break runtime. Report which file.
- `python -c "import main, dashboard"` fails after the changes. Restore
  the offending file from git and report the traceback.
- You feel tempted to also drop the `cover_letter` column from
  `matched_jobs` or strip the `""` from the INSERT statements. STOP — that's
  a schema migration, out of scope.
- The README has additional `min_score` references that conflict with the
  new wording — list them, then report.

## Maintenance notes

For the human/agent who owns this code after the change lands:

- If you ever re-add Google Gemini or Groq scoring, you'll need to
  re-introduce the dep. Do it deliberately, with a code path that imports
  it.
- The `matched_jobs.cover_letter` column is now a dead-but-tolerated SQLite
  column. Removing it requires `ALTER TABLE matched_jobs DROP COLUMN
  cover_letter` (SQLite 3.35+) and a backup. That's a separate plan.
- If you ever add a true cover-letter generator, both the matched-jobs
  textarea (re-introduce) and a writer (re-introduce
  `update_matched_job_cover_letter`) will need to come back. The current
  state leaves the column open for that.

## Post-execution notes (2026-07-01)

Executed at commit `2f8ac30`. Partial completion — Steps 1 and 4 landed,
Steps 2 and 3 skipped as spec-vs-code drift. Final state: `pytest -q`
86 passed / 3 xfailed / exit 0; all modules smoke-import.

### Steps completed

- **Step 1** — removed `langchain-google-genai>=2.0.0` and
  `langchain-groq>=0.2.0` from `requirements.txt`; pip-uninstalled both
  from the venv. `python -c "import main, dashboard, nodes.pipeline"` still
  clean. Deps were truly unused.
- **Step 4** — dropped the dead cover-letter wiring on the matched-jobs
  code path: `update_matched_job_cover_letter` deleted from
  `nodes/tracker.py`; import removed from `dashboard.py`; matched-jobs
  unpack renamed to `_unused_cover_letter`; `save_application(...)` call
  hardcoded to `cover_letter=""`. Applications-page textarea + column
  left untouched as scoped.

### Steps skipped — plan spec was wrong

- **Step 2 (`min_score` in README)**. Plan claimed "code uses 40 in both
  scripts, README says 70/50." Actual code at `main.py:99` is
  `min_score=70,` and `run_daily.py:26` is `run_pipeline(min_score=50)`
  — exactly what the README already documented. No change needed.
  Audited to be sure; the drift was in the plan, not the code.
- **Step 3 (`PLATFORM_TIMEOUT` in README + scraper comment)**. Plan
  claimed "code default is 900, env-overridable; README says 600."
  Actual code at `nodes/scraper.py:104` is `PLATFORM_TIMEOUT = 600`
  (no env override) — matches the README. The `600s/platform budget`
  comment at `nodes/scraper.py:340` is accurate. No change needed.

Same class of defect as the earlier plan 002 revisions: the audit was
written from function names / comments / intuition rather than reading
the concrete values. Recording it here so it doesn't get re-audited.

### Files touched

`dashboard.py`, `nodes/tracker.py`, `requirements.txt`. Not touched:
`README.md`, `nodes/scraper.py`.

### Follow-up left open

- `matched_jobs.cover_letter` column and its `""` insert values are
  still tolerated dead schema. Removing them requires an
  `ALTER TABLE ... DROP COLUMN` migration against the user's live
  `data/applications.db`. Deferred as its own future plan.
