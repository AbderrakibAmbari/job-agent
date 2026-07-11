# Plan 024: Housekeeping II — root cleanup, stale README, orphan script, `.env.example`

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**:
> `git diff --stat fb39d98..HEAD -- README.md nodes/scraper.py cleanup_duplicates.py login_linkedin.py`
> If any listed file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P3
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: tech-debt (organization) + docs + DX
- **Planned at**: commit `fb39d98`, 2026-07-11

## Why this matters

Five small housekeeping items are bundled here because each is trivial in
isolation and the same shape as plan 021 (single-branch, small diff, no
behavior change). Landing them together closes drift that has accumulated
across the last several plans:

- `cleanup_duplicates.py` is orphaned since plan 016 did a documented
  DB-level dedup. Its regexes (`_GENDER_RE`, `_COMPANY_SUFFIX_RE`) are
  hand-copied from an old `nodes/tracker.py` and were **not** updated
  when plan 007 added `(f/m/d)` / `(f/m/x)` to the gender regex — so
  rerunning the script today would silently mis-dedup those cases.
- `README.md` still documents `nodes/feedback_log.py` (deleted plan 021),
  `Indeed` as a live scraper (retired plan 019), and `cleanup_duplicates.py`
  as a supported utility.
- `login_linkedin.py` sits at repo root while its sibling one-off script
  `scripts/backfill_from_gmail.py` lives in `scripts/`. Pick one convention.
- 14 dashboard screenshot PNGs are gitignored (this session) but still on
  disk, cluttering `ls` and consuming ~1.7 MB.
- No `.env.example`: fresh clones must read prose in `README.md:84-89` to
  discover the required env var. A standard `.env.example` sitting next to
  `.env` (in `.gitignore`) is the industry norm.

## Current state

Files touched by this plan:

- `cleanup_duplicates.py` — orphan one-off dedup script at repo root
- `login_linkedin.py` — active-but-misplaced one-off script at repo root
- `nodes/scraper.py:581` — print line that names `login_linkedin.py` and
  will drift if the file moves without a matching update
- `README.md` — stale references to Indeed / feedback_log / cleanup_duplicates
- Root-level PNG files (14 of them) — dashboard screenshots
- `.env.example` — does not exist; needs to be created

### `cleanup_duplicates.py` (as it exists today)

Lines 1-25 confirm this is the orphan:

```python
"""
One-time script to merge duplicate jobs in matched_jobs that share the same
normalized title+company but have different URLs (cross-platform / cross-day duplicates).
...
Run once:  python cleanup_duplicates.py
"""
import re
import sqlite3
from collections import defaultdict

DB_PATH = "data/applications.db"

_GENDER_RE = re.compile(
    r'\s*\(m/w/d\)|\s*\(w/m/d\)|\s*\(m/f/d\)|\s*\(m/w/x\)|\s*\(w/m/x\)|\s*\(all genders\)',
    re.IGNORECASE,
)
```

The live regex in `nodes/tracker.py:14` covers additional variants
(`(f/m/d)`, `(f/m/x)`, added by plan 007). Zero code paths import from
`cleanup_duplicates.py`; plan 016's post-exec note documents the DB-level
dedup that superseded this script (see `plans/README.md:30`).

### `README.md` stale references

Verify with `grep -n "Indeed\|feedback_log\|cleanup_duplicates" README.md`:

```
9:- 🔍 **Multi-platform scraper** — Indeed, Stepstone, XING, LinkedIn, Glassdoor (Playwright) + Arbeitsagentur (REST API), all run in parallel
23:| Job sources | Indeed, Stepstone, XING, LinkedIn, Glassdoor, Arbeitsagentur |
117:├── cleanup_duplicates.py    # One-off DB dedup utility
118:├── login_linkedin.py        # Saves LinkedIn session cookies
128:│   └── feedback_log.py      # Append-only notes log for the dashboard
135:│   ├── feedback_log.txt
```

- `README.md:9` and `README.md:23` list Indeed — retired plan 019.
- `README.md:117` documents the orphan.
- `README.md:118` documents the correct location (which will change in
  this plan) — must be updated to `scripts/login_linkedin.py`.
