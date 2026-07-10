import re
import sqlite3
import json
import shutil
import glob
import logging
import os
from datetime import date, datetime, timedelta

logger = logging.getLogger(__name__)
DB_PATH = "data/applications.db"

# Strip gender suffixes before title+company dedup
_GENDER_RE = re.compile(
    r'\s*\(m/w/d\)|\s*\(w/m/d\)|\s*\(m/f/d\)|\s*\(f/m/d\)|\s*\(m/w/x\)|\s*\(w/m/x\)|\s*\(f/m/x\)|\s*\(all genders\)',
    re.IGNORECASE,
)
# Strip common legal suffixes so "Arvato" and "Arvato SE" normalise to the same key
_COMPANY_SUFFIX_RE = re.compile(
    r'\b(GmbH\s*&\s*Co\.?\s*KG|GmbH|AG|SE|Ltd\.?|LLC|Inc\.?|KG|e\.V\.|gGmbH|plc)(?=\s|[.,;]|$)',
    re.IGNORECASE,
)


def _norm_title(title: str) -> str:
    return _GENDER_RE.sub('', title or '').lower().strip()


def _norm_company(company: str) -> str:
    c = _COMPANY_SUFFIX_RE.sub('', company or '').lower()
    return re.sub(r'\s+', ' ', c).strip()


def _title_company_key(title: str, company: str) -> str:
    t = _norm_title(title)
    c = _norm_company(company)
    if c and c not in ('unknown', '', 'n/a'):
        return f"{t}|{c}"
    return t


def _normalize_url(url: str) -> str:
    """Canonical form used for storage + UNIQUE index.

    Strips query string, trailing slash, and lowercases. Idempotent —
    safe to call on already-canonical URLs. Must stay in sync with
    `nodes.scraper._url_key`.
    """
    return url.split("?")[0].rstrip("/").lower() if url else ""


def _conn():
    return sqlite3.connect(DB_PATH)


def _backfill_normalize_urls(conn):
    """One-shot: rewrite job_url in all three tables to canonical form.
    Idempotent — subsequent runs find already-canonical URLs and no-op.
    Collisions are impossible if plan 016 was applied; if any occur (e.g.
    fresh DB with unexpected data), the earliest id wins and later dupes
    are deleted.
    """
    cur = conn.cursor()
    for table in ("applications", "matched_jobs", "not_matched_jobs"):
        rows = cur.execute(
            f"SELECT id, job_url FROM {table} "
            f"WHERE job_url IS NOT NULL AND job_url != ''"
        ).fetchall()
        # Build a normalized-URL -> surviving-id map (keep earliest id per group)
        keeper = {}
        to_delete = []
        for rid, url in rows:
            norm = _normalize_url(url)
            if not norm:
                continue
            if norm in keeper:
                to_delete.append(rid)
            else:
                keeper[norm] = rid
        # Delete late-arriving collisions
        if to_delete:
            cur.executemany(
                f"DELETE FROM {table} WHERE id = ?",
                [(rid,) for rid in to_delete],
            )
            logger.info(
                "Backfill: dropped %d URL collisions from %s", len(to_delete), table
            )
        # Now UPDATE only rows whose stored URL differs from canonical
        updated = 0
        for norm, rid in keeper.items():
            cur.execute(
                f"UPDATE {table} SET job_url = ? WHERE id = ? AND job_url != ?",
                (norm, rid, norm),
            )
            if cur.rowcount:
                updated += 1
        if updated:
            logger.info(
                "Backfill: normalized %d URLs in %s", updated, table
            )
    conn.commit()


