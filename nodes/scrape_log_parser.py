"""Parse the box-drawing scrape summary that `_print_summary` writes
to data/scrape_log.txt. Pure read-side — never mutates the log.

Each run summary produces one dict:
    {
        "timestamp": "2026-06-29 17:31:38",
        "platforms": {
            "Arbeitsagentur": {"terms": 39, "cards": 352, "added": 137,
                               "exp": 0, "depr": 55},
            ...
        },
        "total": {"terms": 39, "cards": 950, "added": 491,
                  "exp": 0, "depr": 101},
        "top_terms": [("Graduate Software Engineer", 253),
                      ("Trainee IT", 63),
                      ("Vollzeit Softwareentwickler", 35)],
    }
"""
import os
import re
from collections import defaultdict
from typing import Iterable

DEFAULT_LOG_PATH = "data/scrape_log.txt"

_TIMESTAMP_RE  = re.compile(r"^║\s*Scrape Summary\s*[—-]\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
_ROW_RE        = re.compile(
    r"^║\s*([A-Za-z][A-Za-z0-9]*)\s*║\s*"  # platform (or TOTAL)
    r"(\d+)\s*║\s*(\d+)\s*║\s*(\d+)\s*║\s*(\d+)\s*║\s*(\d+)"
)
_TOP_TERMS_RE  = re.compile(r"^\s*Top terms by jobs added:\s*(.+)$")
_TERM_RE       = re.compile(r"^(.*?)\s*\((\d+)\)\s*$")


def parse_scrape_log(path: str = DEFAULT_LOG_PATH) -> list[dict]:
    """Return list of run dicts, oldest first."""
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    return _parse_text(text)


def _parse_text(text: str) -> list[dict]:
    runs: list[dict] = []
    current: dict | None = None

    for raw in text.splitlines():
        m_ts = _TIMESTAMP_RE.match(raw)
        if m_ts:
            if current is not None:
                runs.append(current)
            current = {
                "timestamp": m_ts.group(1),
                "platforms": {},
                "total": None,
                "top_terms": [],
            }
            continue

        if current is None:
            continue

        m_row = _ROW_RE.match(raw)
        if m_row:
            name, terms, cards, added, exp, depr = m_row.groups()
            stat = {
                "terms": int(terms), "cards": int(cards), "added": int(added),
                "exp":   int(exp),   "depr":  int(depr),
            }
            if name == "TOTAL":
                current["total"] = stat
            else:
                current["platforms"][name] = stat
            continue

        m_top = _TOP_TERMS_RE.match(raw)
        if m_top:
            for chunk in m_top.group(1).split(","):
                m = _TERM_RE.match(chunk.strip())
                if m:
                    current["top_terms"].append((m.group(1).strip(), int(m.group(2))))

    if current is not None:
        runs.append(current)
    return runs


def platform_history(runs: list[dict], platform: str, limit: int = 20) -> list[dict]:
    """Slice runs to the last `limit` where `platform` appeared. Newest-last."""
    filtered = [
        {"timestamp": r["timestamp"], **r["platforms"][platform]}
        for r in runs if platform in r["platforms"]
    ]
    return filtered[-limit:]


def broken_platforms(runs: list[dict], streak: int = 3) -> list[str]:
    """Platforms with `streak` consecutive most-recent runs where added=0.

    Only reports platforms that HAVE data in the log — a completely absent
    platform isn't 'broken', it's just not configured.
    """
    if not runs or len(runs) < streak:
        return []
    seen = set()
    for r in runs[-streak:]:
        seen.update(r["platforms"].keys())

    result = []
    for platform in sorted(seen):
        window = [r["platforms"].get(platform) for r in runs[-streak:]]
        if all(w is not None and w["added"] == 0 for w in window):
            result.append(platform)
    return result


def top_terms_aggregated(runs: Iterable[dict], limit: int = 10) -> list[tuple[str, int]]:
    """Sum term counts across the given runs. Returns sorted desc by count."""
    totals: dict[str, int] = defaultdict(int)
    for r in runs:
        for name, count in r.get("top_terms", []):
            totals[name] += count
    return sorted(totals.items(), key=lambda x: x[1], reverse=True)[:limit]