- `README.md:128` lists `feedback_log.py` in `nodes/` — deleted plan 021.
- `README.md:135` lists `feedback_log.txt` in `data/` — while `data/` is
  gitignored, that file is dead output that plan 021's post-exec note
  documented as no longer written to (see `plans/README.md:35`). Leaving
  the line in the tree diagram is misleading; delete it.

### `login_linkedin.py` current location + its one back-reference

At repo root today. The other one-off script is at
`scripts/backfill_from_gmail.py`. Only one file references it by path:

```
nodes/scraper.py:581:                    print(f"      Run: python login_linkedin.py")
```

That print fires when the LinkedIn cookie file is missing, telling the
operator how to regenerate it. After the move it must read
`python scripts/login_linkedin.py`. Read `nodes/scraper.py:575-590` to
confirm the surrounding code before editing — no other logic in that block
depends on the string.

### Stray PNGs at root

Run `ls *.png 2>/dev/null` in the repo root. Expected file list (14 files,
all screenshot artifacts from V2 / My Apps live smokes):

```
dashboard-v2-actions.png
dashboard-v2-buttons.png
dashboard-v2-iframe.png
dashboard-v2-matches-empty.png
dashboard-v2-matches-full.png
dashboard-v2-my-apps.png
dashboard-v2-not-matched.png
dashboard-v2-scrape-health.png
dashboard-v2-two-pane.png
myapps-after-repaint.png
myapps-dark-repaint.png
myapps-light-fixed.png
scrape-light-fixed.png
```

(One filename may vary — that's fine; the pattern `*.png` at repo root is
the target.) Verify none are tracked: `git ls-files '*.png'` must be empty.
`.gitignore` already contains `*.png` (added session before this plan).

### `.env.example` — file does not exist

Confirm: `test -f .env.example && echo present || echo missing` → `missing`.
The real `.env` at the repo root is gitignored (`.gitignore:2`). Only
`ANTHROPIC_API_KEY` is required for the current codebase (see
`nodes/analyzer.py` where `langchain-anthropic` reads it, and
`README.md:84-89`). Plan 020's Gmail flow uses a separate JSON file
(`data/gmail_credentials.json`), not env vars — do not add Gmail vars here.

## Commands you will need

| Purpose      | Command                                                                 | Expected on success |
|--------------|-------------------------------------------------------------------------|---------------------|
| Tests        | `"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -m pytest -x` | 307 passed / 0 failed |
| Tracked-PNG check | `git ls-files '*.png'`                                             | empty output        |
| Root-PNG count    | `ls *.png 2>/dev/null | wc -l`                                     | `0` after step 4    |
| Stale-ref check   | `grep -n "cleanup_duplicates\|feedback_log\|Indeed" README.md`      | zero matches after step 2 |

## Scope

**In scope** (the only files you should modify or delete):

- Delete: `cleanup_duplicates.py`
- Move: `login_linkedin.py` → `scripts/login_linkedin.py`
- Edit: `README.md`
- Edit: `nodes/scraper.py` (one line — the print at line 581)
- Delete: `*.png` at repo root (14 files)
- Create: `.env.example`

**Out of scope** (do NOT touch):

- Any file inside `nodes/`, `tests/`, `plans/`, `scripts/backfill_from_gmail.py`
  — no logic changes.
- `dashboard.py`, `main.py`, `run_daily.py`, `pipeline.py`.
- `.gitignore` — already updated in the session preceding this plan
  (commit `fb39d98`).
- `data/` — gitignored; leave the runtime tree alone.
- `nodes/scraper.py` beyond the exact string on line 581. If you find a
  second reference, STOP and report.

## Git workflow

- Branch: `advisor/024-housekeeping-ii`
- One commit is fine (this is a housekeeping bundle, matches plan 021's
  shape — see `git log --oneline 4dc6bc1` for the exemplar commit).
- Commit style: conventional commits (see `git log --oneline -20`). Suggested
  subject: `chore: housekeeping II — root cleanup, stale README, orphan script, .env.example`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Delete `cleanup_duplicates.py`

Delete the file at repo root. No callers exist.