def init_db():
    os.makedirs("data", exist_ok=True)
    with _conn() as conn:
        c = conn.cursor()

        c.execute("""
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company TEXT,
                job_title TEXT,
                platform TEXT,
                date_applied TEXT,
                status TEXT DEFAULT 'Sent',
                cover_letter TEXT,
                job_url TEXT,
                follow_up_date TEXT
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS matched_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_title TEXT,
                company TEXT,
                location TEXT,
                platform TEXT,
                job_url TEXT,
                match_score INTEGER,
                recommendation TEXT,
                match_reasons TEXT,
                missing TEXT,
                contract_type TEXT,
                work_mode TEXT,
                link_status TEXT,
                cover_letter TEXT,
                date_found TEXT,
                applied INTEGER DEFAULT 0,
                all_urls TEXT DEFAULT '[]'
            )
        """)

        # Safe column migrations
        for col, definition in [
            ("applied",           "INTEGER DEFAULT 0"),
            ("all_urls",          "TEXT DEFAULT '[]'"),
            ("job_category",      "TEXT DEFAULT 'Other'"),
            ("rejection_reason",  "TEXT DEFAULT ''"),
            ("rejection_note",    "TEXT DEFAULT ''"),
        ]:
            try:
                c.execute(f"ALTER TABLE matched_jobs ADD COLUMN {col} {definition}")
            except Exception:
                pass

        c.execute("""
            CREATE TABLE IF NOT EXISTS not_matched_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_title TEXT,
                company TEXT,
                location TEXT,
                platform TEXT,
                job_url TEXT,
                match_score INTEGER,
                recommendation TEXT,
                match_reasons TEXT,
                missing TEXT,
                contract_type TEXT,
                work_mode TEXT,
                date_found TEXT
            )
        """)

        # Plan 017: canonicalize URLs before creating UNIQUE indexes.
        # Idempotent — no-op once URLs are already canonical.
        _backfill_normalize_urls(conn)

        c.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_applications_url
            ON applications(job_url)
            WHERE job_url IS NOT NULL AND job_url != ''
        """)

        c.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_not_matched_url
            ON not_matched_jobs(job_url)
            WHERE job_url IS NOT NULL AND job_url != ''
        """)

        # Indexes
        c.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_matched_jobs_url
            ON matched_jobs(job_url)
            WHERE job_url IS NOT NULL AND job_url != ''
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_matched_jobs_date
            ON matched_jobs(date_found)
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_matched_jobs_score
            ON matched_jobs(match_score DESC)
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_matched_jobs_applied
            ON matched_jobs(applied)
        """)

        conn.commit()


def backup_db():
    """Keep rolling 30-day backup of the SQLite DB."""
    if not os.path.exists(DB_PATH):
        return
    os.makedirs("data/backups", exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest  = f"data/backups/applications_{stamp}.db"
    try:
        shutil.copy(DB_PATH, dest)
        backups = sorted(glob.glob("data/backups/applications_*.db"))
        for old in backups[:-30]:
            os.remove(old)
        logger.info("DB backup saved to %s", dest)
    except Exception as e:
        logger.warning("DB backup failed: %s", e)


def save_application(company: str, job_title: str, platform: str,
                     cover_letter: str, job_url: str) -> None:
    norm_url = _normalize_url(job_url)
    with _conn() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT id FROM applications
            WHERE job_url = ? OR (company = ? AND job_title = ?)
        """, (norm_url, company, job_title))
        if c.fetchone():
            return
        today = datetime.now().strftime("%Y-%m-%d")
        c.execute("""
            INSERT INTO applications
            (company, job_title, platform, date_applied,
             cover_letter, job_url, follow_up_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            company, job_title, platform,
            today, cover_letter, norm_url,
            _default_followup_date(today),
        ))
        conn.commit()


def _default_followup_date(from_date_str: str, days: int = 7) -> str:
    """Compute the default follow-up date. Pure function — safe to unit-test.

    from_date_str: 'YYYY-MM-DD'
    Returns: 'YYYY-MM-DD' of from_date + days.
    """
    d = date.fromisoformat(from_date_str)
    return (d + timedelta(days=days)).strftime("%Y-%m-%d")


# Plan 021: public alias for external callers (dashboard). Internal caller
# save_application keeps the underscored name to avoid a same-module sweep.
default_followup_date = _default_followup_date


def get_due_followups(today_str: str = None) -> list:
    """Return applications with status in ('Sent', 'Waiting') AND
    follow_up_date <= today. Ordered oldest-follow-up first.

    Rows shape matches applications table:
    (id, company, job_title, platform, date_applied, status,
     cover_letter, job_url, follow_up_date)
    """
    today = today_str or datetime.now().strftime("%Y-%m-%d")
    with _conn() as conn:
        return conn.execute("""
            SELECT id, company, job_title, platform, date_applied, status,
                   cover_letter, job_url, follow_up_date
            FROM applications
            WHERE status IN ('Sent', 'Waiting')
              AND follow_up_date IS NOT NULL
              AND follow_up_date != ''
              AND follow_up_date <= ?
            ORDER BY follow_up_date ASC, date_applied ASC
        """, (today,)).fetchall()


def update_followup_date(app_id: int, new_date: str) -> None:
    """Update follow_up_date for a given application. new_date: 'YYYY-MM-DD'."""
    with _conn() as conn:
        conn.execute(
            "UPDATE applications SET follow_up_date = ? WHERE id = ?",
            (new_date, app_id)
        )
        conn.commit()


def save_matched_jobs(jobs: list) -> None:
    today    = datetime.now().strftime("%Y-%m-%d")
    inserted = 0

    with _conn() as conn:
        c = conn.cursor()
        for job in jobs:
            raw_url = job.get("url", "")
            norm_url = _normalize_url(raw_url)
            all_urls = json.dumps(
                job.get("urls", [{"platform": job.get("platform", ""), "url": raw_url}])
            )
            c.execute("""
                INSERT OR IGNORE INTO matched_jobs
                (job_title, company, location, platform, job_url,
                 match_score, recommendation, match_reasons, missing,
                 contract_type, work_mode, link_status, cover_letter,
                 date_found, applied, all_urls, job_category)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """, (
                job.get("title", ""),
                job.get("company", ""),
                job.get("location", ""),
                job.get("platform", ""),
                norm_url,
                job.get("score", 0),
                job.get("recommendation", ""),
                " | ".join(job.get("match_reasons", [])),
                " | ".join(job.get("missing", [])),
                job.get("contract_type", ""),
                job.get("work_mode", ""),
                job.get("link_status", ""),
                "",
                today,
                all_urls,
                job.get("job_category", "Other"),
            ))
            if c.rowcount:
                inserted += 1
            else:
                # Job already in DB — merge any new platform URLs
                c.execute(
                    "SELECT id, all_urls FROM matched_jobs WHERE job_url = ?",
                    (norm_url,)
                )
                row = c.fetchone()
                if row:
                    existing      = json.loads(row[1] or "[]")
                    existing_urls = {e.get("url") for e in existing}
                    new_urls      = job.get("urls", [])
                    merged        = existing + [u for u in new_urls if u.get("url") not in existing_urls]
                    if len(merged) > len(existing):
                        c.execute(
                            "UPDATE matched_jobs SET all_urls = ? WHERE id = ?",
                            (json.dumps(merged), row[0])
                        )

        conn.commit()

    skipped = len(jobs) - inserted
    suffix  = f" ({skipped} already in DB, skipped)" if skipped else ""
    print(f"[tracker] Saved {inserted} new matched jobs{suffix}")


def save_not_matched_jobs(jobs: list) -> None:
    today    = datetime.now().strftime("%Y-%m-%d")
    inserted = 0
    with _conn() as conn:
        c = conn.cursor()
        for job in jobs:
            c.execute("""
                INSERT OR IGNORE INTO not_matched_jobs
                (job_title, company, location, platform, job_url,
                 match_score, recommendation, match_reasons, missing,
                 contract_type, work_mode, date_found)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job.get("title", ""),
                job.get("company", ""),
                job.get("location", ""),
                job.get("platform", ""),
                _normalize_url(job.get("url", "")),
                job.get("score", 0),
                job.get("recommendation", ""),
                " | ".join(job.get("match_reasons", [])),
                " | ".join(job.get("missing", [])),
                job.get("contract_type", ""),
                job.get("work_mode", ""),
                today,
            ))
            if c.rowcount:
                inserted += 1
        conn.commit()
    print(f"[tracker] Saved {inserted} not-matched jobs")


