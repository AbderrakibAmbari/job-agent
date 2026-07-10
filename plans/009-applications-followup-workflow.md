# Plan 009: Applications follow-up workflow (status transitions + stale reminders)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command. Stop on any STOP condition. Update the status
> row in `plans/README.md` when done.
>
> **Drift check (run first)**: `git diff --stat 35bacd0..HEAD -- dashboard.py nodes/tracker.py`
> If either file changed since this plan was written, compare the
> "Current state" excerpts against live code before proceeding.
>
> **Re-affirmation note (2026-07-10, `35bacd0`)**: this plan was
> originally written at `5bed640` on 2026-07-02. Line numbers have
> drifted since then (plans 014/016/017 landed), but STRUCTURE is
> intact. Corrected line references:
> - `save_application` is now at `nodes/tracker.py:230-252` (was 161-182).
>   Plan 017 added `_normalize_url(job_url) → norm_url` at line 232 and
>   changed the INSERT to store `norm_url` (line 249). **PRESERVE
>   these when applying the Step 1 edit** — the follow-up-date change
>   is orthogonal to the URL-normalization work.
> - `update_status` / `delete_application` are at `nodes/tracker.py:561`
>   and `:570` (were 487-500).
> - "My Applications" page in `dashboard.py` starts at line 382 (was 367).
>   Metrics `st.columns(5)` row is at `dashboard.py:387` (was 374).
>   Status selectbox is at line 441 (was 428).
> - Baseline test count is 212 → target after this plan is 225 passed
>   (212 + 13 new).

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: LOW
- **Depends on**: none (soft-dep on `plans/002` for the pytest infra used
  by the new helper tests)
- **Category**: direction (feature — application lifecycle)
- **Planned at**: commit `5bed640`, 2026-07-02 (re-affirmed at `35bacd0`, 2026-07-10)

## Why this matters

The Applications page in `dashboard.py` shows a `status` selectbox with
6 options (`Pending Review`, `Sent`, `Waiting`, `Interview`, `Rejected`,
`Offer`). But in `data/applications.db` on 2026-07-02, **all 139
applications sit at `status = "Sent"`**. Not one has moved. Two failure
modes explain that:

1. The status column is out of view — the operator doesn't remember it
   exists.
2. There's no signal for *when* to check on an application. A recruiter
   who was going to reply within a week hasn't replied — nobody's told
   the operator to poke them.

The applications table already has a `follow_up_date` column
(`nodes/tracker.py:56-63`), populated at insert-time to `date_applied`
(which effectively means "same day", i.e. useless as a reminder). The
schema is there; the UX around it isn't.

This plan makes two changes:

1. **Auto-suggest a follow-up date** at the point where a new
   application is saved. Default: `date_applied + 7 days`. The
   `save_application` function currently overwrites `follow_up_date`
   with `date_applied` — change that to +7 days.
2. **Add a "Follow-up due" section** to the top of the Applications
   page that lists rows where `status = "Sent"` OR `"Waiting"` AND
   `follow_up_date <= today`. One row per due follow-up with the
   company, role, days-since-application, and quick-action buttons
   (`Waiting → Rejected`, `Waiting → Interview`).

Both changes are small, keep the current UI shape, and directly address
the observed "139 stuck at Sent" pattern without inventing a whole
workflow tool. If richer lifecycle tracking (email integration,
calendar sync, etc.) is wanted later, that's a separate plan.

Do NOT restructure the applications page or introduce a new page. Do NOT
add a state machine — keep the existing selectbox as the single source
of truth for status.

## Current state

Relevant files:

- `nodes/tracker.py:161-182` — `save_application()` currently sets
  `follow_up_date = date_applied` (same day):
  ```python
  # nodes/tracker.py:161-182
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

- `nodes/tracker.py:487-500` — `update_status()` and
  `delete_application()`; `update_status` only touches `status`, not
  `follow_up_date`.

- `dashboard.py:367-450` — the "My Applications" page. Metrics row +
  filters + expander list. This is where the new "Follow-up due"
  section goes, immediately below the metrics row (line 386-ish) and
  above the filter row (line 392).

- `dashboard.py:411-449` — the per-application expander. Contains the
  status selectbox (line 428-433) and save button (434-438). No
  follow-up date is currently displayed inside the expander.

Repo conventions:
- All DB access via `nodes/tracker.py` helpers — dashboard.py never
  runs raw SQL. Add helpers there; don't inline SQL in dashboard.py.
- `st.cache_data.clear()` before `st.rerun()` after any DB mutation
  (see dashboard.py:436 for the pattern).
- Use `_esc(...)` / `_safe_url(...)` for anything interpolated into
  `unsafe_allow_html=True` blocks (Plan 004's convention).
- Follow-up date format: `YYYY-MM-DD` strings, not `datetime` objects
  (the schema stores TEXT).

## Commands you will need

| Purpose | Command |
|---------|---------|
| Activate venv | `source venv/Scripts/activate` |
| Run tracker tests | `venv/Scripts/python.exe -m pytest tests/ -v` |
| Full suite | `venv/Scripts/python.exe -m pytest -q` |
| Launch dashboard for manual smoke | `venv/Scripts/streamlit run dashboard.py` |
| Inspect current data | `venv/Scripts/python.exe -c "from nodes.tracker import get_all_applications; [print(r) for r in get_all_applications()[:3]]"` |

## Scope

**In scope**:

- `nodes/tracker.py` — change `save_application`'s follow-up date
  default from same-day to +7 days. Add three new helpers:
  `get_due_followups()`, `update_followup_date(app_id, new_date)`,
  `_default_followup_date(from_date_str)` (pure, testable).
- `dashboard.py` — add a "Follow-up due" section at the top of the
  Applications page, above the metrics row. Add a follow-up-date
  display + editable input inside each expander.
- `tests/test_tracker_followup.py` (NEW) — pure-function tests for
  `_default_followup_date` and integration tests for
  `get_due_followups()` using a temp DB fixture (see conftest for
  the pattern if it exists).

**Out of scope** (do NOT touch):

- The `applications` schema — no new columns needed. Everything fits
  in the existing `follow_up_date` TEXT column.
- Any migration to backfill existing rows. Leave the 139 existing
  applications' `follow_up_date` as-is; they'll all show as "due
  today" until manually updated, which is *the right behavior* — the
  operator has been ignoring them for months and should be nudged.
- Email/calendar/webhook integrations. Plan 010 covers push
  notifications for a different concern; do not chain them.
- Changing the STATUS_OPTIONS constant or the state selectbox
  behavior.
- `matched_jobs` table or the Today's Matches page. Unrelated.

## Git workflow

- Branch: `advisor/009-applications-followup`
- 2 commits recommended: (1) tracker + tests, (2) dashboard wiring.
  One combined is fine if it stays under ~200 lines.
- Commit message: `Plan 009: applications follow-up workflow`
- Do NOT push or open a PR unless instructed.

## Steps

### Step 1: Add follow-up helpers to `nodes/tracker.py`

Add these functions. Place them near the other application helpers
(after `save_application`, around line 183):

```python
from datetime import date, timedelta


def _default_followup_date(from_date_str: str, days: int = 7) -> str:
    """Compute the default follow-up date. Pure function — safe to unit-test.

    from_date_str: 'YYYY-MM-DD'
    Returns: 'YYYY-MM-DD' of from_date + days.
    """
    d = date.fromisoformat(from_date_str)
    return (d + timedelta(days=days)).strftime("%Y-%m-%d")


def get_due_followups(today_str: str = None) -> list:
    """Return applications with status in ('Sent', 'Waiting') AND
    follow_up_date <= today. Ordered oldest-follow-up first.

    Rows shape matches applications table:
    (id, company, job_title, platform, date_applied, status,
     cover_letter, job_url, follow_up_date)
    """
    today = today_str or datetime.now().strftime("%Y-%m-%d")
    with _conn() as conn:
        return conn.execute("""
            SELECT id, company, job_title, platform, date_applied, status,
                   cover_letter, job_url, follow_up_date
            FROM applications
            WHERE status IN ('Sent', 'Waiting')
              AND follow_up_date IS NOT NULL
              AND follow_up_date != ''
              AND follow_up_date <= ?
            ORDER BY follow_up_date ASC, date_applied ASC
        """, (today,)).fetchall()


