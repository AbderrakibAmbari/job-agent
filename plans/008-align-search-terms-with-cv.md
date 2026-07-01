# Plan 008: Align scraper search terms with the operator's CV

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 7d391d6..HEAD -- nodes/scraper.py`
> If `nodes/scraper.py` changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: LOW
- **Depends on**: `plans/002-pure-function-test-baseline.md` (soft — the
  baseline pytest suite catches accidental import/module-level breakage
  after the edit)
- **Category**: tech-debt / direction
- **Planned at**: commit `7d391d6`, 2026-07-02

## Why this matters

The operator's CV (`my_cv.txt`) and profile (`config/profile.yaml`) show
a Junior Backend / Full-Stack focus in **Java (Spring Boot, Spring
Security), Python (FastAPI, Flask), Kotlin, TypeScript**, with hands-on
frontend work in **Angular (production Werkstudent experience at
Toolineo), Vue 3, React**, plus **Docker, Linux, DevOps** exposure and
an AI Bachelorarbeit using **Anthropic API / MCP / LangGraph**. Career
narrative in `profile.yaml:34-37` explicitly welcomes Cloud/DevOps and
"nah an Infrastruktur" roles.

The current search vocabulary in `nodes/scraper.py` is misaligned in
three ways that all waste the finite 600s-per-platform scrape budget:

1. **Zero SAP/ERP/ABAP/Dynamics 365 signal on the CV** — yet
   `SAP_TRAINING_TERMS` (11 terms) is fed to Arbeitsagentur every run,
   plus 5 more SAP/ERP/Dynamics/ABAP terms live inside `JUNIOR_TERMS`.
   `nodes/analyzer.py` already caps SAP scores at 55 (confirming the
   mismatch), meaning every SAP hit is a scored Anthropic call for a job
   that can't clear the 70/50 threshold.
2. **Missing dedicated terms for the CV's actual skill anchors** —
   nothing searches for "Spring Boot", "Angular", "Vue", "React",
   "FastAPI", or "Docker" as first-class Junior/Trainee terms. These
   are only caught incidentally when a listing happens to also say
   "Junior Java Developer" or "Junior Software Engineer".
3. **Missing sysadmin/DevOps entry-level track** — the profile explicitly
   welcomes it, but there is no "Junior Systemadministrator", "Junior
   Linux Administrator", "Junior IT Systemadministrator", or "Junior SRE"
   term. (Note: `Junior SRE` exists — good — but the German-language
   sysadmin variants dominate the DE market and are missing.)
4. **Five duplicate strings** between `JUNIOR_TERMS` and
   `TRAINEE_VOLLZEIT_TERMS` (`Trainee IT`, `Trainee IT Consulting`,
   `Trainee Software Engineer`, `Trainee Softwareentwicklung`,
   `Direkteinstieg IT Beratung`, `Young Professional IT`, plus
   `Junior Full Stack Entwickler` appearing twice inside `JUNIOR_TERMS`
   itself) — they double-scrape the same query and burn budget.

This plan rewrites the three term-list constants (and one `ba_terms`
line) in `nodes/scraper.py` to (a) drop SAP/ERP/Dynamics/ABAP, (b) add
first-class terms for the CV's real stack, (c) add German sysadmin/
DevOps entry-level terms, (d) remove intra-list duplicates. No new
tests are required — the search-terms constants are static data with
no pure-function surface.

## Current state

Relevant file: `nodes/scraper.py`. Three list constants and one derived
constant + one `ba_terms` line are in scope.

**Current `JUNIOR_TERMS`** (`nodes/scraper.py:201-268`) — 55 items, 4
tiers. Contains the SAP/ERP/Dynamics/ABAP terms this plan removes:

```python
JUNIOR_TERMS = [
    # Tier 1 — highest recall German compounds
    "Junior Softwareentwickler",
    "Junior Backend Entwickler",
    "Junior Software Engineer",
    "Junior Backend Developer",
    # Tier 1 — AI/GenAI
    "Junior AI Engineer",
    "Junior Generative AI Engineer",
    "Junior NLP Engineer",
    "AI Software Engineer",
    # Tier 1 — QA
    "Junior QA Engineer",
    "Junior Test Automation Engineer",
    "Junior Software Tester",
    "Junior SDET",
    # Tier 1 — IT Consulting / Trainee Programs
    "Junior IT Consultant",
    "IT Trainee",
    "Trainee IT Consulting",
    "Trainee Softwareentwicklung",
    # Tier 1 — Full Stack / Cloud / DevOps
    "Junior Full Stack Developer",
    "Junior Full Stack Entwickler",
    "Junior DevOps Engineer",
    "Junior Cloud Engineer",
    "Junior Platform Engineer",
    # Tier 1 — Data
    "Junior Data Engineer",
    "Junior Data Analyst",
    "Junior Data Scientist",
    "Junior BI Developer",
    # Tier 2 — Language-specific English
    "Junior Python Developer",
    "Junior Java Developer",
    "Junior Machine Learning Engineer",
    "Junior LLM Engineer",
    # Tier 2 — Language-specific German
    "Junior Python Entwickler",
    "Junior Java Entwickler",
    "Junior Full Stack Entwickler",       # duplicate of Tier 1 entry
    "Junior Webentwickler",
    "Junior Frontend Entwickler",
    "Junior Kotlin Entwickler",
    "Junior TypeScript Entwickler",
    # Tier 2 — ERP / SAP / Dynamics
    "Junior SAP Berater",
    "Junior SAP Consultant",
    "Junior ERP Consultant",
    "Junior Dynamics 365 Consultant",
    "Junior ABAP Entwickler",
    # Tier 2 — Broader entry-level
    "Junior KI Engineer",
    "Junior Analytics Engineer",
    "Junior SRE",
    "Direkteinstieg IT Beratung",         # duplicate of TRAINEE_VOLLZEIT_TERMS
    "Young Professional IT",              # duplicate of TRAINEE_VOLLZEIT_TERMS
    "Junior Anwendungsentwickler",
    "Junior Wirtschaftsinformatiker",
    # Tier 3 — German entry-level qualifiers
    "Trainee Software Engineer",          # duplicate of TRAINEE_VOLLZEIT_TERMS
    "Berufseinsteiger Entwickler",
    "Berufseinsteiger Softwareentwicklung",
    "Softwareentwickler Berufseinsteiger",
    "Absolvent Informatik",
    "Quereinsteiger Softwareentwickler",
    "Trainee IT",                         # duplicate of TRAINEE_VOLLZEIT_TERMS
]
```

**Current `SAP_TRAINING_TERMS`** (`nodes/scraper.py:288-302`) — 11 items,
all SAP/ABAP/consulting-tracks. Removed entirely by this plan:

```python
SAP_TRAINING_TERMS = [
    "Junior SAP Berater",
    "Junior SAP Consultant",
    "Trainee SAP Beratung",
    "SAP Trainee",
    "adesso Trainee",
    "Capgemini Junior",
    "Materna Trainee",
    "Sopra Steria Junior",
    "msg Trainee",
    "Trainee IT Beratung",
    "Absolventenprogramm IT",
]
```

**Current `TRAINEE_VOLLZEIT_TERMS`** (`nodes/scraper.py:304-327`) — 20
items, all reasonable. This plan leaves it unchanged.

**Current derived constants and BA slice** (`nodes/scraper.py:329-335, 908`):

```python
# Line 331
SEARCH_TERMS = TRAINEE_VOLLZEIT_TERMS + JUNIOR_TERMS + SAP_TRAINING_TERMS
# Line 335
PLATFORM_SEARCH_TERMS = TRAINEE_VOLLZEIT_TERMS[:14] + JUNIOR_TERMS[:18]
# Line 908 (inside _run_arbeitsagentur)
ba_terms = TRAINEE_VOLLZEIT_TERMS + SAP_TRAINING_TERMS + JUNIOR_TERMS[:10]
```

Downstream consumers of these constants (verified via `grep`):

- `nodes/scraper.py:114` uses `DEPRIORITIZE_TITLES` (unrelated, do not touch)
- `nodes/scraper.py:634` uses `PLATFORM_SEARCH_TERMS`
- `nodes/scraper.py:908` uses `TRAINEE_VOLLZEIT_TERMS`, `SAP_TRAINING_TERMS`, `JUNIOR_TERMS`
- **No other file** imports any of these (`grep` on the repo returns
  only `nodes/scraper.py`, `README.md`, `plans/README.md`)
- **No test file** touches them — safe to change without test updates.

Repo conventions: module-level constants use `SCREAMING_SNAKE_CASE`,
tier comments precede grouped items (`# Tier 1 — ...`), items are
one-per-line trailing-comma. Match this shape exactly.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Activate venv | `source venv/Scripts/activate` (bash on Windows) | prompt shows `(venv)` |
| Import smoke test | `python -c "from nodes.scraper import JUNIOR_TERMS, TRAINEE_VOLLZEIT_TERMS, PLATFORM_SEARCH_TERMS; print(len(JUNIOR_TERMS), len(TRAINEE_VOLLZEIT_TERMS), len(PLATFORM_SEARCH_TERMS))"` | prints three integers, no exception |
| Duplicate check | `python -c "from nodes.scraper import JUNIOR_TERMS, TRAINEE_VOLLZEIT_TERMS; a=JUNIOR_TERMS; b=TRAINEE_VOLLZEIT_TERMS; print('dupes_in_junior:', len(a)-len(set(a))); print('cross_dupes:', len(set(a) & set(b)))"` | both print `0` |
| SAP-absence check | `python -c "from nodes.scraper import SEARCH_TERMS; print([t for t in SEARCH_TERMS if 'sap' in t.lower() or 'abap' in t.lower() or 'dynamics' in t.lower()])"` | prints `[]` |
| Full test suite | `python -m pytest -q` | 86 passed / 3 xfailed / exit 0 (baseline still holds) |

