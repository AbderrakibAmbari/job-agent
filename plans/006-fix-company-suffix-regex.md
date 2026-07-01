# Plan 006: Fix `_COMPANY_SUFFIX_RE` trailing-period bugs

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**:
> `git diff --stat 79c1536..HEAD -- nodes/tracker.py tests/test_tracker_keys.py`
> If either in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P3
- **Effort**: S
- **Risk**: LOW
- **Depends on**: 002 (plan 002 introduced the xfailed tests this plan flips green)
- **Category**: bug
- **Planned at**: commit `79c1536`, 2026-07-01

## Why this matters

`nodes/tracker._COMPANY_SUFFIX_RE` is used to normalize company names so
that variants like `"Arvato"`, `"Arvato SE"`, and `"Arvato GmbH"` produce
the same dedup key. Three suffix forms fail the strip today:

- `"Acme Ltd."` → `"acme ."` (trailing period leaks through)
- `"Acme Inc."` → `"acme ."` (same)
- `"Acme e.V."` → `"acme e.v."` (no strip at all)

Consequence: `"Acme Ltd"` and `"Acme Ltd."` hash to different dedup keys
and do not merge — a real but small correctness bug in the tracker's
title+company dedup path (also mirrored downstream in
`cleanup_duplicates.py`).

Discovered while writing plan 002's `tests/test_tracker_keys.py`. Those
three cases are currently `pytest.param(..., marks=xfail(strict=True))`
with a reason string pointing at this plan. This plan fixes the regex and
flips the xfail cases back to normal `pytest.param` entries.

## Current state

**File in scope**: `nodes/tracker.py`. Excerpt (lines 13–31):

```python
# Strip gender suffixes before title+company dedup
_GENDER_RE = re.compile(
    r'\s*\(m/w/d\)|\s*\(w/m/d\)|\s*\(m/f/d\)|\s*\(m/w/x\)|\s*\(w/m/x\)|\s*\(all genders\)',
    re.IGNORECASE,
)
# Strip common legal suffixes so "Arvato" and "Arvato SE" normalise to the same key
_COMPANY_SUFFIX_RE = re.compile(
    r'\b(GmbH\s*&\s*Co\.?\s*KG|GmbH|AG|SE|Ltd\.?|LLC|Inc\.?|KG|e\.V\.|gGmbH|plc)\b',
    re.IGNORECASE,
)


def _norm_title(title: str) -> str:
    return _GENDER_RE.sub('', title or '').lower().strip()


def _norm_company(company: str) -> str:
    c = _COMPANY_SUFFIX_RE.sub('', company or '').lower()
    return re.sub(r'\s+', ' ', c).strip()
```

**Root cause**: the trailing `\b` requires a word-to-non-word transition.
For `Ltd.` and `Inc.` the engine backtracks off the optional `\.?` because
matching the period leaves `\b` between two non-word chars (`.` and space
or end-of-string) — no transition. The result is that `Ltd`/`Inc` match
but the trailing `.` is left in the string; the whitespace-collapse step
turns it into `"acme ."`. For `e\.V\.` at end-of-string, the engine
cannot match the trailing `\b` at all (end-of-string is treated as
non-word), so no strip happens.

**File in scope (tests)**: `tests/test_tracker_keys.py`. Current
xfail block (lines 37–48 or thereabouts — verify with the drift-check
diff before editing):

```python
_XFAIL_TRAILING_PERIOD = pytest.mark.xfail(
    reason=(
        "BUG: _COMPANY_SUFFIX_RE uses trailing \\b which cannot cross a trailing "
        "period. 'Ltd.'/'Inc.' strip to 'acme .' (leaving the period), 'e.V.' at "
        "end-of-string does not match at all. Out of scope for plan 002 — logged "
        "for a follow-up plan."
    ),
    strict=True,
)


@pytest.mark.parametrize("raw, expected", [
    ("Acme GmbH", "acme"),
    ("Acme AG", "acme"),
    ("Acme SE", "acme"),
    ("Acme Ltd", "acme"),
    pytest.param("Acme Ltd.", "acme", marks=_XFAIL_TRAILING_PERIOD),
    ("Acme LLC", "acme"),
    ("Acme Inc", "acme"),
    pytest.param("Acme Inc.", "acme", marks=_XFAIL_TRAILING_PERIOD),
    ("Acme KG", "acme"),
    pytest.param("Acme e.V.", "acme", marks=_XFAIL_TRAILING_PERIOD),
    ("Acme gGmbH", "acme"),
    ("Acme plc", "acme"),
    ("Acme GmbH & Co. KG", "acme"),
    ("Acme GmbH & Co KG", "acme"),
    ("ACME GMBH", "acme"),
])
def test_norm_company_strips_legal_suffix(raw, expected):
    assert _norm_company(raw) == expected
```

**Duplicated but out of scope**: `cleanup_duplicates.py:18-38` carries a
near-copy of `_COMPANY_SUFFIX_RE`. It's documented in
`plans/README.md` "Findings considered and rejected" as one-off. Do NOT
touch it in this plan — the trade-off there is unchanged.

**Existing test infrastructure**: pytest baseline established by plan
002. `pytest -q` runs green (with `x` markers for the three current
xfails).

## Commands you will need

| Purpose                | Command                                          | Expected on success                          |
|------------------------|--------------------------------------------------|----------------------------------------------|
| Run tracker tests      | `pytest -q tests/test_tracker_keys.py`           | exit 0, all pass, no xfails                  |
| Run full suite         | `pytest -q`                                      | exit 0                                       |
| Verify scope           | `git diff --name-only 79c1536..HEAD`             | only `nodes/tracker.py` + `tests/test_tracker_keys.py` |