def update_followup_date(app_id: int, new_date: str) -> None:
    """Update follow_up_date for a given application. new_date: 'YYYY-MM-DD'."""
    with _conn() as conn:
        conn.execute(
            "UPDATE applications SET follow_up_date = ? WHERE id = ?",
            (new_date, app_id)
        )
        conn.commit()
```

Then edit `save_application` at lines 230-252 to use the new default.
**IMPORTANT**: preserve plan 017's `_normalize_url(job_url) → norm_url`
call and use `norm_url` in both the SELECT and the INSERT:

```python
def save_application(company: str, job_title: str, platform: str,
                     cover_letter: str, job_url: str) -> None:
    norm_url = _normalize_url(job_url)  # plan 017 — preserve
    with _conn() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT id FROM applications
            WHERE job_url = ? OR (company = ? AND job_title = ?)
        """, (norm_url, company, job_title))
        if c.fetchone():
            return
        today = datetime.now().strftime("%Y-%m-%d")
        c.execute("""
            INSERT INTO applications
            (company, job_title, platform, date_applied,
             cover_letter, job_url, follow_up_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            company, job_title, platform,
            today, cover_letter, norm_url,
            _default_followup_date(today),
        ))
        conn.commit()
```

**Verify**:

```bash
venv/Scripts/python.exe -c "
from nodes.tracker import _default_followup_date
print(_default_followup_date('2026-07-02'))
print(_default_followup_date('2026-12-30'))
"
```

Expected: `2026-07-09` then `2027-01-06`.

### Step 2: Add tests

Create `tests/test_tracker_followup.py`:

```python
import os
import tempfile
import pytest
from datetime import date, timedelta

from nodes import tracker


# ---------- _default_followup_date (pure) ----------

def test_default_followup_default_is_plus_7_days():
    assert tracker._default_followup_date("2026-07-02") == "2026-07-09"


def test_default_followup_crosses_month_boundary():
    assert tracker._default_followup_date("2026-06-28") == "2026-07-05"


def test_default_followup_crosses_year_boundary():
    assert tracker._default_followup_date("2026-12-30") == "2027-01-06"


def test_default_followup_custom_days():
    assert tracker._default_followup_date("2026-07-02", days=14) == "2026-07-16"


def test_default_followup_zero_days_returns_same_day():
    assert tracker._default_followup_date("2026-07-02", days=0) == "2026-07-02"


def test_default_followup_leap_year():
    # 2028 is a leap year; feb 22 + 7 days = feb 29
    assert tracker._default_followup_date("2028-02-22") == "2028-02-29"


def test_default_followup_invalid_input_raises():
    with pytest.raises(ValueError):
        tracker._default_followup_date("not-a-date")


# ---------- get_due_followups / update_followup_date (DB) ----------