## Scope

**In scope** (the only file to modify):

- `nodes/scraper.py` — replace three list constants (`JUNIOR_TERMS`,
  `SAP_TRAINING_TERMS`, `TRAINEE_VOLLZEIT_TERMS`), adjust the two derived
  lines below them (`SEARCH_TERMS`, `PLATFORM_SEARCH_TERMS`), and adjust
  the `ba_terms` line at 908.

**Out of scope** (do NOT touch):

- `DEPRIORITIZE_TITLES` (line 76) — separate filter mechanism, not search
  terms.
- `_JUNIOR_INDICATOR` / `_CONSULTANT_WORDS` regex (lines 89–93).
- The scoring rules and score caps in `nodes/analyzer.py` — the caps
  double-guard against SAP mismatches; leave them in place.
- `nodes/tracker.py`, `nodes/pipeline.py` — no dedup logic changes here.
- `README.md` — the "Search behavior is controlled in `nodes/scraper.py`"
  block already mentions the constants by name without listing items,
  so it stays accurate. Do NOT rewrite it.
- Tests — no test file references any of these lists (`grep` confirmed);
  no test changes required or expected.

## Git workflow

- Branch: `advisor/008-align-search-terms`
- One commit is fine (single file, coherent rewrite). Message: `Plan 008: align scraper search terms with CV, drop SAP/ERP/ABAP`
- Do NOT push or open a PR unless the operator instructs it.

