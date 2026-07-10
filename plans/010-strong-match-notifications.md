# Plan 010: Notify on strong matches at end of `run_daily.py`

> **Executor instructions**: Follow this plan step by step. Run every
> verification command. If a STOP condition fires, stop and report — do
> not improvise. Update the status row for this plan in `plans/README.md`
> when done.
>
> **Drift check (run first)**: `git diff --stat b02e7e8..HEAD -- run_daily.py nodes/pipeline.py nodes/tracker.py`
> If any of these changed since this plan was written, compare the
> "Current state" excerpts against live code before proceeding.
>
> **Re-affirmation note (2026-07-10, `b02e7e8`)**: this plan was
> originally written at `5bed640` on 2026-07-02. Re-affirmed at
> `b02e7e8` after plan 019 retired Indeed. `run_daily.py:25` still
> mentions "Indeed" in its log string — that's stale but OUT OF SCOPE
> for this plan (drop it in a separate one-line cleanup, or leave it
> for a future plan). Do NOT touch it here.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: direction (feature)
- **Planned at**: commit `5bed640`, 2026-07-02 (re-affirmed at `b02e7e8`, 2026-07-10)

## Why this matters

`run_daily.py` runs the pipeline unattended (when re-enabled — the
scheduled task is currently disabled). At the end it writes one line to
`data/scheduler_log.txt`: `"N strong matches found and saved"`. The
operator has to remember to open the dashboard to see if any of those N
are actually worth applying to — nothing surfaces the high-signal
matches at the moment they happen.

In `data/applications.db` today, matches with `match_score >= 85` are
rare and precious — only 4 out of 777 matched rows across the whole
history. When one appears, the operator should know within the hour, not
whenever they next open the dashboard. Missing a strong match on a
first-30-days posting is directly costly.

A single Windows toast (native, no service dependency) at the end of
`run_daily.py` is sufficient. Do NOT build an email/Slack/webhook
pipeline in this plan — that's overkill for a single-operator local
tool. If the user wants push-to-phone later, that's a separate plan.

Keep the notification silent when there are no strong matches — no
"nothing today" toast — so the operator only sees signal.

## Current state

Relevant files:

- `run_daily.py` — 41 lines, entirety shown below.
- `nodes/pipeline.py` — `run_pipeline(min_score: int = 70)` returns
  `list[dict]` of matched jobs (each dict has `title`, `company`,
  `score`, `platform`, `url`, `recommendation`, etc. — see
  `save_matched_jobs` in `nodes/tracker.py:185-244` for the full shape).
- `nodes/tracker.py:66-96` — `matched_jobs` schema; the `applied` column
  exists at index 15 (0 = unreviewed).
- `requirements.txt` — currently has `plyer` NOT listed. `winotify` NOT
  listed. Any new dep must be added.

Current code:

```python
# run_daily.py:18-36
def main():
    log("Daily job agent started")
    try:
        from dotenv import load_dotenv
        from nodes.pipeline import run_pipeline
        load_dotenv()

        log("Running pipeline: scrape (Indeed/Stepstone/XING/LinkedIn/Glassdoor) → validate → score → save...")
        scored = run_pipeline(min_score=50)

        if scored:
            log(f"{len(scored)} strong matches found and saved.")
            log("Open dashboard: streamlit run dashboard.py")
        else:
            log("No strong matches today.")

    except Exception as e:
        log(f"Fatal error: {e}")
        sys.exit(1)
```

Repo conventions: this project runs on Windows 11 (per operator's
environment). Notifications should use a Windows-native API path. The
project has no test runner for `run_daily.py` beyond import smoke.
Notifications are inherently side-effect-y and hard to unit-test — do
NOT write a test that actually raises a toast. Test the *decision
logic* (which jobs cross the threshold) as a pure function; skip the
actual toast call in tests via monkeypatch.

## Commands you will need

