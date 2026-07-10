# Plan 020: Gmail-driven application status automation (backfill + ongoing)

**Planned at commit**: `70bc593` (main)
**Category**: Feature (external integration + DB writeback)
**Effort**: L (phase 1 = M, phase 2 = M-L, both together L)
**Risk**: MEDIUM (touches real Gmail account read-scope; writes to
`applications.status` in production DB — must be idempotent + reversible)
**Depends on**: 009 (follow-up workflow — this plan REPLACES the manual
buttons that plan added)
**Skill to execute with**: `/improve deep`

## Why this matters

Plan 009 landed a manual follow-up workflow: 138 apps show as "due", each
row has Interview / Rejected / Snooze +7d buttons the operator clicks
after reading the reply email. That's the right seam — it just shouldn't
require the human at all. Gmail already knows the answer.

Every job application generates a mail trail:
- **Acknowledgement** ("Wir haben Ihre Bewerbung erhalten") within minutes
- **Rejection** ("Absage" / "leider können wir Ihnen keine Zusage geben")
  usually within 2-6 weeks
- **Interview invite** ("Einladung zum Gespräch" / "Interview") within
  1-3 weeks for the ~5-10% that progress
- **Offer** ("Vertragsangebot" / "Zusage") — rare, but the reason the
  whole system exists

The operator (Abderrakib) currently reads each of these by hand and
clicks a button in the dashboard. With 138 open applications and a
growing pipeline, this is the next bottleneck. Gmail is the source of
truth; the dashboard should mirror it, not require it to be re-entered.

## Scope: two phases

### Phase 1 — one-shot backfill (implement first, land, verify)

Scan the operator's Gmail for the last 6 months, classify each thread
that matches an application in `applications.job_url`/`company`/
`job_title`, and update `applications.status` in place. **Read-only on
Gmail; write-only on the `status` column.** Every other column stays as
plan 009 left it.

Success criterion: of the 138 apps in "Sent"/"Waiting", the majority
should land in a terminal state ("Rejected"/"Interview"/"Offer") or stay
in "Waiting" with a fresh `follow_up_date`. Rough expectation: 40-60%
rejections, 5-10% interviews, remainder still-pending — but that's a
prediction, not a spec.

### Phase 2 — ongoing sync + remove manual buttons

After phase 1 verifies the classifier works, wire it into `run_daily.py`
as a scheduled task (same cadence as the scraper). New Gmail messages
since last sync get classified and applied. Once phase 2 is stable for
one week, **delete the Interview/Rejected/Snooze buttons and the per-app
`status` selectbox** from `dashboard.py` — the dashboard becomes
read-only for status.

Phase 2 is a separate follow-up commit; phase 1 must be landed and
verified against real data before phase 2 starts.

## Environment

- Windows 11, bash shell
- Python: `"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe"`
- Operator's Gmail: `abderrakib8@gmail.com`
- You are running inside a git worktree at `.claude/worktrees/agent-<id>/`

**Data provisioning** — copy the real DB into place so the classifier
can be dry-run against real applications:

```bash
mkdir -p data
cp /c/Users/abam/Documents/job-agent/data/applications.db data/applications.db
```

## Drift check

Before starting, verify main hasn't moved past the planning SHA:

```bash
git rev-parse HEAD  # expect 70bc593
git log --oneline nodes/tracker.py dashboard.py run_daily.py | head -5
```

If nodes/tracker.py, dashboard.py, or run_daily.py have new commits since
`70bc593`, re-read them before writing the classifier — the schema or
the button set may have shifted.

## Design

### Auth: Gmail API via OAuth2 installed-app flow

Do **not** use IMAP + app password. Gmail deprecated less-secure-app
access, and the operator is on a personal Google account with 2FA. Use
the official Gmail API:

- Package: `google-auth`, `google-auth-oauthlib`, `google-api-python-client`
- OAuth flow: `InstalledAppFlow.from_client_secrets_file(...)` — one-time
  browser consent on the operator's machine, then a refresh-token stored
  at `data/gmail_token.json` (add to `.gitignore` — see safety section)
- Scope: `https://www.googleapis.com/auth/gmail.readonly` (phase 1) —
  read-only is enough; we never send or delete mail
