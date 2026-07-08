# Plan 012: Scrape-source health tab in the dashboard

> **Executor instructions**: Follow this plan step by step. Run every
> verification command. Stop on any STOP condition. Update the status
> row in `plans/README.md` when done.
>
> **Drift check (run first)**: `git diff --stat 5bed640..HEAD -- dashboard.py nodes/scraper.py`
> If either file changed since this plan was written, compare the
> "Current state" excerpts against live code before proceeding.

## Status

- **Priority**: P2
- **Effort**: S-M
- **Risk**: LOW (parse-and-display only; no scraper changes)
- **Depends on**: none
- **Category**: direction (feature — observability)
- **Planned at**: commit `5bed640`, 2026-07-02

## Why this matters

`data/scrape_log.txt` already contains rich per-platform yield data from
every run — this is what plan 015 mines by hand today. But it's a plain
text log the operator opens in Notepad and squints at. In two of the last
five runs (2026-06-23, 2026-06-29), **Indeed / Stepstone / XING added
zero jobs each** and it took a manual audit to notice. This is the exact
failure `run_daily.py` was designed to survive gracefully — and gracefully
means "silently".

A dedicated dashboard page that parses the scrape log and surfaces:

- **Per-platform yield over the last N runs** — a color-coded table
  showing Added counts, so zeros stand out.
- **Broken-platform warnings** — highlight platforms with three or more
  consecutive zero-Added runs.
- **Top terms** — currently shown as one comma-separated line at the
  bottom of each summary; surface the aggregate across the window so
  the operator can drop dead terms.

...turns a manual investigation into a five-second glance. That is what
observability is for.

This plan does NOT change the scraper, does NOT change the log format,
and does NOT introduce a new database table. It just parses what
`_print_summary` already writes.

## Current state

Relevant files:

- `nodes/scraper.py:735-790` — `_print_summary()` writes each run
  summary to `data/scrape_log.txt` via a rotating file handler
  (`maxBytes=2_000_000, backupCount=5`). The format is a fixed
  box-drawing table (already stable across many runs).
- `data/scrape_log.txt` — plain text, growing top-to-bottom. Each
  summary block starts with `╔══...══╗` and a `║  Scrape Summary — <ts>`
  line. Ends with `╚══...══╝` and an optional `  Top terms by jobs
  added: ...` trailing line.
- `dashboard.py:325-332` — the sidebar navigation `st.radio` with 3
  current pages. This is where the new page name gets added.
- `dashboard.py:369, 454, 644` — the three `if page == ... elif page ==
  ...` blocks. The new page's block goes after "Not Matched".

Sample of the log format (verified 2026-07-02 from
`data/scrape_log.txt`):

```
╔══════════════════════════════════════════════════════════════════════╗
║  Scrape Summary — 2026-06-29 17:31:38                              ║
╠════════════════╦════════╦══════════╦════════╦═══════════╦═════════════╣
║ Platform       ║  Terms ║    Cards ║  Added ║     Exp ❌ ║      Depr ❌ ║
╠════════════════╬════════╬══════════╬════════╬═══════════╬═════════════╣
║ Arbeitsagentur ║     39 ║      352 ║    137 ║         0 ║          55 ║
║ Glassdoor      ║      3 ║       30 ║     20 ║         0 ║           5 ║
║ Indeed         ║      2 ║        0 ║      0 ║         0 ║           0 ║
║ LinkedIn       ║      9 ║      568 ║    334 ║         0 ║          41 ║
║ Stepstone      ║      2 ║        0 ║      0 ║         0 ║           0 ║
║ XING           ║      2 ║        0 ║      0 ║         0 ║           0 ║
╠════════════════╬════════╬══════════╬════════╬═══════════╬═════════════╣
║ TOTAL          ║     39 ║      950 ║    491 ║         0 ║         101 ║
╚══════════════════════════════════════════════════════════════════════╝
  Top terms by jobs added: Graduate Software Engineer (253), Trainee IT (63), Vollzeit Softwareentwickler (35)
```

