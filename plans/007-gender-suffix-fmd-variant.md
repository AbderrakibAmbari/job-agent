# Plan 007: Add `(f/m/d)` and `(f/m/x)` to the gender-suffix strip regex

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 7d391d6..HEAD -- nodes/tracker.py tests/test_tracker_keys.py`
> If either file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: `plans/002-pure-function-test-baseline.md` (uses its pytest infra)
- **Category**: bug
- **Planned at**: commit `7d391d6`, 2026-07-02

## Why this matters

The 2026-06-29 pipeline run re-scraped a Hyundai AutoEver posting titled
`Linux/Unix Systems Engineer (f/m/d)` as a "new" job — its earlier scrape
was `Linux/Unix Systems Engineer (m/f/d)`. Same job, same company, different
gender-suffix ordering. The dedup key differs because `_GENDER_RE` in
`nodes/tracker.py` strips `(m/w/d)`, `(w/m/d)`, `(m/f/d)`, `(m/w/x)`,
`(w/m/x)`, `(all genders)` but not `(f/m/d)` or `(f/m/x)`. LinkedIn/XING
postings that lead with `f` (female-first ordering, increasingly common in
DE listings) leak through as duplicates every time the ordering flips.

Adding these two variants to `_GENDER_RE` costs one line and makes the
title-company dedup stable across reorderings. In-DB investigation on
2026-07-02 found this as the only clear-cut regex gap in three months of
scrape history — the two other near-duplicate leaks that same day
(`(Junior)` prefix churn, `für` preposition drop) are ambiguous and
explicitly out of scope for this plan (see maintenance notes below).

## Current state

Relevant files:

- `nodes/tracker.py` — `_GENDER_RE` at lines 14–17; drives `_norm_title` at
  line 26, which drives `_title_company_key` at line 34, which is what
  `get_known_title_keys()` (line 406) returns and what
  `nodes/pipeline.py:_job_title_key` (line 16) compares against for
  the "have we seen this title+company before?" dedup pass.
- `tests/test_tracker_keys.py` — pytest baseline covering
  `_title_company_key`. The gender-suffix cases live at the top of the
  parametrize block. This is where the new xfail-then-green case belongs
  once we've flipped it.

Current code:

```python
# nodes/tracker.py:13-17
# Strip gender suffixes before title+company dedup
_GENDER_RE = re.compile(
    r'\s*\(m/w/d\)|\s*\(w/m/d\)|\s*\(m/f/d\)|\s*\(m/w/x\)|\s*\(w/m/x\)|\s*\(all genders\)',
    re.IGNORECASE,
)
```

Real-world evidence (verified 2026-07-02 via `data/applications.db`):

```
[2026-06-29] 'Linux/Unix Systems Engineer (f/m/d)'  @ 'Hyundai AutoEver Europe GmbH'
[2026-06-23] 'Linux/Unix Systems Engineer (m/f/d)'  @ 'Hyundai AutoEver Europe GmbH'
```

Repo conventions: this is a plain module-level `re.compile()` — match the
existing pattern exactly (no new imports, no factoring). The regex is
case-insensitive already (`re.IGNORECASE`), so the new alternatives inherit
that. Test style: parametrized cases with `pytest.param(..., id=...)`, see
`tests/test_tracker_keys.py` for the shape.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Activate venv | `venv\Scripts\activate` (Windows bash: `source venv/Scripts/activate`) | prompt shows `(venv)` |
| Run tracker tests | `python -m pytest tests/test_tracker_keys.py -v` | all pass; new cases green |
| Full suite | `python -m pytest -q` | 86+ passed, 3 xfailed, exit 0 |

## Scope

**In scope** (only files you should modify):

- `nodes/tracker.py` — regex change (one line, plus the docstring line above it if you want to note the new variants)
- `tests/test_tracker_keys.py` — new parametrized cases

**Out of scope** (do NOT touch, even though they look related):

- `nodes/scraper.py:_title_key` — a *separate* dedup function used only for intra-scrape merges; its gender handling uses `\s*\(.*?\)\s*` which catches any parenthetical, so this bug does not affect it.
- `_COMPANY_SUFFIX_RE` (line 19) — that's plan 006's territory. Do not touch.
- The `(Junior)` prefix / preposition dedup regressions surfaced 2026-06-29 — see the maintenance notes; they need a *different* fix and are explicitly deferred.

## Git workflow

- Branch: `advisor/007-gender-suffix-fmd`
- One commit is fine (small change). Message style — match recent commits: `Plan 007: cover (f/m/d) and (f/m/x) in _GENDER_RE`
- Do NOT push or open a PR unless the operator instructs it.

## Steps

### Step 1: Extend `_GENDER_RE` with the two missing variants

Edit `nodes/tracker.py` lines 14–17. Add `(f/m/d)` and `(f/m/x)` as
alternatives. Preserve the existing order, `re.IGNORECASE` flag, and the
`\s*` prefix pattern on each alternative:

```python
_GENDER_RE = re.compile(
    r'\s*\(m/w/d\)|\s*\(w/m/d\)|\s*\(m/f/d\)|\s*\(f/m/d\)|\s*\(m/w/x\)|\s*\(w/m/x\)|\s*\(f/m/x\)|\s*\(all genders\)',
    re.IGNORECASE,
)
```

**Verify**: `python -c "from nodes.tracker import _norm_title; print(repr(_norm_title('Linux/Unix Systems Engineer (f/m/d)')))"` → `'linux/unix systems engineer'`
Also: `python -c "from nodes.tracker import _norm_title; print(repr(_norm_title('Data Analyst (f/m/x)')))"` → `'data analyst'`

### Step 2: Add regression tests

Open `tests/test_tracker_keys.py`. Locate the parametrized block that
covers gender-suffix stripping (the `_title_company_key` tests — the first
big `@pytest.mark.parametrize` in the file). Add cases in the same shape
as the existing `(m/w/d)` / `(m/f/d)` cases:

```python
pytest.param(
    "Linux/Unix Systems Engineer (f/m/d)", "Hyundai AutoEver Europe GmbH",
    "linux/unix systems engineer|hyundai autoever europe",
    id="strips_f_m_d_variant",
),
pytest.param(
    "Data Analyst (f/m/x)", "Acme",
    "data analyst|acme",
    id="strips_f_m_x_variant",
),
```

Preserve the exact key-string format used by neighboring cases (pipe
separator, lowercase, company-suffix stripped). If the surrounding cases
use a different tuple shape (three-arg tuples without `pytest.param`),
match that shape instead — do not restructure the block.

**Verify**: `python -m pytest tests/test_tracker_keys.py -v -k "f_m_d or f_m_x"` → 2 passed, 0 failed, 0 xfailed.

### Step 3: Confirm no regressions in the full suite

**Verify**: `python -m pytest -q` → same total as before *plus* 2, still 3 xfailed (plan 006's cases), exit 0. Baseline before this plan was 86 passed / 3 xfailed. Expected after: 88 passed / 3 xfailed.

### Step 4: Update `plans/README.md`

Change plan 007's status column from `TODO` to `DONE` and add a one-line
post-exec note pointing at the commit SHA.

**Verify**: `git diff plans/README.md` shows only the status change and
note; no other rows edited.

## Test plan

- **New tests** in `tests/test_tracker_keys.py`, in the existing
  parametrized `_title_company_key` block:
  - `strips_f_m_d_variant`: title `"Linux/Unix Systems Engineer (f/m/d)"`, company `"Hyundai AutoEver Europe GmbH"` → key `"linux/unix systems engineer|hyundai autoever europe"`
  - `strips_f_m_x_variant`: title `"Data Analyst (f/m/x)"`, company `"Acme"` → key `"data analyst|acme"`
- **Model after** the existing `strips_m_w_d_variant` and
  `strips_m_f_d_variant` cases in the same file.
- **Verification**: `python -m pytest tests/test_tracker_keys.py -v` — all
  pass including the two new cases; xfail count unchanged (still 3 from
  plan 006).

## Done criteria

ALL must hold:

- [ ] `python -m pytest tests/test_tracker_keys.py -v` → all pass, new cases green
- [ ] `python -m pytest -q` → 88 passed / 3 xfailed / 0 failed / exit 0
- [ ] `python -c "from nodes.tracker import _norm_title; print(_norm_title('X (f/m/d)'), _norm_title('X (f/m/x)'))"` prints `x x` (both stripped)
- [ ] `git diff --stat` shows only `nodes/tracker.py`, `tests/test_tracker_keys.py`, `plans/README.md` modified
- [ ] `plans/README.md` row for plan 007 flipped to `DONE`

## STOP conditions

Stop and report back (do not improvise) if:

- The `_GENDER_RE` line in `nodes/tracker.py` doesn't match the excerpt
  above (the file has drifted).
- The parametrize block in `tests/test_tracker_keys.py` doesn't already
  contain `strips_m_f_d_variant` or an obvious analog — the plan assumed
  plan 002's baseline is in place. If it's not, stop and report.
- Full-suite pytest reports fewer than 86 pre-existing pass rows or more
  than 3 xfailed — a different plan has landed since 7d391d6 and this
  plan's baseline is stale.
- You find yourself editing anything other than the three files listed
  in Scope.

## Maintenance notes

- **New gender-suffix variants keep appearing.** German job boards are
  actively adding orderings (`(d/m/w)`, `(x/m/w)`, `(d/w/m)`, `(w/d/m)`
  are all seen in the wild). Next time a duplicate leaks through with a
  novel ordering, add it here rather than building a permutation
  generator — an explicit whitelist is easier to audit than a regex
  covering all 6 permutations of `{m,w,d,f,x}`.
- **Explicitly deferred (do NOT try to fix in this plan):**
  1. `(Junior)` prefix churn — reposts where `(Junior) Software Engineer`
     becomes `Software Engineer` at the same company. Fixing this by
     stripping `(Junior)` from titles risks *false merges* of genuinely
     different roles at large employers (Rheinmetall, Reply, Debeka
     regularly post `Senior X (m/w/d)` and `Junior X (m/w/d)`
     side-by-side).
  2. Preposition drop — reposts where `Softwareentwickler für
     Entwicklungsprojekte` becomes `Softwareentwickler
     Entwicklungsprojekte`. Fixing this by stripping German prepositions
     is high-blast-radius; `Berater für SAP` and `Berater SAP` may be
     the same role, but `Analyst für Cybersecurity` vs `Cybersecurity
     Analyst` might not.
     If either regression becomes frequent, revisit with a plan that adds
     a *fuzzy* second-pass dedup (edit distance ≤ 2 on
     tokenized+sorted titles at the same company) rather than more
     regex — that's a controlled, measurable fix, not a slippery-slope
     one.
- **Reviewer focus:** the four new alternatives are `(f/m/d)`, `(f/m/x)`
  — verify both are in the regex and that no unintended reorderings
  slipped in (the existing alternatives should remain byte-identical).
