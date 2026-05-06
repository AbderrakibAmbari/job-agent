"""
One-time script to merge duplicate jobs in matched_jobs that share the same
normalized title+company but have different URLs (cross-platform / cross-day duplicates).

For each duplicate group:
  - Keep the row with applied=1 if any (user already applied).
  - Otherwise keep the highest-scoring row.
  - Delete all others.

Run once:  python cleanup_duplicates.py
"""
import re
import sqlite3
from collections import defaultdict

DB_PATH = "data/applications.db"

_GENDER_RE = re.compile(
    r'\s*\(m/w/d\)|\s*\(w/m/d\)|\s*\(m/f/d\)|\s*\(m/w/x\)|\s*\(w/m/x\)|\s*\(all genders\)',
    re.IGNORECASE,
)
_COMPANY_SUFFIX_RE = re.compile(
    r'\b(GmbH\s*&\s*Co\.?\s*KG|GmbH|AG|SE|Ltd\.?|LLC|Inc\.?|KG|e\.V\.|gGmbH|plc)\b',
    re.IGNORECASE,
)


def _norm_company(company: str) -> str:
    c = _COMPANY_SUFFIX_RE.sub('', company or '').lower()
    return re.sub(r'\s+', ' ', c).strip()


def _key(title: str, company: str) -> str:
    t = _GENDER_RE.sub('', title or '').lower().strip()
    c = _norm_company(company)
    if c and c not in ('unknown', '', 'n/a'):
        return f"{t}|{c}"
    return t


def cleanup():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    rows = cur.execute(
        "SELECT id, job_title, company, match_score, applied FROM matched_jobs"
    ).fetchall()

    groups: dict = defaultdict(list)
    for r in rows:
        k = _key(r["job_title"], r["company"])
        if k:
            groups[k].append(dict(r))

    to_delete = []
    for key, group in groups.items():
        if len(group) < 2:
            continue

        applied = [r for r in group if r["applied"] == 1]
        if applied:
            keep_id = applied[0]["id"]
        else:
            keep_id = max(group, key=lambda r: r["match_score"] or 0)["id"]

        dupes = [r["id"] for r in group if r["id"] != keep_id]
        to_delete.extend(dupes)

        titles = set(r["job_title"] for r in group)
        print(
            f"  Duplicate group ({len(group)} rows) — keeping id={keep_id}"
            f"  applied={'yes' if applied else 'no'}"
        )
        for t in titles:
            print(f"    title: {t}")

    if not to_delete:
        print("No title+company duplicates found.")
        conn.close()
        return

    placeholders = ",".join("?" * len(to_delete))
    cur.execute(f"DELETE FROM matched_jobs WHERE id IN ({placeholders})", to_delete)
    conn.commit()
    print(f"\nDeleted {len(to_delete)} duplicate row(s). DB is now clean.")
    conn.close()


if __name__ == "__main__":
    cleanup()