- Credentials file: `data/gmail_credentials.json` — downloaded from
  Google Cloud Console once. Also gitignored.

**Deliverable**: `nodes/gmail_client.py` with:
- `get_service()` — returns an authorized `googleapiclient` service,
  handles token refresh, prompts for consent on first run
- `list_messages(query: str, after: str) -> list[dict]` — thin wrapper
  around `users().messages().list()` with pagination
- `get_message(msg_id: str) -> dict` — fetches full message body +
  headers, returns a normalized dict (from, subject, date, snippet, body)

### Classifier: rule-based first, LLM only for ambiguous cases

Do **not** default to LLM classification for every mail. That's ~$5-10 in
API costs for a 6-month backfill and slow. Ordered rule pipeline:

1. **Body regex match on rejection phrases** (fast, high-precision):
   - DE: `absage`, `leider|bedauern`, `nicht (weiter |mehr )?berücksichtigen`,
     `nicht in die (engere|nächste)`, `andere.*entschieden`, `not (moving |proceeding )?forward`,
   - EN: `we regret`, `unfortunately`, `not (moving forward|selected|proceeding)`,
     `decided to move (forward|on) with (another|other)`, `position has been filled`
2. **Body regex match on interview invites**:
   - DE: `einladung zum (interview|gespräch|kennenlernen)`, `möchten wir Sie gerne`,
     `terminvorschlag`, `videocall`, `zoom-einladung`
   - EN: `we'd like to invite you`, `interview (invitation|scheduled)`,
     `next step is (a )?(video|phone) call`
3. **Body regex match on offers** (rare, high value):
   - DE: `vertragsangebot`, `wir freuen uns.*einstellung`, `arbeitsvertrag`
   - EN: `we're pleased to offer`, `offer of employment`, `employment agreement`
4. **Auto-acknowledge detection** (skip, keep as "Waiting"):
   - Subject starts with `Bewerbungseingang|Ihre Bewerbung|Application received|Thank you for applying`
   - Body is <30 lines or contains `automatisch generiert|do not reply|noreply`
5. **LLM fallback for the residue** — anything that didn't hit 1-4 and
   isn't obviously an autoresponder gets sent to Claude Haiku 4.5 with a
   3-example prompt: `{Rejected, Interview, Offer, Waiting}`. Cap at
   ~50 tokens output. Budget: 20 calls per backfill run max — if the
   residue is larger, log a WARN and stop LLM'ing (something's wrong
   with the rules; adjust rules first, don't burn API).

**Deliverable**: `nodes/gmail_classifier.py` with:
- `_REJECTION_PATTERNS`, `_INTERVIEW_PATTERNS`, `_OFFER_PATTERNS`,
  `_AUTOACK_PATTERNS` — ordered regex lists
- `classify_message(msg: dict) -> str | None` — returns
  `"Rejected"|"Interview"|"Offer"|"Waiting"|None`. `None` means "no
  signal, don't touch the row".
- `classify_with_llm(msg: dict) -> str` — used only from the backfill
  script's residue loop.

### Matching: mail → application row

The hard part. Each `applications` row has `(company, job_title,
platform, job_url, date_applied)`. A rejection email typically has:
- **From**: `noreply@company-domain.com` or `careers@company-domain.com`
- **Subject**: contains `job_title` or an internal ATS reference
  (`Req-12345`, `2024-08-BE-Junior`)
- **Body**: often echoes `company_name` and sometimes the position title

Matching pipeline (per mail thread):

1. **Company domain match** — extract `company` from `applications`
   rows in `("Sent","Waiting")`. Slugify: `Deutsche Bahn AG` →
   `deutschebahn`. Match against sender domain (`.com`, `.de`,
   `.io`, `.jobs`). Multi-company matches → tie-break by date proximity
   (`abs(mail_date - date_applied)`), take the smallest.
2. **Subject substring** — for each row, check if a normalized version
   of `job_title` appears in normalized subject (lowercase, gender
   suffixes stripped — reuse `nodes/tracker._GENDER_RE`, `_normalize_job_title`).
3. **Body substring** — same normalization, applied to first 1000 chars
   of body.
