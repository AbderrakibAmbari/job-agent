# Plan 015 — Findings: Silent scraper failures on Indeed / Stepstone / XING

- **Investigated at**: main HEAD `1f845b3`, `nodes/scraper.py` unchanged
  since planning commit `5bed640` (`git diff --stat 5bed640..HEAD --
  nodes/scraper.py` returned empty).
- **Sources**: `data/scrape_log.txt` (full file, 26 summary blocks
  2026-05-06 → 2026-06-29), `data/applications.db` (read-only).
- **Step 4 (manual single-platform reproduction)**: **skipped**, log
  signal was decisive. Justification is in the "Reproduction" section.
- **Time spent**: ~35 minutes. Confidence ratings below.

## Log evidence

Last 3 runs — per-platform per-run summary. Columns from the log table
plus a "Bail-out warn?" column inferred from `_scrape_platform`
mechanics (see "Warn lines are stdout-only" note below the table).

### Run 2026-06-21 12:29:56

| Platform       | Terms | Cards | Added | Exp | Depr | Bail-out warn (stdout) |
|----------------|------:|------:|------:|----:|-----:|------------------------|
| Arbeitsagentur | 39    | 364   | 141   | 0   | 53   | —                      |
| Glassdoor      | 3     | 30    | 18    | 0   | 7    | —                      |
| **Indeed**     | 2     | 0     | 0     | 0   | 0    | **32-zero-card**       |
| LinkedIn       | 8     | 145   | 118   | 0   | 24   | —                      |
| **Stepstone**  | 2     | 0     | 0     | 0   | 0    | **32-zero-card**       |
| **XING**       | 2     | 0     | 0     | 0   | 0    | **32-zero-card**       |

### Run 2026-06-23 10:53:56

| Platform       | Terms | Cards | Added | Exp | Depr | Bail-out warn (stdout) |
|----------------|------:|------:|------:|----:|-----:|------------------------|
| Arbeitsagentur | 39    | 367   | 145   | 0   | 53   | —                      |
| Glassdoor      | 3     | 30    | 17    | 0   | 8    | —                      |
| **Indeed**     | 2     | 0     | 0     | 0   | 0    | **32-zero-card**       |
| LinkedIn       | 8     | 149   | 107   | 0   | 38   | —                      |
| **Stepstone**  | 2     | 0     | 0     | 0   | 0    | **32-zero-card**       |
| **XING**       | 2     | 0     | 0     | 0   | 0    | **32-zero-card**       |

### Run 2026-06-29 17:31:38

| Platform       | Terms | Cards | Added | Exp | Depr | Bail-out warn (stdout) |
|----------------|------:|------:|------:|----:|-----:|------------------------|
| Arbeitsagentur | 39    | 352   | 137   | 0   | 55   | —                      |
| Glassdoor      | 3     | 30    | 20    | 0   | 5    | —                      |
| **Indeed**     | 2     | 0     | 0     | 0   | 0    | **32-zero-card**       |
| LinkedIn       | 9     | 568   | 334   | 0   | 41   | —                      |
| **Stepstone**  | 2     | 0     | 0     | 0   | 0    | **32-zero-card**       |
| **XING**       | 2     | 0     | 0     | 0   | 0    | **32-zero-card**       |

### Key patterns from the full log

- **Indeed has produced 0 cards / 0 added on *every* run in the log,
  going back to the earliest entry 2026-05-06**. This is not a recent
  regression — Indeed has been silently dead the entire history the
  rotating log retains.
- **Stepstone and XING dropped to 0 on the same run: 2026-06-19 11:06**.
  The 2026-06-18 run had Stepstone Cards=1963 / Added=318 and XING
  Cards=1142 / Added=886. One day later, both platforms return 0 cards
  on every one of the 32 search × region combinations. Simultaneous
  drop across two independent platforms on the same day is the
  smoking gun — see "Suspected cause" below for why the same-day
  correlation is diagnostic.
- **All three broken platforms show `Terms = 2` on every recent run.**
  That's the bail-out signature: the 32-zero-card threshold at
  `scraper.py:721-724` fires after exactly `2 terms × 16 Bundesländer
  = 32` searches, then breaks the outer `for term in terms` loop.
