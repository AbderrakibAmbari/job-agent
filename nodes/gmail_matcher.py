"""Match a Gmail message to an application row.

Signals used, each a boolean per (message, app) pair:
  - company_domain: sender-domain slug matches slugified company
  - subject:        normalized job_title substring in normalized subject
  - body:           normalized job_title substring in first 1500 chars of body
  - job_url:        normalized job_url appears in body

A match requires **at least 2 signals** on the same app. If multiple
apps tie on signal count, tie-break by date proximity: the app whose
`date_applied` is closest to the mail's date wins.

Anything with <2 signals is either dropped (0) or logged for manual
review by the caller (1-signal case → `data/gmail_review.jsonl`).
"""
import logging
import re
from datetime import datetime, date
from email.utils import parseaddr, parsedate_to_datetime
from typing import Optional

from nodes.tracker import _GENDER_RE, _normalize_url

logger = logging.getLogger(__name__)


_LEGAL_SUFFIX_RE = re.compile(
    r"\b(gmbh\s*&\s*co\.?\s*kg|gmbh|ag|se|ltd\.?|llc|inc\.?|kg|e\.v\.|ggmbh|plc)\b",
    re.IGNORECASE,
)
_NONWORD_RE = re.compile(r"[^a-z0-9]+")


def _slugify_company(name: str) -> str:
    """Company name → slug for domain matching.

    'Deutsche Bahn AG' → 'deutschebahn'
    'BMW Group'        → 'bmwgroup'
    'thoughtworks'     → 'thoughtworks'
    """
    if not name:
        return ""
    s = _LEGAL_SUFFIX_RE.sub(" ", name.lower())
    s = _NONWORD_RE.sub("", s)
    return s


def _extract_sender_domain(from_header: str) -> Optional[str]:
    """RFC-2822 From → registrable domain slug for matching.

    'Careers Team <careers@bahn.de>' → 'bahn'
    'noreply@jobs.thoughtworks.com'  → 'thoughtworks'
    """
    if not from_header:
        return None
    _, addr = parseaddr(from_header)
    if "@" not in addr:
        return None
    domain = addr.rsplit("@", 1)[1].lower().strip()
    parts = [p for p in domain.split(".") if p]
    if len(parts) < 2:
        return None
    # Drop 2-letter public suffixes ('.de', '.io'); for '.co.uk'-style
    # keep the SLD by dropping the last two parts if both are ≤3 letters.
    if len(parts) >= 3 and len(parts[-1]) <= 3 and len(parts[-2]) <= 3:
        core = parts[-3]
    else:
        core = parts[-2]
    # If the SLD looks like an ATS (workday, greenhouse, personio, etc.),
    # the *subdomain* holds the real company slug.
    _ATS_HOSTS = {"workday", "myworkday", "greenhouse", "lever",
                  "personio", "smartrecruiters", "workable", "recruitee",
                  "successfactors", "taleo", "jobvite", "concludis"}
    if core in _ATS_HOSTS and len(parts) >= 3:
        core = parts[-3]
    return _NONWORD_RE.sub("", core) or None


def _normalize_text(text: str) -> str:
    """Lowercase + strip gender suffixes. Reuses tracker._GENDER_RE."""
    return _GENDER_RE.sub("", (text or "").lower()).strip()


def _mail_date(msg: dict) -> Optional[date]:
    raw = msg.get("date")
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw).date()
    except Exception:
        return None


def _parse_app_date(d) -> Optional[date]:
    if d is None:
        return None
    if isinstance(d, date):
        return d
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(str(d), fmt).date()
        except ValueError:
            continue
    return None


def _score(msg: dict, app: dict) -> tuple[int, list[str]]:
    """Return (signal_count, signal_names) for a single (msg, app) pair."""
    signals: list[str] = []
    company = app.get("company") or ""
    job_title = app.get("job_title") or ""
    job_url = app.get("job_url") or ""

    company_slug = _slugify_company(company)
    sender_slug = _extract_sender_domain(msg.get("from", ""))
    if company_slug and sender_slug and (
        company_slug == sender_slug
        or company_slug in sender_slug
        or sender_slug in company_slug
    ):
        signals.append("company_domain")

    title_norm = _normalize_text(job_title)
    subject_norm = _normalize_text(msg.get("subject", ""))
    if title_norm and len(title_norm) >= 4 and title_norm in subject_norm:
        signals.append("subject")

    body_head = _normalize_text((msg.get("body") or "")[:1500])
    if title_norm and len(title_norm) >= 4 and title_norm in body_head:
        signals.append("body")

    if job_url:
        norm = _normalize_url(job_url)
        if norm and norm in (msg.get("body") or "").lower():
            signals.append("job_url")

    return len(signals), signals


def match_message_to_application(msg: dict, apps: list[dict]) -> tuple[Optional[int], list[str]]:
    """Match a message against a list of app rows.

    Returns (application_id, signals). `application_id` is None if no app
    scored ≥2 signals. Ties on signal count broken by mail_date closest
    to date_applied.
    """
    if not apps:
        return None, []

    scored = []
    for app in apps:
        n, signals = _score(msg, app)
        if n >= 1:
            scored.append((n, signals, app))

    if not scored:
        return None, []

    max_n = max(n for n, _, _ in scored)
    if max_n < 2:
        # Single-signal candidate — caller decides whether to log for review.
        n, signals, app = max(scored, key=lambda t: t[0])
        return None, signals

    top = [(n, signals, app) for n, signals, app in scored if n == max_n]
    if len(top) == 1:
        _, signals, app = top[0]
        return app.get("id"), signals

    md = _mail_date(msg)
    if md is None:
        _, signals, app = top[0]
        return app.get("id"), signals

    def proximity(entry):
        _, _, a = entry
        ad = _parse_app_date(a.get("date_applied"))
        if ad is None:
            return 10**9
        return abs((md - ad).days)

    _, signals, app = min(top, key=proximity)
    return app.get("id"), signals
