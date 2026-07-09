# Plan 018: Diagnose Stepstone with a headed browser, then rewrite selectors OR retire

**Planned at commit**: `1028a25` (main)
**Category**: Bug (scraper — selector rot or bot block)
**Effort**: S diagnosis + M rewrite (branch A), or S retirement (branch B)
**Risk**: LOW-MEDIUM (touches production scraper config; behavior verified against real browser before merge)
**Depends on**: 015 (findings report)

## Why this matters

Plan 015 (see `plans/015-findings.md`) identified Stepstone as the
highest-leverage broken platform: **last landing 2026-06-18**, zero
cards on every search since **2026-06-19**, ~500 `not_matched_jobs` per
run + ~100–130 `matched_jobs`/week returned if fixed. That's the
biggest single yield loss in the pipeline right now.

Plan 015 ruled out a Playwright/Chromium version bump as the cause
(Playwright 1.58.0 + chromium-1208 both installed 2026-03-18, untouched
since). Two suspects remain:

1. **Selector rot** — Stepstone rebuilt the search-results DOM on
   2026-06-19, and `card_selector` (which ends in a bare `article`
   fallback) no longer matches.
2. **Bot block** — Stepstone (probably behind Cloudflare / DataDome /
   Kasada) rolled new headless-Chrome detection on 2026-06-19 and now
   serves a challenge page instead of results.

**A 5-minute headed browser check decides between them.** Selector rot
is fixable with a config change; bot block requires either residential
proxies (out of scope for this project) or retirement of the platform.
This plan runs the diagnosis, then executes whichever branch the
evidence points to.

## Environment

- Windows 11, bash shell
- Python: `"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe"`
- Playwright 1.58.0 (already installed)
- You are running inside a git worktree at `.claude/worktrees/agent-<id>/`

**Data provisioning** — if the worktree lacks `data/`, copy the real DB
into place so any DB read still works (nothing in this plan writes to
it, but `nodes.tracker` opens it on import indirectly through
`nodes.pipeline`):

```bash
mkdir -p data
cp /c/Users/abam/Documents/job-agent/data/applications.db data/applications.db
```

## Drift check (run first)

```bash
git diff --stat 1028a25..HEAD -- nodes/scraper.py
```

If the file changed, re-read the excerpts below against the live file
before quoting them in commits. All line numbers below are from
`1028a25`.

## Current state

- `nodes/scraper.py:386-428` — `PLATFORM_CONFIGS['Stepstone']`
  - `build_url` (line 387-392): produces
    `https://www.stepstone.de/jobs/<term>/in-<region>?wp=<days>`
  - `cookie_selector` (line 393): `button[id='ccmgt_explicit_accept']`
  - `card_selector` (line 394):
    `article[data-at='job-item'], article[class*='job'], div[class*='JobCard'], article`
  - `selectors` dict (line 395-423): title, company, location, link,
    snippet — all a chain of `data-at=...` first, then class-based
    fallbacks, then bare tag
  - `link_base` (line 425): `https://www.stepstone.de`
  - `login_indicators` (line 426): `[]` — Stepstone has no known
    login-redirect URL fragment
  - `quick_apply_selector` (line 427):
    `[data-testid='quick-apply'], .quick-apply`
- `nodes/scraper.py:549-602` — `_build_job` reads the `selectors` dict
  and returns `(job|None, reason)`. Reads: `title`, `company`,
  `location`, `link` (mandatory), `snippet` (optional).
- `nodes/scraper.py:605-732` — `_scrape_platform` runs the browser,
  clicks cookie banner, queries `card_selector`, iterates cards.
  Bail-out at line 711 (3 consecutive broken-selector) or line 721
  (32 consecutive zero-card).

## Scope

**In scope**:

- Read `data/scrape_log.txt`, `plans/015-findings.md` for context
- Run a headed Playwright browser once, manually, to observe Stepstone's
  live search-results page (Step 1)
- Depending on Step 1's outcome, EITHER:
  - **Branch A (selector rot)**: modify `PLATFORM_CONFIGS['Stepstone']`
    in `nodes/scraper.py` — `card_selector` and possibly the inner
    `selectors` dict — and add a lightweight regression test
  - **Branch B (bot block)**: remove `"Stepstone"` from
    `PLATFORM_CONFIGS`; remove any Stepstone-specific test cases; add
    a note to `plans/README.md` "considered and rejected" section