Constants in the format that a parser can rely on:

- Every summary begins with `╔`, ends with `╚`.
- The timestamp line is `║  Scrape Summary — YYYY-MM-DD HH:MM:SS`.
- Data rows start with `║ ` and have exactly 5 numeric columns after
  the platform name.
- Platform names include `TOTAL` — skip that.
- Top-terms trailing line matches `^  Top terms by jobs added: (.*)$`
  and each term matches `<name> (<count>)`.

The log rotates at 2 MB with 5 backups (`data/scrape_log.txt.1` …
`data/scrape_log.txt.5`) — the parser must read the base file plus the
most recent one or two backups if it wants > N runs of history, but for
"last 20 runs" a single base file is more than enough (~150 KB for that
many summaries).

Repo conventions:
- Cached loaders use `@st.cache_data(ttl=300)` with explicit
  `st.cache_data.clear()` before rerun after writes. For a read-only
  page (this one), the TTL alone is fine; no writes to invalidate.
- Emoji-heavy page names in the sidebar radio (`📊`, `🔍`, `❌`).
- Use `_esc(...)` for anything interpolated into HTML blocks with
  `unsafe_allow_html=True` (Plan 004 pattern).

## Commands you will need

| Purpose | Command |
|---------|---------|
| Activate venv | `source venv/Scripts/activate` |
| Run tests | `venv/Scripts/python.exe -m pytest tests/ -v` |
| Full suite | `venv/Scripts/python.exe -m pytest -q` |
| Launch dashboard for smoke | `venv/Scripts/streamlit run dashboard.py` |
| Sanity-check parser | see Step 1 verify block |

## Scope

**In scope**:

- `nodes/scrape_log_parser.py` (NEW) — pure module that parses
  `data/scrape_log.txt` into a list-of-dicts. Includes:
  - `parse_scrape_log(path=...) -> list[dict]`
  - `platform_history(runs, platform, limit=20) -> list[dict]`
  - `broken_platforms(runs, streak=3) -> list[str]`
  - `top_terms_aggregated(runs, limit=10) -> list[tuple[str, int]]`
- `dashboard.py`:
  - Add `"📈  Scrape Health"` to the sidebar radio.
  - Add a fourth `elif page == "📈  Scrape Health":` block at the end.
  - Add a cached loader that calls the parser.
- `tests/test_scrape_log_parser.py` (NEW) — fixture with two hand-
  crafted summary blocks and assertions over the parser output.

**Out of scope** (do NOT touch):

- `nodes/scraper.py` — the `_print_summary` output format stays as-is.
  Do not change columns, box characters, or spacing. The parser adapts
  to the format, not vice versa.
- Rotation limits (`maxBytes=2_000_000, backupCount=5` at
  `nodes/scraper.py:50`) — leave them.
- `run_daily.py` — do NOT add "if broken platform, raise notification"
  logic here. That's a natural follow-up, but scope-creepy: this plan
  just surfaces the data.
- Historical rotated log files (`.1`, `.2`, …). Reading only
  `data/scrape_log.txt` is sufficient; ~20 runs fit comfortably below
  the 2 MB rotation threshold.
- DB queries (matched_jobs, not_matched_jobs) — the source of truth
  is the text log, not the DB. Do not cross-reference here.

## Git workflow

- Branch: `advisor/012-scrape-health-tab`
- 2 commits recommended: (1) parser + tests, (2) dashboard page.
- Commit message: `Plan 012: scrape-source health tab`
- Do NOT push or open a PR unless instructed.

## Steps

### Step 1: Write the parser module

Create `nodes/scrape_log_parser.py`:

```python
"""Parse the box-drawing scrape summary that `_print_summary` writes
to data/scrape_log.txt. Pure read-side — never mutates the log.

Each run summary produces one dict:
    {
        "timestamp": "2026-06-29 17:31:38",
        "platforms": {
            "Arbeitsagentur": {"terms": 39, "cards": 352, "added": 137,
                               "exp": 0, "depr": 55},
            ...
        },
        "total": {"terms": 39, "cards": 950, "added": 491,
                  "exp": 0, "depr": 101},
        "top_terms": [("Graduate Software Engineer", 253),
                      ("Trainee IT", 63),
                      ("Vollzeit Softwareentwickler", 35)],
    }
"""
import os
import re
from collections import defaultdict
from typing import Iterable

DEFAULT_LOG_PATH = "data/scrape_log.txt"

_TIMESTAMP_RE  = re.compile(r"^║\s*Scrape Summary\s*[—-]\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
_ROW_RE        = re.compile(
    r"^║\s*([A-Za-z][A-Za-z0-9]*)\s*║\s*"  # platform (or TOTAL)
    r"(\d+)\s*║\s*(\d+)\s*║\s*(\d+)\s*║\s*(\d+)\s*║\s*(\d+)"
)
_TOP_TERMS_RE  = re.compile(r"^\s*Top terms by jobs added:\s*(.+)$")
_TERM_RE       = re.compile(r"^(.*?)\s*\((\d+)\)\s*$")


def parse_scrape_log(path: str = DEFAULT_LOG_PATH) -> list[dict]:
    """Return list of run dicts, oldest first."""
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    return _parse_text(text)


def _parse_text(text: str) -> list[dict]:
    runs: list[dict] = []
    current: dict | None = None

    for raw in text.splitlines():
        m_ts = _TIMESTAMP_RE.match(raw)
        if m_ts:
            if current is not None:
                runs.append(current)
            current = {
                "timestamp": m_ts.group(1),
                "platforms": {},
                "total": None,
                "top_terms": [],
            }
            continue

        if current is None:
            continue

        m_row = _ROW_RE.match(raw)
        if m_row:
            name, terms, cards, added, exp, depr = m_row.groups()
            stat = {
                "terms": int(terms), "cards": int(cards), "added": int(added),
                "exp":   int(exp),   "depr":  int(depr),
            }
            if name == "TOTAL":
                current["total"] = stat
            else:
                current["platforms"][name] = stat
            continue

        m_top = _TOP_TERMS_RE.match(raw)
        if m_top:
            for chunk in m_top.group(1).split(","):
                m = _TERM_RE.match(chunk.strip())
                if m:
                    current["top_terms"].append((m.group(1).strip(), int(m.group(2))))

    if current is not None:
        runs.append(current)
    return runs


def platform_history(runs: list[dict], platform: str, limit: int = 20) -> list[dict]:
    """Slice runs to the last `limit` where `platform` appeared. Newest-last."""
    filtered = [
        {"timestamp": r["timestamp"], **r["platforms"][platform]}
        for r in runs if platform in r["platforms"]
    ]
    return filtered[-limit:]


def broken_platforms(runs: list[dict], streak: int = 3) -> list[str]:
    """Platforms with `streak` consecutive most-recent runs where added=0.

    Only reports platforms that HAVE data in the log — a completely absent
    platform isn't 'broken', it's just not configured.
    """
    if not runs:
        return []
    seen = set()
    for r in runs[-streak:]:
        seen.update(r["platforms"].keys())

    result = []
    for platform in sorted(seen):
        window = [r["platforms"].get(platform) for r in runs[-streak:]]
        if all(w is not None and w["added"] == 0 for w in window):
            result.append(platform)
    return result


def top_terms_aggregated(runs: Iterable[dict], limit: int = 10) -> list[tuple[str, int]]:
    """Sum term counts across the given runs. Returns sorted desc by count."""
    totals: dict[str, int] = defaultdict(int)
    for r in runs:
        for name, count in r.get("top_terms", []):
            totals[name] += count
    return sorted(totals.items(), key=lambda x: x[1], reverse=True)[:limit]
```

**Verify** (uses your live log):

