# Plan 014: Add missing German cities to `_GERMANY_LOCATION` regex

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving on.
> If anything in "STOP conditions" fires, stop and report — do not
> improvise. When done, update the status row for this plan in
> `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 5bed640..HEAD -- nodes/analyzer.py tests/test_analyzer_filters.py`
> If either file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: `plans/002-pure-function-test-baseline.md` (uses its pytest infra + existing `test_analyzer_filters.py`)
- **Category**: bug (correctness)
- **Planned at**: commit `5bed640`, 2026-07-02

## Why this matters

`nodes/analyzer._quick_reject` drops any job whose `location` string does
not match the `_GERMANY_LOCATION` regex and does not literally contain
`"remote"`. The regex only lists ~15 places: `germany`, `deutschland`,
`nordrhein`, `bayern`, `berlin`, `hamburg`, `hessen`, `nrw`, `bochum`,
`dortmund`, `cologne`/`köln`, `düsseldorf`, `münchen`, `frankfurt`,
`stuttgart`, `essen`, `remote`. Everything else falls off the cliff with a
`"Outside Germany (<loc>)"` reason — before any LLM scoring happens.

A read of `data/not_matched_jobs.match_reasons` on 2026-07-02 shows
**hundreds** of postings falsely rejected as "Outside Germany" for cities
that are unambiguously German:

| City | Falsely rejected postings |
|---|---|
| Braunschweig | 42 |
| Bremen | 28 |
| Kiel | 17 |
| Hannover | 16 |
| Oldenburg | 15 |
| Bonn | 14 |
| Nürnberg | 11 |
| Eschborn | 8 |
| Augsburg | 8 |
| Wolfsburg | 7 |
| Saarbrücken | 7 |
| Dresden | 7 |
| Coburg | 7 |
| Bielefeld | 7 |
| **Total (top-14)** | **194** |

These jobs never reached the Claude scorer, never went into
`matched_jobs`, and are invisible in the dashboard as "matches you might
have missed" — they show up only as "outside Germany" rows in
`not_matched_jobs`. Fresh graduate applications typically favor
mid-sized German cities (Braunschweig, Hannover, Bremen etc.); losing
these silently hurts recall of an agent whose only reason to exist is
recall.

Adding the missing cities and Bundesland names to the regex is one line
of code and clears the recall bug.

## Current state

Relevant files:

- `nodes/analyzer.py` — `_GERMANY_LOCATION` at lines 285–288; used at
  line 319 inside `_quick_reject`.
- `tests/test_analyzer_filters.py` — pytest coverage for `_quick_reject`
  including a `test_quick_reject_german_locations_pass` parametrized case
  at lines 55–57 that currently only checks `Bochum`, `NRW`,
  `Deutschland`. This is where the regression cases belong.

Current code:

```python
# nodes/analyzer.py:281-288
_EXPERIENCE_EXTREME = re.compile(
    r"\b([5-9]\+?\s*jahre?|[5-9]\s*years?|1[0-9]\+?\s*jahre?|min\w*\.?\s*[5-9]\s*jahre?)\b",
    re.IGNORECASE,
)
_GERMANY_LOCATION = re.compile(
    r"(germany|deutschland|nordrhein|bayern|berlin|hamburg|hessen|nrw|bochum|dortmund|cologne|köln|düsseldorf|münchen|frankfurt|stuttgart|essen|remote)",
    re.IGNORECASE,
)
```

```python
# nodes/analyzer.py:319-320
    if loc and not _GERMANY_LOCATION.search(loc) and "remote" not in loc.lower():
        return f"Outside Germany ({loc})"
```

Existing test that covers this path:

```python
# tests/test_analyzer_filters.py:55-57
@pytest.mark.parametrize("loc", ["Bochum", "NRW", "Deutschland"])
def test_quick_reject_german_locations_pass(loc):
    assert _quick_reject({"title": "Junior Backend", "location": loc}) is None
```

