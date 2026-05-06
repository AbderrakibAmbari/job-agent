import re
import sqlite3
import json
import shutil
import glob
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)
DB_PATH = "data/applications.db"

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


def _title_company_key(title: str, company: str) -> str:
    t = _norm_title(title)
    c = _norm_company(company)
    if c and c not in ('unknown', '', 'n/a'):
        return f"{t}|{c}"
    return t


def _conn():
    return sqlite3.connect(DB_PATH)


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
            ("applied",       "INTEGER DEFAULT 0"),
            ("all_urls",      "TEXT DEFAULT '[]'"),
            ("job_category",  "TEXT DEFAULT 'Other'"),
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
    with _conn() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT id FROM applications
            WHERE job_url = ? OR (company = ? AND job_title = ?)
        """, (job_url, company, job_title))
        if c.fetchone():
            return
        c.execute("""
            INSERT INTO applications
            (company, job_title, platform, date_applied,
             cover_letter, job_url, follow_up_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            company, job_title, platform,
            datetime.now().strftime("%Y-%m-%d"),
            cover_letter, job_url,
            datetime.now().strftime("%Y-%m-%d"),
        ))
        conn.commit()


def save_matched_jobs(jobs: list) -> None:
    today    = datetime.now().strftime("%Y-%m-%d")
    inserted = 0

    with _conn() as conn:
        c = conn.cursor()
        for job in jobs:
            all_urls = json.dumps(
                job.get("urls", [{"platform": job.get("platform", ""), "url": job.get("url", "")}])
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
                job.get("url", "").strip(),
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
                    (job.get("url", "").strip(),)
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
                job.get("url", "").strip(),
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


def update_matched_job_cover_letter(job_id: int, cover_letter: str) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE matched_jobs SET cover_letter = ? WHERE id = ?",
            (cover_letter, job_id)
        )
        conn.commit()


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
    for (url,) in matched + not_matched:
        urls.add(url.split("?")[0].rstrip("/").lower())
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