```bash
venv/Scripts/python.exe -c "
from nodes.scrape_log_parser import parse_scrape_log, broken_platforms, platform_history, top_terms_aggregated
runs = parse_scrape_log()
print(f'{len(runs)} runs parsed')
print(f'last run: {runs[-1][\"timestamp\"] if runs else None}')
print(f'broken platforms (last 3 runs, added=0): {broken_platforms(runs)}')
hist = platform_history(runs, 'LinkedIn', limit=5)
print(f'LinkedIn last 5: {[(h[\"timestamp\"], h[\"added\"]) for h in hist]}')
print(f'top terms (aggregated last 20): {top_terms_aggregated(runs[-20:], limit=5)}')
"
```

Expected on the operator's machine (as of 2026-07-02, tail of
`data/scrape_log.txt`): parser finds 20+ runs, `broken_platforms` returns
at least `['Indeed', 'Stepstone', 'XING']`, LinkedIn shows non-zero
added counts, top terms surface `Graduate Software Engineer` at the top.

### Step 2: Add parser tests

Create `tests/test_scrape_log_parser.py`:

```python
import textwrap

from nodes.scrape_log_parser import (
    _parse_text,
    platform_history,
    broken_platforms,
    top_terms_aggregated,
)


SAMPLE_TWO_RUNS = textwrap.dedent("""\
    ╔══════════════════════════════════════════════════════════════════════╗
    ║  Scrape Summary — 2026-06-23 10:53:56                              ║
    ╠════════════════╦════════╦══════════╦════════╦═══════════╦═════════════╣
    ║ Platform       ║  Terms ║    Cards ║  Added ║     Exp ❌ ║      Depr ❌ ║
    ╠════════════════╬════════╬══════════╬════════╬═══════════╬═════════════╣
    ║ Arbeitsagentur ║     39 ║      367 ║    145 ║         0 ║          53 ║
    ║ Glassdoor      ║      3 ║       30 ║     17 ║         0 ║           8 ║
    ║ Indeed         ║      2 ║        0 ║      0 ║         0 ║           0 ║
    ║ LinkedIn       ║      8 ║      149 ║    107 ║         0 ║          38 ║
    ║ Stepstone      ║      2 ║        0 ║      0 ║         0 ║           0 ║
    ║ XING           ║      2 ║        0 ║      0 ║         0 ║           0 ║
    ╠════════════════╬════════╬══════════╬════════╬═══════════╬═════════════╣
    ║ TOTAL          ║     39 ║      546 ║    269 ║         0 ║          99 ║
    ╚══════════════════════════════════════════════════════════════════════╝
      Top terms by jobs added: Graduate Software Engineer (97), Vollzeit Softwareentwickler (36), Trainee Softwareentwicklung (19)

    ╔══════════════════════════════════════════════════════════════════════╗
    ║  Scrape Summary — 2026-06-29 17:31:38                              ║
    ╠════════════════╦════════╦══════════╦════════╦═══════════╦═════════════╣
    ║ Platform       ║  Terms ║    Cards ║  Added ║     Exp ❌ ║      Depr ❌ ║
    ╠════════════════╬════════╬══════════╬════════╬═══════════╬═════════════╣
    ║ Arbeitsagentur ║     39 ║      352 ║    137 ║         0 ║          55 ║
    ║ Glassdoor      ║      3 ║       30 ║     20 ║         0 ║           5 ║
    ║ Indeed         ║      2 ║        0 ║      0 ║         0 ║           0 ║
    ║ LinkedIn       ║      9 ║      568 ║    334 ║         0 ║          41 ║
    ║ Stepstone      ║      2 ║        0 ║      0 ║         0 ║           0 ║
    ║ XING           ║      2 ║        0 ║      0 ║         0 ║           0 ║
    ╠════════════════╬════════╬══════════╬════════╬═══════════╬═════════════╣
    ║ TOTAL          ║     39 ║      950 ║    491 ║         0 ║         101 ║
    ╚══════════════════════════════════════════════════════════════════════╝
      Top terms by jobs added: Graduate Software Engineer (253), Trainee IT (63), Vollzeit Softwareentwickler (35)
""")


def test_parse_two_runs_returns_two_dicts():
    runs = _parse_text(SAMPLE_TWO_RUNS)
    assert len(runs) == 2
    assert runs[0]["timestamp"] == "2026-06-23 10:53:56"
    assert runs[1]["timestamp"] == "2026-06-29 17:31:38"


def test_parse_platforms_populated_and_totals_extracted():
    runs = _parse_text(SAMPLE_TWO_RUNS)
    last = runs[-1]
    assert set(last["platforms"].keys()) == {"Arbeitsagentur", "Glassdoor", "Indeed", "LinkedIn", "Stepstone", "XING"}
    assert last["platforms"]["LinkedIn"]["added"] == 334
    assert last["platforms"]["Indeed"]["added"] == 0
    assert last["total"] == {"terms": 39, "cards": 950, "added": 491, "exp": 0, "depr": 101}


def test_parse_top_terms():
    runs = _parse_text(SAMPLE_TWO_RUNS)
    assert runs[-1]["top_terms"][0] == ("Graduate Software Engineer", 253)
    assert len(runs[-1]["top_terms"]) == 3


def test_parse_empty_text_returns_empty_list():
    assert _parse_text("") == []
    assert _parse_text("noise\ndata\n") == []


def test_platform_history_slices_to_limit():
    runs = _parse_text(SAMPLE_TWO_RUNS)
    hist = platform_history(runs, "LinkedIn", limit=1)
    assert len(hist) == 1
    assert hist[0]["added"] == 334


def test_platform_history_skips_runs_missing_platform():
    # Craft a run without Stepstone
    partial = SAMPLE_TWO_RUNS.replace("║ Stepstone      ║      2 ║        0 ║      0 ║         0 ║           0 ║\n", "", 2)
    runs = _parse_text(partial)
    assert platform_history(runs, "Stepstone", limit=5) == []


def test_broken_platforms_finds_three_consecutive_zero_added():
    # Repeat SAMPLE_TWO_RUNS to get a 3-run window with Indeed/Stepstone/XING at zero
    runs = _parse_text(SAMPLE_TWO_RUNS + SAMPLE_TWO_RUNS)
    broken = broken_platforms(runs, streak=3)
    for p in ("Indeed", "Stepstone", "XING"):
        assert p in broken
    for p in ("LinkedIn", "Arbeitsagentur", "Glassdoor"):
        assert p not in broken


def test_broken_platforms_empty_input():
    assert broken_platforms([], streak=3) == []


def test_broken_platforms_below_streak_length_no_alert():
    runs = _parse_text(SAMPLE_TWO_RUNS)
    assert broken_platforms(runs, streak=3) == []  # only 2 runs in the log


def test_top_terms_aggregated_sums_across_runs():
    runs = _parse_text(SAMPLE_TWO_RUNS)
    aggregated = top_terms_aggregated(runs, limit=5)
    top = dict(aggregated)
    assert top["Graduate Software Engineer"] == 97 + 253
    assert top["Vollzeit Softwareentwickler"] == 36 + 35


def test_top_terms_aggregated_respects_limit():
    runs = _parse_text(SAMPLE_TWO_RUNS)
    assert len(top_terms_aggregated(runs, limit=1)) == 1
```

