# Plan 005: Collapse `main.py` onto `run_pipeline()` and drop LangGraph

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**:
> `git diff --stat ee9a6e2..HEAD -- main.py nodes/pipeline.py run_daily.py requirements.txt`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code; on mismatch, STOP.
>
> **SHA note**: Plan 001 (executed 2026-07-01) rewrote every commit SHA via
> `git filter-repo`. The original `Planned at` commit `29244f6` was replaced
> by its rewritten equivalent `ee9a6e2` (same tree, same message). All
> SHAs in this plan use the new value.

## Status

- **Priority**: P3
- **Effort**: M
- **Risk**: LOW (with tests in place)
- **Depends on**: 002 (test baseline — required, not just useful)
- **Category**: tech-debt / architecture
- **Planned at**: commit `29244f6` / rewritten `ee9a6e2`, 2026-06-30

## Why this matters

There are two parallel implementations of the same pipeline:

1. `main.py` builds a LangGraph `StateGraph` with three linear nodes
   (`fetch_jobs → validate_job_links → analyze_jobs`) — 143 lines.
2. `nodes/pipeline.py:run_pipeline()` does the same scrape → validate →
   dedup → score → save flow in plain Python — 65 lines.

The graph has no branching, no conditional edges, no checkpointing, no
human-in-the-loop steps. It is strictly more boilerplate than
`run_pipeline()`. The two paths have already started to drift:

- `main.py:99` hardcodes `min_score=40`.
- `run_daily.py:26` passes `min_score=40` as an argument.
- `main.py` writes the tee log (`data/run_<stamp>.txt`).
- `pipeline.py` does not.
- Both paths re-read `my_cv.txt` at module import.

Future maintenance has to remember which copy to edit. The LangGraph deps
(`langgraph==1.1.2`, `langgraph-checkpoint==4.0.1`, `langgraph-prebuilt`,
`langgraph-sdk`) install a meaningful amount of code for nothing.

After this plan: `main.py` is a thin wrapper that sets up the tee log,
loads env, and calls `run_pipeline(min_score=40)`. The LangGraph deps are
removed from `requirements.txt`. The README no longer mentions the
`StateGraph` topology.

## Current state

`main.py` HEAD `ee9a6e2`, lines 40-121, has these load-bearing parts that
`run_pipeline` does NOT have:

- The tee-logging setup (lines 12-38) writes a `data/run_<stamp>.txt` file
  that captures stdout and stderr. The README documents this at line 139
  (`run_<stamp>.txt` — Full console log tee'd from each main.py run).
- A `KeyboardInterrupt` handler at lines 140-143 that prints a friendly
  message and exits 130.
- A startup banner with `RUN_DATE` printed at lines 126-129.
- A final "Done! Open the dashboard..." message at lines 138-139.

The three graph nodes themselves (`fetch_jobs`, `validate_job_links`,
`analyze_jobs`) replicate logic already in `run_pipeline()`:

- Both call `scrape_jobs()`, `validate_jobs(...)`, then filter for
  `link_status != "expired"`, then filter against `get_known_urls()` and
  `get_known_title_keys()`.
- Both ultimately call `score_and_filter_jobs(...)` which persists
  incrementally (see `nodes/pipeline.py:7` docstring).

`nodes/pipeline.py:20-65` (current `run_pipeline`):
```python
def run_pipeline(min_score: int = 40) -> list:
    init_db()
    with open("my_cv.txt", "r", encoding="utf-8") as f:
        cv = f.read()
    jobs = scrape_jobs()
    if not jobs:
        print("[pipeline] Scraper returned 0 jobs.")
        return []
    jobs = validate_jobs(jobs)
    alive = [j for j in jobs if j.get("link_status") != "expired"]
    expired = len(jobs) - len(alive)
    known_urls = get_known_urls()
    after_url = [j for j in alive if _url_key(j.get("url", "")) not in known_urls]
    known_titles = get_known_title_keys()
    new_jobs = [j for j in after_url if _job_title_key(j) not in known_titles]
    url_dupes   = len(alive) - len(after_url)
    title_dupes = len(after_url) - len(new_jobs)
    print(
        f"[pipeline] Scraped: {len(jobs)}  |  Alive: {len(alive)}  |  "
        f"Expired: {expired}  |  URL-known: {url_dupes}  |  "
        f"Title-known: {title_dupes}  |  New: {len(new_jobs)}"
    )
    if not new_jobs:
        print("[pipeline] Nothing new to score today.")
        return []
    try:
        matched, not_matched = score_and_filter_jobs(cv=cv, jobs=new_jobs, min_score=min_score)
    except KeyboardInterrupt:
        print("[pipeline] Interrupted — partial results already persisted in DB.")
        raise
    print(f"[pipeline] Scored: {len(new_jobs)}  |  Matched (>={min_score}%): {len(matched)}  |  Below threshold: {len(not_matched)}")
    return matched
```

This already handles `KeyboardInterrupt` by re-raising — main can catch it.

`requirements.txt` LangGraph entries (lines 32-36):
```
langgraph==1.1.2
langgraph-checkpoint==4.0.1
langgraph-prebuilt==1.0.8
langgraph-sdk==0.3.11
```

LangGraph references in code (verified by grep):
- `main.py:8`: `from langgraph.graph import StateGraph, END`
- `main.py:111-121`: build / compile / wire the graph
- No other `nodes/*.py` or `dashboard.py` imports langgraph.

README references to LangGraph (search `grep -n -i langgraph README.md`):
- Line 3: title summary "LangGraph-powered job-matching agent".
- Line 22: tech stack table row "Agent framework | LangGraph".
- Lines 60-61: "`main.py` wires this as a LangGraph `StateGraph` with three
  nodes (`fetch_jobs → validate_job_links → analyze_jobs`)."

## Commands you will need

| Purpose          | Command                                          | Expected on success |
|------------------|--------------------------------------------------|---------------------|
| Run tests        | `pytest -q`                                      | exit 0              |
| Import smoke     | `python -c "import main, run_daily, nodes.pipeline"` | no traceback   |
| LangGraph search | `grep -rn "langgraph\|StateGraph\|langchain.langgraph" --include='*.py' .` | only matches in venv/ or none |

## Scope

**In scope** (the only files you should modify):

- `main.py` — rewrite as a thin wrapper around `run_pipeline()`. Keep tee
  logging, KeyboardInterrupt handling, banner, and final message.
- `requirements.txt` — remove the 4 langgraph lines.
- `README.md` — update the description, the tech-stack table, and the
  pipeline section to match the new structure.
- `tests/test_pipeline_smoke.py` — new, very small smoke test verifying
  the wrapper exists with the right shape (does NOT call the real
  pipeline — that hits the network).

**Out of scope** (do NOT touch):

- `nodes/pipeline.py` — already correct. Use it as-is.
- `run_daily.py` — already correct.
- `nodes/scraper.py`, `nodes/analyzer.py`, `nodes/validator.py`,
  `nodes/tracker.py` — no changes needed.
- The `dashboard.py` workflow — independent.
- Removal of `langchain==1.2.12`, `langchain-anthropic==1.4.0`,
  `langchain-core==1.2.19` — those ARE used by `nodes/analyzer.py:9` via
  `ChatAnthropic`. Do NOT touch them.

## Git workflow

- Branch: `advisor/005-drop-langgraph`.
- Two commits is natural: one for the code change, one for `README.md`.
- Message style: `replace LangGraph wrapper with direct run_pipeline call`.

## Steps

### Step 1: Run the test baseline (must be green BEFORE changing)

```
pytest -q
```

**Expected**: exit 0, all baseline tests pass.

If plan 002 is NOT done yet, STOP and report — this plan depends on it.

### Step 2: Rewrite `main.py`

Replace the entire contents of `main.py` with:

```python
"""
Entry point for an interactive run of the job-matching pipeline.
Mirrors the scheduled run in run_daily.py but with a different log target
(per-run tee file in data/run_<stamp>.txt) and friendlier banners.
"""
import os
import sys
import atexit
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv


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

load_dotenv()

# Import the pipeline AFTER load_dotenv() so ANTHROPIC_API_KEY is available.
from nodes.pipeline import run_pipeline


RUN_DATE = datetime.now().strftime("%Y-%m-%d")


if __name__ == "__main__":
    print("\n🤖 Job Application Agent Starting...")
    print(f"📅 Run date: {RUN_DATE}")
    print(f"📝 Run log:  {_LOG_PATH}")
    print("=" * 60)

    try:
        matched = run_pipeline(min_score=40)
        if matched:
            print(f"\n🏆 Top matches today:")
            for job in matched[:5]:
                print(f"   {job['score']}% {job['title']} @ {job['company']}")
        print(f"\n✅ Done! Open the dashboard to review matches:")
        print(f"   streamlit run dashboard.py")
    except KeyboardInterrupt:
        print("\n🛑 Aborted by user — partial results saved to DB and run log:")
        print(f"   {_LOG_PATH}")
        sys.exit(130)
```

Key behavior preserved:

- Tee log written to `data/run_<stamp>.txt` (unchanged).
- `load_dotenv()` called before importing `nodes.pipeline` (so analyzer's
  module-level `llm = ChatAnthropic(...)` sees the API key).
- KeyboardInterrupt prints the same banner and exits 130.
- The top-5 matches print, previously inside `analyze_jobs`, is now in
  `main.py` driven by the matched list `run_pipeline` returns.
- The "No strong matches found today." line in the old `analyze_jobs` is
  intentionally dropped — `run_pipeline` already prints
  `[pipeline] Scored: ... Matched: 0` which carries the same signal.

**Verify**:
```
python -c "import main; print('OK')"
```
→ prints `OK`, no traceback.

```
grep -n "langgraph\|StateGraph\|AgentState" main.py
```
→ no matches.

### Step 3: Remove LangGraph from `requirements.txt`

Delete these four lines:
```
langgraph==1.1.2
langgraph-checkpoint==4.0.1
langgraph-prebuilt==1.0.8
langgraph-sdk==0.3.11
```

**Verify**:
```
grep -n "langgraph" requirements.txt
```
→ no matches.

```
pip uninstall -y langgraph langgraph-checkpoint langgraph-prebuilt langgraph-sdk
python -c "import main, run_daily, nodes.pipeline, dashboard"
```
→ no `ImportError`, no traceback.

(If you see "WARNING: ... is not installed" from pip uninstall, that's
fine — the goal is the import test passing.)

### Step 4: Update README

In `README.md`:

1. **Line 3** — change:
   > A LangGraph-powered job-matching agent that scrapes German job boards in parallel,

   To:
   > A job-matching agent that scrapes German job boards in parallel,

2. **Line 22** (the tech stack table row) — delete the row:
   ```
   | Agent framework | LangGraph |
   ```

3. **Lines 60-61** — change:
   > `main.py` wires this as a LangGraph `StateGraph` with three nodes
   > (`fetch_jobs → validate_job_links → analyze_jobs`).
   > `nodes/pipeline.py` is the shared implementation also used by `run_daily.py`.

   To:
   > `nodes/pipeline.py` is the shared implementation. Both `main.py`
   > (interactive run, with per-run log file) and `run_daily.py`
   > (scheduled / scriptable run) call `run_pipeline()`.

**Verify**:
```
grep -ni "langgraph" README.md
```
→ no matches.

```
grep -n "StateGraph\|fetch_jobs.*validate_job_links" README.md
```
→ no matches.

### Step 5: Add a small smoke test

Create `tests/test_pipeline_smoke.py`:

```python
"""Smoke test: the public surface of run_pipeline / main is intact.

This test does NOT call run_pipeline() — that hits the network. It only
verifies the import wiring main.py depends on after plan 005.
"""
import inspect


def test_run_pipeline_is_importable_and_has_min_score_kwarg():
    from nodes.pipeline import run_pipeline
    sig = inspect.signature(run_pipeline)
    assert "min_score" in sig.parameters
    assert sig.parameters["min_score"].default == 40


def test_main_module_imports_without_running_pipeline():
    # Importing main.py runs the tee-log setup but must NOT invoke
    # run_pipeline (that's guarded by `if __name__ == "__main__"`).
    import main  # noqa: F401
    # No assertion needed — a clean import is the test.
```

**Verify**:
```
pytest -q tests/test_pipeline_smoke.py
```
→ both pass.

### Step 6: Full test-suite run

```
pytest -q
```

**Expected**: all baseline tests from plan 002 still pass, plus the two
new smoke tests in `tests/test_pipeline_smoke.py`.

### Step 7: Side-effect-free import check

```
python -c "import main, run_daily, dashboard, nodes.pipeline, nodes.tracker, nodes.analyzer, nodes.scraper, nodes.validator, nodes.feedback_log, cleanup_duplicates"
```

**Expected**: no traceback. Importing `main` creates a new
`data/run_<stamp>.txt` file (that's a known side effect of the tee setup,
preserved from before).

### Step 8: Verify no langgraph references remain in project code

```
grep -rn "langgraph\|StateGraph" --include="*.py" . | grep -v venv
```

**Expected**: no matches. (`grep -v venv` filters out the still-installed
package files in `venv/` if anyone pip-installs langgraph later.)

## Test plan

- `tests/test_pipeline_smoke.py` (new, see Step 5):
  - `run_pipeline` is importable from `nodes.pipeline` and has
    `min_score` keyword with default `40`.
  - `import main` succeeds (catches regressions where someone wires
    `run_pipeline()` at module scope and forgets it hits the network).
- The plan 002 baseline (`tests/test_tracker_keys.py`,
  `tests/test_analyzer_filters.py`, `tests/test_scraper_helpers.py`)
  continues to pass — proves no business logic changed.

## Done criteria

ALL must hold:

- [ ] `grep -rn "langgraph\|StateGraph" --include='*.py' .` returns no
      matches outside `venv/`.
- [ ] `grep -ni "langgraph" README.md` returns no matches.
- [ ] `grep -n "langgraph" requirements.txt` returns no matches.
- [ ] `python -c "import main"` exits 0.
- [ ] `pytest -q` exits 0 and includes both new smoke tests passing.
- [ ] `main.py` is ≤ ~80 lines (was 143).
- [ ] `git status --porcelain` shows changes only in `main.py`,
      `requirements.txt`, `README.md`, `tests/test_pipeline_smoke.py`, and
      `plans/README.md`.
- [ ] `plans/README.md` status row updated to DONE.

## STOP conditions

Stop and report (do not improvise) if:

- Plan 002 is not DONE in `plans/README.md` — this plan depends on it.
- `pytest -q` was failing BEFORE you started — fix the baseline first; do
  not introduce a refactor on red tests.
- `python -c "import main"` after Step 2 takes more than 5 seconds OR
  triggers a network call (you can tell from the tee log it writes — if
  you see scrape output, the `if __name__ == "__main__"` guard is wrong;
  STOP).
- The README has additional `LangGraph` / `StateGraph` references not
  listed in Step 4 — list them, then ask the operator whether to update
  them.

## Maintenance notes

For the human/agent who owns this code after the change lands:

- If you ever NEED real graph features (conditional edges, human-in-the-loop,
  checkpointing, replay), reintroduce LangGraph then — the migration back
  is small (`run_pipeline` becomes the body of a single node). Don't keep
  it speculatively.
- The tee log lives in `main.py` only. `run_daily.py` writes its own
  simpler log (`data/scheduler_log.txt`). That asymmetry is intentional:
  interactive runs want every print captured, scheduled runs want a short
  daily summary.
- `nodes/pipeline.py` is now the single source of truth for the
  scrape→score flow. Any future scraper/scorer changes go there.
