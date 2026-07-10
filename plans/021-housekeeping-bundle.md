# Plan 021: Housekeeping bundle (orphan module + stale log line + import hygiene + pytest pin)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 69d5279..HEAD -- nodes/feedback_log.py run_daily.py dashboard.py nodes/tracker.py requirements.txt`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P3
- **Effort**: S
- **Risk**: LOW
- **Depends on**: 013 (which removed the last `feedback_log` caller); 019 (which retired Indeed)
- **Category**: tech-debt
- **Planned at**: commit `69d5279`, 2026-07-10

## Why this matters

Four small drifts have accumulated. None is urgent; together they clean
up ~85 lines of dead code, stop a misleading operational log, remove a
lingering underscore-prefixed import into UI code, and align
`requirements.txt` with the rest of the pinned deps. This is
housekeeping — one merge, one PR, no behavior change.

Findings covered (from the 2026-07-10 audit against `69d5279`):

1. **`nodes/feedback_log.py` is orphan.** Plan 013 removed the last
   caller (`from nodes.feedback_log import append_feedback` was deleted
   from `dashboard.py:6`). Grep across `**/*.py` confirms zero callers.
   Plan 013's maintenance notes explicitly deferred this cleanup to a
   follow-up. This is it.
2. **`run_daily.py:65` names retired platforms.** Log message reads
   `"scrape (Indeed/Stepstone/XING/LinkedIn/Glassdoor)"`, but Indeed
   was retired in plan 019 and Arbeitsagentur (via a separate API
   scraper at `nodes/scraper.py:807`) has been contributing rows since
   at least 2026-05. Misleading operational log every daily run.
3. **`dashboard.py:438` imports a private tracker helper inside a
   button handler.** `from nodes.tracker import _default_followup_date`
   runs on every "Snooze +7d" click. Underscore-prefixed = reaching
   into a private API from another module. Belongs in the top-of-file
   import block, and the tracker should expose it publicly.
4. **`pytest` is unpinned in `requirements.txt`.** Every other package
   is pinned; `pytest` is a bare name. A future breaking release lands
   on the next `pip install`. Currently installed: `9.1.1`.

## Current state

Relevant files:

- **`nodes/feedback_log.py`** — 83-line module. Three public functions
  (`append_feedback`, `get_feedback_for_job`, `list_recent_feedback`).
  Grep confirms zero importers across the codebase since plan 013.
  Corresponding data file `data/feedback_log.txt` lives in a
  gitignored directory (`data/` is in `.gitignore` at line 15).

- **`run_daily.py:65`** — the log line:
  ```python
  log("Running pipeline: scrape (Indeed/Stepstone/XING/LinkedIn/Glassdoor) → validate → score → save...")
  ```
  The truth per code + live DB inspection:
  - `PLATFORM_CONFIGS.keys()` in `nodes/scraper.py` = `['Stepstone', 'XING', 'LinkedIn', 'Glassdoor']` (Indeed removed by plan 019)
  - Arbeitsagentur is scraped separately via `_run_arbeitsagentur` at `nodes/scraper.py:807`, submitted as a parallel future at `nodes/scraper.py:857`. It is NOT in `PLATFORM_CONFIGS`.
  - Live DB confirms all 5 platforms have contributed rows in 2026: `LinkedIn (345)`, `XING (313)`, `Stepstone (88)`, `Arbeitsagentur (17)`, `Glassdoor (14)`.

- **`dashboard.py:438-442`** — inside the "Snooze +7d" button handler:
  ```python
  with fu_cols[3]:
      if st.button("Snooze +7d", key=f"fu_snz_{app_id}"):
          from nodes.tracker import _default_followup_date
          today = datetime.now().strftime("%Y-%m-%d")
          update_followup_date(app_id, _default_followup_date(today))
          st.cache_data.clear()
          st.rerun()
  ```
  The top-of-file tracker import block is at `dashboard.py:7-16`:
  ```python
  from nodes.tracker import (
      init_db, get_all_applications, get_matched_jobs,
      update_status, delete_application,
      update_matched_job_company, update_matched_job_applied,
      get_applied_status, get_applied_statuses, save_application,
      get_not_matched_jobs, get_scrape_dates,
      promote_not_matched_to_matched,
      get_due_followups, update_followup_date,  # Plan 009
      update_matched_job_rejection, get_rejection_row,  # Plan 013
  )
  ```

- **`nodes/tracker.py`** — the current definition of the follow-up helper:
  ```python
  # around line 260-ish, verify with grep
  def _default_followup_date(from_date_str: str, days: int = 7) -> str:
      d = date.fromisoformat(from_date_str)
      return (d + timedelta(days=days)).strftime("%Y-%m-%d")
  ```
  Only two callers: `save_application` (same module) and the button
  handler in `dashboard.py:438`.

- **`requirements.txt`** — `pytest` appears on its own line, no version:
  ```
  ...
  pytest
  python-dateutil==2.9.0.post0
  ...
  ```
  Every other dep is `name==x.y.z`. Currently installed `pytest`
  version (from `python -c "import pytest; print(pytest.__version__)"`)
  is `9.1.1`.