| Purpose | Command | Expected |
|---------|---------|---|
| Activate venv | `source venv/Scripts/activate` | prompt `(venv)` |
| Install winotify | `pip install winotify==1.1.0` | installs cleanly |
| Full test suite | `venv/Scripts/python.exe -m pytest -q` | 169 passed → 178 passed after this plan |
| Manual smoke — no matches | see Step 4 | no toast, no crash |
| Manual smoke — with mock matches | see Step 4 | one toast appears |

## Scope

**In scope**:

- `run_daily.py` — add a `_notify_strong_matches(jobs, threshold=85)`
  helper and call it after `run_pipeline` returns
- `requirements.txt` — add `winotify` dependency
- `tests/test_run_daily_notify.py` (NEW) — pure-function tests for the
  filter/format logic, with the actual toast call monkeypatched to a
  no-op

**Out of scope** (do NOT touch):

- `main.py` — the interactive entrypoint. The operator is already
  looking at the terminal; toasts would be noise. Leave it alone.
- `nodes/pipeline.py` — the pipeline itself must not know about
  notifications. Notification is a *presentation* concern.
- Adding email, SMTP, Slack, ntfy, Pushover, or any external transport.
  Windows-native toast only. If the operator asks for phone push
  later, that's a separate plan.
- `dashboard.py` — completely unrelated.
- Threshold tuning — 85 is the chosen default. If the operator wants
  to change it, that's a config change, not a scope of this plan.

## Git workflow

- Branch: `advisor/010-strong-match-notifications`
- Two commits recommended: (1) code change + requirements bump, (2)
  tests. One combined commit is also fine.
- Commit message style: `Plan 010: notify on strong matches at end of run_daily`
- Do NOT push or open a PR unless instructed.

## Steps

### Step 1: Add `winotify` to requirements.txt

Append `winotify==1.1.0` to `requirements.txt`, alphabetized if the file
is sorted, otherwise at the bottom. Then:

```bash
pip install winotify==1.1.0
```

**Verify**: `venv/Scripts/python.exe -c "from winotify import Notification; print('ok')"` prints `ok`.

If the install fails (Windows APIs missing on non-Windows environments),
STOP — this plan assumes Windows. Report the failure and ask the
operator whether to switch to a cross-platform library.

### Step 2: Add the notification helper to `run_daily.py`

Insert the following function above `def main()`. Preserve import style
— top-of-file `import` for pure-Python modules, function-local import
for winotify (matches the existing style: `dotenv` and `run_pipeline`
are function-local, delaying their load until pipeline execution).

```python
STRONG_MATCH_THRESHOLD = 85


def _select_strong_matches(jobs: list, threshold: int = STRONG_MATCH_THRESHOLD) -> list:
    """Return jobs with match_score >= threshold, sorted by score desc, capped at 5.

    Pure function — safe to unit-test.
    """
    strong = [j for j in (jobs or []) if int(j.get("score", 0)) >= threshold]
    strong.sort(key=lambda j: int(j.get("score", 0)), reverse=True)
    return strong[:5]


def _format_notification_body(jobs: list) -> str:
    """One line per job: score, title, company. Toast bodies wrap at ~5 lines."""
    return "\n".join(
        f"[{j.get('score', 0)}] {j.get('title', '?')} @ {j.get('company', '?')}"
        for j in jobs
    )


def _notify_strong_matches(jobs: list) -> int:
    """Raise one Windows toast if any strong matches exist. Returns count notified."""
    strong = _select_strong_matches(jobs)
    if not strong:
        return 0
    try:
        from winotify import Notification, audio
        n = Notification(
            app_id="Job Agent",
            title=f"{len(strong)} strong match{'es' if len(strong) > 1 else ''} today",
            msg=_format_notification_body(strong),
        )
        n.set_audio(audio.Default, loop=False)
        n.show()
    except Exception as e:
        log(f"[notify] toast failed: {e}")
    return len(strong)
```

Then edit the `if scored:` branch of `main()` to call the helper:

```python
        if scored:
            log(f"{len(scored)} strong matches found and saved.")
            log("Open dashboard: streamlit run dashboard.py")
            n_notified = _notify_strong_matches(scored)
            if n_notified:
                log(f"[notify] raised toast for {n_notified} match(es) with score >= {STRONG_MATCH_THRESHOLD}")
        else:
            log("No strong matches today.")
```