- **Warn lines are stdout-only.** `_print_summary` at
  `scraper.py:735-790` writes to the rotating file handler; the
  `[warn] ... platform likely blocked` and `[warn] ... broken-selector`
  messages at `scraper.py:712` and `:722` go to `print()` only. So
  `grep 'warn|blocked|broken-selector'` on `data/scrape_log.txt`
  returns nothing — I confirmed. This is why the operator can't see
  the outage from the summary alone.

## DB evidence

`SELECT platform, MAX(date_found), COUNT(*) FROM <table> GROUP BY
platform ORDER BY 2 DESC`:

### `matched_jobs`

| Platform       | Last `date_found` | Total rows |
|----------------|-------------------|-----------:|
| LinkedIn       | 2026-06-29        | 345        |
| Arbeitsagentur | 2026-06-29        | 17         |
| **XING**       | **2026-06-15**    | 313        |
| **Stepstone**  | **2026-06-15**    | 88         |
| Glassdoor      | 2026-06-09        | 14         |
| **Indeed**     | **(no rows)**     | **0**      |

### `not_matched_jobs`

| Platform       | Last `date_found` | Total rows |
|----------------|-------------------|-----------:|
| LinkedIn       | 2026-06-29        | 1259       |
| Arbeitsagentur | 2026-06-29        | 183        |
| **XING**       | **2026-06-18**    | 729        |
| **Stepstone**  | **2026-06-18**    | 705        |
| Glassdoor      | 2026-06-18        | 45         |
| **Indeed**     | **(no rows)**     | **0**      |

### Outage-onset dates

- **Indeed**: never landed a job — outage predates the earliest log
  entry (2026-05-06). The `matched_jobs`/`not_matched_jobs` row counts
  are 0/0. This is a long-standing dead platform, not a fresh regression.
- **Stepstone**: last landing `2026-06-18`; first zero-card day
  `2026-06-19`. Outage onset: **2026-06-19**.
- **XING**: last landing `2026-06-18`; first zero-card day
  `2026-06-19`. Outage onset: **2026-06-19** — **same day as
  Stepstone**.

## Suspected cause per platform

### Indeed — BOT_BLOCK (confidence: HIGH)

The log shows 0 cards on every run for 8+ weeks straight, including
runs with a different search-term slate (SEARCH_TERMS was expanded
between 2026-06-06 and 2026-06-15, and Indeed still produced zero).
The DB has never held a single Indeed row. `login_indicators` is empty
so the early-return at `scraper.py:654-657` never fires — that path
requires the URL to change to a known login-page fragment. Indeed's
anti-bot response is to serve a challenge page that *keeps* the
original URL and just replaces the DOM with a CAPTCHA — so
`card_selector = "div.job_seen_beacon"` matches nothing but the
"login_indicator" bail-out never trips. The pattern is textbook silent
bot block. Config field to investigate: **none** — the fix isn't a
selector change; Indeed's Playwright-friendliness has degraded and
would need residential proxy + more elaborate stealth (or retirement).

### Stepstone — SELECTOR_ROT (confidence: MEDIUM-HIGH)

The abrupt same-day drop on 2026-06-19 across all 32 term × region
combinations is inconsistent with a bot block that ramps up as the
scraper hammers the site — a real IP-based block would let the first
few searches through and only block later. Zero on the *first*
search of a fresh browser context is the fingerprint of a DOM
redesign. `card_selector` for Stepstone
(`article[data-at='job-item'], article[class*='job'], div[class*='JobCard'], article`)
is a chain that ends in the bare tag `article` — that fallback used
to guarantee *some* card would match. If it now returns zero, the
page structure changed so there is no `<article>` in the search-
results section at all (Stepstone rebuilt to a `<div role="listitem">`
or `<li>` layout). Config field to investigate: **`PLATFORM_CONFIGS['Stepstone']['card_selector']`**, plus the inner
`selectors` dict (`title`, `company`, `location`, `link`, `snippet`)
since they'd all be data-at-attribute-based and would break together.

### XING — SELECTOR_ROT or BOT_BLOCK (confidence: MEDIUM)