Repo conventions:

- All DB writes go through `nodes/tracker.py`. Dashboard never runs
  raw SQL. Public helpers are named without leading underscore.
- Requirements pinning: exact-version (`==`) for every third-party
  dep. See `anthropic==0.85.0`, `streamlit==1.55.0` etc.
- Log lines in `run_daily.py` use plain `f"..."` strings via the
  local `log()` helper.
- Scraper platforms live in two categories: Playwright-based (in
  `PLATFORM_CONFIGS`) and API-based (Arbeitsagentur). A single flat
  list of "platforms scraped by this run" doesn't currently exist —
  keep the log line hand-written (see Step 2 note).

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Activate venv | `source venv/Scripts/activate` (Git Bash) | prompt shows `(venv)` |
| Tests | `venv/Scripts/python.exe -m pytest -q` | 236 passed, exit 0 |
| Import smoke | `venv/Scripts/python.exe -c "import dashboard; print('OK')"` | prints `OK` (Streamlit warnings on stderr are OK) |
| Grep audit | `grep -rn "append_feedback\|feedback_log\|_default_followup_date" --include="*.py"` | see Step 5 |

## Scope

**In scope** (the only files you should modify):

- `nodes/feedback_log.py` — **delete this file**.
- `run_daily.py` — one log-line change at line 65.
- `dashboard.py` — remove the inline import at line 438; add
  `default_followup_date` to the top-of-file import block.
- `nodes/tracker.py` — add a thin public alias
  `default_followup_date = _default_followup_date` at the same
  visibility level as the underscore-prefixed function, so both the
  legacy internal callers (`save_application`) and the new public
  callers work. (Do NOT rename `_default_followup_date` — that would
  break `save_application`'s caller and it's cheaper to add an alias
  than sweep all callers.)
- `requirements.txt` — pin `pytest` to `9.1.1`.
- `plans/README.md` — flip row 021 to DONE at the end.

**Out of scope** (do NOT touch, even though they look related):

- `data/feedback_log.txt` — the 688-byte historical log. `data/` is
  gitignored so this file isn't in git anyway; leave it on disk
  (respect the past). Deletion is the operator's call, not this plan's.
- `nodes/scraper.py`'s `PLATFORM_CONFIGS` — don't try to add
  Arbeitsagentur to it. Arbeitsagentur is deliberately a separate API
  path; changing that is a much larger refactor.
- Any other tracker helper. `_default_followup_date` is the ONLY
  helper this plan promotes to public. Don't sweep the module.
- Any pytest config or version-bump changes beyond adding `==9.1.1`.

## Git workflow

- Branch: `advisor/021-housekeeping-bundle`
- Single commit. Message:
  ```
  Plan 021: housekeeping bundle (retire feedback_log + fix stale log line + lift import + pin pytest)
  ```
- Do NOT push, do NOT open a PR. Reviewer merges into `main` manually.

## Steps

### Step 1: Delete `nodes/feedback_log.py`

Confirm zero callers first:

```bash
grep -rn "feedback_log\|append_feedback\|get_feedback_for_job\|list_recent_feedback" --include="*.py"
```

**Expected**: only matches are inside `nodes/feedback_log.py` itself.
If any match appears outside that file, STOP — plan 013's removal was
incomplete and this plan's assumption is false.

Then:

```bash
rm nodes/feedback_log.py
```

**Verify**: `ls nodes/feedback_log.py 2>&1` → `No such file or directory`.

### Step 2: Fix the stale log line in `run_daily.py:65`

Current line 65:

```python
log("Running pipeline: scrape (Indeed/Stepstone/XING/LinkedIn/Glassdoor) → validate → score → save...")
```

Replace with a hand-written accurate list (5 platforms today). Do NOT
try to derive from `PLATFORM_CONFIGS.keys()` — that misses
Arbeitsagentur (see "Current state" note). Keep it as a plain string:

```python
log("Running pipeline: scrape (Stepstone/XING/LinkedIn/Glassdoor/Arbeitsagentur) → validate → score → save...")
```

**Verify**: `grep -n "Indeed" run_daily.py` → no matches.
**Verify**: `grep -n "Arbeitsagentur" run_daily.py` → one match at line 65.

### Step 3: Add `default_followup_date` public alias in `nodes/tracker.py`

Find the current `_default_followup_date` definition:

```bash
grep -n "_default_followup_date" nodes/tracker.py
```

Expected: 3 hits — the def, one use inside `save_application`, and (if
any) a re-export. Immediately AFTER the `def _default_followup_date(...)`
block, add ONE line:

```python
# Public alias for external callers (dashboard); internal callers keep the
# underscored name to avoid touching save_application.
default_followup_date = _default_followup_date
```

**Verify**: `venv/Scripts/python.exe -c "from nodes.tracker import default_followup_date; print(default_followup_date('2026-07-10'))"` → prints `2026-07-17`.

### Step 4: Lift the import in `dashboard.py`

Edit the top-of-file tracker import block at `dashboard.py:7-16`. Add
`default_followup_date` to the last line:

```python
    update_matched_job_rejection, get_rejection_row,  # Plan 013
    default_followup_date,  # Plan 021
)
```

Then edit `dashboard.py:438` — remove the inline import and use the
lifted name:

```python
with fu_cols[3]:
    if st.button("Snooze +7d", key=f"fu_snz_{app_id}"):
        today = datetime.now().strftime("%Y-%m-%d")
        update_followup_date(app_id, default_followup_date(today))
        st.cache_data.clear()
        st.rerun()
```

**Verify**: `grep -n "_default_followup_date" dashboard.py` → no matches.
**Verify**: `venv/Scripts/python.exe -c "import dashboard; print('OK')" 2>/dev/null` → prints `OK`.

### Step 5: Pin `pytest` in `requirements.txt`

Find the line:

```bash
grep -n "^pytest$" requirements.txt
```

Expected: one match. Replace `pytest` with `pytest==9.1.1`. Preserve
alphabetical position (already correct — sits between `pyee` and
`python-dateutil`).

**Verify**: `grep -n "pytest" requirements.txt` → one match, exactly
`pytest==9.1.1`.

### Step 6: Full-suite regression check

```bash
venv/Scripts/python.exe -m pytest -q
```

**Expected**: `236 passed` (unchanged from baseline). No skips, no
failures, no errors.

### Step 7: Post-cleanup grep audit

```bash
grep -rn "append_feedback\|feedback_log" --include="*.py"
grep -rn "_default_followup_date" --include="*.py"
grep -n "Indeed" run_daily.py
```

**Expected**:
- Line 1: no matches at all (feedback_log module + all references gone).
- Line 2: only 2 matches, both in `nodes/tracker.py` — the `def
  _default_followup_date` line and the one internal use inside
  `save_application`.
- Line 3: no matches.

## Test plan

- **No new tests.** This plan removes dead code, fixes a string
  literal, moves an import, and pins a version. None of that has
  observable behavior worth a test.
- **Regression**: the existing 236 tests must all still pass. That's
  the gate.
- **Import smoke**: `import dashboard` must succeed after the changes.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `ls nodes/feedback_log.py 2>&1` → `No such file or directory`.
- [ ] `grep -rn "append_feedback\|feedback_log" --include="*.py"` → 0 matches.
- [ ] `grep -n "Indeed" run_daily.py` → 0 matches.
- [ ] `grep -n "Arbeitsagentur" run_daily.py` → exactly 1 match at line 65.
- [ ] `grep -n "_default_followup_date" dashboard.py` → 0 matches.
- [ ] `grep -n "default_followup_date" dashboard.py` → exactly 2 matches (import + call site).
- [ ] `venv/Scripts/python.exe -c "from nodes.tracker import default_followup_date; print(default_followup_date('2026-07-10'))"` → prints `2026-07-17`.
- [ ] `grep -n "pytest" requirements.txt` → exactly 1 match, `pytest==9.1.1`.
- [ ] `venv/Scripts/python.exe -m pytest -q` → `236 passed`, exit 0.
- [ ] `venv/Scripts/python.exe -c "import dashboard; print('OK')" 2>/dev/null` → prints `OK`.
- [ ] `git diff --stat` shows exactly 5 files touched: `nodes/feedback_log.py` (deleted), `run_daily.py`, `dashboard.py`, `nodes/tracker.py`, `requirements.txt` (+ `plans/README.md` if the executor updates the row itself).
- [ ] `plans/README.md` row for plan 021 is set to DONE (or the reviewer will do this — check the executor-dispatch instructions).

## STOP conditions

Stop and report back (do not improvise) if:

- Grep in Step 1 finds a caller of anything in `nodes/feedback_log.py`
  outside the module itself. Some other code path has crept in since
  plan 013 landed and this plan's assumption is stale.
- The `_default_followup_date` function's signature has changed —
  currently `(from_date_str: str, days: int = 7) -> str`. If different,
  the alias may need adjustment.
- `run_daily.py:65` doesn't match the excerpt — some other plan
  already touched the log line.
- The 236-test baseline regresses even one test.
- `import dashboard` starts raising after the changes. Most likely
  cause: typo in the new import name. Undo Step 4's edit to
  `dashboard.py:7-16` and re-check.

## Maintenance notes

- `data/feedback_log.txt` (688 bytes, 2 historical entries from
  2026-04-28) stays on disk. It's gitignored. When the operator
  decides those 2 entries are no longer worth keeping around, they
  can `rm data/feedback_log.txt` manually.
- The `default_followup_date` public alias is a soft-migration
  pattern: both the underscored form (used by `save_application` in
  the same module) and the public form work. If a future plan sweeps
  all in-module callers to use the public name, the underscored form
  can be removed. Not urgent.
- If Arbeitsagentur ever gets folded into `PLATFORM_CONFIGS` (larger
  refactor — would need to unify Playwright and requests-based
  scraping), the Step 2 log line becomes derivable from
  `PLATFORM_CONFIGS.keys()`. Until then, hand-written.
- Pytest 9.x is current; if a future major bump requires new syntax
  in test files, bump the pin then. Don't chase minor versions.
