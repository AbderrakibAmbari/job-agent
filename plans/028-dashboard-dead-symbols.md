# Plan 028: Remove dead imports + dead `STATUS_COLORS` from `dashboard.py`

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving on.
> Touch only the files listed as in scope. If any STOP condition occurs,
> stop and report. SKIP the plan's instruction to update `plans/README.md`
> — your reviewer maintains the index.
>
> **Drift check (run first)**:
> `git diff --stat 0270e38..HEAD -- dashboard.py`
> If `dashboard.py` changed since this plan was written, verify each
> target symbol still exists at the described location before editing.

## Status

- **Priority**: P3
- **Effort**: S
- **Risk**: LOW
- **Depends on**: `027-dashboard-split.md` (DONE — this cleans up leftovers)
- **Category**: tech-debt
- **Planned at**: commit `0270e38`, 2026-07-13

## Why this matters

Plan 027's status row flagged four dead symbols in `dashboard.py`
explicitly deferred out of scope (that plan was pure extraction). They
survived the split unchanged and are still dead. Removing them shrinks
`dashboard.py` by ~15 lines and drops one dead-code false positive that
would confuse anyone reading the file.

## Current state

Verified against `dashboard.py` at commit `0270e38`:

1. **`import sqlite3`** (line 2). Grep `\bsqlite3\.` in `dashboard.py` returns zero hits. Unused since the `nodes/tracker` layer landed; `dashboard.py` opens no SQLite connections.

2. **`import os`** (line 14). Grep `\bos\.` in `dashboard.py` returns zero hits. Unused.

3. **`get_applied_status`** (singular) inside the `from nodes.tracker import (…)` block on line 7. Grep `\bget_applied_status\b` returns exactly one hit (the import line itself). The plural `get_applied_statuses` IS used at line 323 (`get_applied_statuses([j[0] for j in matched])`). Keep the plural, drop the singular.

4. **`STATUS_COLORS`** dict (line 222) with the comment on line 221 that says: `# STATUS_COLORS below is currently unused; kept in place for a future cleanup.` This is that future cleanup. Grep `\bSTATUS_COLORS\b` across `dashboard.py`, `dashboard_pages/`, `tests/`, `nodes/` returns only the self-reference (comment + definition). The live `_MYAPPS_STATUS_COLORS` at `dashboard_pages/myapps.py` is a different symbol; leave it alone.

### Import block excerpt (lines 1-14)

```
import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
from nodes.tracker import (
    init_db, get_all_applications, get_matched_jobs,
    get_applied_status, get_applied_statuses,
    get_not_matched_jobs, get_scrape_dates,
    promote_not_matched_to_matched,
)
from nodes.scrape_log_parser import (
    parse_scrape_log, platform_history, broken_platforms, top_terms_aggregated,
)
import os
```

## Commands you will need

| Purpose | Command | Expected |
|---|---|---|
| Tests | `"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -m pytest -x` | 312 passed |
| Syntax check | `"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -c "import ast; ast.parse(open('dashboard.py',encoding='utf-8').read())"` | exit 0 |
| Streamlit smoke | headless start on port 8501, then `curl http://localhost:8501/_stcore/health` | `ok` |

## Scope

**In scope**:
- Edit: `dashboard.py` (only — one file, four small removals)

**Out of scope**:
- `dashboard_pages/*.py`, `nodes/*`, tests, any other file.
- The unused imports IF they turn out to be used somewhere the "Current
  state" section missed (see STOP conditions).

## Git workflow

- Branch: use the worktree branch as-is.
- Single commit.
- Suggested subject: `refactor(dashboard): drop dead imports and STATUS_COLORS after plan 027 split`
- Do NOT push or open a PR.

## Steps

### Step 1: Baseline

`pytest -x` → `312 passed`. Do not proceed if any test fails.

### Step 2: Remove `import sqlite3` (line 2)

Delete that one line entirely.

**Verify**: `grep -n "^import sqlite3" dashboard.py` → 0.

### Step 3: Remove `import os` (was line 14; may shift to 13 after Step 2)

Delete that one line entirely.

**Verify**: `grep -n "^import os" dashboard.py` → 0.

### Step 4: Remove `get_applied_status,` from the tracker import block

The line reads (with 4-space indent):

```
    get_applied_status, get_applied_statuses,
```

Change to:

```
    get_applied_statuses,
```

Do NOT remove the plural. Preserve the trailing comma and indentation.

**Verify**:
- `grep -n "get_applied_status\b" dashboard.py` → 0 (singular gone)
- `grep -n "get_applied_statuses" dashboard.py` → 2 hits (import block + line ~323 call site)

### Step 5: Remove `STATUS_COLORS` block

Delete lines 221-232 in the current file (a 1-line comment + the dict definition + its blank line separator). The comment reads
`# STATUS_COLORS below is currently unused; kept in place for a future cleanup.` and the block ends at the closing `}`. Delete only this
block; the surrounding "Status config" section header (if still
present) and any other constant stay. If the executor sees any adjacent
line that isn't the comment or the dict body, STOP.

**Verify**:
- `grep -rn "\bSTATUS_COLORS\b" dashboard.py dashboard_pages/ tests/ nodes/` → 0 hits.

### Step 6: Syntax + tests + streamlit smoke

- `python -c "import ast; ast.parse(open('dashboard.py',encoding='utf-8').read())"` → exit 0
- `pytest -x` → `312 passed` (same count as baseline)
- Start streamlit headless on port 8501; `curl http://localhost:8501/_stcore/health` → `ok`; kill the server.

### Step 7: Line count sanity

`wc -l dashboard.py` → ~495 (was 510). Anything under 505 is fine — the
gate is "shrank, didn't accidentally grow".

Commit: `refactor(dashboard): drop dead imports and STATUS_COLORS after plan 027 split`.

## Done criteria

- [ ] `grep -c "^import sqlite3\|^import os" dashboard.py` → 0
- [ ] `grep -c "\bget_applied_status\b" dashboard.py` → 0 (singular gone; plural stays and is only matched by `get_applied_statuses` which has a trailing char)
- [ ] `grep -c "\bSTATUS_COLORS\b" dashboard.py` → 0
- [ ] `pytest -x` → 312 passed
- [ ] Streamlit `_stcore/health` → `ok`
- [ ] `wc -l dashboard.py` reports fewer lines than before (was 510)

## STOP conditions

Stop if:
- `grep -rn "\bos\.\|\bsqlite3\." dashboard.py` returns any hit — one of the imports was not actually dead; report the hit and do not remove that import.
- `get_applied_status` (singular, word-bounded) is called anywhere in `dashboard.py` besides the import line — the singular is in use; leave it.
- `STATUS_COLORS` is referenced anywhere besides its own definition — it's not dead; leave it.
- Any test fails after any step. Report which one and stop.
- Streamlit fails to start or returns non-ok on health — read the traceback, do not improvise.

## Maintenance notes

- Anyone adding future `os` or `sqlite3` usage back to `dashboard.py`
  will need to re-add the imports. The library layer for `sqlite3`
  usage lives in `nodes/tracker.py`; prefer adding calls there over
  re-importing sqlite3 in dashboard.py.
- If a future page needs a color-per-status dict for a legacy-style
  emoji indicator, revive from git history rather than re-adding
  dead code preemptively.