4. **Job URL** — some ATS mails include a link back to the posting.
   `_normalize_url` from `nodes/tracker.py` (plan 017) → exact match on
   `applications.job_url`.

A match requires **at least two of {company_domain, subject, body,
job_url}** to hit the same row. Single-signal matches go to a
`data/gmail_review.jsonl` file for manual review (log the mail id,
matched row candidates, and the signal). Do not silently guess.

**Deliverable**: `nodes/gmail_matcher.py` with:
- `match_message_to_application(msg: dict, apps: list) -> int | None` —
  returns `application_id` or `None`
- `_slugify_company(name: str) -> str`
- `_extract_sender_domain(from_header: str) -> str | None`

### Backfill script

**Deliverable**: `scripts/backfill_from_gmail.py` (new file). CLI:

```bash
python scripts/backfill_from_gmail.py --months 6 --dry-run
python scripts/backfill_from_gmail.py --months 6 --apply
```

Flow:

1. `service = get_service()` — auth
2. Load open apps: `SELECT id, company, job_title, platform, job_url,
   date_applied, status FROM applications WHERE status IN ('Sent',
   'Waiting')` — 138 rows currently
3. Query Gmail: `service.users().messages().list(userId='me',
   q=f'after:{six_months_ago} -in:sent -label:draft')` — paginate
4. For each message: `get_message()` → `classify_message()` →
   `match_message_to_application()`
5. Aggregate `{app_id: [(mail_date, classified_status)]}`. If an app has
   multiple mails, take the **latest terminal state** (Rejected > Offer
   > Interview > Waiting). Rationale: an interview invite followed by a
   rejection is a rejection; a rejection followed by an offer would be
   bizarre but if it happens, log a WARN and keep the offer.
6. Print a review table (Rich): `app_id | company | job_title |
   old_status | new_status | mail_date | matched_signals`
7. `--dry-run` stops here. `--apply` writes: `UPDATE applications SET
   status = ?, follow_up_date = NULL WHERE id = ?` (NULL because
   Rejected/Interview/Offer are terminal-ish — no further nudge needed;
   Interview should get a follow_up_date reset in phase 2's ongoing
   sync when it becomes stale, but out of scope here).
8. Print summary counts by new status.

Backup DB before applying: `python -c "from nodes.tracker import
backup_db; backup_db()"` — reuse the existing helper.

### Phase 2 — ongoing sync (deferred; sketch only)

- New file: `nodes/gmail_sync.py` with `sync_since(last_ts: str) -> int`
  — same pipeline as backfill, but incremental. Stores `last_ts` in a
  new tiny table `sync_state(key TEXT PRIMARY KEY, value TEXT)`.
- Wire into `run_daily.main()` **after** the scraper block, **before**
  the strong-match notification block: `sync_since(last)`. Failures
  should log-and-continue (don't crash the daily run if Google API is
  down).
- **Only after phase 2 has been stable for ≥ 7 days**, remove from
  `dashboard.py`:
  - Lines 427-437: the Interview / Rejected / Snooze +7d buttons
    (`fu_int_*`, `fu_rej_*`, `fu_snz_*`) inside the follow-up expander
  - Line 511 area: the per-app `status` selectbox in the "My
    Applications" table (verify exact block before deletion; the
    `update_status` import can go too once no more callers)
  - The "Follow-up due" banner section itself stays — it's still useful
    as a "these are the rows where Gmail hasn't heard anything back yet"
    view.

## Safety

- **Read-only Gmail scope** in phase 1. No `gmail.modify`, no
  `gmail.send`. If the operator ever wants auto-reply, that's a
  different plan.
- **Never commit `data/gmail_credentials.json` or `data/gmail_token.json`.**
  Add both to `.gitignore` as the first step of the executor's work.
  Also add `data/gmail_review.jsonl` since it will contain mail
  snippets.
- **DB backup before `--apply`.** The backfill can rewrite up to 138
  rows. Make it easy to roll back.
- **Idempotent apply**: rerunning `--apply` on the same data should
  produce zero writes. Achieve via `WHERE status != ?` guard on the
  UPDATE (only write if the new value differs from current).
