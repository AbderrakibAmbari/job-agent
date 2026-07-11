# Plan 026: Rotate `data/run_*.txt` logs — cap retention, prevent unbounded growth

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**:
> `git diff --stat fb39d98..HEAD -- main.py`
> If `main.py` changed since this plan was written, compare the tee
> implementation against the "Current state" excerpt before proceeding.

## Status

- **Priority**: P3
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: DX
- **Planned at**: commit `fb39d98`, 2026-07-11

## Why this matters

Every interactive run of `main.py` writes a tee'd log to
`data/run_<YYYYMMDD_HHMMSS>.txt`. There is no eviction. At the time this
plan is written, `data/` already contains **49** such files. On a mildly
active week (2 runs/day) that's ~700 files per year. `data/` is
gitignored so nothing external cares, but:

- The dashboard's scrape-health page and the tracker's DB backups both
  live under `data/`. A directory with thousands of noisy log files
  makes debugging harder for the operator.
- Some `run_*.txt` files are ~150-400 KB each. Left unbounded, this grows
  into hundreds of MB over years for no operational value — the last
  handful of runs is the only useful window.

The fix is one small function called at the top of `main.py`'s
`__main__` block: on startup, list `data/run_*.txt`, sort newest-first,
delete anything past a fixed retention count. Retention chosen as
**30 runs** — enough for a couple weeks of daily use, matches the
`data/backups/` "rolling 30-day" convention documented in `README.md:16`.

The related unbounded log is `data/scheduler_log.txt` written by
`run_daily.py`, but that is a *single append-only file* rotated by
nobody. This plan does NOT touch it — different lifecycle, different
fix; add if it ever becomes an issue.

## Current state

### `main.py` — tee logging as it exists today

Lines 15-43 of `main.py`:

```python
# ── Tee logging: mirror every print()/stderr line to data/run_<stamp>.txt ──
# Line-buffered so partial output survives Ctrl+C and crashes.
class _Tee:
    def __init__(self, *streams):
        self._streams = streams
    def write(self, data):
        for s in self._streams:
            try:
                s.write(data)
                s.flush()
            except Exception:
                pass
    def flush(self):
        for s in self._streams:
            try:
                s.flush()
            except Exception:
                pass
    def isatty(self):
        return False


_LOG_DIR = Path("data")
_LOG_DIR.mkdir(exist_ok=True)
_LOG_PATH = _LOG_DIR / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
_log_handle = open(_LOG_PATH, "w", encoding="utf-8", buffering=1)
sys.stdout = _Tee(sys.__stdout__, _log_handle)
sys.stderr = _Tee(sys.__stderr__, _log_handle)
atexit.register(_log_handle.close)
```

Everything from line 37 onward runs at import time (before the
`if __name__ == "__main__":` guard at line 54). This plan preserves that
existing behavior (fixing the import-side-effect issue is a separate
finding deferred out of scope — see Maintenance notes).

### `run_daily.py` — separate log target, NOT touched by this plan

`run_daily.py:7-15` writes to a single append-only `data/scheduler_log.txt`.
No rotation, different problem, different fix. **Out of scope.**

### File pattern to prune