Repo conventions: this is a plain module-level `re.compile()`. Match the
existing pattern — flat alternation inside a single non-capturing-ish
group, `re.IGNORECASE`, no word boundaries (the alternation intentionally
matches substrings so `"Munich, Germany"` and `"Berlin Mitte"` both pass).
Test style: parametrized cases with the shape shown above.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Activate venv | `source venv/Scripts/activate` (Windows bash) | prompt shows `(venv)` |
| Sanity-check regex | see Step 1 verify block | prints `None` for each city |
| Run analyzer tests | `venv/Scripts/python.exe -m pytest tests/test_analyzer_filters.py -v` | all pass, new cases green |
| Full suite | `venv/Scripts/python.exe -m pytest -q` | 106+ passed / 0 xfailed / 0 failed / exit 0 |

## Scope

**In scope** (only files you should modify):

- `nodes/analyzer.py` — extend `_GERMANY_LOCATION` regex (one line)
- `tests/test_analyzer_filters.py` — extend the existing German-location
  parametrize case with the new cities

**Out of scope** (do NOT touch, even though they look related):

- The 16 `REGIONS` list in `nodes/scraper.py` — that's the *scraper's*
  search regions, unrelated to the *quick-reject* filter this plan
  addresses.
- `_SENIOR_TITLE`, `_JUNIOR_TITLE`, `_NON_TECH_TITLE`,
  `_EXPERIENCE_EXTREME` — different regexes; don't touch.
- `_norm_title` / `_norm_company` in `nodes/tracker.py` — different
  problem space entirely.
- Any historical `not_matched_jobs` rows in the DB — this fix is
  forward-looking. Do NOT try to re-score old rows.

## Git workflow

- Branch: `advisor/014-germany-location-regex`
- One commit is fine. Message style — match recent commits:
  `Plan 014: extend _GERMANY_LOCATION with missing German cities`
- Do NOT push or open a PR unless the operator instructs it.

## Steps

### Step 1: Extend `_GERMANY_LOCATION`

Edit `nodes/analyzer.py` lines 285–288. Add the following place names
inside the existing alternation, preserving IGNORECASE and the flat-
alternation shape. Add Bundesländer that are missing plus the top
falsely-rejected cities from the audit:

- Bundesländer to add: `baden-württemberg`, `württemberg`,
  `niedersachsen`, `sachsen`, `rheinland-pfalz`, `saarland`,
  `schleswig-holstein`, `mecklenburg`, `brandenburg`, `thüringen`,
  `bremen`.
  Rationale: 5 of the 16 Bundesländer are already in the regex (nordrhein,
  bayern, hessen, hamburg-as-city-state, berlin-as-city-state). Adding
  the remaining 11 as substrings makes any "Company X, <Bundesland>"
  location string pass automatically, regardless of city.
- Cities to add (the top-14 from evidence + a few common ones): `bremen`
  (already covered by Bundesland — deduplicate), `braunschweig`,
  `hannover`, `nürnberg`, `nurnberg`, `augsburg`, `bielefeld`, `bonn`,
  `dresden`, `kiel`, `leipzig`, `mannheim`, `oldenburg`, `saarbrücken`,
  `saarbruecken`, `coburg`, `eschborn`, `wolfsburg`, `karlsruhe`,
  `wiesbaden`, `mainz`, `münster`, `muenster`, `aachen`, `hamm`,
  `duisburg`, `wuppertal`, `bochum` (already present — deduplicate),
  `chemnitz`, `magdeburg`, `heidelberg`, `göttingen`, `goettingen`,
  `paderborn`, `regensburg`, `ulm`, `freiburg`, `mönchengladbach`,
  `moenchengladbach`, `krefeld`, `gelsenkirchen`, `hagen`, `oberhausen`,
  `leverkusen`.
  Rationale: covers 100% of the falsely-rejected top-14 cities from the
  2026-07-02 audit plus every DE city with population > 100k. Adding the
  ASCII fallbacks (`nurnberg` alongside `nürnberg`) protects against
  ATS feeds that strip umlauts.

Recommended final regex (keep on ONE long line to match the existing
style — do not split into multi-line concatenation):

