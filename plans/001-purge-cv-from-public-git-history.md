# Plan 001: Purge `my_cv.txt` from the public git history of this repo

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. This plan rewrites git history and force-pushes
> to a public remote — do not skip the confirmation step. When done, update
> the status row for this plan in `plans/README.md`.
>
> **Drift check (run first)**: `git log --all --oneline -- my_cv.txt`
> If the output is empty, `my_cv.txt` has already been purged — STOP and
> report.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: HIGH (rewrites history on a public remote)
- **Depends on**: none
- **Category**: security
- **Planned at**: commit `29244f6`, 2026-06-30

## Why this matters

`my_cv.txt` contains personal data (real name, location, employment history).
It is `.gitignore`d *now* but was committed in two commits (`a845c8d`,
`9648d22`) before it was added to `.gitignore`. The repository is **public**
on GitHub (`https://github.com/AbderrakibAmbari/job-agent`, verified
`"visibility":"public"` via the GitHub API). Anyone — including search
engines and automated PII scrapers — can fetch the file from the history at
those commit SHAs. Removing the working-tree copy did not remove it from
history.

After this plan: the CV is no longer reachable from any ref in the public
repo, and a clone of `main` does not contain the file in any historical
commit.

## Current state

- File still present in the working tree at `my_cv.txt` (read by `main.py:60`
  and `nodes/pipeline.py:27` at runtime — must remain on disk, just not in git).
- `.gitignore:7` already lists `my_cv.txt`.
- `git log --all --oneline -- my_cv.txt` currently returns:
  ```
  9648d22 Enhance job application pipeline with new features and improvements
  a845c8d Initial commit: LangGraph job application agent
  ```
- The remote is `https://github.com/AbderrakibAmbari/job-agent.git`,
  branch `main`. The user is `abderrakibambari`.
- No collaborators known on this repo — the operator works alone.

## Commands you will need

| Purpose                  | Command                                                          | Expected on success |
|--------------------------|------------------------------------------------------------------|---------------------|
| Confirm Python available | `python --version`                                               | exit 0, 3.11+       |
| Install git-filter-repo  | `python -m pip install --user git-filter-repo`                   | exit 0              |
| Check it installed       | `git filter-repo --version`                                      | exit 0, version >=2.38 |
| Local backup             | `git clone --mirror . ../job-agent-prepurge-backup.git`          | exit 0              |
| List CV refs             | `git log --all --oneline -- my_cv.txt`                           | (used for verification) |
| Purge file from history  | `git filter-repo --invert-paths --path my_cv.txt --force`        | exit 0              |
| Re-add remote (purge wipes it) | `git remote add origin https://github.com/AbderrakibAmbari/job-agent.git` | exit 0 |
| Force-push rewritten history | `git push --force origin main`                               | exit 0              |

