# Plan 015: Diagnose Indeed / Stepstone / XING silent scraper failures

> **Executor instructions**: This is a **spike / investigation plan**, not
> a code-change plan. Your deliverable is a report saved to
> `plans/015-findings.md` — no source-file edits, no test changes. Follow
> the steps in order; stop early if the report is already conclusive.
>
> **Drift check (run first)**: `git diff --stat 5bed640..HEAD -- nodes/scraper.py`
> If the file changed since this plan was written, compare the "Current
> state" excerpts against live code before proceeding.

## Status

- **Priority**: P3
- **Effort**: S (time-boxed to 90 minutes of investigation)
- **Risk**: LOW (no code changes)
- **Depends on**: none
- **Category**: bug (correctness / silent failure)
- **Planned at**: commit `5bed640`, 2026-07-02

## Why this matters

The 2026-06-23 and 2026-06-29 scrape summaries in `data/scrape_log.txt`
show **Indeed, Stepstone, and XING each added zero jobs** on both runs,
across every search term × region combination. LinkedIn (334 added) and
Arbeitsagentur (137 added) masked the failure — the total scrape count
looked healthy, matches landed in the dashboard, and no error was
raised. In `matched_jobs`, the historical platform breakdown shows XING
313, Stepstone 88 — so these platforms *used to work*. Something
between the last-good run and 2026-06-23 broke them.

Three failure modes fit the pattern:

1. **Bot block / login wall**: `_scrape_platform` has a bail-out at 32
   consecutive zero-card searches — Indeed/Stepstone may be hitting it
   silently (only a `[warn] ... platform likely blocked` line, no error).
2. **Selector rot**: DOM changes on the target sites, so cards are
   present but `card_selector` matches nothing. `_selector_broken`
   bail-out at 3 consecutive broken-selector searches would trip, but
   again only prints a warn, doesn't fail loudly.
3. **CAPTCHAs / IP throttling** — same UX as bot block; only fix is
   proxy or re-tuned user-agent rotation.

The `run_daily.py` scheduler is currently disabled — so the operator
runs the pipeline manually and eyeballs the summary table each time. In
that summary a platform showing `added=0` blends in with a platform
showing `added=5`, and the failure isn't obvious.

This spike answers three questions so the operator can decide what to
fix in a follow-up plan:

1. Which of the three platforms is actually broken? All? Just one?
2. Is it bot-block (bail-out fired) or selector-rot (no cards ever
   extracted despite cards being visible)?
3. What is the minimum change to restore the platform — new selector,
   cookie warm-up, per-platform proxy, or retirement?

Do not try to fix anything in this plan. Fixes may be non-trivial
(selector rewriting, IP rotation), and the operator should decide plan
priority once the diagnosis is in hand.

## Current state

Relevant files:

- `nodes/scraper.py:605-732` — `_scrape_platform` (the generic Playwright
  runner used by Indeed, Stepstone, XING, LinkedIn, Glassdoor).
- `nodes/scraper.py:711-724` — bail-out logic:
  - line 711–714: 3 consecutive broken-selector searches → skip platform.
  - line 721–724: 32 consecutive zero-card searches → skip platform.
- `nodes/scraper.py:527-535` — `_selector_broken` heuristic
  (`cards_found > 0 and added == 0 and parse_errors == 0`).
- `nodes/scraper.py:735-790` — `_print_summary` writes to stdout AND to
  `data/scrape_log.txt` via a rotating file handler.
- `PLATFORM_CONFIGS` dict (not read in this plan; the executor will
  grep for it in Step 1) — contains `card_selector` per platform.
- `data/scrape_log.txt` — rolling log of scrape summaries. Contains
  the smoking gun for this investigation.

## Commands you will need

| Purpose | Command |
|---------|---------|
| Activate venv | `source venv/Scripts/activate` |
| Tail scrape log | `tail -200 data/scrape_log.txt` |
| Grep the summary table | `grep -E "Indeed|Stepstone|XING\|" data/scrape_log.txt \| head -40` |
| Grep the bail-out warnings | `grep -E "platform likely blocked\|broken-selector\|skipping platform" data/scrape_log.txt` |
| Find PLATFORM_CONFIGS | `grep -n "PLATFORM_CONFIGS\|card_selector\|login_indicators" nodes/scraper.py` |
| Query DB for last successful landing | see Step 2 SQL |

