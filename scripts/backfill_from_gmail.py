"""Plan 020 phase 1: one-shot Gmail -> applications.status backfill.

Usage:
    python scripts/backfill_from_gmail.py --months 6 --dry-run
    python scripts/backfill_from_gmail.py --months 6 --apply

--dry-run prints the review table without touching the DB.
--apply backs up the DB, applies the updates idempotently (only writes
where status would actually change), and prints a summary.
"""
import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

# Allow `python scripts/backfill_from_gmail.py` to find the nodes package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nodes.gmail_classifier import classify_message, classify_with_llm  # noqa: E402
from nodes.gmail_matcher import match_message_to_application  # noqa: E402
from nodes.tracker import DB_PATH, backup_db  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("backfill")

_STATUS_PRIORITY = {"Rejected": 3, "Offer": 2, "Interview": 1, "Waiting": 0}
_TERMINAL = {"Rejected", "Offer"}
_REVIEW_PATH = "data/gmail_review.jsonl"
_LLM_BUDGET = 20


def _load_open_apps() -> list[dict]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, company, job_title, platform, job_url, date_applied, status "
            "FROM applications WHERE status IN ('Sent','Waiting')"
        ).fetchall()
    return [dict(r) for r in rows]


def _log_review(entry: dict) -> None:
    os.makedirs(os.path.dirname(_REVIEW_PATH), exist_ok=True)
    with open(_REVIEW_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _print_table(rows: list[dict]) -> None:
    """Plain-text review table. No external deps."""
    if not rows:
        print("(no changes)")
        return
    cols = ["app_id", "company", "job_title", "old", "new", "mail_date", "signals"]
    widths = {c: len(c) for c in cols}
    for r in rows:
        for c in cols:
            widths[c] = max(widths[c], min(40, len(str(r.get(c, "")))))
    fmt = "  ".join("{:<%d}" % widths[c] for c in cols)
    print(fmt.format(*cols))
    print("-" * (sum(widths.values()) + len(cols) * 2))
    for r in rows:
        vals = [str(r.get(c, ""))[: widths[c]] for c in cols]
        print(fmt.format(*vals))


def _iter_recent_message_ids(service, months: int):
    """Yield Gmail message ids from the last `months` months."""
    from nodes.gmail_client import list_messages

    cutoff = (date.today() - timedelta(days=months * 30)).strftime("%Y/%m/%d")
    query = f"after:{cutoff} -in:sent -label:draft -in:chats"
    logger.info("Gmail query: %s", query)
    for stub in list_messages(service, query):
        yield stub["id"]


def _resolve_status(msg: dict, llm_calls_used: list[int]) -> Optional[str]:
    """Rule-based classify; fall back to LLM only if under budget."""
    status = classify_message(msg)
    if status is not None:
        return status
    if llm_calls_used[0] >= _LLM_BUDGET:
        logger.warning("LLM budget (%d) exhausted; skipping residue mail", _LLM_BUDGET)
        return None
    llm_calls_used[0] += 1
    return classify_with_llm(msg)


def _aggregate_latest_terminal(records: list[tuple[date, str]]) -> str:
    """Pick the winning status from a list of (mail_date, status).

    Rule: latest terminal state wins. If two terminals appear on the same
    day, the priority Rejected > Offer > Interview > Waiting breaks ties.
    Offer arriving *after* Rejected keeps the Offer with a WARN.
    """
    if not records:
        return "Waiting"
    records = sorted(records, key=lambda t: t[0])
    winner = records[-1][1]
    prior_terminals = [(d, s) for d, s in records[:-1] if s in _TERMINAL]
    if winner not in _TERMINAL and prior_terminals:
        winner = prior_terminals[-1][1]
    if winner == "Rejected":
        # Odd but possible: Rejected then Offer — keep the Offer if newer.
        later_offers = [(d, s) for d, s in records if s == "Offer" and d >= records[-1][0]]
        if later_offers:
            logger.warning(
                "Post-rejection offer detected; keeping Offer over Rejected"
            )
            return "Offer"
    return winner


def run(months: int, apply_writes: bool) -> int:
    if not os.path.exists(DB_PATH):
        logger.error("DB not found at %s", DB_PATH)
        return 1

    apps = _load_open_apps()
    if not apps:
        print("No open applications (status in Sent/Waiting).")
        return 0
    logger.info("Loaded %d open applications", len(apps))

    from nodes.gmail_client import get_message, get_service

    service = get_service()
    per_app: dict[int, list[tuple[date, str, list[str]]]] = {}
    reviewed = 0
    llm_calls_used = [0]
    scanned = 0
    matched_mail_count = 0

    for msg_id in _iter_recent_message_ids(service, months):
        scanned += 1
        try:
            msg = get_message(service, msg_id)
        except Exception as e:
            logger.warning("Failed to fetch %s: %s", msg_id, e)
            continue

        app_id, signals = match_message_to_application(msg, apps)
        if app_id is None:
            if len(signals) == 1:
                reviewed += 1
                _log_review({
                    "msg_id": msg_id,
                    "from": msg.get("from", ""),
                    "subject": msg.get("subject", ""),
                    "single_signal": signals[0],
                })
            continue

        status = _resolve_status(msg, llm_calls_used)
        if status is None:
            continue

        from email.utils import parsedate_to_datetime
        try:
            md = parsedate_to_datetime(msg.get("date", "")).date()
        except Exception:
            md = date.today()

        per_app.setdefault(app_id, []).append((md, status, signals))
        matched_mail_count += 1

    logger.info(
        "Scanned %d mails; %d matched an app; %d flagged for single-signal review; %d LLM calls used",
        scanned, matched_mail_count, reviewed, llm_calls_used[0],
    )

    apps_by_id = {a["id"]: a for a in apps}
    changes: list[dict] = []
    for app_id, records in per_app.items():
        app = apps_by_id.get(app_id)
        if app is None:
            continue
        new_status = _aggregate_latest_terminal([(d, s) for d, s, _ in records])
        old_status = app["status"]
        if new_status == old_status:
            continue
        latest = max(records, key=lambda t: t[0])
        changes.append({
            "app_id": app_id,
            "company": app["company"],
            "job_title": app["job_title"],
            "old": old_status,
            "new": new_status,
            "mail_date": latest[0].isoformat(),
            "signals": ",".join(latest[2]),
        })

    changes.sort(key=lambda r: (r["new"], r["company"] or ""))
    print()
    _print_table(changes)
    print()

    if not apply_writes:
        print("[dry-run] No DB writes.")
        return 0

    if not changes:
        print("[apply] No status changes to write.")
        return 0

    backup_db()
    written = 0
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        for row in changes:
            res = c.execute(
                "UPDATE applications SET status = ?, follow_up_date = NULL "
                "WHERE id = ? AND status != ?",
                (row["new"], row["app_id"], row["new"]),
            )
            written += res.rowcount
        conn.commit()

    print(f"[apply] Wrote {written} row updates.")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--months", type=int, default=6, help="Lookback window in months")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", dest="dry_run", action="store_true")
    group.add_argument("--apply", dest="apply_writes", action="store_true")
    args = parser.parse_args(argv)
    return run(args.months, apply_writes=bool(args.apply_writes))


if __name__ == "__main__":
    sys.exit(main())
