# Plan 027: Split `dashboard.py` (1362 lines) into a `dashboard_pages/` package

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**:
> `git diff --stat fb39d98..HEAD -- dashboard.py tests/test_dashboard_helpers.py`
> If either file changed, re-verify the "Current state" line ranges and
> the test's `from dashboard import ...` block before proceeding. **This
> plan is the most drift-sensitive of the set — do not proceed if the
> diff is non-trivial.**

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: MED
- **Depends on**: `025-github-actions-ci.md` (CI must land first so the
  refactor is protected by external verification, not just local pytest)
- **Category**: tech-debt / architecture
- **Planned at**: commit `fb39d98`, 2026-07-11

## Why this matters

`dashboard.py` is 1362 lines / 53 KB. It mixes:

- Shared helpers (`_esc`, `_safe_url`, region/score badges, date chips)
- 145 lines of injected `<style>` CSS
- Cached data loaders (`@st.cache_data` wrappers over `nodes/tracker.py`)
- The V2 two-pane "Today's Matches" renderer (~380 lines including its
  huge inline right pane)
- The "My Applications" renderer (~340 lines including its own CSS
  block and callback handlers)
- Sidebar, page routing, footer

Every dashboard change reads the whole file. There is no clear boundary
between "V2 stuff" and "My Apps stuff"; a change to the V2 shortcut
wiring and a change to the My Apps status dropdown both hit the same
module. 307 tests give a safety net, and — assuming plan 025 lands
first — CI gives an external one. That is exactly the moment to split.

**The split is surgical**: no logic changes. Function bodies move as-is;
imports adjust; the two test-helper imports in
`tests/test_dashboard_helpers.py` point at the new locations. If anything
non-trivial has to change, stop and report — this plan is a mechanical
extraction, not a refactor.

## Current state

### `dashboard.py` structural map (verified by `grep -n "^def \|^# ── " dashboard.py`)