```python
_GERMANY_LOCATION = re.compile(
    r"(germany|deutschland|remote|"
    r"nordrhein|nrw|bayern|baden-württemberg|württemberg|niedersachsen|sachsen|hessen|rheinland-pfalz|saarland|schleswig-holstein|mecklenburg|brandenburg|thüringen|thueringen|"
    r"berlin|hamburg|münchen|muenchen|frankfurt|stuttgart|köln|koeln|cologne|düsseldorf|duesseldorf|dortmund|essen|bremen|hannover|nürnberg|nuernberg|leipzig|dresden|"
    r"bochum|braunschweig|augsburg|bielefeld|bonn|kiel|mannheim|oldenburg|saarbrücken|saarbruecken|coburg|eschborn|wolfsburg|karlsruhe|wiesbaden|mainz|münster|muenster|"
    r"aachen|hamm|duisburg|wuppertal|chemnitz|magdeburg|heidelberg|göttingen|goettingen|paderborn|regensburg|ulm|freiburg|mönchengladbach|moenchengladbach|krefeld|"
    r"gelsenkirchen|hagen|oberhausen|leverkusen)",
    re.IGNORECASE,
)
```

Notes for the executor:

- Preserve `re.IGNORECASE`.
- No word boundaries — this is intentional. "Berlin Mitte" and
  "Frankfurt am Main" must still pass.
- Python string-concatenation across adjacent string literals (the
  `r"..." r"..."` form) is a compile-time join with zero runtime cost.
  Do not `+`-concatenate at runtime.
- Keep `remote` inside the alternation (it was there before). Redundant
  with the `"remote" not in loc.lower()` fallback in `_quick_reject`
  but harmless.

**Verify**:

```bash
venv/Scripts/python.exe -c "from nodes.analyzer import _quick_reject; \
    [print(loc, '->', _quick_reject({'title':'Junior Backend','location':loc})) \
     for loc in ['Braunschweig','Bremen','Kiel','Hannover','Oldenburg','Bonn','Nürnberg','Eschborn','Augsburg','Wolfsburg','Saarbrücken','Dresden','Coburg','Bielefeld','Karlsruhe','Wiesbaden','Mainz']]"
```

Expected: every line prints `... -> None`. If any city prints
`Outside Germany (…)`, the regex is missing that city — add it and
re-verify.

Negative check:

```bash
venv/Scripts/python.exe -c "from nodes.analyzer import _quick_reject; \
    [print(loc, '->', _quick_reject({'title':'Junior Backend','location':loc})) \
     for loc in ['Zürich','Vienna','Wien','London','Warsaw','Amsterdam','Paris','Prague','Zurich']]"
```

Expected: every line prints `... -> Outside Germany (<loc>)`. If any
of these falsely pass, the regex is over-matching — check for stray
substrings (e.g. `wien` accidentally matches `wiesbaden`? — verify).

### Step 2: Extend the regression test

Edit `tests/test_analyzer_filters.py` lines 55–57. Replace the current
short parametrize with the full list. Keep the shape of the existing
test — do not restructure:

```python
@pytest.mark.parametrize("loc", [
    "Bochum", "NRW", "Deutschland",
    "Braunschweig", "Bremen", "Kiel", "Hannover", "Oldenburg", "Bonn",
    "Nürnberg", "Eschborn", "Augsburg", "Wolfsburg", "Saarbrücken",
    "Dresden", "Coburg", "Bielefeld", "Karlsruhe", "Wiesbaden", "Mainz",
    "Münster", "Aachen", "Duisburg", "Wuppertal", "Leipzig",
    "Frankfurt am Main", "Berlin Mitte", "München, Bayern",
    "Baden-Württemberg", "Niedersachsen", "Rheinland-Pfalz",
])
def test_quick_reject_german_locations_pass(loc):
    assert _quick_reject({"title": "Junior Backend", "location": loc}) is None
```

Also add a negative-case parametrize immediately below it (there is no
existing "outside Germany" parametrize — add one; the file already has
a single-case `test_quick_reject_outside_germany_not_remote` for
Zürich, keep that intact and add this alongside):

```python
@pytest.mark.parametrize("loc", [
    "Zürich", "Vienna", "Wien", "London", "Warsaw", "Amsterdam",
    "Paris", "Prague", "Zurich",
])
def test_quick_reject_non_german_locations_rejected(loc):
    reason = _quick_reject({"title": "Junior Backend", "location": loc})
    assert reason is not None
    assert "Outside Germany" in reason
```

