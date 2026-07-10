# Plan 011: Replace LLM `job_category` with a deterministic regex taxonomy

> **Executor instructions**: Follow this plan step by step. Run every
> verification command. Stop on any STOP condition — do not improvise.
> Update the status row in `plans/README.md` when done.
>
> **Drift check (run first)**: `git diff --stat 884bbbd..HEAD -- nodes/analyzer.py nodes/tracker.py tests/test_analyzer_filters.py`
> If any file changed, compare the "Current state" excerpts against
> live code before proceeding.
>
> **Re-affirmation note (2026-07-10, `884bbbd`)**: this plan was
> originally written at `5bed640` on 2026-07-02. Verified against
> live code at `884bbbd`: line numbers `_apply_experience_cap` (72),
> SAP-cap read (98), LLM assignment (237), LLM-crash fallback (263)
> still match. The "third fallback" at line 348 in the original plan
> is now at line 353 (minor drift — same behavior). Baseline test
> count is 178 → target after this plan is ≥ 178 + ~33 new = 211
> passed.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: `plans/002-pure-function-test-baseline.md` (uses its
  pytest infra and the existing SAP-cap tests at
  `tests/test_analyzer_filters.py:105-135` that read `job_category`)
- **Category**: direction (feature — filter quality)
- **Planned at**: commit `5bed640`, 2026-07-02 (re-affirmed at `884bbbd`, 2026-07-10)

## Why this matters

Claude Haiku is currently asked to emit `job_category` as one of 11
labels (`AI/ML`, `Backend`, `Frontend`, `FullStack`, `DevOps/Cloud`,
`QA/Testing`, `SAP/ERP`, `ITConsulting`, `DataEngineering`, `Mobile`,
`Other`). In `data/applications.db` on 2026-07-02, the distribution
across 777 matched rows is:

| Category | Rows |
|---|---|
| Other | 367 (47%) |
| Backend | 132 |
| FullStack | 87 |
| AI/ML | 79 |
| DevOps/Cloud | 32 |
| everything else | < 30 each |

A category filter where 47% of everything lands in "Other" is a filter
you can't use. Manual inspection of samples shows the misses are boring
and predictable — a job called "Backend Java Developer" gets tagged
Other; "React Frontend Engineer" gets tagged Other; "Kubernetes DevOps
Engineer" gets tagged Other. The LLM has bigger things to think about
(scoring), and category is a stylistic aftertaught in the JSON schema.

Only ONE place in the codebase actually reads `job_category`:
`_apply_experience_cap` at `nodes/analyzer.py:98-102`, where it caps SAP
roles at 55. Everything else stores or displays it. So the ceiling for
harm is small — even a category that's completely wrong on rare
edge-cases doesn't degrade scoring outside SAP.

Replacing the LLM's guess with a regex over `title + description` is:

- deterministic (same title always gets the same category)
- reviewable (the operator can inspect and tune the rules)
- almost free (regex compiled once at module load, ran once per job)
- **compatible** with the existing SAP-cap logic (`SAP/ERP` is one of
  the labels the regex emits)

Do NOT remove the LLM's `job_category` field from the prompt in this
plan — that risks silently reducing prompt-cache reuse. Just ignore
what the LLM returns for that field and overwrite with the regex
result. Prompt cleanup can be a follow-up plan when confidence is
higher.

## Current state

Relevant files:

- `nodes/analyzer.py` — reads (line 98) and writes (lines 237, 263, 348)
  `job_category`. Only reader is `_apply_experience_cap` for the SAP
  cap.
- `nodes/tracker.py:91,200,218,324` — schema column + INSERT / update
  wiring. Column definition: `job_category TEXT DEFAULT 'Other'`.
- `tests/test_analyzer_filters.py:105-135` — SAP-cap tests exercising
  `job_category="SAP/ERP"` and `"Other"`. These MUST continue to pass.

Current relevant code:

```python
# nodes/analyzer.py:98-102 (only reader of job_category)
    category = job.get("job_category", "")
    if category == "SAP/ERP" and not _TRAINEE_PROGRAM.search(title):
        if _SAP_TITLE.search(title) and job["score"] > 55:
            job["score"] = 55
            job.setdefault("missing", []).insert(0, "SAP/ERP role — no prior SAP experience, score capped at 55")
```

```python
# nodes/analyzer.py:237 — LLM's guess is stored
        job["job_category"]   = result.get("job_category", "Other")
```

```python
# nodes/analyzer.py:263 (LLM crash fallback) and :348 (other fallback)
        job["job_category"]   = "Other"
```