| Range        | Content                                                                  | Target module |
|--------------|--------------------------------------------------------------------------|---------------|
| 1-24         | Imports (`streamlit`, `sqlite3`, `pandas`, `nodes.tracker` symbols, `streamlit_shortcuts`, `os`, `html`, `urlparse`) | stays in `dashboard.py`; `_shared.py` gets a subset |
| 26-46        | `_esc`, `_safe_url` (pure helpers)                                       | `dashboard_pages/_shared.py` |
| 49-155       | `_MYAPPS_STATUS_COLORS`, `_MYAPPS_STATUS_ORDER`, `_MYAPPS_SORT_OPTIONS`, `_MYAPPS_STATUS_SLUG`, `_status_badge_html`, `_MYAPPS_CSS`, `_apply_filters` | `dashboard_pages/myapps.py` |
| 157-190      | Init + cached loaders (`load_applications`, `load_matched_jobs`, `load_not_matched_jobs`, `load_scrape_runs`, `load_due_followups`) | stays in `dashboard.py` |
| 191-196      | `st.set_page_config(...)`                                                | stays in `dashboard.py` |
| 197-203      | Load CV                                                                  | stays in `dashboard.py` |
| 204-349      | Custom CSS block (145 lines of `st.markdown("""<style>...""")`)          | stays in `dashboard.py` |
| 350-378      | `render_date_chips`                                                      | `dashboard_pages/_shared.py` |
| 380-425      | Status config (constants used by V2 detail pane)                         | `dashboard_pages/matches_v2.py` |
| 426-441      | `get_region_badge`, `get_score_color` (pure helpers, used only by V2)    | `dashboard_pages/matches_v2.py` |
| 443-489      | `_render_job_row_compact`, `_auto_advance` (V2 helpers)                  | `dashboard_pages/matches_v2.py` |
| 490-704      | `_render_job_detail_right` (V2 right pane, 215 lines — biggest single function in the repo) | `dashboard_pages/matches_v2.py` |
| 705-812      | `_render_matches_v2` (V2 page entry)                                     | `dashboard_pages/matches_v2.py` |
| 813-822      | `_APP_COLS`, `_row_to_dict` (My Apps data shape)                         | `dashboard_pages/myapps.py` |
| 823-851      | `_on_status_change`, `_on_followup_change`, `_quick_flip_status`, `_quick_snooze` (callback handlers) | `dashboard_pages/myapps.py` |
| 852-1112     | `_render_myapps_toolbar`, `_render_followup_section`, `_render_followup_card`, `_render_app_card` | `dashboard_pages/myapps.py` |
| 1113-1150    | `_render_myapps_page`                                                    | `dashboard_pages/myapps.py` |
| 1151-1361    | Page routing (`if page == "..."` branches for My Apps, Today's Matches, Not Matched, Scrape Health) | stays in `dashboard.py` |
| 1362-1363    | Footer                                                                   | stays in `dashboard.py` |

Total lines to move: ~830. Lines staying in `dashboard.py`: ~530.

Ranges may drift by ±3 lines between plan-writing and execution — always
re-run `grep -n "^def \|^# ── " dashboard.py` and match against the
function names, not the exact numbers.

### `tests/test_dashboard_helpers.py` import block (lines 1-9 today)

```python
import pytest

from dashboard import (
    _esc,
    _safe_url,
    _status_badge_html,
    _apply_filters,
    _MYAPPS_STATUS_COLORS,
)
```

This is the only test file that imports from `dashboard`. After the
split, it must read:

```python
import pytest

from dashboard_pages._shared import _esc, _safe_url
from dashboard_pages.myapps import (
    _status_badge_html,
    _apply_filters,
    _MYAPPS_STATUS_COLORS,
)
```

The pure-function tests further down the file reference the same symbols
and continue to work verbatim.

### Symbols that cross module boundaries

The extraction is clean because each module imports **only** from
`nodes/`, `streamlit`, `streamlit_shortcuts`, stdlib, or
`dashboard_pages/_shared.py`. Verified cross-references (from reading
the file):

- `matches_v2.py` uses `_safe_url`, `_esc` → import from `_shared`
- `myapps.py` uses `_esc`, `_safe_url` → import from `_shared`
- `myapps.py` uses `nodes.tracker` symbols (`update_status`,
  `update_followup_date`, `delete_application`, `default_followup_date`,
  `save_application` etc.) → keeps its own imports
- `matches_v2.py` uses `nodes.tracker` symbols (`update_matched_job_*`,
  `save_application`, `get_rejection_row`, `promote_not_matched_to_matched`
  etc.) → keeps its own imports
- Neither page module needs to import the cached loaders in
  `dashboard.py` — the loaders are called by the page-routing code in
  `dashboard.py`, then their results are passed *into* the render
  functions.

**If any function in the moved ranges references a symbol from a
different bucket** (e.g. a MyApps helper calling a V2 helper) — STOP.
The audit did not surface such a case, but if the executor discovers one,
it's a signal the split boundary is wrong.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Test baseline | `"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -m pytest -x` | 307+ passed (whatever count is current after plan 026 lands) |
| Line count of dashboard.py | `wc -l dashboard.py` | ~530 after split, was 1362 |
| Line count of dashboard_pages/ | `wc -l dashboard_pages/*.py` | sums to ~840 |
| Import-graph sanity | `"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -c "import dashboard_pages.myapps, dashboard_pages.matches_v2, dashboard_pages._shared; print('ok')"` | prints `ok` |
| Streamlit smoke | `"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -m streamlit run dashboard.py --server.headless=true --server.port=8501` in a background terminal, then `curl http://localhost:8501/_stcore/health` | server returns `ok` within 5 s; kill after |

## Scope

**In scope**:

- Edit: `dashboard.py`
- Create: `dashboard_pages/__init__.py` (empty)
- Create: `dashboard_pages/_shared.py`
- Create: `dashboard_pages/myapps.py`
- Create: `dashboard_pages/matches_v2.py`
- Edit: `tests/test_dashboard_helpers.py` (import block only)
- Edit: `plans/README.md` (status row)

**Out of scope**:

- Any change inside function bodies. Function bodies move verbatim;
  only their location changes. If a function body needs a fix, that's
  a separate plan.
- Splitting the "Not Matched" or "Scrape Health" pages out. They live
  inline in the page-routing section (~lines 1151-1361) and stay there
  in this plan. A follow-up plan can extract them if warranted.
- Splitting the custom CSS block (lines 204-349) into its own file.
  The block is one string constant with no logic; keep it inline for
  now.
- Any change to `nodes/`, `main.py`, `run_daily.py`, or `pipeline.py`.
- Any change to `streamlit_shortcuts` calls. Shortcut wiring is a V2
  feature and moves with `matches_v2.py`.
- Splitting `dashboard.py` into a `dashboard/` package with an
  `__init__.py`. **Python's import system will not let you have both
  `dashboard.py` and `dashboard/` at the same level.** The chosen
  directory name is `dashboard_pages/` for exactly this reason. Do NOT
  invent a different name.

## Git workflow

- Branch: `advisor/027-dashboard-split`
- **One commit per module extraction is safest** (easier to bisect if
  the streamlit smoke test finds a broken page):
  1. `refactor(dashboard): extract shared helpers to dashboard_pages/_shared`
  2. `refactor(dashboard): extract My Applications page to dashboard_pages/myapps`
  3. `refactor(dashboard): extract V2 matches page to dashboard_pages/matches_v2`
  4. `test(dashboard): repoint dashboard-helper tests at new modules`

  Each commit should leave the suite green. If any commit breaks tests,
  fix in the same commit before proceeding.
- Commit style: conventional commits (see `git log --oneline -20`).
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Establish the baseline

Run:

```
"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -m pytest -x
```

Record the pass count. This is the number the split must preserve
end-to-end. If plan 026 landed first, it's 312; otherwise 307. **Do not
proceed if any test fails** — the split's success criterion is
"suite stays green", not "suite goes from red to a different red".

### Step 2: Create the empty package

```
mkdir dashboard_pages
```

Then create these files with the exact content:

- `dashboard_pages/__init__.py` — empty file.
- `dashboard_pages/_shared.py` — module docstring only for now:
  ```python
  """Shared helpers used across dashboard pages."""
  ```
- `dashboard_pages/myapps.py` — module docstring only for now:
  ```python
  """My Applications page renderer and its pure helpers."""
  ```
- `dashboard_pages/matches_v2.py` — module docstring only for now:
  ```python
  """Today's Matches (V2 two-pane) renderer and helpers."""
  ```

**Verify**: `python -c "import dashboard_pages"` → exit 0.

### Step 3: Move shared helpers into `_shared.py`

Cut from `dashboard.py`:

- Lines 22-23 (the `import html`, `from urllib.parse import urlparse`
  imports — needed by `_esc` and `_safe_url`).
- Lines 26-46 (`_esc`, `_safe_url` function bodies).
- Lines 350-378 (`render_date_chips`).

Paste into `dashboard_pages/_shared.py` in the same order. Add these
imports at the top of `_shared.py`:

```python
import html
from urllib.parse import urlparse
import streamlit as st  # only needed if render_date_chips uses st
```

Read `render_date_chips` before pasting — its imports may need
additional symbols (e.g. `from datetime import ...`). Copy only what
`_shared.py` actually uses.

Now in `dashboard.py`, add at the top of the imports section:

```python
from dashboard_pages._shared import _esc, _safe_url, render_date_chips
```

Do NOT re-export these from `dashboard.py` for backward compatibility.
The test import is the only external caller and it's updated in Step 6.

**Verify**:
- `grep -c "^def _esc\|^def _safe_url\|^def render_date_chips" dashboard.py` → 0
- `grep -c "^def _esc\|^def _safe_url\|^def render_date_chips" dashboard_pages/_shared.py` → 3
- `"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -c "from dashboard_pages._shared import _esc, _safe_url, render_date_chips; print('ok')"` → `ok`
- `"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -m pytest -x` → still passes (the test imports still work because `dashboard.py` re-exports via its own `from ... import`… actually NO — pytest currently imports FROM dashboard, not from `_shared`. This will fail. **Repoint the tests here or the pytest step will red.**)

Actually: the test file imports `_esc, _safe_url` FROM `dashboard`. After Step 3, `dashboard.py` no longer defines them but does `from dashboard_pages._shared import _esc, _safe_url` — Python re-exports imported symbols by default, so `from dashboard import _esc` still works. **Confirm this before proceeding**:

```
"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -c "from dashboard import _esc, _safe_url; print('ok')"
```

Expected: `ok`. If it fails, the imports at the top of `dashboard.py`
were placed after the `st.set_page_config` call — move them above.

Test run at end of Step 3: `pytest -x` → same pass count as Step 1.

Commit: `refactor(dashboard): extract shared helpers to dashboard_pages/_shared`.

### Step 4: Move My Applications into `myapps.py`

This is the biggest move. Cut from `dashboard.py` in order:

- Lines 49-155 (MyApps constants, `_status_badge_html`, `_MYAPPS_CSS`,
  `_apply_filters`).
- Lines 813-822 (`_APP_COLS`, `_row_to_dict`).
- Lines 823-851 (callback handlers `_on_status_change`,
  `_on_followup_change`, `_quick_flip_status`, `_quick_snooze`).
- Lines 852-1112 (renderers `_render_myapps_toolbar`,
  `_render_followup_section`, `_render_followup_card`, `_render_app_card`).
- Lines 1113-1150 (`_render_myapps_page`).

Paste into `dashboard_pages/myapps.py` **in the same order**. At the top,
add all imports the moved code needs. Read each function's body to
determine imports precisely; expected set:

```python
import streamlit as st
from datetime import date, datetime, timedelta

from nodes.tracker import (
    update_status, delete_application,
    save_application, get_all_applications,
    update_matched_job_company,
    get_due_followups, update_followup_date,
    default_followup_date,
)
from dashboard_pages._shared import _esc, _safe_url
```

**Cull the imports in `dashboard.py`** — anything now used only inside
`dashboard_pages/myapps.py` should be removed from `dashboard.py`'s
`from nodes.tracker import (...)` block. Do NOT remove imports that are
still used by the page-dispatch code below (e.g. `get_all_applications`
is called by `load_applications` in `dashboard.py`, so keep it).
Run `python -c "import ast; ast.parse(open('dashboard.py', encoding='utf-8').read())"` after the edit to catch syntax errors.

Update `dashboard.py`'s page-dispatch to import the page entry:

```python
from dashboard_pages.myapps import _render_myapps_page
```

The `if page == "📊  My Applications":` block (~line 1151) already calls
`_render_myapps_page(raw_apps)`. No change to that call site is needed
if the symbol is imported.

**Verify**:
- `grep -c "^def _render_myapps_page" dashboard.py` → 0
- `grep -c "^def _render_myapps_page" dashboard_pages/myapps.py` → 1
- `"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -c "from dashboard_pages.myapps import _render_myapps_page, _status_badge_html, _apply_filters, _MYAPPS_STATUS_COLORS; print('ok')"` → `ok`
- `"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -c "from dashboard import _status_badge_html, _apply_filters, _MYAPPS_STATUS_COLORS; print('ok')"` — this will FAIL because Step 4 did not re-export from `dashboard.py`. The tests will red here.
- Skip repointing tests until Step 6, or repoint incrementally as you go.

Commit: `refactor(dashboard): extract My Applications page to dashboard_pages/myapps`.

### Step 5: Move Today's Matches V2 into `matches_v2.py`

Cut from `dashboard.py`:

- Lines 380-425 (status config).
- Lines 426-441 (`get_region_badge`, `get_score_color`).
- Lines 443-489 (`_render_job_row_compact`, `_auto_advance`).
- Lines 490-704 (`_render_job_detail_right`).
- Lines 705-812 (`_render_matches_v2`).

Paste into `dashboard_pages/matches_v2.py`. Expected import set:

```python
import streamlit as st
from datetime import date, datetime
from streamlit_shortcuts import shortcut_button

from nodes.tracker import (
    update_matched_job_company, update_matched_job_applied,
    update_matched_job_rejection, get_rejection_row,
    save_application, promote_not_matched_to_matched,
    _REJECTION_REASONS,
)
from dashboard_pages._shared import _esc, _safe_url
```

Move the `_LEFT_RATIO` / `_LEFT_PANE_HEIGHT` constants from
`dashboard.py:163-164` into `matches_v2.py` (they are only used by the
V2 renderer).

Update `dashboard.py`'s imports:

```python
from dashboard_pages.matches_v2 import _render_matches_v2
```

**Verify**:
- `grep -c "^def _render_matches_v2" dashboard.py` → 0
- `grep -c "^def _render_matches_v2" dashboard_pages/matches_v2.py` → 1
- `wc -l dashboard.py` → ~530 (from 1362)
- `"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -c "import dashboard_pages.matches_v2; print('ok')"` → `ok`

Commit: `refactor(dashboard): extract V2 matches page to dashboard_pages/matches_v2`.

### Step 6: Repoint the tests

Edit `tests/test_dashboard_helpers.py` lines 1-9. Replace the current
import block with:

```python
import pytest

from dashboard_pages._shared import _esc, _safe_url
from dashboard_pages.myapps import (
    _status_badge_html,
    _apply_filters,
    _MYAPPS_STATUS_COLORS,
)
```

Everything else in the file — the `_auto_advance_pure` mirror on line
66, the `test_*` functions — stays byte-identical. The test file does
not import `_render_*` renderer functions.

**Verify**:
- `"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -m pytest tests/test_dashboard_helpers.py -v` → all pass
- Full suite: `"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -m pytest -x` → same pass count as Step 1

Commit: `test(dashboard): repoint dashboard-helper tests at new modules`.

### Step 7: Streamlit smoke test — every page renders

Start the dashboard in the background:

```
"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -m streamlit run dashboard.py --server.headless=true --server.port=8501
```

Wait for `You can now view your Streamlit app in your browser.` then
open http://localhost:8501 and manually click through each sidebar
page:

- 📊 My Applications — cards render; status dropdown works; follow-up
  date input works; toolbar filter/sort works.
- 🎯 Today's Matches — V2 two-pane layout renders; left list scrolls;
  right pane shows job detail; keyboard shortcuts (`a`, `n`, `→`) fire.
- 🔍 Not Matched — table renders.
- 📈 Scrape Health — banner + yield table + top terms render.

If any page crashes with a Python traceback, kill the server, read the
traceback, and fix the specific import or forward-reference. Do NOT
"just try again" — the traceback identifies the exact missing symbol.

Kill the server with Ctrl+C or `taskkill //F //PID <pid>` on Windows
Git Bash.

### Step 8: Line-count sanity

```
wc -l dashboard.py dashboard_pages/*.py
```

Expected (approximate — small drift is fine):

```
   ~530 dashboard.py
     ~1 dashboard_pages/__init__.py
    ~80 dashboard_pages/_shared.py
   ~420 dashboard_pages/myapps.py
   ~410 dashboard_pages/matches_v2.py
  ~1441 total
```

Total should be within ±5% of 1362 (original `dashboard.py` line count)
plus the new module-level docstrings and import blocks. If the total
is more than 1600, the plan likely duplicated code — investigate before
committing.

### Step 9: Update `plans/README.md`

Add a new row after the plan 026 row:

```
| 027  | Split dashboard.py into a dashboard_pages/ package                    | P2       | M      | MED  | 025        | DONE — dashboard.py 1362 → ~530 lines; dashboard_pages/{_shared,myapps,matches_v2}.py extracted verbatim (no logic changes); tests/test_dashboard_helpers.py repointed at new modules; suite <N> passed / 0 failed; streamlit smoke: all 4 pages render. |
```

Replace `<N>` with the actual pass count.

## Test plan

**No new tests.** This plan is a mechanical extraction — the existing
307+ tests are the safety net. The test file gets a two-block import
edit (see Step 6). Every other test file is untouched.

Streamlit smoke (Step 7) is the human-visible verification; there is no
existing framework for automated end-to-end Streamlit tests in this
repo and adding one is out of scope.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `test -d dashboard_pages && test -f dashboard_pages/__init__.py`
- [ ] `test -f dashboard_pages/_shared.py && test -f dashboard_pages/myapps.py && test -f dashboard_pages/matches_v2.py`
- [ ] `grep -c "^def _esc\|^def _safe_url\|^def render_date_chips" dashboard.py` → 0
- [ ] `grep -c "^def _render_myapps_page\|^def _render_matches_v2\|^def _render_job_detail_right" dashboard.py` → 0
- [ ] `grep -c "^def _esc\|^def _safe_url\|^def render_date_chips" dashboard_pages/_shared.py` → 3
- [ ] `grep -c "^def _status_badge_html\|^def _apply_filters\|^def _render_myapps_page" dashboard_pages/myapps.py` → 3
- [ ] `grep -c "^def _render_matches_v2\|^def _render_job_detail_right" dashboard_pages/matches_v2.py` → 2
- [ ] `python -m pytest -x` → same pass count as Step 1 baseline
- [ ] Streamlit smoke (Step 7): all 4 sidebar pages render without traceback
- [ ] `wc -l dashboard.py` reports under 700 (was 1362)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back if:

- Any moved function references a symbol from another moved bucket
  (e.g. a MyApps function calls a V2 helper, or vice versa). The plan
  assumes the split boundary is clean; if it isn't, the buckets need
  redesigning before proceeding.
- The custom CSS block (lines 204-349) contains inline references to a
  Python symbol (not observed at plan-writing time; possible but
  unlikely). If it does, that string constant needs to move to
  `dashboard.py`'s in-scope area.
- Any test unrelated to `test_dashboard_helpers.py` fails after the
  split. The plan makes no logic changes — a test failure elsewhere
  is a symptom of an import cycle, a missing re-export, or a
  forward-reference.
- The streamlit smoke fails with `ModuleNotFoundError: dashboard_pages`.
  That means `streamlit run dashboard.py` was executed from a
  directory other than the repo root. Cd to repo root and retry
  before treating it as a bug.
- More than three commits' worth of "just one more fix" is required
  after the smoke test. That is a strong signal the split boundary
  chosen here is wrong; STOP and report which functions actually
  need to move together.

## Maintenance notes

- **Future page additions**: create a new `dashboard_pages/<page>.py`
  module and add its entry-point call in `dashboard.py`'s page-dispatch
  block. The pattern to match is the two extractions in this plan.
- **Do NOT re-export from `dashboard.py`** for the pages' internals
  going forward. The point of the split is that `dashboard.py` becomes
  a thin shell; growing it back into a re-export hub defeats the
  purpose.
- **`test_dashboard_helpers.py`** is the only file that imports from
  the pure-helper modules for testing. If a future plan adds pure
  helpers to `matches_v2.py`, add matching imports to the test file.
- **Not Matched + Scrape Health** live inline in the page-dispatch
  code. If they grow past ~150 lines each, extract them the same way
  as this plan (small follow-up plan, not this one).
- **Reviewer scrutiny**: the diff for this plan should be dominated by
  moves (git recognizes them under `-M`). Any non-move diff hunk is a
  place to double-check — the plan is meant to be behavior-preserving.