## Steps

### Step 1: Rewrite `JUNIOR_TERMS`

Replace the entire `JUNIOR_TERMS = [...]` block at lines 201–268 with:

```python
JUNIOR_TERMS = [
    # Tier 1 — highest-recall German compounds (broadest CV match)
    "Junior Softwareentwickler",
    "Junior Software Engineer",
    "Junior Backend Entwickler",
    "Junior Backend Developer",
    "Junior Full Stack Entwickler",
    "Junior Full Stack Developer",
    # Tier 1 — language-specific matching the CV's primary stack
    "Junior Java Developer",
    "Junior Java Entwickler",
    "Junior Python Developer",
    "Junior Python Entwickler",
    # Tier 1 — framework-specific matching the CV's project stack
    "Junior Spring Boot Entwickler",
    "Junior Angular Entwickler",
    "Junior Vue Entwickler",
    "Junior React Entwickler",
    "Junior FastAPI Entwickler",
    # Tier 1 — AI/GenAI (Bachelorarbeit stack, actively growing category)
    "Junior AI Engineer",
    "AI Software Engineer",
    "Junior AI Application Engineer",
    # Tier 1 — DevOps / Cloud / SRE / Sysadmin entry
    # (profile.yaml career_narrative welcomes infra-adjacent roles)
    "Junior DevOps Engineer",
    "Junior Cloud Engineer",
    "Junior Platform Engineer",
    "Junior SRE",
    "Junior Site Reliability Engineer",
    "Junior Systemadministrator",
    "Junior IT Systemadministrator",
    "Junior Linux Administrator",
    # Tier 2 — QA/Test (candidate has direct Werkstudent QA experience)
    "Junior QA Engineer",
    "Junior Test Automation Engineer",
    "Junior Software Tester",
    # Tier 2 — Language / framework secondaries
    "Junior TypeScript Entwickler",
    "Junior Kotlin Entwickler",
    "Junior Webentwickler",
    "Junior Frontend Entwickler",
    # Tier 2 — Consulting / Trainee (kept for volume; consultant filter
    # in is_deprioritized already gates junior-vs-senior consultant hits)
    "Junior IT Consultant",
    "IT Trainee",
    "Junior Anwendungsentwickler",
    # Tier 3 — German-language entry qualifiers
    "Berufseinsteiger Entwickler",
    "Berufseinsteiger Softwareentwicklung",
    "Absolvent Informatik",
    "Quereinsteiger Softwareentwickler",
    "Junior Wirtschaftsinformatiker",
    "Junior Machine Learning Engineer",
    "Junior LLM Engineer",
    "Junior KI Engineer",
]
```