XING dropped on the exact same day as Stepstone (2026-06-19). Two
independent platforms failing on the same calendar day would be a
massive coincidence for two separate DOM redesigns — so the more
likely story is that the failure share a common *upstream* cause on
the operator's side (browser fingerprint / user-agent / IP suddenly
being on a shared blocklist for anti-bot services both platforms use)
rather than coincidental selector rot. But XING's `card_selector`
(`[data-testid='job-posting-item'], article`) has the same
"fallback to `article`" structure as Stepstone, so if XING did
redesign its cards, the failure mode would look identical. Config
field to investigate: **`PLATFORM_CONFIGS['XING']['card_selector']`**
first (cheaper to check), then if that's still valid, treat as bot
block. `cookie_selector` is `None` so a cookie-modal regression
can't be the cause here.

### Cross-cutting hypothesis (worth mentioning)

The same-day Stepstone+XING drop, combined with Arbeitsagentur also
crashing from 343 cards to 15 on the same 2026-06-19 run (Arbeitsagentur
recovered on the next run), suggests something in the *runtime
environment* changed on 2026-06-19 — user-agent update, Playwright
version bump, or a Windows/Chromium security update that broke
headless-Chromium's TLS handshake with these specific sites. Worth
checking `pip show playwright` version and the last Chromium download
timestamp before rewriting selectors.

## Reproduction

**Skipped** — Step 4 was optional and the plan explicitly says "skip
if possible" when the log signal is clean. It is:

- All three platforms exhibit the same signature: `Terms=2`, `Cards=0`,
  `Added=0`, no `exp_filter` / `deprioritized` / `no_data` count. That
  matches the 32-zero-card bail-out at `scraper.py:721` firing after
  exactly `2 terms × 16 regions` — nothing else in `_scrape_platform`
  can produce that exact shape.
- The `_selector_broken` heuristic (`cards_found > 0 and added == 0`)
  never triggers because `cards_found` is 0, so the 3-consecutive
  broken-selector bail-out at `scraper.py:711` is not what fired here.
  The signal is unambiguous: **cards never rendered at all** —
  either the CSS `card_selector` never matched (selector rot) or the
  page load itself returned a challenge / empty DOM (bot block).
- Running the single-platform reproduction would only tell us which
  of those two it is. That distinction matters for the *fix* but not
  for the finding. The follow-up plan for whichever platform the
  operator decides to invest in should start with a headed
  reproduction as its Step 1 — that's the right place to spend the
  10 minutes on a live browser inspection, not here.

## Recommended follow-up

Ranked by leverage (jobs / week that would return, per operator's
usage pattern of ~1 pipeline run every 3-6 days):

1. **Retire Indeed from `PLATFORM_CONFIGS`** — S effort. Indeed has
   never contributed a single job in the entire retained log history
   (8+ weeks), never landed a DB row, and is silently bot-blocked
   without a viable fix short of residential proxies. Every scrape run
   currently spends ~30-90 seconds hitting Indeed to produce zero
   results. **Leverage: 0 jobs/week gained but ~1 minute/run saved
   and one dead platform stops masking the real breakages.** Follow-up
   plan should remove the `"Indeed"` key from `PLATFORM_CONFIGS` and
   delete the tests (if any) that reference it.

2. **Diagnose Stepstone with a headed 5-minute browser inspection,
   then either rewrite `card_selector` or retire** — M effort for
   rewrite, S for retire. Stepstone was the second-highest scraper
   yield before the outage (~500 added/run, ~130 matched jobs/week
   at typical scoring rates). If the DOM redesign is confirmed and
   the new selector is a single-attribute change, this is the highest-
   leverage single fix in the whole codebase right now. **Leverage:
   ~100-130 matched jobs/week returned if fixed; 0 if retired.** The
   headed inspection is the go/no-go: if the site shows a CAPTCHA
   instead of cards, retire; if it shows cards under a new selector,
   fix.

3. **Same for XING** — M effort for rewrite, S for retire. XING was
   the highest volume scraper (~1100 added/run pre-outage, ~110
   matched jobs/week). Do it after Stepstone: if the Stepstone
   inspection reveals a bot-block-shaped page, XING is almost
   certainly the same and both should retire together. If Stepstone
   was pure selector rot, XING probably is too — but check
   independently before touching config. **Leverage: ~80-110 matched
   jobs/week returned if fixed; 0 if retired.**

Optional (worth capturing but not urgent): **investigate whether
Playwright / Chromium was updated around 2026-06-19** — same-day
failure across two unrelated platforms is a strong smell for a
runtime-side cause, and the fix might be a single dependency pin
rather than three selector rewrites. Check `pip show playwright` and
`playwright install --dry-run chromium` output before starting on the
selector work.