@pytest.fixture
def temp_db(monkeypatch):
    """Point DB_PATH at a fresh temp file and init_db it."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(tracker, "DB_PATH", path)
    tracker.init_db()
    yield path
    os.remove(path)


def test_get_due_followups_returns_only_sent_and_waiting(temp_db):
    tracker.save_application("Acme", "Junior Dev", "LinkedIn", "", "https://x/1")
    tracker.save_application("Beta", "Backend", "XING", "", "https://x/2")
    tracker.save_application("Gamma", "Frontend", "Indeed", "", "https://x/3")
    # Move Beta to Rejected — shouldn't show up
    rows = tracker.get_all_applications()
    beta_id = [r[0] for r in rows if r[1] == "Beta"][0]
    tracker.update_status(beta_id, "Rejected")
    # Force everyone's follow-up to today
    today = date.today().strftime("%Y-%m-%d")
    for r in tracker.get_all_applications():
        tracker.update_followup_date(r[0], today)

    due = tracker.get_due_followups()
    companies = [r[1] for r in due]
    assert "Acme" in companies
    assert "Gamma" in companies
    assert "Beta" not in companies


def test_get_due_followups_excludes_future_dates(temp_db):
    tracker.save_application("Future", "Role", "LinkedIn", "", "https://x/f")
    row = tracker.get_all_applications()[0]
    future = (date.today() + timedelta(days=30)).strftime("%Y-%m-%d")
    tracker.update_followup_date(row[0], future)
    assert tracker.get_due_followups() == []


def test_get_due_followups_includes_overdue(temp_db):
    tracker.save_application("Overdue", "Role", "LinkedIn", "", "https://x/o")
    row = tracker.get_all_applications()[0]
    past = (date.today() - timedelta(days=14)).strftime("%Y-%m-%d")
    tracker.update_followup_date(row[0], past)
    due = tracker.get_due_followups()
    assert len(due) == 1
    assert due[0][1] == "Overdue"


def test_get_due_followups_orders_by_follow_up_date_asc(temp_db):
    tracker.save_application("A", "R", "L", "", "https://x/a")
    tracker.save_application("B", "R", "L", "", "https://x/b")
    a_id, b_id = [r[0] for r in tracker.get_all_applications()]
    tracker.update_followup_date(a_id, "2026-07-01")
    tracker.update_followup_date(b_id, "2026-06-20")
    due = tracker.get_due_followups(today_str="2026-07-10")
    assert [r[1] for r in due] == ["B", "A"]


def test_update_followup_date_persists(temp_db):
    tracker.save_application("Acme", "Role", "LinkedIn", "", "https://x/u")
    row = tracker.get_all_applications()[0]
    tracker.update_followup_date(row[0], "2027-01-15")
    row = tracker.get_all_applications()[0]
    assert row[8] == "2027-01-15"  # follow_up_date column


def test_save_application_default_followup_is_plus_7_days(temp_db):
    tracker.save_application("Acme", "Role", "LinkedIn", "", "https://x/s")
    row = tracker.get_all_applications()[0]
    d_applied = date.fromisoformat(row[4])
    d_followup = date.fromisoformat(row[8])
    assert (d_followup - d_applied).days == 7
```

**Verify**: `venv/Scripts/python.exe -m pytest tests/test_tracker_followup.py -v` → 13 passed, 0 failed.

### Step 3: Wire the "Follow-up due" section into the dashboard

Edit `dashboard.py` — add the import at the top (near line 7-14):

```python
from nodes.tracker import (
    init_db, get_all_applications, get_matched_jobs,
    update_status, delete_application,
    update_matched_job_company, update_matched_job_applied,
    get_applied_status, get_applied_statuses, save_application,
    get_not_matched_jobs, get_scrape_dates,
    promote_not_matched_to_matched,
    get_due_followups, update_followup_date,  # ← Plan 009
)
```

Add a cached loader right after the existing ones (around line 60):

```python
@st.cache_data(ttl=300)
def load_due_followups():
    return get_due_followups()
```

Then edit the "My Applications" page. Insert a new section IMMEDIATELY
after the title/hr (i.e. between `st.markdown("---")` at line 372 and
the metrics-row `col1, col2, col3, col4, col5 = st.columns(5)` at line
374):

```python
    # ── Follow-up due (Plan 009) ──────────────────────
    due = load_due_followups()
    if due:
        st.markdown(
            f'<div style="padding:10px 14px; margin-bottom:12px; '
            f'border-left:3px solid #d29922; background:#332b00; '
            f'border-radius:4px; color:#e6e6e6;">'
            f'🔔 <strong>{len(due)} follow-up{"s" if len(due) > 1 else ""} due</strong> '
            f'— applications waiting on a reply past their follow-up date.'
            f'</div>',
            unsafe_allow_html=True,
        )
        with st.expander(f"Show {len(due)} due follow-up(s)", expanded=False):
            for r in due:
                app_id, company, job_title, platform, date_applied, status, _cover, job_url, follow_up = r
                days_since = (
                    datetime.now().date() - datetime.strptime(date_applied, "%Y-%m-%d").date()
                ).days if date_applied else 0

                fu_cols = st.columns([3, 1, 1, 1, 1])
                with fu_cols[0]:
                    safe = _safe_url(job_url) if job_url else ""
                    link_html = (
                        f' <a href="{safe}" target="_blank" style="color:#58a6ff; '
                        f'font-size:12px; text-decoration:none;">↗</a>'
                        if safe else ""
                    )
                    st.markdown(
                        f"**{_esc(company)}** — {_esc(job_title)}  "
                        f"<span style='color:#8b949e;font-size:12px;'>"
                        f"({days_since}d ago · {_esc(status)}){link_html}"
                        f"</span>",
                        unsafe_allow_html=True,
                    )
                with fu_cols[1]:
                    if st.button("Interview", key=f"fu_int_{app_id}"):
                        update_status(app_id, "Interview")
                        st.cache_data.clear()
                        st.rerun()
                with fu_cols[2]:
                    if st.button("Rejected", key=f"fu_rej_{app_id}"):
                        update_status(app_id, "Rejected")
                        st.cache_data.clear()
                        st.rerun()
                with fu_cols[3]:
                    if st.button("Snooze +7d", key=f"fu_snz_{app_id}"):
                        from nodes.tracker import _default_followup_date
                        today = datetime.now().strftime("%Y-%m-%d")
                        update_followup_date(app_id, _default_followup_date(today))
                        st.cache_data.clear()
                        st.rerun()
                with fu_cols[4]:
                    st.markdown(
                        f"<span style='color:#8b949e;font-size:11px;'>due {_esc(follow_up)}</span>",
                        unsafe_allow_html=True,
                    )
        st.markdown("---")
```

Inside the per-application expander (starting around line 411), add a
follow-up date row below the existing `Status` line. Insert after
`st.markdown(f"**Status** ... ")` at line 422:

```python
                    fu_col1, fu_col2 = st.columns([3, 1])
                    with fu_col1:
                        new_fu = st.date_input(
                            "Follow-up date",
                            value=(
                                datetime.strptime(row["follow_up_date"], "%Y-%m-%d").date()
                                if row["follow_up_date"] else datetime.now().date()
                            ),
                            key=f"fu_date_{row['id']}",
                        )
                    with fu_col2:
                        st.markdown("<br>", unsafe_allow_html=True)
                        if st.button("Save follow-up", key=f"fu_save_{row['id']}"):
                            update_followup_date(row["id"], new_fu.strftime("%Y-%m-%d"))
                            st.cache_data.clear()
                            st.success(f"Follow-up set to {new_fu}")
                            st.rerun()
```

### Step 4: Manual smoke test

```bash
venv/Scripts/streamlit run dashboard.py
```

Open in browser. Go to "My Applications" page. Expected:

1. **Follow-up due banner appears** at the top (all 139 existing
   applications have `follow_up_date = date_applied`, so most/all should
   be overdue).
2. **Expander shows the due list** with columns: company/title/status,
   Interview button, Rejected button, Snooze +7d button, due date.
3. **Clicking Snooze +7d** on a row bumps its `follow_up_date` by 7 days
   and re-runs; the row disappears from the "due" list.
4. **Clicking Rejected** moves the row to `status = "Rejected"` and it
   disappears from the "due" list.
5. **Opening any individual application expander** shows the
   follow-up-date date_input widget. Changing the date and clicking
   "Save follow-up" persists.
6. **Existing behavior is intact** — filter, search, status selectbox,
   delete button, cover letter display all work as before.

**Verify DB directly** after clicking Rejected on one row:

```bash
venv/Scripts/python.exe -c "
from nodes.tracker import get_all_applications
rows = [r for r in get_all_applications() if r[5] == 'Rejected']
print(f'{len(rows)} Rejected applications')
"
```

Expected: count > 0 (one for each click).

### Step 5: Update `plans/README.md`

Flip plan 009's status row to `DONE` with the commit SHA and pass counts.

## Test plan

- **New unit tests** in `tests/test_tracker_followup.py` — 13 cases:
  - `_default_followup_date` — 7 cases (default, month/year boundaries,
    custom days, zero days, leap year, invalid input).
  - `get_due_followups` — 4 cases (only Sent/Waiting; future excluded;
    overdue included; ordering).
  - `update_followup_date` persistence — 1 case.
  - `save_application` default is +7 days — 1 case.
- **Manual smoke** — Step 4 recipe. Non-automated but critical because
  Streamlit UI can't be unit-tested easily.
- **Verification**: `venv/Scripts/python.exe -m pytest -q` → 212 + 13
  = 225 passed, 0 xfailed, 0 failed.

## Done criteria

ALL must hold:

- [ ] `nodes/tracker.py` has `_default_followup_date`,
      `get_due_followups`, `update_followup_date` and the updated
      `save_application`.
- [ ] `tests/test_tracker_followup.py` exists with 13 passing tests.
- [ ] `dashboard.py` imports `get_due_followups` /
      `update_followup_date`, has the "Follow-up due" section at the top
      of the Applications page, and the follow-up date_input inside
      each expander.
- [ ] `venv/Scripts/python.exe -m pytest -q` → 225 passed / 0 xfailed
      / 0 failed / exit 0.
- [ ] Manual smoke (Step 4) all 6 checks pass.
- [ ] `plans/README.md` row for plan 009 flipped to `DONE`.
- [ ] `git diff --stat` shows only `nodes/tracker.py`, `dashboard.py`,
      `tests/test_tracker_followup.py`, `plans/README.md` modified.

## STOP conditions

Stop and report if:

- `save_application` at lines 161-182 doesn't match the excerpt above
  (drift).
- The applications table already has a status transition workflow
  (someone landed a similar plan; check `plans/README.md`).
- Any existing test in `tests/` fails after your changes. In
  particular, watch `tests/test_tracker_keys.py` — it uses `_conn()`
  indirectly via `get_known_urls`/`get_known_title_keys`; the fixture
  isolation must not leak.
- The Streamlit reload behavior on Snooze/Rejected/Save is broken (row
  doesn't disappear, exception in terminal). `st.cache_data.clear()`
  before `st.rerun()` is the pattern — verify all four button handlers
  do both.
- You find yourself introducing a state machine, notifications, or
  email — out of scope.
- You find yourself editing `matched_jobs` or Today's Matches UI —
  wrong table, wrong page.

## Maintenance notes

- **The 7-day default is a heuristic.** Some hiring processes are
  faster (14 days feels lazy in Germany's junior market, and 7 days is
  aggressive enough to actually create pressure without spamming).
  Trivial to change — one constant in `_default_followup_date`. Don't
  over-tune; the operator will discover the right cadence.
- **Existing 139 rows will all show as "due"** on first render. That
  is deliberate — the whole point is that they've been ignored for
  months. If the banner looks alarming, use the Snooze buttons or
  Rejected buttons to walk them down.
- **When Plan 013 (rejection-reason capture) lands**, the "Rejected"
  button in the due-list will become richer — probably a popover with
  a reason dropdown before actually updating status. Design for that:
  keep the current button as-is; Plan 013 can swap the handler.
- **Reviewer focus:** verify that `save_application`'s dedup check
  (the `SELECT id FROM applications WHERE job_url = ? OR (company = ?
  AND job_title = ?)` at line 165-167) still short-circuits before
  the new follow-up date computation. The current diff should show
  only the INSERT body changing; the SELECT stays identical.
- **Cache invalidation:** `load_due_followups` is
  `@st.cache_data(ttl=300)`. Every mutation (`update_status`,
  `update_followup_date`) MUST be followed by `st.cache_data.clear()`
  before `st.rerun()` — otherwise the banner won't refresh. The
  pattern is already established in the file (see the existing Save
  button at line 434-438).