Note the intentional omissions vs the old list:
`Junior SAP Berater`, `Junior SAP Consultant`, `Junior ERP Consultant`,
`Junior Dynamics 365 Consultant`, `Junior ABAP Entwickler`,
`Junior Data Engineer`, `Junior Data Analyst`, `Junior Data Scientist`,
`Junior BI Developer`, `Junior Analytics Engineer`,
`Junior Generative AI Engineer`, `Junior NLP Engineer`, `Junior SDET`,
`Trainee IT Consulting`, `Trainee Softwareentwicklung`,
`Trainee Software Engineer`, `Trainee IT`, `Direkteinstieg IT Beratung`,
`Young Professional IT`, `Softwareentwickler Berufseinsteiger`,
`Junior Full Stack Entwickler` (2nd copy). Reasons: SAP/ERP/ABAP/
Dynamics don't match CV; data-heavy roles have no matching CV projects;
GenAI/NLP too specialized; SDET niche; Trainee/Direkteinstieg/Young
Professional variants already live in `TRAINEE_VOLLZEIT_TERMS`.

**Verify**: `python -c "from nodes.scraper import JUNIOR_TERMS; print(len(JUNIOR_TERMS), len(set(JUNIOR_TERMS)))"` → both integers equal (no duplicates), value ≈ 45.

### Step 2: Drop `SAP_TRAINING_TERMS`

Delete the entire `SAP_TRAINING_TERMS = [...]` block at lines 288–302,
including the comment above it (`# Used primarily for the Arbeitsagentur
API ...`). Replace with a single-line comment recording the removal so
future readers understand why the constant is gone:

```python
# SAP/ERP/ABAP search terms removed in plan 008 — CV has no SAP/ABAP signal
# and nodes/analyzer.py already caps SAP roles at 55. Re-add here if the
# operator's target profile changes.
```

**Verify**: `python -c "import nodes.scraper as s; print(hasattr(s, 'SAP_TRAINING_TERMS'))"` → `False`.

### Step 3: Update the derived `SEARCH_TERMS` line

`SEARCH_TERMS` (line 331) currently is:

```python
SEARCH_TERMS = TRAINEE_VOLLZEIT_TERMS + JUNIOR_TERMS + SAP_TRAINING_TERMS
```

Change it to drop the removed constant:

```python
SEARCH_TERMS = TRAINEE_VOLLZEIT_TERMS + JUNIOR_TERMS
```

**Verify**: `python -c "from nodes.scraper import SEARCH_TERMS; print(len(SEARCH_TERMS)); print([t for t in SEARCH_TERMS if 'sap' in t.lower()])"` → prints total length (≈ 65) and `[]`.

### Step 4: Update `PLATFORM_SEARCH_TERMS` slice

`PLATFORM_SEARCH_TERMS` (line 335) currently is:

```python
PLATFORM_SEARCH_TERMS = TRAINEE_VOLLZEIT_TERMS[:14] + JUNIOR_TERMS[:18]
```