def get_last_scrape_date() -> str | None:
    """Most recent date_found across matched + not_matched jobs (YYYY-MM-DD), or None."""
    with _conn() as conn:
        row = conn.execute("""
            SELECT MAX(d) FROM (
                SELECT MAX(date_found) AS d FROM matched_jobs
                WHERE date_found IS NOT NULL AND date_found != ''
                UNION ALL
                SELECT MAX(date_found) AS d FROM not_matched_jobs
                WHERE date_found IS NOT NULL AND date_found != ''
            )
        """).fetchone()
    return row[0] if row and row[0] else None


def promote_not_matched_to_matched(nm_id: int) -> bool:
    """Move a row from not_matched_jobs into matched_jobs.

    Returns True on success (row moved or already present in matched).
    The not_matched row is deleted either way so it stops showing up.
    """
    with _conn() as conn:
        c = conn.cursor()
        row = c.execute(
            "SELECT job_title, company, location, platform, job_url, "
            "match_score, recommendation, match_reasons, missing, "
            "contract_type, work_mode, date_found "
            "FROM not_matched_jobs WHERE id = ?",
            (nm_id,)
        ).fetchone()
        if not row:
            return False

        (job_title, company, location, platform, job_url,
         match_score, recommendation, match_reasons, missing,
         contract_type, work_mode, date_found) = row

        all_urls = json.dumps([{"platform": platform or "", "url": job_url or ""}])
        today = datetime.now().strftime("%Y-%m-%d")

        c.execute("""
            INSERT OR IGNORE INTO matched_jobs
            (job_title, company, location, platform, job_url,
             match_score, recommendation, match_reasons, missing,
             contract_type, work_mode, link_status, cover_letter,
             date_found, applied, all_urls, job_category)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
        """, (
            job_title, company, location, platform, _normalize_url(job_url or ""),
            match_score, recommendation, match_reasons, missing,
            contract_type, work_mode, "manual review", "",
            date_found or today, all_urls, "Other",
        ))

        c.execute("DELETE FROM not_matched_jobs WHERE id = ?", (nm_id,))
        conn.commit()
    return True