**Verify**: `venv/Scripts/python.exe -m pytest tests/test_scrape_log_parser.py -v` → 11 passed / 0 failed.

### Step 3: Wire the "Scrape Health" page into the dashboard

Edit `dashboard.py`:

**3a. Add import** (top of file, near line 12-14):

```python
from nodes.scrape_log_parser import (
    parse_scrape_log, platform_history, broken_platforms, top_terms_aggregated,
)
```

**3b. Add cached loader** (near the other loaders, around line 55-60):

```python
@st.cache_data(ttl=60)
def load_scrape_runs():
    """Read the scrape log fresh at most once a minute."""
    return parse_scrape_log()
```

TTL of 60s is deliberate: this page is for looking at recent runs, so
staleness of a full 5 minutes would confuse the operator right after
they ran `main.py`.

**3c. Add page to sidebar radio** at line 329-332:

```python
    page      = st.radio(
        "nav",
        [
            "📊  My Applications",
            "🔍  Today's Matches",
            "❌  Not Matched",
            "📈  Scrape Health",
        ],
        label_visibility="collapsed"
    )
```

**3d. Add page block** at the END of the existing `if/elif` chain
(after the "❌  Not Matched" block ends around line 640-ish; use the
last `elif` as the anchor):

```python
elif page == "📈  Scrape Health":

    st.title("Scrape Source Health")
    st.markdown("Per-platform yield from the last runs, parsed from `data/scrape_log.txt`.")
    st.markdown("---")

    runs = load_scrape_runs()

    if not runs:
        st.info("📭 No scrape summaries yet. Run `python main.py` first.")
    else:
        # ── Broken-platform alert ────────────────────────
        broken = broken_platforms(runs, streak=3)
        if broken:
            names = ", ".join(_esc(b) for b in broken)
            st.markdown(
                f'<div style="padding:10px 14px; margin-bottom:12px; '
                f'border-left:3px solid #f85149; background:#3d0f10; '
                f'border-radius:4px; color:#e6e6e6;">'
                f'⚠️ <strong>{len(broken)} platform(s) added zero jobs across the last 3 runs:</strong> {names}. '
                f'Likely bot-block or broken selectors. See <code>plans/015-diagnose-silent-scraper-failures.md</code>.'
                f'</div>',
                unsafe_allow_html=True,
            )

        # ── Per-platform yield table ──────────────────────
        st.subheader("Recent runs")
        num_runs = st.slider("How many recent runs to show", 3, 20, min(10, len(runs)))
        window = runs[-num_runs:]

        platforms = sorted({p for r in window for p in r["platforms"]})
        rows = []
        for run in window:
            row = {"Timestamp": run["timestamp"]}
            for p in platforms:
                row[p] = run["platforms"].get(p, {}).get("added", None)
            row["TOTAL"] = (run.get("total") or {}).get("added", None)
            rows.append(row)

        df = pd.DataFrame(rows)
        # newest at the top
        df = df.iloc[::-1].reset_index(drop=True)

        def _highlight_zero(v):
            if v == 0:
                return "background-color:#3d0f10; color:#f85149;"
            return ""

        styled = df.style.applymap(_highlight_zero, subset=platforms)
        st.dataframe(styled, use_container_width=True, hide_index=True)

        # ── Top terms aggregated ──────────────────────────
        st.subheader("Top search terms (aggregated across window)")
        top = top_terms_aggregated(window, limit=15)
        if top:
            top_df = pd.DataFrame(top, columns=["Term", "Jobs added"])
            st.dataframe(top_df, use_container_width=True, hide_index=True)
        else:
            st.info("No top-terms line found in the recent runs.")
```