Repo conventions:
- Module-level `re.compile()` with `re.IGNORECASE`, alphabetical
  proximity to related regexes.
- Match "junior" cascade shape at analyzer.py:42-66 — one regex per
  concept, referenced by name.
- Pure functions live above the classes/tests that use them; tests in
  `tests/test_analyzer_filters.py` use `pytest.parametrize` for
  boundary sweeps.

## Commands you will need

| Purpose | Command | Expected |
|---------|---------|---|
| Activate venv | `source venv/Scripts/activate` | prompt `(venv)` |
| Sanity-check taxonomy | see Step 1 verify block | prints correct label |
| Run analyzer tests | `venv/Scripts/python.exe -m pytest tests/test_analyzer_filters.py -v` | all pass |
| Full suite | `venv/Scripts/python.exe -m pytest -q` | 178 passed baseline → ~211 passed after this plan |

## Scope

**In scope**:

- `nodes/analyzer.py` — add a `_infer_category(title, description)`
  helper + a `_CATEGORY_PATTERNS` mapping. Call it from `score_job` to
  overwrite whatever the LLM returned.
- `tests/test_analyzer_filters.py` — add parametrized coverage for the
  taxonomy.
- `plans/README.md` — flip status row.

**Out of scope** (do NOT touch):

- The `_SCORING_RULES` prompt string in `nodes/analyzer.py:107-176`.
  Leave the LLM `job_category` field in the JSON schema. It costs 1
  cached token and removing it invalidates the prompt cache.
- `nodes/tracker.py` — schema column, INSERT wiring, and DEFAULT all
  stay. Data flows the same way; only the *source* of the value
  changes (from `result.get(...)` to `_infer_category(...)`).
- `dashboard.py` — the "Other" bucket may become smaller, which will
  make the existing category filter more useful. No dashboard code
  changes needed.
- Historical rows in `matched_jobs` — do NOT try to re-tag
  retroactively. The new tagging is forward-looking.
- The SAP cap threshold (55) — leave it.
- `_JUNIOR_KEYWORDS`, `_VOLLZEIT_OR_ENTRY`, `_EXPERIENCE_HARD`,
  `_SAP_TITLE`, `_TRAINEE_PROGRAM`, `_WERKSTUDENT_TITLE` — these regexes
  are for the scoring cap logic, not category tagging. Do not
  refactor them.

## Git workflow

- Branch: `advisor/011-regex-job-category`
- One commit is fine.
- Commit message: `Plan 011: overwrite LLM job_category with regex taxonomy`
- Do NOT push or open a PR unless instructed.

## Steps

### Step 1: Add the taxonomy regexes and helper

Insert immediately above `_apply_experience_cap` (i.e. before line 72 of
`nodes/analyzer.py`, after the existing pre-compiled regex block):