def get_not_matched_jobs(date_filter: str = None) -> list:
    with _conn() as conn:
        if date_filter:
            return conn.execute("""
                SELECT * FROM not_matched_jobs
                WHERE date_found = ?
                ORDER BY match_score DESC
            """, (date_filter,)).fetchall()
        return conn.execute("""
            SELECT * FROM not_matched_jobs
            ORDER BY date_found DESC, match_score DESC
        """).fetchall()


def update_matched_job_company(job_id: int, company: str) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE matched_jobs SET company = ? WHERE id = ?",
            (company, job_id)
        )
        conn.commit()


def update_matched_job_applied(job_id: int, state: int) -> None:
    """0 = unreviewed, 1 = applied, 2 = not applying."""
    with _conn() as conn:
        conn.execute(
            "UPDATE matched_jobs SET applied = ? WHERE id = ?",
            (state, job_id)
        )
        conn.commit()


_REJECTION_REASONS = (
    "not-tech",
    "wrong-tech",
    "wrong-seniority",
    "wrong-location",
    "wrong-contract",
    "employer-mismatch",
    "already-applied-elsewhere",
    "link-broken",
    "other",
)


def update_matched_job_rejection(job_id: int, reason: str, note: str = "") -> None:
    """Mark a matched job as not-applying with a captured reason.

    reason: one of _REJECTION_REASONS (soft validation — unknown reasons are
    stored verbatim so we don't lose data if the dropdown drifts).
    """
    with _conn() as conn:
        conn.execute(
            "UPDATE matched_jobs "
            "SET applied = 2, rejection_reason = ?, rejection_note = ? "
            "WHERE id = ?",
            (reason or "", note or "", job_id)
        )
        conn.commit()


