# Plan 019 — Retire the Indeed platform

**Planned at commit**: `95673fd` (main)
**Category**: Cleanup (dead code / dead platform)
**Effort**: S
**Risk**: LOW (deletion only; a single dead entry in `PLATFORM_CONFIGS`)
**Depends on**: 015 (findings — Indeed diagnosis)

## Why this matters

Plan 015's diagnostic report (`plans/015-findings.md`) established that
Indeed has produced **0 cards and 0 added rows on every scrape run in
the retained log history (2026-05-06 onward)** and has never landed a
single row in `matched_jobs` or `not_matched_jobs`. Indeed's anti-bot
posture serves a challenge page while keeping the URL unchanged, so
the `login_indicators` early-return at `nodes/scraper.py:654-657`
never fires. The `card_selector` (`div.job_seen_beacon`) never
matches. Result: every pipeline run burns ~30–90 seconds hitting a
dead site, the health dashboard displays a persistent "zero-added"
row for Indeed that masks other outages, and the `PLATFORM_CONFIGS`
entry pretends to be an active platform.

Fixing Indeed's bot-block problem is not viable within this project's
architecture — the resolution requires either residential proxies or
a substantial stealth-plugin investment. This plan retires it.

## Concurrent recon finding — XING is healthy

A Phase 1 recon on XING (2026-07-09) confirmed XING is currently
scraping cleanly:
`_scrape_platform('XING', days_window=7, max_per_search=1)` returned
`cards_found=21` and `added=1` per row across all Bundesländer.
The 2026-06-19 → 2026-06-29 outage in plan 015's findings has
self-resolved between 2026-07-02 and 2026-07-09. The hypothesis that
XING shared Stepstone's union-chain bug was **not reproducible** in
live traffic. Plan 019 does NOT touch XING.

This plan adds a note to the "considered and rejected" section of
`plans/README.md` recording the XING recovery so a future audit
doesn't re-open the same investigation.

## Environment

- Windows 11, bash shell
- Python: `"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe"`
- You are in a git worktree at `.claude/worktrees/agent-<id>/`

## Drift check (run first)

```bash
git diff --stat 95673fd..HEAD -- nodes/scraper.py
```

Expect empty. If the file changed, re-read the excerpts below against
the live file before editing.

## Current state

- `nodes/scraper.py:339` — `PLATFORM_CONFIGS = {`
- `nodes/scraper.py:341-385` — `"Indeed": { ... }` entry, ending with
  a closing `},` on line 385. (Verify exact line boundaries in your
  worktree before editing.)
- `nodes/scraper.py:895` — `platforms = list(PLATFORM_CONFIGS.keys())`
  picks up the removal automatically; no other reference to
  `"Indeed"` in `nodes/*.py` should be affected.

Quick sanity grep to locate the entry and any strays:

```bash
grep -n "\"Indeed\"\|'Indeed'\|indeed" nodes/scraper.py
```

## Scope

**In scope**:

- Delete the `"Indeed": { ... },` block from `PLATFORM_CONFIGS` in
  `nodes/scraper.py`
- Add a "considered and rejected" bullet to `plans/README.md` for
  the XING self-recovery finding (a companion to the Indeed
  retirement, so the two decisions are recorded together)
- Update `plans/README.md` row 019 to `DONE (retired)` with an
  observation line

**Out of scope**:

- Any change to XING, Stepstone, LinkedIn, Glassdoor, or
  Arbeitsagentur configs
- Any change to `_scrape_platform`, `_build_job`, or the bail-out
  logic
- Deletion of historical Indeed rows from `data/applications.db`
  (there are zero — nothing to delete)
- Test file for the deletion — a "make sure Indeed is not in
  PLATFORM_CONFIGS" test would be over-engineering; the empty
  historical record is the load-bearing signal, and reintroducing
  Indeed by mistake would be an obvious code-review catch

## Git workflow

- Branch: `advisor/019-retire-indeed`
- One commit for the code change; one for the README flip (or one
  combined — either is fine)
- Do NOT push, do NOT open a PR

## Steps

### Step 1 — Verify Indeed is still dead