`git filter-repo` is the maintainer-recommended replacement for the deprecated
`git filter-branch` (https://github.com/newren/git-filter-repo).

## Scope

**In scope**:
- All git objects/refs referencing `my_cv.txt` (removed by `git filter-repo`).
- The remote `origin/main` ref (force-pushed).

**Out of scope** (do NOT touch):
- The working-tree file `my_cv.txt` itself — the runtime depends on it.
  `git filter-repo` only touches history; the working file survives.
- Any other tracked file (no other PII files were identified).
- Any rebase/rewrite of unrelated commits.

## Git workflow

This plan IS the git workflow. No feature branch — operate on `main` directly.
The user has authorized the force-push by selecting this plan.

## Steps

### Step 1: Hard prerequisites and operator confirmation

Before running any destructive command:

1. Confirm the working tree is clean (or all changes are committed/stashed):
   ```
   git status --porcelain
   ```
   **Expected**: empty output. If non-empty, STOP and report — the operator
   has uncommitted work that history rewriting will collide with.

2. Confirm you are on `main`:
   ```
   git rev-parse --abbrev-ref HEAD
   ```
   **Expected**: `main`. If not, STOP and report.

3. Print a confirmation banner to stdout for the operator:
   ```
   This plan will REWRITE PUBLIC GIT HISTORY for github.com/AbderrakibAmbari/job-agent.
   It will:
     - run `git filter-repo --invert-paths --path my_cv.txt --force`
     - force-push the rewritten main to origin
   The old commits SHAs will become unreachable on the remote. A local mirror
   backup will be made first at ../job-agent-prepurge-backup.git.
   Anyone who has cloned the repo will need to re-clone.
   ```

**Verify**: `git status --porcelain` is empty AND `git rev-parse --abbrev-ref HEAD` prints `main`.

### Step 2: Local mirror backup

Make a defensive backup of the current repo (refs + objects) before any
rewrite, so the operation is recoverable if `filter-repo` mangles something
unexpected.

```
git clone --mirror . ../job-agent-prepurge-backup.git
```

**Verify**:
```
ls ../job-agent-prepurge-backup.git
```
→ contains `HEAD`, `refs/`, `packed-refs` (i.e. it's a bare mirror clone).

If this command fails (disk full, permission), STOP and report.

### Step 3: Install git-filter-repo

```
python -m pip install --user git-filter-repo
git filter-repo --version
```

**Verify**: `git filter-repo --version` prints a version `2.38` or higher and
exits 0.

### Step 4: Verify the file is reachable in history before purging

This is the "before" snapshot used to confirm the purge worked.

```
git log --all --oneline -- my_cv.txt
```

**Expected** (must match exactly, modulo the commit subjects which are
informational only):
```
9648d22 Enhance job application pipeline with new features and improvements
a845c8d Initial commit: LangGraph job application agent
```

If the output is empty, the file has already been purged — STOP and report.
If the output lists *different* commits than the two above, the history has
drifted since this plan was written — STOP and report.

### Step 5: Run the purge

`git filter-repo` requires a fresh-clone-style state to operate safely. It
will refuse if it detects you're in a non-bare clone with a remote — that's
the `--force` flag's purpose here, and is the documented usage for
purge-and-republish.

```
git filter-repo --invert-paths --path my_cv.txt --force
```

**Verify**: exit code 0 AND the file is gone from history:
```
git log --all --oneline -- my_cv.txt
```
→ empty output.

If `filter-repo` reports errors, do NOT proceed to force-push. STOP and
report. The mirror backup from Step 2 is your recovery path:
`git clone ../job-agent-prepurge-backup.git restored-repo`.

### Step 6: Re-add the origin remote

`git filter-repo` deliberately removes the `origin` remote after rewriting to
prevent accidental push to the original. Re-add it:

```
git remote add origin https://github.com/AbderrakibAmbari/job-agent.git
git remote -v
```

**Verify**: `git remote -v` shows the `origin` URL with both (fetch) and
(push) lines.

### Step 7: Force-push the rewritten history

```
git push --force origin main
```

**Verify**: command exits 0, and remote HEAD now matches local HEAD:
```
git fetch origin
git log -1 --format=%H
git log -1 --format=%H origin/main
```
→ both print the same SHA.

### Step 8: Post-purge verification on the remote

This step proves the public remote no longer serves the file. Use any HTTPS
client (the `curl` examples below assume the deleted blob hashes for the file
at each old commit — since we just rewrote, fetching the *old* commit SHA
directly should 404 because that object no longer exists on the rewritten
history):

```
curl -sI https://raw.githubusercontent.com/AbderrakibAmbari/job-agent/a845c8d/my_cv.txt
curl -sI https://raw.githubusercontent.com/AbderrakibAmbari/job-agent/9648d22/my_cv.txt
```

**Expected**: both return HTTP 404 (the old commits are no longer reachable
from any ref). If either returns 200, STOP and report — the force-push did
not take.

Also verify in the GitHub UI by visiting
`https://github.com/AbderrakibAmbari/job-agent/blob/main/my_cv.txt` →
should render "404 — This is not the web page you are looking for."

### Step 9: Confirm the working tree CV still exists

The runtime reads `my_cv.txt` at module load (`main.py:60`, `pipeline.py:27`).
Confirm it's still on disk and untouched:

```
ls -la my_cv.txt
head -1 my_cv.txt
```

**Expected**: file exists, first line is `Name: Ambari`.

### Step 10: Smoke-test the application still loads

The CV file is still on disk and the runtime should be unaffected.

```
python -c "from nodes.pipeline import run_pipeline; print('import OK')"
```

**Expected**: prints `import OK` with no errors. (Do not run the full
pipeline — it scrapes the web. The import alone exercises the file-load
paths in `main.py`/`pipeline.py` because they're at module scope.)

Actually — `main.py:60` reads `my_cv.txt` at module load. So:

```
python -c "import main"
```

**Expected**: no `FileNotFoundError`, no traceback.

## Done criteria

ALL must hold:

- [ ] `git log --all --oneline -- my_cv.txt` returns empty output (local).
- [ ] `curl -sI https://raw.githubusercontent.com/AbderrakibAmbari/job-agent/a845c8d/my_cv.txt` returns HTTP 404.
- [ ] `curl -sI https://raw.githubusercontent.com/AbderrakibAmbari/job-agent/9648d22/my_cv.txt` returns HTTP 404.
- [ ] `ls my_cv.txt` shows the file still present in the working tree.
- [ ] `python -c "import main"` exits 0 (CV still readable at runtime).
- [ ] `../job-agent-prepurge-backup.git` exists (the mirror backup).
- [ ] `plans/README.md` status row updated to DONE.

## STOP conditions

Stop and report (do not improvise) if:

- The drift check shows `my_cv.txt` listed in commits *other than* `a845c8d`
  and `9648d22` — additional commits would mean the file was re-added after
  this plan was written, and we'd be purging history the operator may not
  expect.
- `git status --porcelain` is non-empty in Step 1.
- The local mirror backup in Step 2 fails for any reason.
- `git filter-repo` errors out or reports objects it couldn't rewrite.
- The force-push in Step 7 fails (auth, branch protection, etc.) — do NOT
  retry with different args; report.
- The post-purge `raw.githubusercontent.com` check in Step 8 still returns
  200 — the cache hasn't flushed yet OR the push didn't take. Wait 60s and
  re-check once; if still 200, report.
- The operator's working-tree `my_cv.txt` is missing or empty at any point —
  abort immediately and restore from the mirror.

## Maintenance notes

For the human/agent who owns this code after the change lands:

- **GitHub's content cache**: GitHub may serve the old blob via `?blame=`
  and other endpoints for a few hours after force-push. The 404s in Step 8
  confirm the canonical paths are gone; if the operator finds a cached copy
  via search later, they can contact GitHub Support to invalidate it
  (https://docs.github.com/en/site-policy/content-removal-policies/github-private-information-removal-policy).
- **Forks / mirrors**: if anyone has forked this repo (visible at
  `https://github.com/AbderrakibAmbari/job-agent/network/members`), their
  forks still contain the file in *their* history. There is no way to purge
  forks; the operator can only request removal via the link above.
- **Consider rotating contact info** in the CV (email, phone) if those are
  there too — anything that was in the public file should be treated as
  leaked for the period it was visible. Take a look at the working-tree
  `my_cv.txt` and decide.
- **A future commit that re-adds `my_cv.txt`** will silently undo this plan.
  The `.gitignore` entry prevents accidental `git add`, but `git add -f
  my_cv.txt` would bypass it. Reviewers (or a `pre-commit` hook) should
  reject any diff that re-adds the file.
- After this lands, the local mirror backup in `../job-agent-prepurge-backup.git`
  still contains the CV. The operator should delete it once they're confident
  the purge succeeded (e.g. after a week of normal operation).