**Verify**:
- `test ! -f cleanup_duplicates.py && echo gone` → `gone`
- `grep -rn "cleanup_duplicates" . --exclude-dir=venv --exclude-dir=.git --exclude-dir=__pycache__ --exclude-dir=plans` → zero matches (plans dir is allowed to still reference it historically)

### Step 2: Update `README.md`

Make these edits — all are line-level replacements:

1. **Line 9** — remove "Indeed, " from the platform bullet. New line:
   `- 🔍 **Multi-platform scraper** — Stepstone, XING, LinkedIn, Glassdoor (Playwright) + Arbeitsagentur (REST API), all run in parallel`
2. **Line 23** — remove "Indeed, " from the table row. New row:
   `| Job sources | Stepstone, XING, LinkedIn, Glassdoor, Arbeitsagentur |`
3. **Line 96-98** — update the code block that says
   `python login_linkedin.py` to
   `python scripts/login_linkedin.py`.
4. **Line 117** — delete the `cleanup_duplicates.py` entry from the
   Project Structure tree.
5. **Line 118** — update the `login_linkedin.py` entry so its indentation
   still lines up in the tree and its path reflects the new location.
   Move the entry from the top-level of the tree into the existing
   `scripts/` block if one is present; otherwise add a `scripts/` block
   next to `nodes/` containing both `backfill_from_gmail.py` and
   `login_linkedin.py`. Match the surrounding tree-drawing characters
   (`├──`, `│`, `└──`) exactly — read the raw file to see the current
   character widths before editing.
6. **Line 128** — delete the `nodes/feedback_log.py` entry from the
   `nodes/` tree block.
7. **Line 135** — delete the `data/feedback_log.txt` entry from the
   `data/` tree block.

**Verify**:
- `grep -n "cleanup_duplicates\|feedback_log\|Indeed" README.md` → zero matches
- `grep -n "login_linkedin" README.md` → matches all now read
  `scripts/login_linkedin.py`
- Manually re-read the Project Structure block (`README.md:111-141`) and
  confirm the tree diagram still renders (indentation is consistent, no
  orphaned continuation lines).

### Step 3: Move `login_linkedin.py` → `scripts/login_linkedin.py`

Use `git mv login_linkedin.py scripts/login_linkedin.py` (preserves file
history in `git log --follow`). Then update the single back-reference in
`nodes/scraper.py`.

**Edit `nodes/scraper.py:581`**:

Read `nodes/scraper.py:575-590` first to confirm the block. The one string
change is:

- Before: `print(f"      Run: python login_linkedin.py")`
- After:  `print(f"      Run: python scripts/login_linkedin.py")`

Do not touch surrounding lines. Do not reformat the file.

**Verify**:
- `test -f scripts/login_linkedin.py && test ! -f login_linkedin.py && echo moved` → `moved`
- `grep -rn "python login_linkedin.py" . --exclude-dir=venv --exclude-dir=.git --exclude-dir=__pycache__ --exclude-dir=plans` → zero matches
- `grep -n "login_linkedin" nodes/scraper.py` → one match, the updated line
- `"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -c "import ast; ast.parse(open('nodes/scraper.py', encoding='utf-8').read())"` → exit 0 (syntax intact)

### Step 4: Delete the 14 stray PNGs from disk

Run in Git Bash (from repo root):

```bash
rm -f dashboard-v2-*.png myapps-*.png scrape-*.png
```

If any other `*.png` files sit at repo root that were NOT in the "Current
state" list, STOP — you have discovered something this plan did not
anticipate; do not delete it.

**Verify**:
- `ls *.png 2>/dev/null | wc -l` → `0`
- `git ls-files '*.png'` → empty (confirms none were tracked — safety net)
- `git status --short` → shows no untracked PNGs (they were untracked and
  are now gone; if any appear as deleted, that would mean a PNG had been
  tracked and this plan would need to reconsider — STOP and report)

### Step 5: Create `.env.example`