**Verify**: `venv/Scripts/python.exe -m pytest tests/test_analyzer_filters.py -v -k "german_locations or non_german_locations"` → all pass, 0 failed, 0 xfailed.

### Step 3: Confirm no regressions in the full suite

**Verify**: `venv/Scripts/python.exe -m pytest -q` → same passed count as
baseline plus the number of new parametrize cases, 0 xfailed changes, 0
failed, exit 0. Baseline before this plan is 106 passed / 0 xfailed.
Expected after: ≥ 106 + new-cases passed / 0 xfailed / 0 failed.

### Step 4: Update `plans/README.md`

Change plan 014's status column from `TODO` to `DONE` and add a one-line
post-exec note pointing at the commit SHA and the pass counts.

**Verify**: `git diff plans/README.md` shows only plan 014's row edited
plus a possible line in the "Direction findings considered" section if
present. No other rows edited.

## Test plan

- **Extended parametrize** in `tests/test_analyzer_filters.py`:
  - `test_quick_reject_german_locations_pass` — 30+ cities and
    Bundesländer that must not be rejected.
  - `test_quick_reject_non_german_locations_rejected` (NEW) — 9 non-DE
    cities that must return an `"Outside Germany"` reason.
- **Verification**: full analyzer test file passes; total suite
  ≥ 106 + new-cases passed.

## Done criteria

ALL must hold:

- [ ] `venv/Scripts/python.exe -c "from nodes.analyzer import _quick_reject; \
    print(_quick_reject({'title':'Junior Backend','location':'Braunschweig'}))"` prints `None`.
- [ ] `venv/Scripts/python.exe -c "from nodes.analyzer import _quick_reject; \
    print(_quick_reject({'title':'Junior Backend','location':'Zürich'}))"` prints `Outside Germany (Zürich)`.
- [ ] `venv/Scripts/python.exe -m pytest tests/test_analyzer_filters.py -v` → all pass, new cases green.
- [ ] `venv/Scripts/python.exe -m pytest -q` → total ≥ 106 + new-cases, 0 xfailed, 0 failed, exit 0.
- [ ] `git diff --stat` shows only `nodes/analyzer.py`,
      `tests/test_analyzer_filters.py`, `plans/README.md` modified.
- [ ] `plans/README.md` row for plan 014 flipped to `DONE`.

## STOP conditions

Stop and report back (do not improvise) if:

- The `_GERMANY_LOCATION` line in `nodes/analyzer.py` doesn't match the
  excerpt at lines 285–288 (the file has drifted).
- The parametrize at `tests/test_analyzer_filters.py:55-57` doesn't
  exist or doesn't match the shape shown — plan 002's baseline may not
  be in place.
- Any of the "outside Germany" negative cases starts falsely passing
  after your regex change (over-matching). Do not "just live with it" —
  the recall win is not worth false-positive DE tagging on Austrian
  or Swiss postings.
- The regex change causes the module to fail to import
  (`venv/Scripts/python.exe -c "import nodes.analyzer"` raises).

## Maintenance notes

- **New falsely-rejected cities will appear.** German ATS feeds vary; if
  in six months' time you see `"Outside Germany (Halle)"` or similar in
  `data/applications.db`, add that city here rather than switching to a
  fuzzy match. An explicit whitelist stays auditable; a fuzzy match
  starts silently matching `Warsaw` because it shares three letters with
  `Waren`. Query to run:
  ```sql
  SELECT SUBSTR(match_reasons, 18, LENGTH(match_reasons) - 18) AS city, COUNT(*) c
  FROM not_matched_jobs
  WHERE match_reasons LIKE 'Outside Germany (%'
  GROUP BY city ORDER BY c DESC LIMIT 30;
  ```
- **Historical rows stay rejected.** This fix is forward-looking. If the
  operator wants to reclaim the 194 falsely-rejected postings from
  before this fix, that is a separate plan (needs to re-fetch by URL and
  re-score) and probably not worth doing — the postings are stale by
  now.
- **Reviewer focus:** verify the regex still doesn't match `Zürich`,
  `Wien`, or `Vienna`. `zurich` shares no substring with the added
  cities, but `wien` overlaps with `wiesbaden` — ensure the negative-
  case parametrize catches that if it ever regresses.