## Scope

**In scope**:

- Read `data/scrape_log.txt`
- Read `data/applications.db` via `sqlite3` CLI or Python
- Read `nodes/scraper.py` (do NOT modify)
- Optionally: run a single-platform scrape by hand to reproduce (see
  Step 4) — but only if the log tail is inconclusive
- Write the findings report to `plans/015-findings.md`

**Out of scope**:

- Any edit to `nodes/scraper.py`, `nodes/*.py`, `config/*`, or tests.
- Running the full pipeline. If reproduction is needed, use the
  single-platform recipe in Step 4 — do not `python main.py`.
- Trying to fix a broken selector or bot-block "while you're at it".
- Rotating LinkedIn cookies (they're working — not the target).

## Git workflow

- Branch: `advisor/015-scraper-diagnosis`
- One commit — the findings report file only.
  Message: `Plan 015: diagnose Indeed/Stepstone/XING silent failures`
- Do NOT push or open a PR.

## Steps

### Step 1: Confirm the failure signature from the log

Read `data/scrape_log.txt` (the rotating log — most recent summary is at
the bottom). Look for the summary table blocks. For each of the last
3 runs, note:

- `Indeed`, `Stepstone`, `XING`: `Cards` and `Added` columns.
- Whether any `[warn] <platform>: 32 consecutive zero-card searches`
  or `[warn] <platform>: 3 consecutive broken-selector searches`
  lines appear.

Classification cheat-sheet:

| Signal | Diagnosis |
|---|---|
| `Cards > 0`, `Added = 0`, and a "broken-selector" warn | **Selector rot** — DOM changed |
| `Cards = 0`, `Added = 0`, and a "platform likely blocked" warn | **Bot block / login wall** |
| `Cards = 0`, `Added = 0`, no warns, ran to completion | **Silent zero** — usually bot block that didn't hit the 32-search threshold, or empty DOM (CAPTCHA / login redirect) |
| `Cards > 0`, `Added = 0`, no broken-selector warn | Cards exist but every one is filtered out — either `exp_filter` / `deprioritized` accounts for it (look at those columns) or selectors half-broke (some fields extract, some don't → `no_data`) |

**Record** in `plans/015-findings.md` under a `## Log evidence` heading:
per-platform per-run table with Cards / Added / Exp / Depr counts + which
bail-out warn (if any) appears in the log.

### Step 2: Confirm from the DB when each platform last worked

Run this Python snippet (adjust the sqlite3 path if it fails — it's
`data/applications.db`):

```bash
venv/Scripts/python.exe -c "
import sqlite3
conn = sqlite3.connect('data/applications.db')
for src in ['matched_jobs', 'not_matched_jobs']:
    print(f'\\n--- {src} ---')
    for row in conn.execute(f'SELECT platform, MAX(date_found), COUNT(*) FROM {src} GROUP BY platform ORDER BY 2 DESC'):
        print(row)
"
```

**Record** in `plans/015-findings.md` under `## DB evidence`: the last
`date_found` per platform for both tables. If Indeed/Stepstone/XING's
last row is before 2026-06-23, that's the outage date — pinpoint it.

### Step 3: Diagnose the failure mode without touching production

For each broken platform, read the `PLATFORM_CONFIGS` entry in
`nodes/scraper.py` (grep for the platform name) and note:

- `card_selector` — the CSS selector for job cards. Suspect for
  selector-rot.
- `login_indicators` — URL fragments that trigger the "requires login"
  early-return at scraper.py:654-657.
- `cookie_selector` — the cookie-consent button. If this changed on
  the target site, all subsequent page interactions fail silently
  because of the swallowed `except Exception: pass`.

Cross-reference against the log signal from Step 1:

- If Step 1 said "selector rot", the culprit is `card_selector` or one
  of the inner field selectors used by `_build_job`.
- If Step 1 said "bot block", the culprit is upstream — the site
  serves a login/CAPTCHA page before cards render.

**Record** in `plans/015-findings.md` under `## Suspected cause per
platform` — one paragraph each for Indeed / Stepstone / XING with the
signal, the config field to investigate, and a confidence level
(HIGH / MEDIUM / LOW).

### Step 4: (Optional, only if Step 1 was inconclusive) — reproduce one platform manually

Only do this if Step 1's log tail didn't give a clean signal. It's the
slowest step; skip if possible.

```bash
venv/Scripts/python.exe -c "
from nodes.scraper import _scrape_platform
# Pick ONE platform per invocation. Do not run all three.
jobs, stats = _scrape_platform('Indeed', days_window=7, max_per_search=5)
print(f'jobs={len(jobs)}  stats_rows={len(stats)}')
for s in stats[:5]:
    print(s)
"
```

- `days_window=7` widens the window vs the daily default so the run
  finishes in <2 minutes even with the smaller `max_per_search=5`.
- If this returns `jobs=0` and every stats row has `cards_found=0`, the
  platform is bot-blocked or wall-gated at page-load — check with a
  headed browser (see optional non-code step below).
- If it returns `jobs=0` but `cards_found>0` per stats row, it's
  selector rot in `_build_job`.

Optional non-code step: open one of the URLs that `_scrape_platform`
would visit (build one by hand from `PLATFORM_CONFIGS[platform]
["build_url"]("Junior Backend Developer", "Nordrhein-Westfalen", 5, 7)`
in a Python REPL) and inspect the page in a real browser. If it shows a
login/CAPTCHA, that's bot-block. If it shows cards, inspect the DOM to
compare against `card_selector`. **Do not** save cookies or log in.

**Record** in `plans/015-findings.md` under `## Reproduction` — either
"skipped, log signal was decisive" or the observed jobs/stats plus a
manual-browser observation.

### Step 5: Write recommendations, not fixes

At the bottom of `plans/015-findings.md`, add a `## Recommended
follow-up` section with 1–3 bullets. Examples of the right shape:

- **Retire XING** — API access is gated behind partner status; the
  Playwright approach has bot-blocked, and Arbeitsagentur+LinkedIn
  already cover its role. Write a plan to delete XING config +
  scraper wiring.
- **Stepstone selector rewrite** — cards render but `.res-cnt-list`
  no longer matches; DOM is now `[data-testid="job-item"]`. Write
  a plan to update `PLATFORM_CONFIGS['Stepstone']`.
- **Indeed bot block** — every request hits a CAPTCHA within 3 tries;
  no viable fix without residential proxy. Recommend removing.

Each recommendation should end with a coarse effort estimate (S/M/L)
and a leverage judgment (how many jobs per week would return).

### Step 6: Update `plans/README.md`

Change plan 015's status to `DONE (investigation — see
plans/015-findings.md)`.

## Test plan

None — this is a spike. Do not add tests. Do not run `pytest`.

## Done criteria

ALL must hold:

- [ ] `plans/015-findings.md` exists and has sections:
      `## Log evidence`, `## DB evidence`, `## Suspected cause per
      platform`, `## Recommended follow-up`.
- [ ] `git diff --stat` shows only `plans/015-findings.md` (new file) and
      `plans/README.md` (status row) modified. **No source files
      touched.**
- [ ] `plans/README.md` row for plan 015 flipped to `DONE`.

## STOP conditions

Stop and report back (do not improvise) if:

- You find yourself editing any file under `nodes/`, `config/`, or
  `tests/` — this plan is diagnosis-only.
- `data/scrape_log.txt` is missing or empty. Note that in the report
  and stop — nothing else in this plan works without the log.
- The DB query in Step 2 returns platform counts that contradict the
  premise — e.g. Stepstone with `date_found >= 2026-06-30` and
  `count > 10`. In that case, note the discrepancy and stop; the
  problem may have already resolved itself.
- Time-box: if you've spent more than 90 minutes and are still not
  confident in the classification, write down what you have with a
  `confidence: LOW` note and stop. The operator can dispatch a deeper
  investigation later if needed.

## Maintenance notes

- **Silent scrape failures are a systemic risk** — the pipeline was
  designed to be resilient (bail-outs, per-platform crash isolation)
  which is exactly why failures don't shout. Plan 012 (scrape-source
  health tab in dashboard) is the standing fix for detection; this
  plan is the one-shot diagnostic for the current outage.
- **This spike may get repeated.** The same failure signature will
  probably reappear every 6–12 months as target sites redesign. Keep
  this plan on file as a template — the executor can copy the steps
  wholesale for the next round of "platform X quietly died".
- **Reviewer focus:** confirm no source files were edited. The whole
  value of a spike is preserving the option to do something different
  once the operator sees the findings; a "quick fix" in the same PR
  destroys that option.