The new `JUNIOR_TERMS` has 27 highly-CV-relevant items before the
Tier 2 boundary (see Step 1's tier comments). Bump the slice so the
platforms scrape the full Tier 1 block (0..26 inclusive) instead of
stopping mid-tier:

```python
# Tier 1 in the new JUNIOR_TERMS ends at index 26 inclusive — see plan 008.
PLATFORM_SEARCH_TERMS = TRAINEE_VOLLZEIT_TERMS[:14] + JUNIOR_TERMS[:27]
```

The `TRAINEE_VOLLZEIT_TERMS[:14]` slice is unchanged; we're not touching
that list at all in this plan.

**Verify**: `python -c "from nodes.scraper import PLATFORM_SEARCH_TERMS, JUNIOR_TERMS; print(len(PLATFORM_SEARCH_TERMS)); print('Junior Systemadministrator' in PLATFORM_SEARCH_TERMS)"` → prints `41` and `True`.

### Step 5: Update the Arbeitsagentur slice at line 908

Currently:

```python
def _run_arbeitsagentur(days_window: int = 1) -> tuple:
    # Lead with Trainee/Vollzeit (top priority), then SAP/Training, then top Juniors.
    ba_terms = TRAINEE_VOLLZEIT_TERMS + SAP_TRAINING_TERMS + JUNIOR_TERMS[:10]
```

`SAP_TRAINING_TERMS` no longer exists. Replace the block with:

```python
def _run_arbeitsagentur(days_window: int = 1) -> tuple:
    # Lead with Trainee/Vollzeit (top priority), then the top Junior terms.
    # SAP/ABAP terms removed in plan 008 — see comment near SAP_TRAINING_TERMS deletion.
    ba_terms = TRAINEE_VOLLZEIT_TERMS + JUNIOR_TERMS[:15]
```

Rationale for the `[:15]` slice: previously BA got 20 (trainee) + 11 (SAP)
+ 10 (junior) = 41 terms. Post-change with `:15` it gets 20 + 15 = 35
terms — slightly leaner (Arbeitsagentur's REST API is cheap so keeping
the volume reasonable is fine, but no need to backfill the exact old
count when the removed terms were low-yield).

**Verify**: `python -c "from nodes.scraper import _run_arbeitsagentur; import inspect; src=inspect.getsource(_run_arbeitsagentur); assert 'SAP_TRAINING_TERMS' not in src; assert 'JUNIOR_TERMS[:15]' in src; print('ok')"` → prints `ok`.

### Step 6: Full-suite regression check

Nothing in the test suite depends on these constants, but a module-level
`import` error would break the whole suite. Run pytest as a smoke test:

**Verify**: `python -m pytest -q` → `86 passed, 3 xfailed` (exact
baseline from plan 002 post-exec; if plan 007 also landed, it's
`88 passed, 3 xfailed`). Exit 0 either way. No new failures.

### Step 7: Update `plans/README.md`

Change plan 008's row from `TODO` to `DONE`. Add a one-line
post-exec note pointing at the commit SHA.

**Verify**: `git diff plans/README.md` shows only the status change and
note; no other rows edited.

## Test plan

No new tests. Rationale: these are static-data constants with no branch
logic to test. The verification commands in Steps 1–5 already assert:

- No duplicates within `JUNIOR_TERMS` (Step 1 verify)
- `SAP_TRAINING_TERMS` no longer exists as a module attribute (Step 2 verify)
- No SAP/ABAP/Dynamics substrings in `SEARCH_TERMS` (Step 3 verify)
- The new DevOps terms are in the platform slice (Step 4 verify)
- The `ba_terms` line no longer references `SAP_TRAINING_TERMS` (Step 5 verify)
- Module still imports cleanly and the pytest baseline still holds (Step 6)

If a "no forbidden substrings" regression test is desired for the
future, add it to a new `tests/test_search_terms.py` file — but that is
follow-up work, not part of this plan.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `python -c "from nodes.scraper import JUNIOR_TERMS, TRAINEE_VOLLZEIT_TERMS, PLATFORM_SEARCH_TERMS; print(len(JUNIOR_TERMS), len(TRAINEE_VOLLZEIT_TERMS), len(PLATFORM_SEARCH_TERMS))"` — prints three integers, no exception
- [ ] `python -c "from nodes.scraper import JUNIOR_TERMS; assert len(JUNIOR_TERMS) == len(set(JUNIOR_TERMS)); print('no dupes')"` — prints `no dupes`
- [ ] `python -c "from nodes.scraper import JUNIOR_TERMS, TRAINEE_VOLLZEIT_TERMS; assert not (set(JUNIOR_TERMS) & set(TRAINEE_VOLLZEIT_TERMS)); print('no cross dupes')"` — prints `no cross dupes`
- [ ] `python -c "from nodes.scraper import SEARCH_TERMS; assert not [t for t in SEARCH_TERMS if any(x in t.lower() for x in ('sap','abap','dynamics','erp consultant'))]; print('no sap/abap/dynamics/erp')"` — prints `no sap/abap/dynamics/erp`
- [ ] `python -c "import nodes.scraper as s; assert not hasattr(s, 'SAP_TRAINING_TERMS'); print('constant gone')"` — prints `constant gone`
- [ ] `python -c "from nodes.scraper import PLATFORM_SEARCH_TERMS; assert 'Junior Systemadministrator' in PLATFORM_SEARCH_TERMS; assert 'Junior Angular Entwickler' in PLATFORM_SEARCH_TERMS; assert 'Junior Spring Boot Entwickler' in PLATFORM_SEARCH_TERMS; print('devops+framework terms in platform slice')"` — prints the message
- [ ] `python -m pytest -q` exits 0 with the same or higher pass count as before, no new failures
- [ ] `git status --short` shows exactly `nodes/scraper.py` and `plans/README.md` modified — no other files
- [ ] `plans/README.md` row for plan 008 flipped to `DONE`

## STOP conditions

Stop and report back (do not improvise) if:

- Any excerpt in "Current state" doesn't match the live code — the file
  has drifted since 7d391d6.
- `PLATFORM_SEARCH_TERMS` after Step 4 has fewer than 40 or more than 45
  entries (a slicing error) — expected exactly `14 + 27 = 41`.
- `python -m pytest -q` reports a fresh failure in a test that was
  passing before this plan — the module-level rewrite broke an import
  path or downstream constant.
- `grep -n "SAP_TRAINING_TERMS" nodes/scraper.py` after Step 5 returns
  any hit — a reference was missed.
- The operator's CV or `config/profile.yaml` has been rewritten since
  2026-07-02 with a materially different skill profile (SAP/data
  suddenly added or Angular/Vue/React removed) — the whole rationale
  for these term choices needs re-verification.

## Maintenance notes

- **CV drift is the number-one reason to revisit this file.** If the
  operator picks up SAP contracts, adds a data-engineering project, or
  drops Angular from their stack, the tier assignments here go stale
  fast. Rule of thumb: any time `my_cv.txt` or `config/profile.yaml`
  gains a new top-line skill category, add at least one dedicated
  Junior/Trainee term for it and consider promoting it into Tier 1.
- **Watch `PLATFORM_SEARCH_TERMS` slice arithmetic.** The `[:27]` in
  Step 4 assumes the Tier 1 boundary in `JUNIOR_TERMS`. If tiers are
  reordered, the slice number MUST move — or the platforms will scrape
  a random mid-tier subset. A reviewer's mental model should be:
  "`PLATFORM_SEARCH_TERMS` = the front-loaded tier that fits in the
  600s/platform budget."
- **`SAP_TRAINING_TERMS` is intentionally missing, not forgotten.** The
  removed comment block in Step 2 is the tombstone. If someone re-adds
  SAP without also re-adding SAP-specific scoring rules in
  `nodes/analyzer.py`, the results will hit the score cap and count
  against the LLM quota. Add the term list *and* consider the analyzer
  cap together, or don't add either.
- **The three near-duplicate leaks from 2026-06-29** documented in plan
  007's Maintenance notes are independent of this change — search term
  selection doesn't affect dedup outcome, only volume.
- **Reviewer focus:** verify (a) no removed term secretly matches a
  real CV skill (e.g. `Junior Data Engineer` doesn't — the CV has
  Pandas/Streamlit but no data-engineering framing), (b) no added term
  overreaches (e.g. `Junior Spring Boot Entwickler` — is that a real
  German posting phrasing? confirm on `linkedin.com/jobs` before
  merging), (c) the platform-slice number matches the actual tier
  boundary in the new list.