- Verify with one live single-platform reproduction call (see Step 3)
- Update `plans/README.md` row 018 to DONE with which branch was taken

**Out of scope**:

- Fixing XING or Indeed in the same PR — they're separate leverage
  decisions; XING is plan 019 (write later if operator wants), Indeed
  is separate retirement
- Adding proxy support or stealth-plugin tricks — if Stepstone is
  bot-blocked, this project's answer is retirement, not an arms race
- Rewriting `_build_job`, `_scrape_platform`, or the bail-out logic
- Running the full pipeline (`python main.py`)
- Rotating LinkedIn cookies

## Git workflow

- Branch: `advisor/018-stepstone-fix`
- One commit for the config change (or retirement), plus one commit for
  README status flip if you prefer clean history — either is fine
- Do NOT push, do NOT open a PR

## Steps

### Step 0 — Baseline: confirm the failure still reproduces

Before the headed check, confirm Stepstone is still broken in headless
mode. This proves the diagnosis was still valid at the time of the fix
(sites recover on their own sometimes):

```bash
"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -c "
from nodes.scraper import _scrape_platform
jobs, stats = _scrape_platform('Stepstone', days_window=7, max_per_search=3)
print(f'jobs={len(jobs)}  stats_rows={len(stats)}')
# Print first 3 stats rows
for s in stats[:3]:
    print(f\"  {s['term'][:24]:<24} | {s['region'][:16]:<16} | cards={s['cards_found']} added={s['added']}\")
"
```

Expected:
- `jobs=0`
- `cards_found = 0` on all rows (that's the outage signature)
- Runtime ~30-60 seconds (bail-out fires after 32 zero-card searches)

If this returns `jobs > 0` or `cards_found > 0` on any row: **STOP** —
Stepstone recovered on its own. Note that in the commit message,
update `plans/README.md` row 018 to `REJECTED (Stepstone recovered
2026-XX-XX, no fix needed)`, and stop.

### Step 1 — Headed browser diagnosis (5 minutes, manual)

This is the decision-maker. You will open one real Stepstone search URL
in a visible browser and read what the page shows.

```bash
"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -c "
from playwright.sync_api import sync_playwright
# One representative URL — the same shape _scrape_platform generates
url = 'https://www.stepstone.de/jobs/Junior-Backend-Developer/in-Nordrhein-Westfalen?wp=7'
with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)   # HEADED
    ctx = browser.new_context()
    page = ctx.new_page()
    page.goto(url, timeout=30000)
    print(f'URL after navigation: {page.url}')
    print(f'Title: {page.title()}')
    input('Inspect the page in the visible browser. Press Enter to close...')
    browser.close()
"
```

**What you are looking for** — inspect visually AND note the final URL:

| Observation | Diagnosis | Branch |
|---|---|---|
| Cards visible, page URL unchanged, cookie banner appears | **SELECTOR_ROT** — proceed to Branch A | A |
| Cloudflare / DataDome challenge page, or CAPTCHA, or the URL redirected to something like `stepstone.de/challenge` or `stepstone.de/human-check` | **BOT_BLOCK** — proceed to Branch B | B |
| Page shows "0 jobs found" / "keine Jobs gefunden" but the layout is intact | **DEAD SEARCH TERM** (unlikely — the term is a well-known one; but if it happens, try `url = '.../Softwareentwickler/in-Nordrhein-Westfalen?wp=30'`) | retry Step 1 |
| Blank page or infinite loading spinner | **BOT_BLOCK** (JS not allowed to run) | B |

Record the observation (screenshot optional) in your commit message
under a `## Observation` line. **The observation is the load-bearing
evidence for the whole plan — do not skip or paraphrase it.**

If you can't tell which category applies (page loads partially, some
cards render but layout is broken), classify as SELECTOR_ROT and
proceed to Branch A — a selector rewrite is cheaper to try than a
retirement, and Branch A's Step 3 verification will catch a
false-positive.

### Step 2 — Branch A: Selector rewrite (only if Step 1 classified as SELECTOR_ROT)

Skip this whole step if Step 1 classified as BOT_BLOCK — jump to
"Branch B" below.

#### 2A.1 — Extract the new selectors from the live page