**Note**: `pd` is already imported at the top of `dashboard.py:3`.
Reuse it; do not re-import.

### Step 4: Manual smoke

```bash
venv/Scripts/streamlit run dashboard.py
```

Navigate to the new "📈  Scrape Health" page.

Expected on the operator's machine (based on 2026-07-02 log state):

1. Red alert banner at the top: "3 platform(s) added zero jobs across
   the last 3 runs: Indeed, Stepstone, XING."
2. Slider defaults to 10 runs.
3. Yield table shows one row per run, newest at top. Indeed, Stepstone,
   XING columns highlight in red (zero-added). LinkedIn / Glassdoor /
   Arbeitsagentur show normal numeric cells.
4. Top-terms table lists Graduate Software Engineer at #1.
5. Toggling the slider to 3 vs 20 changes both tables.
6. No terminal exceptions.

### Step 5: Update `plans/README.md`

Flip plan 012's status row to `DONE` with the commit SHA and pass counts.

## Test plan

- **New unit tests** in `tests/test_scrape_log_parser.py` — 11 cases:
  - `_parse_text` — 4 cases (two-run parse; platform + total extraction;
    top-terms parse; empty-input).
  - `platform_history` — 2 cases (limit slicing; missing-platform skip).
  - `broken_platforms` — 3 cases (finds; below streak; empty).
  - `top_terms_aggregated` — 2 cases (sums; limit respected).