## Scope

**In scope** (only files you may modify):

- `nodes/tracker.py` — change one line: the `_COMPANY_SUFFIX_RE` pattern.
- `tests/test_tracker_keys.py` — remove the `_XFAIL_TRAILING_PERIOD`
  marker definition and unwrap the three `pytest.param(...)` entries
  back into plain tuples.

**Out of scope** (do NOT touch):

- `cleanup_duplicates.py` — one-off script; documented as accepted drift.
- `_GENDER_RE`, `_norm_title`, `_norm_company` body, `_title_company_key`
  body — unchanged.
- Any addition of a new normalization helper. This is a one-line regex
  fix; do not refactor.

## Git workflow

- Branch: `advisor/006-company-suffix-regex-fix`.
- One commit: `fix(tracker): strip trailing period on Ltd./Inc./e.V. suffixes`.
- Do NOT push or open a PR unless the operator asks.

## Steps

### Step 1: Fix the regex

Edit `nodes/tracker.py`. Replace the current `_COMPANY_SUFFIX_RE` (the
line beginning with `r'\b(GmbH\s*&\s*Co...'`) with:

```python
_COMPANY_SUFFIX_RE = re.compile(
    r'\b(GmbH\s*&\s*Co\.?\s*KG|GmbH|AG|SE|Ltd\.?|LLC|Inc\.?|KG|e\.V\.|gGmbH|plc)(?=\s|[.,;]|$)',
    re.IGNORECASE,
)
```

What changed and why:

- Trailing `\b` → `(?=\s|[.,;]|$)`. A lookahead for whitespace,
  common punctuation, or end-of-string does not require a word/non-word
  transition, so `Ltd.` and `Inc.` can consume their trailing period and
  `e.V.` at end-of-string can match.
- The lookahead does not consume, so multiple matches on one string
  still work (e.g. hypothetical `"Acme GmbH, Berlin"`).
- Leading `\b` is kept — we still don't want to strip `LtdConsulting` or
  similar false hits.

Do NOT change any other line of `nodes/tracker.py`.

**Verify**: `pytest -q tests/test_tracker_keys.py` still passes with the
current xfail markers (the fix should now make those cases pass; strict
xfail flips them from `x` to `X` / failure). This is expected — Step 2
removes the markers.

### Step 2: Remove the xfail wrapper in the test file

Edit `tests/test_tracker_keys.py`:

1. Delete the `_XFAIL_TRAILING_PERIOD = pytest.mark.xfail(...)` block
   (the whole assignment including the multi-line reason string).
2. Replace each `pytest.param("Acme Ltd.", "acme", marks=_XFAIL_TRAILING_PERIOD)`
   line with a plain tuple `("Acme Ltd.", "acme")`. Same for the `Inc.`
   and `e.V.` lines. The parametrize list should read cleanly with all
   entries as tuples.

**Verify**:
```
pytest -q tests/test_tracker_keys.py
```
→ 39 passed, 0 failed, 0 xfailed. Exit 0.

### Step 3: Full suite

```
pytest -q
```
→ exit 0, all tests pass, no unexpected xfails.

### Step 4: Scope check

```
git diff --name-only 79c1536..HEAD
```
→ exactly two files: `nodes/tracker.py` and
`tests/test_tracker_keys.py`. If anything else shows up, STOP and
report.

## Test plan

- Coverage of the fix is provided entirely by the existing parametrize
  in `test_norm_company_strips_legal_suffix`. No new test file needed.
- The three previously-xfailed cases now assert the fixed behavior.
- No new production-facing edge case is introduced — the fix narrows
  the trailing anchor, it does not broaden what gets stripped.

## Done criteria

ALL must hold:

- [ ] `pytest -q tests/test_tracker_keys.py` → exit 0, 39 passed,
      0 xfailed.
- [ ] `pytest -q` → exit 0.
- [ ] `git diff --name-only 79c1536..HEAD` shows only
      `nodes/tracker.py` and `tests/test_tracker_keys.py`.
- [ ] The `_XFAIL_TRAILING_PERIOD` marker no longer appears in
      `tests/test_tracker_keys.py`.
- [ ] `plans/README.md` status row for plan 006 updated to DONE.

## STOP conditions

Stop and report (do not improvise) if:

- The drift check shows `nodes/tracker.py` changed and the excerpt in
  "Current state" no longer matches — the fix may need a different shape.
- Any test other than the three previously-xfailed cases changes result
  after the regex edit (e.g. a `GmbH & Co. KG` case starts failing).
  The lookahead should be behavior-compatible for those, but if it
  isn't, do NOT force a broader fix — report and hand back.
- Full suite `pytest -q` regresses on tests unrelated to tracker keys.
  That would imply `_COMPANY_SUFFIX_RE` is imported somewhere unexpected;
  investigate before proceeding.
- You find yourself wanting to also change `cleanup_duplicates.py`. That
  is explicitly out of scope — STOP.

## Maintenance notes

- If the tracker's suffix list ever grows (new legal forms), add each
  alternative to the group inside `_COMPANY_SUFFIX_RE`. Keep the trailing
  lookahead group `(?=\s|[.,;]|$)` — do NOT revert to `\b`.
- `cleanup_duplicates.py` still contains the old regex. If that script
  is ever re-run, either mirror this fix into it or accept the small
  divergence for the one-off cleanup. Documented trade-off; not a bug
  to be surprised by.
- Reviewer scrutiny: verify the lookahead uses `(?=...)` (non-consuming)
  not `(?:...)` — that's the difference between a working fix and a
  regression on multi-suffix strings.