Do NOT change the `min_score=50` argument to `run_pipeline` — that's
the pipeline threshold, unrelated to the notify threshold. They are
independent by design.

**Verify**:
```bash
venv/Scripts/python.exe -c "
from run_daily import _select_strong_matches, _format_notification_body
picks = _select_strong_matches([
    {'title':'a','company':'c1','score':90},
    {'title':'b','company':'c2','score':70},
    {'title':'c','company':'c3','score':85},
])
print(len(picks), [p['title'] for p in picks])
print(_format_notification_body(picks))
"
```

Expected: `2 ['a', 'c']` then the two `[score] title @ company` lines.

### Step 3: Add tests

Create `tests/test_run_daily_notify.py`:

```python
import pytest

from run_daily import (
    _select_strong_matches,
    _format_notification_body,
    _notify_strong_matches,
    STRONG_MATCH_THRESHOLD,
)


def test_select_strong_matches_filters_below_threshold():
    picks = _select_strong_matches([
        {"title": "a", "company": "c1", "score": 90},
        {"title": "b", "company": "c2", "score": 70},
        {"title": "c", "company": "c3", "score": 85},
    ])
    assert [p["title"] for p in picks] == ["a", "c"]


def test_select_strong_matches_sorts_desc_and_caps_at_five():
    jobs = [{"title": f"j{i}", "company": "c", "score": 85 + i} for i in range(10)]
    picks = _select_strong_matches(jobs)
    assert len(picks) == 5
    scores = [p["score"] for p in picks]
    assert scores == sorted(scores, reverse=True)


def test_select_strong_matches_empty_input_returns_empty():
    assert _select_strong_matches([]) == []
    assert _select_strong_matches(None) == []


def test_select_strong_matches_respects_custom_threshold():
    jobs = [{"title": "a", "score": 60}, {"title": "b", "score": 80}]
    picks = _select_strong_matches(jobs, threshold=50)
    assert [p["title"] for p in picks] == ["b", "a"]


def test_select_strong_matches_missing_score_treats_as_zero():
    picks = _select_strong_matches([{"title": "a", "company": "c"}])
    assert picks == []


def test_format_body_contains_score_title_company():
    body = _format_notification_body([
        {"title": "Backend Dev", "company": "Acme", "score": 88},
    ])
    assert "88" in body
    assert "Backend Dev" in body
    assert "Acme" in body


def test_notify_returns_zero_when_no_strong_matches(monkeypatch):
    # Ensure winotify is never imported when no strong matches — proves early return
    monkeypatch.setitem(__import__("sys").modules, "winotify", None)
    n = _notify_strong_matches([{"title": "a", "score": 60}])
    assert n == 0


def test_notify_returns_count_when_toast_call_stubbed(monkeypatch):
    """Stub the winotify.Notification so we can assert count without raising a real toast."""
    class _StubNotification:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
        def set_audio(self, *args, **kwargs):
            pass
        def show(self):
            pass

    class _StubAudio:
        Default = "default"

    stub_module = type("m", (), {"Notification": _StubNotification, "audio": _StubAudio})
    monkeypatch.setitem(__import__("sys").modules, "winotify", stub_module)

    n = _notify_strong_matches([
        {"title": "a", "company": "c", "score": 90},
        {"title": "b", "company": "c", "score": 88},
    ])
    assert n == 2


def test_strong_match_threshold_default_is_85():
    assert STRONG_MATCH_THRESHOLD == 85
```

**Verify**: `venv/Scripts/python.exe -m pytest tests/test_run_daily_notify.py -v` → 9 passed / 0 failed.

### Step 4: Manual smoke tests

**Smoke 1 — no matches, no toast:**

```bash
venv/Scripts/python.exe -c "
from run_daily import _notify_strong_matches
print(_notify_strong_matches([{'title':'a','score':60}]))
"
```

Expected: prints `0`, no toast pops up.

**Smoke 2 — one strong match, one toast:**