Before deletion, one last check that Indeed hasn't spontaneously
recovered (unlikely but the same self-recovery pattern hit XING, so
it's cheap to verify):

```bash
"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -c "
from nodes.scraper import _scrape_platform
jobs, stats = _scrape_platform('Indeed', days_window=7, max_per_search=1)
print(f'JOBS={len(jobs)}  STATS_ROWS={len(stats)}')
for s in stats[:5]:
    print(f\"  {s['term'][:24]:<24} | {s['region'][:16]:<16} | cards={s['cards_found']} added={s['added']}\")
"
```

Timebox: 90 seconds. If it runs longer, kill it — bail-out should
fire after 32 zero-card searches (~30–60 seconds).

Expected: `JOBS=0` and `cards_found = 0` on every row.

If `JOBS > 0`: **STOP** — Indeed recovered. Do not delete. Mark plan
019 as REJECTED in README with the recovery observation. Save the
output.

If bail-out fires with `JOBS=0`: proceed.

Save the output for the final report.

### Step 2 — Delete the Indeed entry

Locate the Indeed block in `nodes/scraper.py`. It starts around
line 341 with `"Indeed": {` and ends with the matching closing brace
plus trailing comma. Delete the entire block including its trailing
comma. The `"Stepstone":` entry (line 386 at plan-write time) should
be the next key in the dict after deletion.

Verify with:

```bash
grep -n "PLATFORM_CONFIGS\|\"Indeed\"\|\"Stepstone\"" nodes/scraper.py | head -10
```

`"Indeed"` should have zero matches inside `nodes/scraper.py`. If any
remain in comments or docstrings and they document the platform as
active, remove them.

### Step 3 — Grep for stragglers across the codebase

```bash
grep -rn "\"Indeed\"\|'Indeed'" nodes/ tests/ 2>&1
```

Expected matches (leave these alone):
- None expected in `nodes/` after Step 2
- None expected in `tests/`

If any `.py` file still references `"Indeed"` as an active platform
config (not as documentation/history), remove that reference — no
Indeed-specific code paths remain.

Historical references in `data/scrape_log.txt` and
`data/applications.db` (there are none for the DB) are unchanged —
those are historical record.

### Step 4 — Run the test suite

```bash
"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -m pytest tests/ -q
```

Expected: `169 passed`.

The test count should NOT change — no tests reference Indeed
specifically. If any test fails, STOP and report — nothing in this
plan should touch tests.

### Step 5 — Update `plans/README.md`

Two edits:

**Edit A** — flip row 019 to DONE. The row is currently absent; add
it after row 018:

```markdown
| 019  | Retire Indeed platform (bot-blocked, 0 jobs contributed ever)      | P3       | S      | LOW  | 015     | DONE (retired) — `PLATFORM_CONFIGS["Indeed"]` deleted; 0 rows ever contributed to `matched_jobs`/`not_matched_jobs` across full retained log history; ~30–60s/run saved and health-dashboard "zero-added Indeed" false alarm silenced. Suite 169p/0xf/0f. |
```

**Edit B** — add a bullet to the "Findings considered and rejected"
section for the XING self-recovery finding:

```markdown
- **XING same-day-outage hypothesis** (2026-07-09, Phase 1 recon
  for a would-be plan 019 on XING): tested hypothesis that XING
  shared Stepstone's union-chain facet-pollution bug (same-day
  2026-06-19 outage in plan 015). Live headless recon returned
  `cards_found=21` and `added=1` per row across all Bundesländer —
  XING self-recovered between plan 015's investigation on 2026-07-02
  and this recon. No fix needed. XING's `card_selector` chain
  (`[data-testid='job-posting-item'], article`) has the same shape
  Stepstone's did, so if XING breaks again, apply plan 018's
  one-line pattern (drop the `, article` fallback).
```

The XING company-field-Unknown observation the recon surfaced is
NOT covered here — that's a separate small plan candidate for a
future session.

### Step 6 — Commit

Two commits (clean history) OR one combined commit. Either shape is
fine; the executor may choose.

Two-commit shape:

```bash
git add nodes/scraper.py
git commit -m "$(cat <<'EOF'
fix(scraper): retire Indeed platform (bot-blocked since first log entry)

Plan 015's findings established that Indeed produced 0 cards / 0 added on
every scrape run in the retained log history (2026-05-06 onward) and never
landed a single row in matched_jobs or not_matched_jobs. Indeed's anti-bot
posture serves a challenge page while keeping the URL unchanged, so the
login_indicators early-return in _scrape_platform never fires and the
card_selector never matches. Every run wasted ~30-60 seconds hitting a
dead site.

Fixing Indeed's bot-block problem requires residential proxies or a
substantial stealth-plugin investment, both out of scope for this project.
This commit retires the platform.
EOF
)"

git add plans/README.md
git commit -m "docs(plans): mark plan 019 DONE (Indeed retired) + record XING self-recovery"
```

Do NOT push. Do NOT open a PR. Do NOT amend.

## Test plan

- Full suite: 169 passed (unchanged — no tests reference Indeed)
- Manual live verification: Step 1 confirms Indeed is still dead
  before deletion (Step 6 obviously doesn't re-verify)

## Done criteria (machine-checkable)

- [ ] `grep -n "\"Indeed\"\|'Indeed'" nodes/scraper.py` returns zero
      matches
- [ ] `git diff main..HEAD -- nodes/scraper.py` shows only the Indeed
      block deleted, nothing else
- [ ] Full test suite: 169 passed
- [ ] `plans/README.md` row 019 = DONE with observation
- [ ] `plans/README.md` "considered and rejected" section has the
      XING self-recovery bullet
- [ ] Working tree clean on branch `advisor/019-retire-indeed`

## STOP conditions

Stop and report back if:

- Step 1 returns `JOBS > 0` — Indeed recovered; mark REJECTED in
  README, don't delete
- Step 4 test suite regresses — nothing in this plan should touch
  tests
- Any file outside `nodes/scraper.py` and `plans/README.md` shows up
  in `git status` after the edits
- The Indeed block boundary is unclear (e.g., you can't find its
  closing brace) — report the ambiguity rather than guess

## Files in scope

- `nodes/scraper.py` (delete PLATFORM_CONFIGS["Indeed"] block only)
- `plans/README.md` (add row 019 + XING rejection bullet)

## Files out of scope

- Everything else. Not a single other file should show up in the
  diff.

## Maintenance notes

- **Reintroducing Indeed** is a decision to reverse. If a future
  proxy/stealth setup makes it viable, git-revert this commit and
  re-verify with the Step 1 recipe.
- **The Stepstone / XING pattern** — same-day outage on 2026-06-19
  had two different explanations (Stepstone: real union-chain bug;
  XING: transient site-side issue that self-resolved). This is
  worth remembering: same-day drops across platforms don't always
  share a single root cause. Diagnose independently.
- **Reviewer focus**: confirm the diff is exactly the Indeed block
  deletion — nothing surrounding it should change. Verify the
  `PLATFORM_CONFIGS` dict remains syntactically valid (Python parses
  the file — a missing/extra comma will surface immediately).
