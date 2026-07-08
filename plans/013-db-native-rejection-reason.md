# Plan 013: Capture rejection reasons on "Not Applying" clicks

> **Executor instructions**: Follow this plan step by step. Run every
> verification command. Stop on any STOP condition. Update the status
> row in `plans/README.md` when done.
>
> **Drift check (run first)**: `git diff --stat 5bed640..HEAD -- dashboard.py nodes/tracker.py`
> If either file changed since this plan was written, compare the
> "Current state" excerpts against live code before proceeding.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: LOW (additive schema column + one UI flow change)
- **Depends on**: soft on `plans/009-applications-followup-workflow.md`
  (both touch matched_jobs UX; 013 does not require 009 landed but
  will re-touch the same expander block — see "Merge notes" below)
- **Category**: direction (feature — feedback loop foundation)
- **Planned at**: commit `5bed640`, 2026-07-02

## Why this matters

The dashboard has TWO ways to record "this job wasn't for me":

1. **"Not Applying" button** at `dashboard.py:610-618` — sets
   `matched_jobs.applied = 2`, no reason captured.
2. **"Log feedback" expander** at `dashboard.py:621-637` — writes to
   `data/feedback_log.txt` via `nodes/feedback_log.py`.

The feedback log has **2 entries total** in `data/feedback_log.txt`,
both from 2026-04-28. It's write-only and hasn't been touched in over
two months. Meanwhile, 411 matched jobs have `applied = 2` ("not
applying") — the operator IS making that decision constantly, just
never capturing *why*. That data would fuel Plan 011's category
taxonomy tuning ("all my not-applying jobs are `SAP/ERP` — cap harder")
and eventually a scorer-calibration feedback loop.

The cheap fix: capture the reason at the moment of the "Not Applying"
click via a small popover (or inline widget) with a fixed dropdown, and
persist to a new `matched_jobs.rejection_reason` TEXT column. Free-text
optional. No new table. No LLM. No lifecycle.

This plan is **feedback-loop foundation only** — capture the signal.
Actually feeding the signal back into the scoring prompt or the
`_quick_reject` regexes is deliberately deferred to a future plan.
Without data, there's nothing to calibrate against, and building the
calibrator before the data exists puts the cart before the horse.

Deprecate the existing "Log feedback" expander in the same change — it's
already write-only in practice, and having two mechanisms for the same
UX invites confusion. Preserve `data/feedback_log.txt` (do NOT delete;
respect the past) but remove the UI hook that adds new entries.

## Current state

Relevant files:

- `dashboard.py:610-618` — "Not Applying" button, single-click, no reason
  capture:
  ```python
  # dashboard.py:610-618
  with btn_col2:
      if st.button(
          "Not Applying",
          key=f"notapplied_{job_id}",
          type="primary" if apply_state != 2 else "secondary"
      ):
          update_matched_job_applied(job_id, 2)
          st.cache_data.clear()
          st.rerun()
  ```

- `dashboard.py:620-637` — "Log feedback" expander, to be removed:
  ```python
  st.markdown("---")
  with st.expander("Log feedback for this job"):
      fb_c1, fb_c2 = st.columns([1, 2])
      with fb_c1:
          fb_result = st.selectbox(
              "Outcome",
              ["applied", "not_interested", "link_broken",
               "needs_review", "saved_for_later"],
              key=f"fb_result_{job_id}"
          )
      with fb_c2:
          fb_action = st.text_input(
              "Action needed (optional)",
              key=f"fb_action_{job_id}"
          )
      if st.button("Log feedback", key=f"fb_btn_{job_id}"):
          append_feedback(company, job_title, platform, fb_result, fb_action)
          st.success("Logged!")
  ```

- `nodes/tracker.py:66-96` — `matched_jobs` schema + safe-migration
  loop (lines 88-96). Add the new column here.

- `nodes/tracker.py:361-368` — `update_matched_job_applied(job_id: int,
  state: int)`. This is the current writer of `applied`. Extend it, or
  add a companion writer for reasons — see Step 2 for the choice.

- `nodes/feedback_log.py` — the append-only text log. NOT modified by
  this plan; the import in dashboard.py just becomes unused.

Repo conventions:
- Schema migrations use the safe-add pattern at
  `nodes/tracker.py:88-96` — `try: ALTER TABLE ADD COLUMN ... except:
  pass`. Add new columns there; do NOT rewrite the CREATE TABLE.
- All DB writes go through `nodes/tracker.py`. `dashboard.py` never
  runs raw SQL.
- Streamlit mutation pattern: DB call → `st.cache_data.clear()` →
  `st.rerun()`.
- Rejection-reason dropdown values should be short, stable strings
  (they'll be aggregated in future) — no free-text-only mode.

## Commands you will need

| Purpose | Command |
|---------|---------|
| Activate venv | `source venv/Scripts/activate` |
| Run tests | `venv/Scripts/python.exe -m pytest tests/ -v` |
| Full suite | `venv/Scripts/python.exe -m pytest -q` |
| Inspect schema | `venv/Scripts/python.exe -c "import sqlite3; c=sqlite3.connect('data/applications.db').execute('PRAGMA table_info(matched_jobs)'); [print(r) for r in c]"` |
| Launch dashboard | `venv/Scripts/streamlit run dashboard.py` |

## Scope

**In scope**:

- `nodes/tracker.py`:
  - Add `rejection_reason TEXT DEFAULT ''` to the safe-migration loop.
  - Add `update_matched_job_rejection(job_id: int, reason: str, note:
    str = "") -> None` — writes both `applied = 2` AND
    `rejection_reason` in one UPDATE.
  - Add `get_rejection_reason_counts() -> list[tuple[str, int]]` for
    the maintenance dashboard.
- `dashboard.py`:
  - Replace the single-click "Not Applying" button with a popover
    containing a reason dropdown + optional note + Save button.
    (Streamlit ≥ 1.32 has `st.popover`; assume it's available — the
    dashboard already uses modern Streamlit features.)
  - Delete the "Log feedback" expander (lines 620-637). Remove the
    `append_feedback` import at line 6 iff no other reference exists.
  - Show the currently stored reason (if any) next to the "Not
    Applying" button when a job already has `applied == 2`.
- `tests/test_tracker_rejection.py` (NEW) — tests for the new writer,
  reader, and safe-migration idempotency.

**Out of scope** (do NOT touch):

- `nodes/feedback_log.py` and `data/feedback_log.txt` — leave the
  legacy module and file untouched. The import goes; the module stays
  in the codebase for now. (Removing the module is a plan-003-style
  cleanup, not this plan.)
- Any calibration/re-scoring based on captured reasons. Data collection
  only.
- The `applied = 1` (applied) path. This plan is symmetric-in-name only
  — no reason capture for the Applied side. If the operator later wants
  an "outcome" column (interview / offer / rejection-by-recruiter),
  that's a plan-009-lifecycle concern, not this one.
- Historical rejections — the 411 existing `applied = 2` rows keep
  `rejection_reason = ''`. Do NOT try to backfill.
- Not-Matched or Applications pages. Rejection reason lives on
  matched_jobs only.

## Merge notes with Plan 009

Plan 009 adds a follow-up-date widget INSIDE the applications-page
expander, not the today's-matches expander. This plan touches the
today's-matches actions column. There is NO shared code between them —
they touch different pages. But if both plans land in the same PR:

- Plan 009 doesn't touch `dashboard.py:585-638`.
- Plan 013 doesn't touch `dashboard.py:411-450`.

If plan 009 landed first, no rebase issues. If plan 013 lands first,
plan 009's insert point (line 422) is unaffected. Order-independent.

## Git workflow

- Branch: `advisor/013-rejection-reason-capture`
- 2 commits recommended: (1) tracker + tests, (2) dashboard rewiring.
- Commit message: `Plan 013: capture rejection reason on Not Applying click`
- Do NOT push or open a PR unless instructed.

## Steps

### Step 1: Extend the schema and add tracker helpers

Edit `nodes/tracker.py:88-96` — add the new column to the safe-migration
loop:

```python
        # Safe column migrations
        for col, definition in [
            ("applied",           "INTEGER DEFAULT 0"),
            ("all_urls",          "TEXT DEFAULT '[]'"),
            ("job_category",      "TEXT DEFAULT 'Other'"),
            ("rejection_reason",  "TEXT DEFAULT ''"),
            ("rejection_note",    "TEXT DEFAULT ''"),
        ]:
            try:
                c.execute(f"ALTER TABLE matched_jobs ADD COLUMN {col} {definition}")
            except Exception:
                pass
```

Then add these helpers near the other `update_matched_job_*` functions
(around line 361 area):

```python
_REJECTION_REASONS = (
    "not-tech",
    "wrong-tech",
    "wrong-seniority",
    "wrong-location",
    "wrong-contract",
    "employer-mismatch",
    "already-applied-elsewhere",
    "link-broken",
    "other",
)


def update_matched_job_rejection(job_id: int, reason: str, note: str = "") -> None:
    """Mark a matched job as not-applying with a captured reason.

    reason: one of _REJECTION_REASONS (validation is soft — unknown reasons
    are stored verbatim so we don't lose data if the dropdown drifts).
    """
    with _conn() as conn:
        conn.execute(
            "UPDATE matched_jobs "
            "SET applied = 2, rejection_reason = ?, rejection_note = ? "
            "WHERE id = ?",
            (reason or "", note or "", job_id)
        )
        conn.commit()


def get_rejection_row(job_id: int) -> tuple[str, str] | None:
    """Return (reason, note) for a job, or None if not rejected."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT rejection_reason, rejection_note FROM matched_jobs WHERE id = ?",
            (job_id,)
        ).fetchone()
    if not row:
        return None
    return (row[0] or "", row[1] or "")


def get_rejection_reason_counts() -> list:
    """Aggregate reason counts across matched_jobs. Empty reason excluded.

    Returns: list[tuple[str, int]] sorted desc by count.
    """
    with _conn() as conn:
        rows = conn.execute(
            "SELECT rejection_reason, COUNT(*) FROM matched_jobs "
            "WHERE applied = 2 AND rejection_reason != '' "
            "GROUP BY rejection_reason ORDER BY 2 DESC"
        ).fetchall()
    return [(r[0], r[1]) for r in rows]
```

**Verify** the migration is idempotent:

```bash
venv/Scripts/python.exe -c "
from nodes.tracker import init_db
init_db(); init_db()  # Run twice — second call must not raise
print('idempotent OK')
import sqlite3
cols = [r[1] for r in sqlite3.connect('data/applications.db').execute('PRAGMA table_info(matched_jobs)')]
assert 'rejection_reason' in cols and 'rejection_note' in cols, cols
print('columns present')
"
```

Expected: `idempotent OK` then `columns present`.

### Step 2: Add tests

Create `tests/test_tracker_rejection.py`:

```python
import os
import tempfile
import pytest

from nodes import tracker


@pytest.fixture
def temp_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(tracker, "DB_PATH", path)
    tracker.init_db()
    yield path
    os.remove(path)


def _seed_job(job_id: int = 1, url: str = "https://x/1"):
    """Insert a matched job with the given id and url."""
    tracker.save_matched_jobs([{
        "title": "Junior Backend", "company": "Acme", "location": "Bochum",
        "platform": "LinkedIn", "url": url, "score": 75,
        "recommendation": "Good Match", "match_reasons": [], "missing": [],
        "contract_type": "Full-time", "work_mode": "Hybrid",
        "link_status": "alive", "job_category": "Backend",
    }])
    # Return the actual generated id
    import sqlite3
    with sqlite3.connect(tracker.DB_PATH) as conn:
        row = conn.execute("SELECT id FROM matched_jobs WHERE job_url = ?", (url,)).fetchone()
    return row[0]


def test_init_db_idempotent(temp_db):
    tracker.init_db()
    tracker.init_db()  # should not raise


def test_schema_has_new_rejection_columns(temp_db):
    import sqlite3
    cols = [r[1] for r in sqlite3.connect(temp_db).execute("PRAGMA table_info(matched_jobs)")]
    assert "rejection_reason" in cols
    assert "rejection_note" in cols


def test_update_rejection_sets_applied_and_reason(temp_db):
    job_id = _seed_job()
    tracker.update_matched_job_rejection(job_id, "wrong-tech", "Java stack only")

    assert tracker.get_applied_status(job_id) == 2
    r = tracker.get_rejection_row(job_id)
    assert r == ("wrong-tech", "Java stack only")


def test_update_rejection_note_defaults_to_empty(temp_db):
    job_id = _seed_job()
    tracker.update_matched_job_rejection(job_id, "wrong-location")
    assert tracker.get_rejection_row(job_id) == ("wrong-location", "")


def test_update_rejection_overwrites_previous(temp_db):
    job_id = _seed_job()
    tracker.update_matched_job_rejection(job_id, "wrong-tech", "first")
    tracker.update_matched_job_rejection(job_id, "wrong-location", "second")
    assert tracker.get_rejection_row(job_id) == ("wrong-location", "second")


def test_get_rejection_row_returns_none_for_missing_job(temp_db):
    assert tracker.get_rejection_row(999) is None


def test_get_rejection_row_returns_empties_for_unrejected(temp_db):
    job_id = _seed_job()
    assert tracker.get_rejection_row(job_id) == ("", "")


def test_get_rejection_reason_counts_aggregates(temp_db):
    id1 = _seed_job(url="https://x/1")
    id2 = _seed_job(url="https://x/2")
    id3 = _seed_job(url="https://x/3")
    tracker.update_matched_job_rejection(id1, "wrong-tech")
    tracker.update_matched_job_rejection(id2, "wrong-tech")
    tracker.update_matched_job_rejection(id3, "wrong-location")

    counts = dict(tracker.get_rejection_reason_counts())
    assert counts == {"wrong-tech": 2, "wrong-location": 1}


def test_get_rejection_reason_counts_excludes_unrejected(temp_db):
    id1 = _seed_job(url="https://x/1")
    _seed_job(url="https://x/2")  # never rejected
    tracker.update_matched_job_rejection(id1, "wrong-tech")

    counts = tracker.get_rejection_reason_counts()
    assert counts == [("wrong-tech", 1)]


def test_get_rejection_reason_counts_excludes_empty_reasons(temp_db):
    id1 = _seed_job(url="https://x/1")
    id2 = _seed_job(url="https://x/2")
    tracker.update_matched_job_rejection(id1, "")   # blank reason — excluded
    tracker.update_matched_job_rejection(id2, "wrong-tech")

    counts = tracker.get_rejection_reason_counts()
    assert counts == [("wrong-tech", 1)]


def test_soft_validation_stores_unknown_reason_verbatim(temp_db):
    """We store unknown reasons rather than reject them — the dropdown
    can drift and we don't want to lose data on version mismatches."""
    job_id = _seed_job()
    tracker.update_matched_job_rejection(job_id, "brand-new-reason-2027")
    assert tracker.get_rejection_row(job_id) == ("brand-new-reason-2027", "")
```

**Verify**: `venv/Scripts/python.exe -m pytest tests/test_tracker_rejection.py -v` → 11 passed / 0 failed.

### Step 3: Wire the reason popover into the dashboard

Edit `dashboard.py`:

**3a. Update imports** — add the new tracker functions to the existing
import block (around line 7-14):

```python
from nodes.tracker import (
    init_db, get_all_applications, get_matched_jobs,
    update_status, delete_application,
    update_matched_job_company, update_matched_job_applied,
    get_applied_status, get_applied_statuses, save_application,
    get_not_matched_jobs, get_scrape_dates,
    promote_not_matched_to_matched,
    update_matched_job_rejection, get_rejection_row,  # ← Plan 013
)
```

Remove the `from nodes.feedback_log import append_feedback` import at
line 6.

**3b. Replace the "Not Applying" button block** at `dashboard.py:610-618`
with a popover form. Note the actual structure of the surrounding code
(from `dashboard.py:586-618`):

```python
                    with col_right:
                        st.markdown("### Actions")

                        st.markdown("**Application Status**")
                        btn_col1, btn_col2 = st.columns(2)

                        with btn_col1:
                            if st.button(
                                "Applied",
                                key=f"applied_{job_id}",
                                type="primary" if apply_state != 1 else "secondary"
                            ):
                                update_matched_job_applied(job_id, 1)
                                save_application(
                                    company=company,
                                    job_title=job_title,
                                    platform=platform,
                                    cover_letter="",
                                    job_url=job_url if job_url else ""
                                )
                                st.cache_data.clear()
                                st.success("Marked as Applied!")
                                st.rerun()

                        with btn_col2:
                            # ── Plan 013: reason capture on Not Applying ──
                            with st.popover(
                                "Not Applying",
                                use_container_width=True,
                            ):
                                st.markdown("**Why skip this job?**")
                                reason = st.selectbox(
                                    "Reason",
                                    [
                                        "not-tech",
                                        "wrong-tech",
                                        "wrong-seniority",
                                        "wrong-location",
                                        "wrong-contract",
                                        "employer-mismatch",
                                        "already-applied-elsewhere",
                                        "link-broken",
                                        "other",
                                    ],
                                    key=f"rej_reason_{job_id}",
                                )
                                note = st.text_input(
                                    "Note (optional)",
                                    key=f"rej_note_{job_id}",
                                    placeholder="e.g. Angular-only shop, no Vue",
                                )
                                if st.button("Save reason", key=f"rej_save_{job_id}"):
                                    update_matched_job_rejection(job_id, reason, note)
                                    st.cache_data.clear()
                                    st.rerun()

                            # If already rejected, show the stored reason inline
                            if apply_state == 2:
                                existing = get_rejection_row(job_id) or ("", "")
                                if existing[0]:
                                    st.caption(f"↳ {_esc(existing[0])}"
                                               + (f" — {_esc(existing[1])}" if existing[1] else ""))
                                else:
                                    st.caption("↳ (legacy — no reason captured)")
```

**3c. Delete the "Log feedback" expander** (dashboard.py:620-637).
Also delete the `st.markdown("---")` at line 620 that separates it
from the actions block.

**3d. Verify the `append_feedback` import is unused** across the file
after your changes:

```bash
grep -n "append_feedback\|nodes.feedback_log" dashboard.py
```

Expected: no matches. If there are, remove them.

### Step 4: Manual smoke tests

```bash
venv/Scripts/streamlit run dashboard.py
```

Navigate to "🔍  Today's Matches". Pick any job.

1. **Click "Not Applying"** — a popover opens with a reason dropdown,
   optional note field, and Save button. The main page does NOT rerun
   yet.
2. **Pick "wrong-tech"**, type "Angular-only shop", click "Save reason".
   Page rerus, job now shows the caption "↳ wrong-tech — Angular-only
   shop" under the Not Applying button.
3. **DB check**:
   ```bash
   venv/Scripts/python.exe -c "
   from nodes.tracker import get_rejection_reason_counts
   print(get_rejection_reason_counts())
   "
   ```
   Expected: at least `[('wrong-tech', 1), ...]`.
4. **Reopen popover, change to "wrong-location"**, no note, Save.
   Caption updates to "↳ wrong-location" (no dash-note suffix).
5. **The "Log feedback for this job" expander is gone.**
6. **Applied button still works** — click on a different job, mark
   Applied; still saves to the applications table like before.
7. **No terminal exceptions.**

### Step 5: Update `plans/README.md`

Flip plan 013's status row to `DONE` with the commit SHA and pass counts.
In the "Direction findings considered" section, note that feedback-loop
foundation is landed and the calibration step is a future plan.

## Test plan

- **New unit tests** in `tests/test_tracker_rejection.py` — 11 cases
  covering schema migration idempotency, writer, reader, aggregation,
  overwrite, empty-state, unknown-reason-passthrough.
- **Manual smoke** — Step 4 recipe. Streamlit `st.popover` isn't easy to
  unit-test; the popover behavior is validated by hand.
- **Verification**: `venv/Scripts/python.exe -m pytest -q` → ≥ 106 + 11
  passed / 0 xfailed / 0 failed.

## Done criteria

ALL must hold:

- [ ] `matched_jobs.rejection_reason` and `matched_jobs.rejection_note`
      columns exist (verified via `PRAGMA table_info`).
- [ ] `nodes/tracker.py` has `update_matched_job_rejection`,
      `get_rejection_row`, `get_rejection_reason_counts` +
      `_REJECTION_REASONS` constant.
- [ ] `tests/test_tracker_rejection.py` exists with 11 passing tests.
- [ ] `dashboard.py` — "Not Applying" is a popover with reason dropdown
      + note field + Save button. Stored reason is shown as caption
      when `apply_state == 2`. "Log feedback" expander removed.
      `append_feedback` import removed. No stale references.
- [ ] `venv/Scripts/python.exe -m pytest -q` → ≥ 117 passed / 0 xfailed
      / 0 failed / exit 0.
- [ ] Manual smoke (Step 4) all 7 checks pass.
- [ ] `plans/README.md` row for plan 013 flipped to `DONE`.
- [ ] `git diff --stat` shows only `nodes/tracker.py`, `dashboard.py`,
      `tests/test_tracker_rejection.py`, `plans/README.md` modified.
- [ ] `nodes/feedback_log.py` and `data/feedback_log.txt` are
      UNCHANGED.

## STOP conditions

Stop and report if:

- The `matched_jobs` schema at `nodes/tracker.py:66-96` has drifted —
  new columns are already present (someone landed a similar plan) or
  the safe-migration block is gone. Do not force it.
- `dashboard.py:610-618` doesn't match the excerpt (the "Not Applying"
  handler has been changed by another plan).
- Streamlit's `st.popover` is not available on the installed
  Streamlit version. Verify with:
  ```bash
  venv/Scripts/python.exe -c "import streamlit as st; print(st.__version__); assert hasattr(st, 'popover'), 'popover missing'"
  ```
  If missing, STOP — don't fall back to an inline expander without
  operator sign-off. `st.popover` was added in Streamlit 1.32; if
  the operator's install is older, the right call is to
  upgrade (a `requirements.txt` bump) which merits explicit approval.
- You find yourself modifying `nodes/feedback_log.py` or
  `data/feedback_log.txt`. Out of scope.
- You find yourself adding logic to `_quick_reject` or the scoring
  prompt based on captured reasons. This is data collection only —
  calibration is a future plan.
- Any historical DB row loses data — the migration MUST be
  additive-only. If a `PRAGMA table_info` query shows a lost column,
  STOP and restore from backup.

## Maintenance notes

- **Reason vocabulary is deliberate.** Nine short kebab-case strings.
  Short so they aggregate cleanly; kebab-case so they're easily
  distinguishable from free-text notes; stable so a future
  scorer-calibration pass can `GROUP BY` them. Adding a tenth is fine;
  renaming is expensive (existing rows keep the old label). Prefer
  additive changes.
- **The dropdown allows verbatim storage of unknown values** (see
  `test_soft_validation_stores_unknown_reason_verbatim`). If a future
  plan tightens this to a hard whitelist, run this query first to see
  what's already in the wild:
  ```sql
  SELECT rejection_reason, COUNT(*) FROM matched_jobs
  WHERE applied = 2 AND rejection_reason != ''
  GROUP BY rejection_reason;
  ```
- **The old feedback log stays around.** Deleting
  `nodes/feedback_log.py` mid-flight would break any external tooling
  that imports it (there isn't any, but this is a low-cost
  self-imposed rule). A follow-up cleanup plan can remove the module
  and the historical text file together, once the operator has
  aggregated whatever they wanted from the two existing entries.
- **When enough data accumulates** (say, 50+ reasoned rejections),
  a future plan can:
  1. Compute per-reason overlap with `job_category` and title tokens.
  2. Propose new `_quick_reject` regex terms based on high-signal
     "wrong-tech" note patterns.
  3. Feed reason distribution back into the prompt (`SCORING_RULES` —
     "the candidate has explicitly declined N SAP roles for reason X;
     score SAP roles more conservatively").
  All of that is DATA-DEPENDENT. Do it later.
- **Reviewer focus:** verify the popover UX doesn't shift the layout of
  the actions column by more than a row-height when opened (the
  parent container is a `st.columns([2, 1])` at line 465-ish; a wide
  popover can push content awkwardly on smaller screens). If it
  feels off, `use_container_width=True` on the popover trigger keeps
  the button flush. Also verify the `↳ (legacy — no reason captured)`
  caption appears for jobs marked `applied = 2` before this plan
  (which is 411 of them right now).