```bash
venv/Scripts/python.exe -c "
from run_daily import _notify_strong_matches
print(_notify_strong_matches([
    {'title':'Junior Python Developer','company':'Acme GmbH','score':90},
]))
"
```

Expected: prints `1`, a Windows toast appears in the bottom-right of
the screen with `"1 strong match today"` as the title and
`"[90] Junior Python Developer @ Acme GmbH"` as the body.

If no toast appears on Windows 11: the Focus Assist / Do Not Disturb
setting may be suppressing it. Check the Notification Center
(`Win+N`) — if the toast is queued there, the feature works; the OS
just muted the popup. Not a bug.

### Step 5: Update `plans/README.md`

Flip plan 010's status row to `DONE` with a one-line post-exec note
(commit SHA, test counts).

## Test plan

- **New tests** in `tests/test_run_daily_notify.py` — 9 cases covering
  `_select_strong_matches`, `_format_notification_body`,
  `_notify_strong_matches` early-return and stubbed-success paths, and
  the exported constant.
- **Pure-function tests only.** The `winotify` module is monkeypatched
  in the one test that exercises the toast call path.
- **Verification**: `venv/Scripts/python.exe -m pytest -q` → total 169
  passed + 9 new = 178 passed, 0 xfailed, 0 failed.
- **Manual smoke**: both Step 4 recipes.

## Done criteria

ALL must hold:

- [ ] `winotify==1.1.0` appended to `requirements.txt` and installed.
- [ ] `run_daily.py` has `_select_strong_matches`,
      `_format_notification_body`, `_notify_strong_matches`,
      `STRONG_MATCH_THRESHOLD`, and the `main()` call site updated.
- [ ] `tests/test_run_daily_notify.py` exists with 9 passing tests.
- [ ] `venv/Scripts/python.exe -m pytest -q` → 178 passed / 0 failed
      / 0 xfailed / exit 0.
- [ ] Smoke test 2 (Step 4) raises exactly one visible toast on the
      operator's Windows 11 machine.
- [ ] `plans/README.md` row for plan 010 flipped to `DONE`.
- [ ] `git diff --stat` shows only `run_daily.py`, `requirements.txt`,
      `tests/test_run_daily_notify.py`, `plans/README.md` modified.

## STOP conditions

Stop and report back if:

- `pip install winotify==1.1.0` fails (non-Windows environment, or
  Python 3.14 incompatibility). This plan assumes Windows; do not
  substitute `plyer` or `win10toast-persist` without asking.
- `run_daily.py` has drifted — the `if scored:` branch at lines 28–32
  doesn't match the excerpt above.
- The manual smoke test 2 raises a Python exception (not a
  "no visible toast" — that's a Focus Assist quirk, not a bug — but an
  actual exception traceback). Investigate; do not `except Exception:
  pass` your way past it.
- You find yourself adding SMTP / Slack / webhook code. Notifications
  are Windows-toast-only in this plan; anything else is scope creep.

## Maintenance notes

- **Threshold is a knob.** 85 was chosen because the historical DB has
  only 4 matches at that level — most days will notify zero, which is
  correct. If the operator finds `run_daily` starts raising toasts too
  often (say, after Plan 011's category taxonomy raises the average
  score), drop `STRONG_MATCH_THRESHOLD` to 90. If they never see a
  toast in a month, lower to 80.
- **Toast content is deliberately terse.** Each strong match is one
  line: `[score] title @ company`. Do not include the URL — the toast
  isn't clickable in this simple integration and adding the URL just
  makes the body scroll off-screen.
- **When the scheduled task is re-enabled** (`schtasks /Change
  /TN "\JobAgent" /ENABLE`), the toast will appear as the invoking
  Windows user. If run_daily.py is ever moved to a service account,
  toasts silently disappear — services can't raise interactive
  notifications on Windows. Note that in the maintenance
  documentation, don't try to work around it here.
- **Reviewer focus:** verify no imports of `winotify` at module top
  level of `run_daily.py` — the function-local import matters for
  test isolation (monkeypatching sys.modules before the import fires).