- **Rate limit on Gmail API**: 250 quota units per user per second is
  the default. Batch reads. If we get 429, exponential backoff (2s,
  4s, 8s, cap at 30s). Don't retry forever — after 3 failures on the
  same message, log and skip.

## Deliverables

Phase 1 (this plan lands here):
- `nodes/gmail_client.py` — auth + list/get helpers
- `nodes/gmail_classifier.py` — regex rules + LLM fallback
- `nodes/gmail_matcher.py` — mail-to-app matching
- `scripts/backfill_from_gmail.py` — CLI backfill runner
- `.gitignore` additions for token/credentials/review files
- `requirements.txt` additions: `google-auth`, `google-auth-oauthlib`,
  `google-api-python-client`
- `tests/test_gmail_classifier.py` — 20+ parametrized cases (real
  German and English rejection/interview/offer/autoack samples,
  anonymized)
- `tests/test_gmail_matcher.py` — 10+ cases covering
  single-signal-rejected, two-signal-accepted, tie-break-by-date,
  no-match
- Manual verify block: dry-run against real Gmail, review the printed
  table, then `--apply` if the operator eyeballs it and says go.

Phase 2 (separate follow-up plan, or same plan / separate PR — decide
after phase 1 lands):
- `nodes/gmail_sync.py` — incremental sync
- `sync_state` table + init_db migration
- `run_daily.py` wiring
- After ≥ 7 days stable: `dashboard.py` cleanup (remove manual buttons
  + `update_status` selectbox + `update_status` import if unused)

## Explicit non-goals

- **No Gmail write access.** Ever. This project reads.
- **No auto-reply.** If the operator wants to auto-decline recruiter
  spam, that's plan 021+.
- **No inbox-wide reclassification.** Only mails from senders that plausibly
  match an application row get processed. Recruiter cold-outreach that
  doesn't match anything is ignored, not filed.
- **No cost cap tightening** on the LLM residue below 20 calls unless
  Haiku 4.5 pricing changes materially. The rules should handle >95%
  of real mails — if the residue is >20, that's a signal to improve
  the rules, and the backfill will surface it.
- **No dashboard button deletion in phase 1.** Buttons stay until phase
  2 proves the automation is trustworthy on real ongoing mail.

## Verification (phase 1 completion criteria)

Run after implementation, in order:

```bash
# 1. Suite still green
"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -m pytest -x

# 2. Classifier unit tests
"C:\Users\abam\Documents\job-agent\venv\Scripts\python.exe" -m pytest tests/test_gmail_classifier.py tests/test_gmail_matcher.py -v

# 3. Dry-run backfill (should print a table, NOT touch DB)
python scripts/backfill_from_gmail.py --months 6 --dry-run

# 4. Sanity: dry-run twice, second run should print identical table
python scripts/backfill_from_gmail.py --months 6 --dry-run > /tmp/run1.txt
python scripts/backfill_from_gmail.py --months 6 --dry-run > /tmp/run2.txt
diff /tmp/run1.txt /tmp/run2.txt  # empty diff expected

# 5. Backup + apply (operator-driven, not in CI)
python -c "from nodes.tracker import backup_db; backup_db()"
python scripts/backfill_from_gmail.py --months 6 --apply

# 6. Verify DB counts changed reasonably
sqlite3 data/applications.db "SELECT status, COUNT(*) FROM applications GROUP BY status ORDER BY 2 DESC"
```

Expected state after step 6: `Sent`/`Waiting` counts are lower than 138;
`Rejected` count is roughly 40-90 (depends on real inbox); some
`Interview` and (hopefully) some `Offer` rows appear.

## STOP conditions — do not merge if

- Any test fails.
- Dry-run diff (step 4) is non-empty — the classifier is non-deterministic.
- Dry-run shows an application flipping to `Offer` that the operator
  didn't actually get an offer for. Verify with the operator before
  running `--apply`.
- The `data/gmail_review.jsonl` file is >20% the size of matched mails —
  the matching rule is too strict; tune before applying.
- `gmail_credentials.json` or `gmail_token.json` appears in `git status`.

## Post-exec notes

_(Fill this in when the plan is executed.)_