```python
# ── Category taxonomy ─────────────────────────────────────────────
# Ordered dict — first match wins. Patterns check title first, then
# description[:400] as a fallback. See _infer_category().
#
# Order matters: SAP is checked before Backend so an "SAP ABAP
# Developer" doesn't get tagged Backend just because ABAP is a
# programming language. DevOps/Cloud is checked before Backend so
# "Kubernetes Engineer" isn't tagged Backend on the strength of
# "backend infrastructure" mentions.
_CATEGORY_PATTERNS = [
    ("SAP/ERP",         re.compile(r"\b(sap|abap|s/4hana|s4hana|hana|salesforce|erp|dynamics\s*365|netsuite|oracle\s*ebs)\b", re.IGNORECASE)),
    ("DevOps/Cloud",    re.compile(r"\b(devops|sre|site\s+reliability|kubernetes|k8s|terraform|ansible|aws|azure(?!\s*devops)|gcp|google\s+cloud|cloud\s+engineer|platform\s+engineer|infrastructure\s+engineer|linux\s+admin|systemadministrator|sysadmin|it-administrator)\b", re.IGNORECASE)),
    ("DataEngineering", re.compile(r"\b(data\s+engineer|dateningenieur|etl|airflow|dbt|snowflake|databricks|spark|kafka|data\s+pipeline|bigquery|redshift)\b", re.IGNORECASE)),
    ("AI/ML",           re.compile(r"\b(ai|artificial\s+intelligence|machine\s+learning|ml\s+engineer|data\s+scientist|nlp|computer\s+vision|deep\s+learning|llm|generative\s+ai|tensorflow|pytorch|hugging\s*face|langchain|prompt\s+engineer)\b", re.IGNORECASE)),
    ("QA/Testing",      re.compile(r"\b(qa\s+engineer|quality\s+assurance|test\s+engineer|test\s+automation|sdet|selenium|cypress|playwright\s+tester|manual\s+tester|softwaretester)\b", re.IGNORECASE)),
    ("Mobile",          re.compile(r"\b(android|ios|swift|kotlin\s+android|flutter|react\s+native|mobile\s+(developer|engineer)|iphone|jetpack\s+compose)\b", re.IGNORECASE)),
    ("ITConsulting",    re.compile(r"\b(it\s*consultant|it\s*berater|technology\s+consultant|solution\s+architect|solutions\s+architect|integration\s+consultant)\b", re.IGNORECASE)),
    ("FullStack",       re.compile(r"\b(full[-\s]?stack|fullstack|full[-\s]?stack\s+(developer|engineer))\b", re.IGNORECASE)),
    # Frontend before Backend so a "React/Node full-stack" not matched by
    # the FullStack rule above (spelling variants) gets Frontend if only
    # frontend markers dominate.
    ("Frontend",        re.compile(r"\b(frontend|front[-\s]end|react(?!\s*native)|angular|vue(?:\.?js|\s*3)?|svelte|next\.?js|nuxt|typescript\s+developer|ui\s+engineer|ui\s+developer|webentwickler\s+frontend)\b", re.IGNORECASE)),
    ("Backend",         re.compile(r"\b(backend|back[-\s]end|java\s+developer|kotlin\s+developer|spring\s+boot|node\.?js|nodejs|python\s+developer|fastapi|django|flask|go(?:lang)?\s+developer|c\#\s+developer|\.net\s+developer|rest\s+api|graphql|api\s+entwickler|softwareentwickler\s+backend)\b", re.IGNORECASE)),
]


def _infer_category(title: str, description: str = "") -> str:
    """Deterministic category tag from title + first 400 chars of description.

    First matching pattern wins. Returns 'Other' if nothing matches.
    Pure function — safe to unit-test independently of the LLM path.
    """
    haystack = f"{title or ''} {(description or '')[:400]}"
    for label, pattern in _CATEGORY_PATTERNS:
        if pattern.search(haystack):
            return label
    return "Other"
```

**Verify**:

```bash
venv/Scripts/python.exe -c "
from nodes.analyzer import _infer_category
cases = [
    ('Junior Backend Java Developer (m/w/d)', ''),
    ('React Frontend Engineer', ''),
    ('Kubernetes DevOps Engineer', ''),
    ('SAP ABAP Consultant', ''),
    ('Software Engineer', 'Wir entwickeln mit Java Spring Boot'),
    ('Trainee Programme', 'Rotational programme'),
    ('Full Stack Web Developer', ''),
    ('Machine Learning Engineer', ''),
    ('Data Engineer', ''),
    ('Software Tester', ''),
    ('Android Developer', ''),
    ('IT Consultant', ''),
]
for title, desc in cases:
    print(f'{_infer_category(title, desc):15}  <-  {title}')
"
```

Expected output (in order): `Backend`, `Frontend`, `DevOps/Cloud`,
`SAP/ERP`, `Backend`, `Other`, `FullStack`, `AI/ML`, `DataEngineering`,
`QA/Testing`, `Mobile`, `ITConsulting`.

If `Trainee Programme` gets tagged as anything other than `Other`,
STOP — a pattern is over-matching. (Trainee programmes are deliberately
untagged because their real category depends on the rotation.)

### Step 2: Wire the helper into `score_job`

Edit `nodes/analyzer.py:237` — after the LLM successfully returns, keep
the LLM assignment for now but immediately overwrite with the regex
result:

```python
        # LLM's own guess is unreliable (47% "Other" in prod). Overwrite with
        # deterministic regex classifier. Plan 011.
        job["job_category"]   = _infer_category(
            job.get("title", ""),
            job.get("description", ""),
        )
```

Replace the original line (the `result.get("job_category", "Other")`
one) — don't stack them.

Also edit line 263 (the LLM-scoring-failed branch) — even when scoring
fails, we still have a title, so we can still classify:

```python
        job["job_category"]   = _infer_category(
            job.get("title", ""),
            job.get("description", ""),
        )
```