def get_rejection_row(job_id: int):
    """Return (reason, note) for a job, or None if the job doesn't exist."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT rejection_reason, rejection_note FROM matched_jobs WHERE id = ?",
            (job_id,)
        ).fetchone()
    if not row:
        return None
    return (row[0] or "", row[1] or "")


def get_rejection_reason_counts() -> list:
    """Aggregate reason counts across matched_jobs. Empty reason excluded.

    Returns: list[tuple[str, int]] sorted desc by count.
    """
    with _conn() as conn:
        rows = conn.execute(
            "SELECT rejection_reason, COUNT(*) FROM matched_jobs "
            "WHERE applied = 2 AND rejection_reason != '' "
            "GROUP BY rejection_reason ORDER BY 2 DESC"
        ).fetchall()
    return [(r[0], r[1]) for r in rows]


def get_applied_status(job_id: int) -> int:
    with _conn() as conn:
        row = conn.execute(
            "SELECT applied FROM matched_jobs WHERE id = ?", (job_id,)
        ).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def get_applied_statuses(job_ids: list) -> dict:
    if not job_ids:
        return {}
    placeholders = ",".join("?" * len(job_ids))
    with _conn() as conn:
        rows = conn.execute(
            f"SELECT id, applied FROM matched_jobs WHERE id IN ({placeholders})",
            job_ids
        ).fetchall()
    return {row[0]: int(row[1]) if row[1] is not None else 0 for row in rows}


def get_known_urls() -> set:
    """Return normalised URLs of every job already in matched_jobs or not_matched_jobs."""
    with _conn() as conn:
        matched = conn.execute(
            "SELECT job_url FROM matched_jobs WHERE job_url IS NOT NULL AND job_url != ''"
        ).fetchall()
        not_matched = conn.execute(
            "SELECT job_url FROM not_matched_jobs WHERE job_url IS NOT NULL AND job_url != ''"
        ).fetchall()
    urls = set()
    # URLs stored canonical since plan 017; no runtime normalization needed
    for (url,) in matched + not_matched:
        urls.add(url)
    return urls


def get_known_title_keys() -> set:
    """Normalized title+company keys for every job ever seen (matched or not)."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT job_title, company FROM matched_jobs WHERE job_title IS NOT NULL"
        ).fetchall()
        rows += conn.execute(
            "SELECT job_title, company FROM not_matched_jobs WHERE job_title IS NOT NULL"
        ).fetchall()
    return {_title_company_key(t, c) for t, c in rows if t}


def get_scrape_dates(source: str = "matched", limit: int = 30) -> list:
    """Distinct (date_found, count) tuples — newest first.

    source = "matched"  -> matched_jobs
    source = "not_matched" -> not_matched_jobs
    """
    table = "matched_jobs" if source == "matched" else "not_matched_jobs"
    with _conn() as conn:
        rows = conn.execute(f"""
            SELECT date_found, COUNT(*) FROM {table}
            WHERE date_found IS NOT NULL AND date_found != ''
            GROUP BY date_found
            ORDER BY date_found DESC
            LIMIT ?
        """, (limit,)).fetchall()
    return [(d, n) for d, n in rows]


def get_all_applications() -> list:
    with _conn() as conn:
        return conn.execute(
            "SELECT * FROM applications ORDER BY date_applied DESC"
        ).fetchall()


def get_matched_jobs(date_filter: str = None, new_only: bool = False) -> list:
    with _conn() as conn:
        if date_filter:
            if new_only:
                rows = conn.execute("""
                    SELECT * FROM matched_jobs
                    WHERE date_found = ?
                    AND (
                        job_url IS NULL OR job_url = ''
                        OR job_url NOT IN (
                            SELECT job_url FROM matched_jobs
                            WHERE date_found < ? AND job_url IS NOT NULL AND job_url != ''
                        )
                    )
                    ORDER BY match_score DESC
                """, (date_filter, date_filter)).fetchall()

                # Also hide jobs the user already applied to (even if the URL differs)
                # row indices: id(0), job_title(1), company(2), ..., applied(15)
                if rows:
                    applied_keys = {
                        _title_company_key(t, c)
                        for (t, c) in conn.execute(
                            "SELECT job_title, company FROM matched_jobs WHERE applied = 1"
                        ).fetchall()
                    }
                    rows = [
                        r for r in rows
                        if r[15] == 1  # always keep rows already marked applied on this date
                        or _title_company_key(r[1], r[2]) not in applied_keys
                    ]
            else:
                rows = conn.execute("""
                    SELECT * FROM matched_jobs
                    WHERE date_found = ?
                    ORDER BY match_score DESC
                """, (date_filter,)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM matched_jobs
                ORDER BY date_found DESC, match_score DESC
            """).fetchall()
    return rows


def update_status(application_id: int, new_status: str) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE applications SET status = ? WHERE id = ?",
            (new_status, application_id)
        )
        conn.commit()


def delete_application(app_id: int) -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM applications WHERE id = ?", (app_id,))
        conn.commit()
