# Plan 016 — One-shot dedup of applications.db

**Planned at commit**: `59b4be3` (main)
**Category**: Data cleanup (one-shot, not a recurring code change)
**Effort**: S
**Risk**: LOW (idempotent SQL, backup taken first, runs against a worktree copy)
**Dependencies**: none

## Why this matters

The DB has:
- 1 exact-URL duplicate in `applications` (139 rows) — same XING URL, two rows
- 24 extra rows in `not_matched_jobs` (2945 rows) across ~10 (title, company) groups — LinkedIn URLs vary slightly between daily scrapes (tracking params / encoding), so the UNIQUE `job_url` index misses them.
- `matched_jobs` (777 rows) is already clean.

Root-cause fix (URL normalization + UNIQUE constraint on `applications.job_url`) is deferred to a future plan. This plan does only the one-shot cleanup.

## Environment

- Windows 11, bash shell
- Python: `"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe"`
- You are running inside a git worktree at `.claude/worktrees/agent-<id>/`
- The worktree already has a copy of the real DB at `data/applications.db` (I pre-populated it — 139/777/2945 rows). If it's missing, STOP and report.

## Baseline verification (do this first)

```bash
"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -c "
import sqlite3
con = sqlite3.connect('data/applications.db')
cur = con.cursor()
for t in ('applications', 'matched_jobs', 'not_matched_jobs'):
    n = cur.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
    print(f'{t}: {n}')
"
```

**Expected exactly:**
```
applications: 139
matched_jobs: 777
not_matched_jobs: 2945
```

If any count differs, STOP — the worktree DB isn't the right copy.

## Steps

### Step 1 — Backup

```bash
cp data/applications.db data/applications.db.bak
ls -la data/applications.db.bak
```

Confirm the backup exists and is the same size as `data/applications.db`.

### Step 2 — Dedup `applications` (drop id=5)

Verify the two duplicate rows exist first:
```bash
"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -c "
import sqlite3
con = sqlite3.connect('data/applications.db')
con.row_factory = sqlite3.Row
cur = con.cursor()
for r in cur.execute(\"SELECT id, company, job_title, date_applied FROM applications WHERE id IN (5, 11)\"):
    print(dict(r))
"
```

Expected:
- `id=5`: company='Unknown', date_applied='2026-04-03'
- `id=11`: company='etalytics GmbH', date_applied='2026-04-16'

If `id=5` doesn't have company='Unknown' or `id=11` doesn't have company='etalytics GmbH', **STOP** — the DB has drifted from the audit; report back so keeper selection can be redone.

Then delete:
```bash
"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -c "
import sqlite3
con = sqlite3.connect('data/applications.db')
cur = con.cursor()
cur.execute('DELETE FROM applications WHERE id = 5')
print('deleted:', cur.rowcount)
con.commit()
"
```

Expected: `deleted: 1`.

### Step 3 — Dedup `not_matched_jobs` (keep MIN(id) per title+company group)

```bash
"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -c "
import sqlite3
con = sqlite3.connect('data/applications.db')
cur = con.cursor()
cur.execute('''
    DELETE FROM not_matched_jobs
    WHERE id NOT IN (
        SELECT MIN(id)
        FROM not_matched_jobs
        WHERE job_title IS NOT NULL AND company IS NOT NULL
        GROUP BY LOWER(TRIM(job_title)), LOWER(TRIM(company))
    )
    AND EXISTS (
        SELECT 1 FROM not_matched_jobs nm2
        WHERE LOWER(TRIM(nm2.job_title)) = LOWER(TRIM(not_matched_jobs.job_title))
          AND LOWER(TRIM(nm2.company))   = LOWER(TRIM(not_matched_jobs.company))
          AND nm2.job_title IS NOT NULL AND nm2.company IS NOT NULL
        GROUP BY LOWER(TRIM(nm2.job_title)), LOWER(TRIM(nm2.company))
        HAVING COUNT(*) > 1
    )
''')
print('deleted:', cur.rowcount)
con.commit()
"
```

Expected: `deleted: 24`.

If the number differs, STOP and report.

### Step 4 — Post-dedup verification

```bash
"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -c "
import sqlite3
con = sqlite3.connect('data/applications.db')
cur = con.cursor()
for t in ('applications', 'matched_jobs', 'not_matched_jobs'):
    n = cur.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
    print(f'{t}: {n}')
print()
# Re-check for title+company duplicates
for t in ('applications', 'not_matched_jobs', 'matched_jobs'):
    extra = sum(r[0] - 1 for r in cur.execute(f'''
        SELECT COUNT(*) FROM {t}
        WHERE job_title IS NOT NULL AND company IS NOT NULL
        GROUP BY LOWER(TRIM(job_title)), LOWER(TRIM(company))
        HAVING COUNT(*) > 1
    '''))
    print(f'{t} title+company duplicates remaining: {extra}')
# Re-check for exact URL duplicates
for t in ('applications', 'not_matched_jobs', 'matched_jobs'):
    extra = sum(r[0] - 1 for r in cur.execute(f'''
        SELECT COUNT(*) FROM {t}
        WHERE job_url IS NOT NULL AND job_url != ''
        GROUP BY job_url HAVING COUNT(*) > 1
    '''))
    print(f'{t} URL duplicates remaining: {extra}')
"
```

**Expected exactly:**
```
applications: 138
matched_jobs: 777
not_matched_jobs: 2921

applications title+company duplicates remaining: 0
not_matched_jobs title+company duplicates remaining: 0
matched_jobs title+company duplicates remaining: 0
applications URL duplicates remaining: 0
not_matched_jobs URL duplicates remaining: 0
matched_jobs URL duplicates remaining: 0
```

### Step 5 — Report

Report to the advisor with:
- All output from Step 1 baseline
- All output from Step 4 verification
- Path and size of the backup
- Any STOP conditions considered but not fired
- Any deviations

**Do NOT**:
- Commit anything to git (this is a data mutation, not a code change)
- Touch the real `data/applications.db` in the main tree — you are working on the worktree copy only
- Delete the backup
- Modify any `.py` files

## Files in scope
- `data/applications.db` (mutated inside the worktree only)
- `data/applications.db.bak` (created by Step 1)

## Files out of scope
- Everything else. This plan does no code changes.

## Done criteria (machine-checkable)
- Post-dedup counts: 138 / 777 / 2921
- Zero title+company duplicates remaining in any table
- Zero URL duplicates remaining in any table
- Backup file exists at `data/applications.db.bak`