- **No dashboard tests**. Streamlit page rendering isn't cheap to
  unit-test; manual smoke (Step 4) covers it.
- **Verification**: full suite green, ≥ 106 + 11 passed.

## Done criteria

ALL must hold:

- [ ] `nodes/scrape_log_parser.py` exists with the four public functions
      + the internal `_parse_text` used by tests.
- [ ] `tests/test_scrape_log_parser.py` exists with 11 passing tests.
- [ ] `dashboard.py` imports the parser, has the fourth
      `"📈  Scrape Health"` sidebar entry, and a corresponding
      `elif page == ...` block.
- [ ] `venv/Scripts/python.exe -m pytest -q` → ≥ 117 passed / 0 xfailed
      / 0 failed / exit 0.
- [ ] Manual smoke (Step 4) all 6 checks pass on the operator's machine.
- [ ] `plans/README.md` row for plan 012 flipped to `DONE`.
- [ ] `git diff --stat` shows only `dashboard.py`,
      `nodes/scrape_log_parser.py`, `tests/test_scrape_log_parser.py`,
      `plans/README.md` modified.
- [ ] `nodes/scraper.py` is NOT modified.

## STOP conditions

Stop and report if:

- The scrape log format has drifted since 2026-07-02 — the
  timestamp regex `_TIMESTAMP_RE` or row regex `_ROW_RE` fails to match
  a live entry. If you change the regex to accommodate drift, that's
  fine, but ALSO update the sample text in the tests to reflect the new
  format so future drift is caught.
- `data/scrape_log.txt` is empty or missing — the parser will return
  `[]` and the page will show a soft empty-state; that's OK. But if
  the operator's log is missing entirely, note it in the report.
- You find yourself changing `_print_summary` in `nodes/scraper.py`.
  Not in scope. The whole point is to parse an existing text
  artifact, not to change how it's produced.
- The Streamlit dataframe `styled` object throws a rendering error
  (older pandas + newer streamlit combinations sometimes clash). If
  so, fall back to a plain `st.dataframe(df, ...)` without the
  highlighter and note the pandas/streamlit versions in the STOP
  report — do not chase the rendering issue.

## Maintenance notes

- **Parser is defensive.** Rows the regex doesn't match are silently
  skipped — including the header row and the `╠╬╣` separators. This
  is intentional: brittle strict parsing would break on any format
  tweak. The tests lock in the current shape; if the format changes,
  the test sample text is what to update.
- **Log rotation.** `nodes/scraper.py:50` uses
  `RotatingFileHandler(maxBytes=2_000_000, backupCount=5)`. That's
  ~40 runs of history in the base file plus five 2 MB backups. The
  parser reads only the base file — sufficient for the "last 20 runs"
  page. If the operator later wants a longer-term trend chart, extend
  the parser to glob `data/scrape_log.txt*` and merge; not needed now.
- **Zero-Added ≠ broken.** Arbeitsagentur can legitimately have runs
  with 0 added when no new postings appear in the API. The alert only
  fires on **three consecutive** zero-added runs. If Arbeitsagentur
  starts flapping into the alert, either widen the streak in
  `broken_platforms` to 4 or exclude Arbeitsagentur explicitly (it
  uses a REST API, not Playwright — its failure mode is not "silent",
  so it's a different alert).
- **Reviewer focus:** verify the alert banner appears only when
  ALL three of the last 3 runs have 0 Added for a platform. A single
  zero-day for Stepstone is normal noise; a streak is signal.
- **Follow-up idea (not this plan):** wire the same
  `broken_platforms` check into `run_daily.py` so a broken-platform
  streak also raises a Windows toast (using Plan 010's helper). Fine
  intersection, but separately planned so each concern stays testable.