Create `.env.example` at repo root with this exact content (no trailing
comments beyond what's here, no real key values):

```
# Copy this file to `.env` and fill in your real key.
# Required for the LLM scoring step (nodes/analyzer.py).
# Get a key at https://console.anthropic.com/
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

Notes:
- Do NOT include Gmail-related variables. Plan 020 stores its OAuth
  credentials in `data/gmail_credentials.json`, not the environment.
- Do NOT include a real key. The placeholder value must literally be
  `sk-ant-your-key-here`.

**Verify**:
- `test -f .env.example && echo present` → `present`
- `grep -c "ANTHROPIC_API_KEY" .env.example` → `1`
- `git check-ignore .env.example` → non-zero exit (i.e. `.env.example` is
  NOT gitignored — the `.env` line in `.gitignore` is a literal filename
  match, not a glob). If it IS ignored, STOP: the gitignore has changed
  since this plan was written.

### Step 6: Run the test suite

**Verify**:
- `"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -m pytest -x` → `307 passed`
- No new tests are added by this plan; the count stays at 307. If any
  test fails, STOP and report — this plan makes no logic changes and any
  failure indicates real drift.

### Step 7: Update `plans/README.md`

Add a new row after the plan 023 row:

```
| 024  | Housekeeping II — root cleanup, stale README, orphan script, .env.example | P3       | S      | LOW  | —          | DONE — <one-line summary of what actually shipped> |
```

Fill in the summary line with the exact concrete facts (files deleted,
paths moved, README lines changed, suite pass count).

## Test plan

No new tests. This plan makes zero behavior changes:

- Step 1 deletes an unused file.
- Step 2 is docs only.
- Step 3 changes one string in a print statement (in a code path that
  fires only when a cookie file is missing — not covered by any test).
- Step 4 is untracked-file removal.
- Step 5 creates a template file.

The verification gate is: `pytest -x` stays at 307 passed / 0 failed.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `test ! -f cleanup_duplicates.py`
- [ ] `test -f scripts/login_linkedin.py && test ! -f login_linkedin.py`
- [ ] `grep -n "cleanup_duplicates\|feedback_log\|Indeed" README.md` → zero matches
- [ ] `grep -n "login_linkedin" README.md` shows only `scripts/login_linkedin.py`
- [ ] `grep -rn "python login_linkedin.py" . --exclude-dir=venv --exclude-dir=.git --exclude-dir=__pycache__ --exclude-dir=plans` → zero matches
- [ ] `ls *.png 2>/dev/null | wc -l` → `0`
- [ ] `test -f .env.example` and it contains `ANTHROPIC_API_KEY=sk-ant-your-key-here`
- [ ] `git check-ignore .env.example` → non-zero exit
- [ ] `"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -m pytest -x` → `307 passed`
- [ ] `git status --short` shows no unintended changes outside the in-scope list
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- The `README.md` line numbers in "Current state" don't match the live
  file — the README has drifted; `grep -n` for each search pattern before
  editing and STOP if the count of hits differs.
- `nodes/scraper.py` contains more than one reference to `login_linkedin.py`
  — the assumption is one back-reference. Report both locations before
  editing either.
- Any `*.png` file at repo root has content that looks like it is not a
  live-smoke artifact (e.g., an image referenced by README or docs).
  Verify with `git log --diff-filter=A --name-only -- '*.png'` before
  deleting; if any is tracked-or-was-tracked, STOP.
- `git check-ignore .env.example` returns exit 0 (meaning it IS ignored)
  — the `.gitignore` pattern for `.env` is broader than assumed; STOP and
  investigate before creating the file.
- `pytest -x` fails on any test after any single step. Do not proceed to
  the next step; report the failure.

## Maintenance notes

- Future changes to `nodes/scraper.py`'s LinkedIn-cookie-missing branch
  (currently around lines 575-590) must keep the printed path in sync with
  wherever `login_linkedin.py` lives. If a future plan moves it back to
  root or renames it, the print string and this README section need
  matching edits.
- If a future feature adds new environment variables, add them to
  `.env.example` with placeholder values in the same commit.
- The `*.png` gitignore rule was added session-preceding this plan
  (commit `fb39d98`). If a future feature needs to ship an actual image
  asset in the repo (unlikely — Streamlit doesn't consume file-system
  images), that rule will need a narrower pattern or an explicit
  `!path/to/tracked.png` exception.