Open the browser DevTools on the same headed page from Step 1 (still
open). Find one job card in the DOM and record:

1. The **card element**: what tag + which attribute uniquely
   identifies a job card in the search-results list? Common patterns
   to look for, in order of preference:
   - `article[data-at='job-item']` (Stepstone's historical convention —
     may still work if only the wrapper changed)
   - `article[data-testid='job-item']`
   - `[data-genesis-element='JOB_CARD']`
   - `li[data-at='job-list-item']`
   - `div[data-testid='job-card']`
   - Record the **most specific selector that matches every card and
     nothing else**. Verify by running
     `document.querySelectorAll('<your-selector>').length` in DevTools
     Console — the count should equal the visible card count on the page.
2. For each **inner field** (title, company, location, link, snippet),
   find one selector that reliably extracts the text from *within a
   card*. Prefer `data-at=...` / `data-testid=...` selectors — they're
   the least likely to break next time. Verify each by:
   ```javascript
   Array.from(document.querySelectorAll('<card-selector>'))
     .slice(0, 3)
     .map(c => c.querySelector('<field-selector>')?.innerText)
   ```
   Should return non-empty strings for the first 3 cards.

#### 2A.2 — Update `PLATFORM_CONFIGS['Stepstone']`

Edit `nodes/scraper.py:386-428`:

- Replace `card_selector` with the new selector. **Keep the historical
  fallback chain** — new first, then old:
  ```python
  "card_selector": "<NEW_SELECTOR>, article[data-at='job-item'], article",
  ```
  The old selector as fallback costs nothing and protects against a
  future partial-revert on Stepstone's side.
- For each inner field in `selectors`, **prepend** the new selector to
  the existing chain. Do NOT delete existing entries — old selectors
  are cheap fallbacks. Example:
  ```python
  "title": [
      "<NEW_TITLE_SELECTOR>",
      "[data-at='job-item-title']",
      "h2[class*='title']",
      ...
  ],
  ```
- If `cookie_selector` on line 393 no longer matches (the button ID
  changed), update it too. Verify in DevTools:
  `document.querySelector("button[id='ccmgt_explicit_accept']")`. If
  `null`, find the current button — Stepstone typically has one
  cookie-banner button labeled "Alle akzeptieren" or "Accept all".

Do NOT touch:
- `build_url` — the URL structure is fine (the URL loaded correctly in
  Step 1)
- `link_base` — unchanged
- `login_indicators` — unchanged
- `quick_apply_selector` — orthogonal to this fix; only touch if you
  observe it broken in Step 1

#### 2A.3 — Add a regression test for the selector chain shape

**Do not attempt to test the actual DOM** — that requires network and
would be flaky. Test only that the config's chain includes the
observed-live selector as the first entry:

Add to `tests/test_scraper_platform_configs.py` (create the file if it
doesn't exist):

```python
"""Regression tests: PLATFORM_CONFIGS invariants that broke in the past."""
import pytest
from nodes.scraper import PLATFORM_CONFIGS


def test_stepstone_card_selector_leads_with_new_selector():
    """Plan 018: Stepstone rebuilt DOM 2026-06-19; the new selector must be first
    in the chain so it's preferred over the old fallback."""
    cs = PLATFORM_CONFIGS["Stepstone"]["card_selector"]
    # First comma-separated entry is the new selector observed on 2026-XX-XX.
    first = cs.split(",")[0].strip()
    assert first == "<NEW_SELECTOR>", (
        f"card_selector should lead with the new Stepstone selector, got: {first!r}"
    )


def test_stepstone_selectors_all_populated():
    """Guard against an accidental empty selector list."""
    sel = PLATFORM_CONFIGS["Stepstone"]["selectors"]
    for field in ("title", "company", "location", "link"):
        assert sel.get(field), f"Stepstone selectors[{field!r}] is empty"
        assert len(sel[field]) >= 2, (
            f"Stepstone selectors[{field!r}] should have at least new + old fallback"
        )
```

Replace `<NEW_SELECTOR>` with the exact string you put into the config
in step 2A.2.

Run the tests:

```bash
"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -m pytest tests/test_scraper_platform_configs.py -v
```

Expected: 2 passed.

Run the full test suite:

```bash
"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -m pytest tests/ -q
```

Expected: `169 passed` (was 167, +2 new). If anything else fails, STOP
and report — nothing you did should touch other tests.

### Step 3 — Branch A verification: single-platform live rerun

Rerun the same reproduction command from Step 0:

```bash
"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -c "
from nodes.scraper import _scrape_platform
jobs, stats = _scrape_platform('Stepstone', days_window=7, max_per_search=3)
print(f'jobs={len(jobs)}  stats_rows={len(stats)}')
# Print first 5 stats rows
for s in stats[:5]:
    print(f\"  {s['term'][:24]:<24} | {s['region'][:16]:<16} | cards={s['cards_found']} added={s['added']}\")
"
```

Expected AFTER the fix:
- `jobs > 0`
- `cards_found > 0` on at least the first few rows (some rows may be 0
  for niche terms; that's fine)

If `jobs = 0` and every `cards_found = 0`: the selector rewrite did
NOT work. STOP. Do NOT commit. Report back with:
- What selector you used in the config
- What DevTools said the selector matched on the live page
- The stats output above

If `jobs > 0` and `cards_found > 0`: skip to Step 5 (commit).

### Step 4 — Branch B: Retire Stepstone (only if Step 1 classified as BOT_BLOCK)

Skip this whole step if Step 1 classified as SELECTOR_ROT.

Rationale: this project does not support proxies. Stepstone's
challenge page cannot be dismissed by a headless Chromium alone.
Keeping the entry in `PLATFORM_CONFIGS` means every scrape run
spends ~30-60 seconds hitting a dead site before the 32-zero-card
bail-out fires. That's wasted time and clutters the health dashboard.

#### 4B.1 — Delete Stepstone from `PLATFORM_CONFIGS`

Edit `nodes/scraper.py:386-428`. Delete the entire `"Stepstone": { ... }`
entry, including its trailing comma. `nodes/scraper.py:895`
(`platforms = list(PLATFORM_CONFIGS.keys())`) picks up the change
automatically — no other reference to search for.

Grep to confirm no stragglers:

```bash
grep -rn "Stepstone\|stepstone" nodes/ tests/ 2>&1
```

Expected: only matches in `nodes/scraper.py` comments (if any),
`data/scrape_log.txt` (historical log — leave alone),
`data/applications.db` rows (historical — leave alone). If any
`.py` file still references `Stepstone` as active platform config,
follow up and remove.

#### 4B.2 — Add a "considered and rejected" note to `plans/README.md`

Add one bullet in the `## Findings considered and rejected` section:

```markdown
- **Stepstone retirement** (2026-XX-XX, plan 018): headed
  browser inspection on <date> confirmed Stepstone now serves a
  <Cloudflare | DataDome | CAPTCHA | login> challenge page instead of
  results. Fix requires residential proxies (out of scope for this
  project). Removed from `PLATFORM_CONFIGS`. If Stepstone drops the
  challenge in the future, revert this plan's commit to restore.
```

Fill in the actual date and the actual challenge vendor observed.

#### 4B.3 — Test suite

```bash
"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -m pytest tests/ -q
```

Expected: still `167 passed` (no new tests added, no existing tests
broken).

If any test references `Stepstone` and fails after the delete, remove
the reference — retirement means removal, not preservation of dead
tests.

### Step 5 — Commit and update `plans/README.md`

Update `plans/README.md` row 018 (add it if not present):

**Branch A:**
```markdown
| 018  | Diagnose Stepstone with headed browser + selector rewrite         | P2 | S+M | LOW | 015 | DONE — headed check 2026-XX-XX classified SELECTOR_ROT; `card_selector` updated to `<NEW>`; inner `selectors[title/company/location/link/snippet]` prepended with new `data-at=...` selectors; 2 regression tests added; single-platform rerun returned N jobs from M cards; suite 169p/0xf/0f. |
```

**Branch B:**
```markdown
| 018  | Diagnose Stepstone with headed browser + retire                   | P2 | S   | LOW | 015 | DONE (retired) — headed check 2026-XX-XX classified BOT_BLOCK (<vendor> challenge page). `"Stepstone"` removed from `PLATFORM_CONFIGS`. Considered-rejected note added. Suite 167p/0xf/0f. |
```

Commit message for the config/code commit:

- Branch A: `fix(scraper): rewrite Stepstone selectors after 2026-06-19 DOM redesign`
- Branch B: `fix(scraper): retire Stepstone platform (bot-blocked since 2026-06-19)`

Second commit for the README flip:
`docs(plans): mark plan 018 DONE in plans/README.md`

## Test plan

**Branch A:**
- New: `tests/test_scraper_platform_configs.py` with 2 tests
- Full suite: 169 passed
- Manual live verification: single-platform rerun in Step 3

**Branch B:**
- No new tests; full suite: 167 passed (unchanged)
- No manual live verification needed — the point of retirement is
  we're not calling the platform anymore

## Done criteria (machine-checkable)

- [ ] Full test suite green (169 pass for Branch A, 167 for Branch B)
- [ ] `plans/README.md` row 018 = DONE with which branch, date, and
      observation
- [ ] Branch A only: single-platform rerun in Step 3 returned `jobs > 0`
      and `cards_found > 0` on at least the first row
- [ ] Branch B only: `grep -rn Stepstone nodes/ tests/` shows no active
      config reference
- [ ] Working tree clean, on branch `advisor/018-stepstone-fix`, one
      or two commits

## STOP conditions

Stop and report back (do not improvise) if:

- Step 0 returns `jobs > 0` — Stepstone recovered on its own; nothing
  to fix. Mark plan REJECTED in README.
- Step 1's headed browser check is ambiguous AND Step 2A.1's DevTools
  card-count check returns 0 — the DOM shape you inferred doesn't hold
  up. Don't guess; report back with what you saw.
- Step 3's post-fix rerun returns 0 jobs — the selector rewrite didn't
  work. Do NOT commit. Report back.
- Test suite regresses on anything OUTSIDE the plan's scope. That
  means the plan touched something it shouldn't have.
- Step 1 shows a partial DOM (some cards render but no data extractable)
  AND Step 2A.1 can't find data-attributes that match. That's a
  half-broken redesign; retire (Branch B) rather than paper over it.

## Files in scope

- `nodes/scraper.py` (Branch A: modify PLATFORM_CONFIGS['Stepstone']; Branch B: delete PLATFORM_CONFIGS['Stepstone'])
- `tests/test_scraper_platform_configs.py` (Branch A only: create)
- `plans/README.md` (either branch: add + update row 018)

## Files out of scope

- `nodes/scraper.py` — anything outside PLATFORM_CONFIGS['Stepstone']
- `nodes/scraper.py` — XING, Indeed, LinkedIn config (separate plans)
- `nodes/pipeline.py`, `nodes/tracker.py`, `nodes/analyzer.py`
- `data/applications.db`, `data/scrape_log.txt` (read only)
- `plans/015-findings.md` (already finalized)
- Any other test file

## Maintenance notes

- **Selector rot is recurring.** Stepstone, XING, LinkedIn, Indeed all
  redesign every 6-18 months. When they do, the diagnostic recipe in
  this plan (headed browser → DevTools → selector rewrite) is the
  standing template. Copy the steps for the next platform.
- **The `data-at=...` and `data-testid=...` attribute conventions**
  are the *most stable* selectors in modern job-board DOMs — they're
  used by the sites' own analytics + testing. Prefer them over class
  names, which are auto-generated by CSS-in-JS frameworks and change
  every deploy.
- **Retiring a platform is a valid outcome.** This project's economics
  don't support arms-racing anti-bot vendors. If a site goes dark and
  the fix requires residential proxies or stealth plugins, retire it
  and move on. The pipeline's design (multiple platforms in parallel)
  is meant to tolerate one going away.
- **After Stepstone lands**, plan 019 (XING same treatment) becomes
  the obvious next spike. If Step 1 here classified BOT_BLOCK, XING is
  almost certainly the same and should probably be retired together.
- **The Playwright/Chromium version pin** noted in plan 015 —
  Playwright 1.58.0 + chromium-1208 installed 2026-03-18 — is worth
  keeping. Upgrading Playwright without a scraper-side test would be a
  silent break. Consider adding a `pip freeze` snapshot check to
  `requirements.txt` if you touch that file again.
- **Reviewer focus for Branch A**: the new selector must lead the
  chain, and the old selectors must be preserved as fallbacks.
  Deletion of the old fallbacks is the mistake that will make the
  next redesign a P0 outage instead of a P2 fix.
