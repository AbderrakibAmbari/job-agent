# Plan 025: Add GitHub Actions CI running `pytest -x` on push and PR

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**:
> `git diff --stat fb39d98..HEAD -- requirements.txt pytest.ini`
> If either file changed since this plan was written, re-verify the
> Python version and test command against the live files before proceeding.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none (independent of plan 024)
- **Category**: DX
- **Planned at**: commit `fb39d98`, 2026-07-11

## Why this matters

The repo has 307 tests that stay green locally, but nothing enforces they
stay green when code lands on `main`. That works today because there is
exactly one committer, but the whole `/improve` workflow you use — where
executor agents (often smaller models) run plans in isolated worktrees —
depends on some external observer verifying "did this actually pass tests
before merge". Right now that verification is manual and depends on the
committer remembering to run pytest.

A single GitHub Actions workflow (~30 lines of YAML) that runs
`pytest -x` on push and PR closes that loop:

- Every commit to `main` and every PR gets a red/green signal in GitHub.
- If a plan executor forgets to run tests locally, CI catches it before
  merge instead of after.
- Future contributors (even if that's only future-you) get the "does this
  branch pass tests" answer without setting up the venv locally.

The repo has no CI at all today (`.github/workflows/` does not exist).
Adding one workflow is the minimum useful thing; more sophisticated CI
(coverage upload, lint, typecheck, matrix over Python versions) can layer
on top if it ever becomes worth it. This plan is deliberately scoped to
the minimum.

## Current state

Facts the executor needs, inlined:

- **Python version**: `README.md:27` says "Python 3.11+". Match `3.11`
  in CI to be conservative — the local dev version.
- **Test command**: `pytest.ini` sets `testpaths = tests` and
  `addopts = -ra --tb=short`. The full command used locally is:
  `"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -m pytest -x`
  On Linux (the Actions runner) this becomes:
  `python -m pytest -x`
- **Dependencies**: `requirements.txt` at repo root, 78 pinned lines.
  Install with `pip install -r requirements.txt`.
- **Playwright browsers are NOT needed for `pytest -x`**: the tests are
  pure-function tests (`test_dashboard_helpers.py`, `test_analyzer_filters.py`,
  `test_scraper_helpers.py`, `test_tracker_*.py`, etc. — 14 test files
  in `tests/`). None start a browser. Verify locally before writing the
  workflow: `grep -rn "sync_playwright\|async_playwright" tests/` → zero
  matches. If any hit appears, STOP: the assumption "no browser needed
  in CI" is wrong for this repo and the plan needs to add
  `playwright install chromium` to CI.
- **No secrets required in CI**: the pure-function tests do not call
  Anthropic or Gmail. Verify: `grep -rn "ANTHROPIC_API_KEY\|GMAIL" tests/`
  → zero matches. If a hit appears, STOP.
- **`.github/` directory does not exist**: `test -d .github && echo present || echo missing` → `missing`.

### Repo layout signal for the workflow file

The workflow lives at `.github/workflows/ci.yml` (single canonical
location; GitHub Actions requires exactly that path).

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Local test parity | `"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -m pytest -x` | `307 passed` |
| YAML syntax check | `"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml', encoding='utf-8'))"` | exit 0, no traceback |
| Playwright-in-tests check | `grep -rn "sync_playwright\|async_playwright" tests/` | zero matches |
| Secret-in-tests check | `grep -rn "ANTHROPIC_API_KEY\|GMAIL" tests/` | zero matches |
| Tracked-file audit | `git status --short` | shows only `.github/workflows/ci.yml` created + `plans/README.md` updated |

## Scope

**In scope**:

- Create: `.github/workflows/ci.yml`
- Edit: `plans/README.md` (status row)

**Out of scope** (do NOT touch):

- `requirements.txt` — do not modify pinned versions.
- `pytest.ini` — do not change test discovery or options.
- Any Python source or test file — this plan is CI infrastructure only.
- Do NOT add lint / typecheck / coverage jobs — they can layer on later
  as separate plans. Adding them here bloats scope and slows the first
  landing.
- Do NOT install Playwright browsers in CI unless the STOP condition on
  playwright-in-tests triggers.

## Git workflow

- Branch: `advisor/025-github-actions-ci`
- Single commit is fine.
- Commit style: conventional commits (see `git log --oneline -20`).
  Suggested subject: `ci: add GitHub Actions workflow running pytest -x on push/PR`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Verify assumptions before writing YAML

Run these read-only checks:

```bash
"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -m pytest -x    # → 307 passed
grep -rn "sync_playwright\|async_playwright" tests/                          # → zero
grep -rn "ANTHROPIC_API_KEY\|GMAIL" tests/                                   # → zero
test -d .github && echo present || echo missing                              # → missing
```

If any expectation fails, STOP and report — the plan is written on those
assumptions.

### Step 2: Create `.github/workflows/ci.yml`

Create the directory tree if it does not exist. Write the file with this
exact content (Unix line endings; YAML is whitespace-sensitive — use
spaces, not tabs):

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'
          cache-dependency-path: 'requirements.txt'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Run tests
        run: python -m pytest -x
```

Notes on the exact shape:

- `on.push.branches: [main]` — trigger only on the branch the operator
  actually merges to. Do not add `[main, develop, feature/**]` — this
  repo has no such branches.
- `on.pull_request.branches: [main]` — every PR targeting main gets a
  check.
- `cache: 'pip'` with `cache-dependency-path: 'requirements.txt'` —
  `setup-python@v5` handles pip caching keyed by requirements.txt hash,
  so subsequent runs skip re-downloading the 78 pinned packages.
- `python -m pytest -x` matches local behavior exactly. No coverage
  flag, no `-v`, no `--tb=long` — those change output shape without
  changing pass/fail.

### Step 3: Verify the YAML parses

Run the syntax check:

```
"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml', encoding='utf-8'))"
```

Expected: exit 0, no output. If a `yaml.YAMLError` is raised, the YAML
is malformed — most likely a tab/space mixup or a mis-indented `steps:`
block. Fix and re-run before proceeding.

### Step 4: Confirm the file is discoverable

```
ls -la .github/workflows/ci.yml
git status --short
```

Expected `git status`:
```
?? .github/
```
(untracked directory containing the new file).

### Step 5: Run the local test suite one more time

Sanity check that nothing changed under the hood:

```
"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -m pytest -x
```

Expected: `307 passed`.

### Step 6: Update `plans/README.md`

Add a new row after the plan 024 row:

```
| 025  | Add GitHub Actions CI running pytest -x on push/PR                   | P2       | S      | LOW  | —          | DONE — .github/workflows/ci.yml added; runs pytest -x on push to main and PRs targeting main; Python 3.11 with setup-python pip cache. |
```

## Test plan

No new pytest tests. The workflow is the test — its correctness is
verified by:

1. The syntax check in Step 3.
2. GitHub actually running it after the branch is pushed (out of scope
   for this plan — the operator does the push).

If the operator does eventually push the branch and observes the workflow
fail on GitHub, that failure and its root cause are follow-up work, not
part of this plan's done criteria.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `.github/workflows/ci.yml` exists at the exact path
- [ ] `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml', encoding='utf-8'))"` exits 0
- [ ] The file contains: `on:` block with both `push` and `pull_request` triggers scoped to `main`, a `test` job on `ubuntu-latest`, `python-version: '3.11'`, `pip install -r requirements.txt`, and `python -m pytest -x`
- [ ] `pytest -x` still passes locally: `307 passed`
- [ ] `git status --short` shows only the new workflow file (plus the
      `plans/README.md` edit)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back if:

- `grep -rn "sync_playwright\|async_playwright" tests/` returns matches
  — a test is starting Playwright, which this plan's CI setup does not
  support. Report the file(s); a revised plan will need to add
  `playwright install chromium` to the workflow.
- `grep -rn "ANTHROPIC_API_KEY\|GMAIL" tests/` returns matches — a test
  requires secrets, which this plan does not provision. Report the
  file(s); a revised plan will need repo secrets configured before CI
  can pass.
- `pytest -x` locally does not report `307 passed` — the test count has
  drifted and the "Done criteria" number is wrong. Stop and update the
  expected count in the plan before proceeding.
- `requirements.txt` has drifted in a way that means `pip install -r
  requirements.txt` on a clean Ubuntu runner would fail (e.g. a Windows-
  only package pin). Do NOT try to remediate — report the specific
  package(s) that would fail.

## Maintenance notes

- The workflow uses `actions/checkout@v4` and `actions/setup-python@v5`.
  When GitHub Actions deprecates one of these (~2 years out), a small
  bump is expected. Watch the deprecation warnings on run pages.
- If a future plan adds Playwright to the test suite (currently no test
  imports it), add `- run: playwright install chromium` after the pip
  install step. Expect ~40 s of extra CI time on cold cache.
- If secrets are ever required, add them via `Settings → Secrets and
  variables → Actions` in the GitHub UI, then reference as
  `env: ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}` on the
  `Run tests` step. Never commit real values to `ci.yml`.
- This workflow is the prerequisite for plan 027 (dashboard split).
  Landing 027 without CI in place means a 1362-line refactor has no
  external safety net beyond the operator's local pytest run.