`data/run_YYYYMMDD_HHMMSS.txt`. Timestamp is monotonic-ish (subject to
clock skew — the operator's laptop, unlikely). Sorting by filename
descending is a reasonable proxy for newest-first; sorting by
`Path.stat().st_mtime` is more correct in edge cases (clock reset,
manual `touch`). Prefer `st_mtime`.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Tests | `"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -m pytest -x` | 307 → 308+ passed |
| Log-file count | `ls data/run_*.txt 2>/dev/null | wc -l` | ~49 before; unchanged after (the plan only prunes future overflow) |

## Scope

**In scope**:

- Edit: `main.py` — add one helper function (~15 lines) and one call
  site in the `__main__` block
- Create or extend: `tests/test_run_log_rotation.py` — pure-function
  tests for the retention helper

**Out of scope**:

- `run_daily.py` and `data/scheduler_log.txt` — different lifecycle
- Any tracker/backup logic under `data/backups/` — plan 015 / 016 covered
  DB dedup and backups have their own retention already
- Retroactive deletion of the existing 49 files — the plan writes the
  rotation logic but does NOT delete any files as part of executing
  this plan; the next real `main.py` run will prune down to 30 on its
  own
- Fixing the import-time side-effect (finding 7 in the advisor session).
  Deferred to keep this plan minimal; kept as a Maintenance note.

## Git workflow

- Branch: `advisor/026-rotate-run-logs`
- Single commit is fine.
- Commit style: conventional commits. Suggested subject:
  `feat(main): rotate data/run_*.txt logs — keep last 30`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Add the retention helper

Add this function to `main.py`, immediately BEFORE the `_Tee` class
(around line 15, above the existing tee logging block). The helper
must be pure — take a directory path and a retention count as
arguments, return a list of file paths to delete. Keep it side-effect
free so it is unit-testable; a thin wrapper does the actual deletion
inside the `__main__` block.

```python
def _stale_run_logs(log_dir: Path, keep: int = 30) -> list[Path]:
    """Return `data/run_*.txt` files past the `keep` newest, sorted oldest first.

    Pure: does not delete anything. Caller is responsible for `.unlink()`.
    Sorted by mtime descending; the oldest overflow files are returned.
    """
    files = sorted(
        log_dir.glob("run_*.txt"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return files[keep:]
```

Style notes:

- Match the surrounding file: 4-space indent, double quotes, docstring
  style used by the pure helpers in `nodes/tracker.py` (e.g.
  `_default_followup_date`).
- Do NOT import anything new — `Path` and `datetime` are already
  imported at the top of `main.py`.
- Do NOT log anything from inside this helper — silent by design so the
  test can assert on its return value.

### Step 2: Wire the call into the `__main__` block

Inside `if __name__ == "__main__":` (line 54), immediately after the
existing three `print()` banners (~line 58, before the `try:` block),
add:

```python
    for stale in _stale_run_logs(_LOG_DIR, keep=30):
        try:
            stale.unlink()
        except OSError:
            pass  # File may have been rotated by a concurrent run — safe to ignore.
```

Rationale for the try/except:
- Two `main.py` processes running concurrently is unlikely but not
  impossible (an operator hits Enter twice). One removing a file
  another was about to remove is a race we can safely swallow.
- Do NOT crash the pipeline over log cleanup — the operator cares about
  scrape/score progress, not eviction.

Do NOT log the deletion count to stdout — that would pollute the run
log itself. If observability is later wanted, use `print(...)` but
scope it to a verbose flag; not this plan.

### Step 3: Add unit tests

Create `tests/test_run_log_rotation.py`. Model structural style after
`tests/test_dashboard_helpers.py` (top-level `import` from the module,
one `pytest` import, small parametrized cases; no fixtures if
`tmp_path` alone is sufficient).

Test cases required (each an independent function):

1. **empty directory** — `_stale_run_logs(empty_dir, keep=30)` returns
   `[]`.
2. **fewer than `keep`** — 5 files created, `keep=30`, returns `[]`.
3. **exactly `keep`** — 30 files created, `keep=30`, returns `[]`.
4. **overflow returns oldest** — 32 files created with mtimes 1..32,
   `keep=30`. Return list has length 2 and both entries are the two
   oldest (mtime 1 and 2).
5. **ignores non-matching files** — 40 `run_*.txt` files plus one
   `scheduler_log.txt` plus one `backups/` subdirectory. `keep=30`
   returns exactly 10 items, none of which are `scheduler_log.txt` or
   the subdir.

Reference pattern for `tmp_path` with mtimes (see also
`tests/conftest.py` if it defines helpers — read it before writing):

```python
def _mk(tmp_path, name: str, mtime_offset: int):
    p = tmp_path / name
    p.write_text("x", encoding="utf-8")
    import os
    os.utime(p, (mtime_offset, mtime_offset))
    return p
```

Import from `main`:

```python
from main import _stale_run_logs
```

**Verify**:

`"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -m pytest tests/test_run_log_rotation.py -v` → all new tests pass.

Then run the full suite: `pytest -x` → 307 + 5 = 312 passed.

### Step 4: Manual smoke — confirm the helper doesn't crash on the live directory

Do NOT execute `main.py` (that would run the full pipeline). Instead:

```
"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -c "from pathlib import Path; from main import _stale_run_logs; print(len(_stale_run_logs(Path('data'), keep=30)))"
```

Expected: a non-negative integer, no traceback. Given ~49 files today,
the number should be ~19 — but do NOT assert on that exact count in
this plan (the operator may have run `main.py` between plan-authoring
and execution).

**IMPORTANT**: This step MUST NOT delete anything. It only calls the
pure helper. The real deletion happens when `main.py` is actually run
by the operator later.

### Step 5: Update `plans/README.md`

Add a new row after the plan 025 row:

```
| 026  | Rotate data/run_*.txt logs — keep last 30                             | P3       | S      | LOW  | —          | DONE — `_stale_run_logs(log_dir, keep=30)` pure helper added to main.py; called at __main__ startup with try/except OSError swallowing races; 5 new tests; suite 307 → 312 passed. |
```

## Test plan

New file: `tests/test_run_log_rotation.py` covering the 5 cases in Step 3.

Existing tests must stay green — this plan changes no logic they exercise.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `main.py` contains `def _stale_run_logs(log_dir: Path, keep: int = 30) -> list[Path]:`
- [ ] `main.py`'s `__main__` block calls `_stale_run_logs(_LOG_DIR, keep=30)`
      and iterates the result, calling `.unlink()` inside a `try/except OSError:`
- [ ] `tests/test_run_log_rotation.py` exists and contains at least
      5 test functions matching the cases in Step 3
- [ ] `python -m pytest -x` → `312 passed` (307 + 5 new)
- [ ] `git status --short` shows only `main.py`, the new test file,
      and the `plans/README.md` update
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back if:

- `main.py` no longer contains the tee block at lines 15-43 — the file
  has been refactored since this plan was written; re-read and revise
  the placement instructions.
- `_LOG_DIR` no longer refers to `Path("data")` — the constant was
  renamed or removed; STOP.
- The `datetime` or `Path` import at the top of `main.py` is gone —
  the plan assumed they're already there; STOP rather than adding
  them from scratch (that indicates deeper refactor happened).
- Adding the helper causes a pytest collection error (e.g. tests
  can't import from `main` because of a top-level side effect the
  plan didn't foresee). Report the error; do not add
  `if __name__ == "__main__":` guards around the tee block (that's
  finding 7, deferred).

## Maintenance notes

- **Retention count**: 30 was picked to match the "30-day rolling
  backups" convention documented in `README.md:16`. If the operator's
  usage pattern shifts (e.g. many runs per day), bump the `keep=`
  argument at the call site — no code shape change needed.
- **Import-time side effects in `main.py`**: opening `_log_handle`
  before the `__main__` guard means any test that `import main`
  spuriously creates a log file. This plan does NOT fix that (finding
  7 in the audit) — deferred so this plan stays small. If a future
  plan moves the tee setup into `__main__`, the `_stale_run_logs`
  call moves with it and the imports stay clean.
- **Concurrency**: the try/except OSError swallow assumes rare double-
  runs. If the operator ever runs `main.py` in a loop (e.g. from a
  monitor script), replace with `pathlib.Path.unlink(missing_ok=True)`
  (Python 3.8+, already in use elsewhere in the codebase — check
  `nodes/tracker.py` for prior use before assuming).
- **Related unrotated log**: `data/scheduler_log.txt` written by
  `run_daily.py` is append-only and never rotated. If it ever becomes
  unwieldy, a follow-up plan can size-cap it (e.g. keep last 1 MB).
