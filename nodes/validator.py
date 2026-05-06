import re
import requests
import logging
from tenacity import (
    retry, stop_after_attempt, wait_exponential,
    retry_if_exception_type, before_sleep_log,
)

logger = logging.getLogger(__name__)

from concurrent.futures import ThreadPoolExecutor

EXPIRED_PATTERNS = [
    "stelle nicht mehr verfügbar",
    "stellenanzeige ist nicht mehr aktiv",
    "job no longer available",
    "position has been filled",
    "position is no longer available",
    "this job has expired",
    "diese stelle ist bereits besetzt",
    "leider ist diese stelle",
]

LOGIN_REQUIRED_DOMAINS = [
    "xing.com",
    "linkedin.com",
    "arbeitsagentur.de",
    "glassdoor",
]

_EXPERIENCE_IN_BODY = re.compile(
    r"\b("
    r"[3-9]\+?\s*jahre?\s*(berufserfahrung|erfahrung|praxis)"
    r"|min\w*\.?\s*[3-9]\s*jahre?"
    r"|[3-9]\+?\s*years?\s*(of\s+)?(experience|professional)"
    r"|mehrjährige\s+\w*(kenntnisse|erfahrung|berufserfahrung|praxis)"
    r"|langjährige\s+\w*(kenntnisse|erfahrung|berufserfahrung)"
    r")",
    re.IGNORECASE,
)

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=8),
    retry=retry_if_exception_type((requests.exceptions.Timeout, requests.exceptions.ConnectionError)),
    before_sleep=before_sleep_log(logger, logging.DEBUG),
    reraise=False,
)
def _fetch(url: str):
    return requests.get(url, timeout=10, allow_redirects=True, headers=_HEADERS)


def validate_job_url(url: str) -> tuple:
    """Returns (link_status, requires_experience_flag)."""
    if not url or not url.startswith("http"):
        return "manual review", False

    for domain in LOGIN_REQUIRED_DOMAINS:
        if domain in url:
            return "active", False

    try:
        response = _fetch(url)
        if response is None:
            return "manual review", False
        if response.status_code in [404, 410]:
            return "expired", False
        content = response.text.lower()
        for pattern in EXPIRED_PATTERNS:
            if pattern in content:
                return "expired", False
        requires_exp = bool(_EXPERIENCE_IN_BODY.search(response.text))
        return "active", requires_exp
    except Exception:
        return "manual review", False


def validate_jobs(jobs: list) -> list:
    print(f"\n🔗 Validating {len(jobs)} job URLs in parallel...")

    def _validate_one(job):
        status, requires_exp = validate_job_url(job.get("url", ""))
        job["link_status"] = status
        if requires_exp:
            job["_requires_experience"] = True
        icon = "✅" if status == "active" else "⚠️" if status == "manual review" else "❌"
        exp_tag = " ⛔exp" if requires_exp else ""
        print(f"  {icon} [{status}]{exp_tag} {job.get('title', '')} @ {job.get('company', '')}")
        return job

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(_validate_one, jobs))

    return results