Check whether analyzer.py:348 exists (there's a third fallback). If it
sets `job["job_category"] = "Other"`, replace it with the same
`_infer_category(...)` call for consistency. If line 348 no longer
exists after the drift check, skip it and note that in your report.

**Verify**:

```bash
venv/Scripts/python.exe -c "
from nodes.analyzer import _infer_category
# Simulate what score_job would do without calling Claude:
job = {'title': 'Junior Backend Java Developer', 'description': 'Wir suchen einen Junior Java Developer mit Spring Boot.'}
job['job_category'] = _infer_category(job.get('title',''), job.get('description',''))
assert job['job_category'] == 'Backend', job['job_category']
print('OK')
"
```

Expected: `OK`.

### Step 3: Preserve the SAP cap behavior

The one existing consumer of `job_category` is the SAP cap at
`_apply_experience_cap` lines 98-102. It reads `SAP/ERP`. The taxonomy
in Step 1 returns exactly `SAP/ERP` for SAP roles, so this should Just
Work. But verify explicitly:

```bash
venv/Scripts/python.exe -m pytest tests/test_analyzer_filters.py -v -k "sap"
```

Expected: all three SAP-cap tests (see `tests/test_analyzer_filters.py:105-135`) pass unchanged.

If any SAP test now fails, either the taxonomy tags `SAP Consultant`
as something other than `SAP/ERP` (STOP and fix the regex), or the
tests hardcode `job_category` in their input dict (which they do —
the tests pre-set `job_category` and then call `_apply_experience_cap`
directly, bypassing `_infer_category`). Either way, verify the tests
still exercise the intended path.

### Step 4: Add taxonomy regression tests

Append to `tests/test_analyzer_filters.py` (below the last existing
test):

```python
# ---------- _infer_category (Plan 011) ----------

from nodes.analyzer import _infer_category


@pytest.mark.parametrize("title,desc,expected", [
    ("Junior Backend Java Developer (m/w/d)", "", "Backend"),
    ("Softwareentwickler Backend", "Java Spring Boot Team", "Backend"),
    ("React Frontend Engineer", "", "Frontend"),
    ("Angular Developer", "", "Frontend"),
    ("Vue.js Developer", "", "Frontend"),
    ("Full Stack Web Developer", "", "FullStack"),
    ("Fullstack Engineer", "", "FullStack"),
    ("Kubernetes DevOps Engineer", "", "DevOps/Cloud"),
    ("SRE Engineer", "", "DevOps/Cloud"),
    ("Cloud Platform Engineer AWS", "", "DevOps/Cloud"),
    ("Linux Systemadministrator", "", "DevOps/Cloud"),
    ("IT-Administrator", "", "DevOps/Cloud"),
    ("Data Engineer", "", "DataEngineering"),
    ("ETL Developer", "Airflow, dbt", "DataEngineering"),
    ("Machine Learning Engineer", "", "AI/ML"),
    ("Data Scientist", "NLP models", "AI/ML"),
    ("Prompt Engineer", "", "AI/ML"),
    ("SAP ABAP Consultant", "", "SAP/ERP"),
    ("Salesforce Developer", "", "SAP/ERP"),
    ("Software Tester", "", "QA/Testing"),
    ("Test Automation Engineer", "Cypress", "QA/Testing"),
    ("Android Developer", "", "Mobile"),
    ("iOS Engineer Swift", "", "Mobile"),
    ("Flutter Mobile Developer", "", "Mobile"),
    ("IT Consultant", "SAP integration", "SAP/ERP"),  # SAP wins over Consulting
    ("IT-Berater", "", "ITConsulting"),
    ("Solution Architect", "", "ITConsulting"),
    ("Trainee Programme Software", "General rotation across teams", "Other"),
    ("Werkstudent Marketing", "", "Other"),
    ("Praktikum Verwaltung", "", "Other"),
    ("Software Engineer", "", "Other"),  # too generic without further signal
])
def test_infer_category(title, desc, expected):
    assert _infer_category(title, desc) == expected


def test_infer_category_empty_input_returns_other():
    assert _infer_category("", "") == "Other"
    assert _infer_category(None, None) == "Other"


def test_infer_category_description_fallback_when_title_generic():
    # Generic title, but description mentions Spring Boot — should classify Backend
    assert _infer_category("Software Engineer", "You'll write Java code with Spring Boot") == "Backend"


def test_infer_category_only_reads_first_400_chars_of_description():
    # Backend keyword after char 500 should NOT match
    filler = "a" * 500
    desc = filler + " Spring Boot"
    assert _infer_category("Software Engineer", desc) == "Other"
```

**Verify**: `venv/Scripts/python.exe -m pytest tests/test_analyzer_filters.py -v -k "infer_category"` → all pass, 0 xfailed, 0 failed.

### Step 5: Confirm no other regressions

Run the full suite:

```bash
venv/Scripts/python.exe -m pytest -q
```

Expected: total passed = 178 baseline + (new parametrize cases from Step 4)
= ~211. 0 xfailed. 0 failed. Exit 0.

If any pre-existing test fails, do NOT skip or xfail it — investigate.
The most likely culprit is a test that expects a specific LLM-set
`job_category` in a fixture. If found, update the fixture to the
taxonomy's output (which is deterministic), not the LLM's guess.

### Step 6: Update `plans/README.md`

Flip plan 011's status row to `DONE` with a one-line post-exec note
(commit SHA + test counts).

## Test plan

- **New tests** in `tests/test_analyzer_filters.py`:
  - `test_infer_category` (parametrized, 30+ cases) — every category
    label represented at least twice.
  - `test_infer_category_empty_input_returns_other`
  - `test_infer_category_description_fallback_when_title_generic`
  - `test_infer_category_only_reads_first_400_chars_of_description`
- **SAP cap tests unchanged** — they pre-set `job_category` in the
  test fixture, so they exercise `_apply_experience_cap` directly and
  aren't affected by the new `_infer_category` call.
- **Verification**: full suite green, 178 baseline + new-cases passed
  (≈ 211 total).

## Done criteria

ALL must hold:

- [ ] `_CATEGORY_PATTERNS` list and `_infer_category` function added to
      `nodes/analyzer.py` above `_apply_experience_cap`.
- [ ] `score_job` calls `_infer_category` immediately after the LLM
      returns (line 237 area) AND in the LLM-crash fallback (line 263
      area).
- [ ] `tests/test_analyzer_filters.py` has 30+ new parametrized cases
      + 3 additional non-parametrized cases, all green.
- [ ] `venv/Scripts/python.exe -m pytest -q` → 178 baseline + new-cases
      passed (≈ 211 total), 0 xfailed, 0 failed, exit 0.
- [ ] The three existing SAP-cap tests still pass with no changes.
- [ ] Regex sanity check from Step 1 verify block emits the expected
      labels in order.
- [ ] `plans/README.md` row for plan 011 flipped to `DONE`.
- [ ] `git diff --stat` shows only `nodes/analyzer.py`,
      `tests/test_analyzer_filters.py`, `plans/README.md` modified.

## STOP conditions

Stop and report if:

- `_SCORING_RULES` string, `_call_llm` retry decorator, or the
  `_apply_experience_cap` function has drifted from the excerpts above.
- Any of the SAP cap tests at lines 105-135 fails after your changes.
- The Step 1 verification sanity-check emits `Trainee Programme` as
  anything other than `Other`. Trainee tagging is a semantic decision
  we're not making here.
- You find yourself removing `job_category` from the LLM's JSON schema
  or the `_SCORING_RULES` prompt. Don't. The plan says leave it. The
  prompt is cached — mutating it silently invalidates the cache and
  raises Anthropic spend.
- You find yourself editing `nodes/tracker.py` or `dashboard.py`. Not
  in scope; the schema and UI are already ready.

## Maintenance notes

- **Order matters and is documented in the code comment.** If the
  operator wants to add a new category (say, `Embedded` for
  microcontroller / firmware roles), decide where in the ordered list
  the new pattern goes — before or after Backend? — before checking
  it in. Silent over-matching from a mis-ordered add is the main
  failure mode.
- **The LLM's `job_category` field lingers.** The prompt still asks
  for it. That's on purpose — Anthropic prompt caching keys on the
  system-message prefix; mutating the prompt to remove one field
  invalidates the cache and doubles input token cost until it
  refills. Future cleanup: a follow-up plan can drop the field from
  the prompt AND from `job.get("job_category", ...)` in the LLM-fail
  branch, once the operator confirms the taxonomy is stable enough to
  trust.
- **Distribution health-check.** After a week of runs, query:
  ```sql
  SELECT job_category, COUNT(*) FROM matched_jobs
  WHERE date_found >= date('now', '-7 days')
  GROUP BY job_category ORDER BY 2 DESC;
  ```
  If "Other" is still > 25% of new rows, sample 10 of them, find the
  common vocabulary, and add patterns. If any category is > 50%, a
  pattern is over-matching and needs word-boundary tightening.
- **Reviewer focus:** verify the ordered list's first-match-wins
  discipline. In particular, `SAP/ERP` before `Backend` so ABAP jobs
  get tagged SAP not Backend; `DevOps/Cloud` before `Backend` so
  "backend infrastructure" mentions in a K8s job don't tag Backend;
  `FullStack` before `Frontend`/`Backend` so mixed roles get the
  right label. If someone re-orders these without adjusting tests,
  the tests fail loudly — that's the safety net.
