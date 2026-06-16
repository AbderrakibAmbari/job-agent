import logging
import json
import re
import functools
from pathlib import Path
import anthropic
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage
from tenacity import (
    retry, wait_exponential, stop_after_attempt,
    retry_if_exception_type, retry_if_exception, before_sleep_log,
)

load_dotenv()
logger = logging.getLogger(__name__)
llm = ChatAnthropic(model="claude-haiku-4-5-20251001")


def _load_profile_text() -> str:
    """Read config/profile.yaml as raw text for inclusion in the scoring prompt.
    Re-read fresh each scoring run so edits to profile.yaml take effect without restart.
    """
    p = Path("config/profile.yaml")
    if not p.exists():
        return ""
    try:
        return p.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning("Could not load profile.yaml: %s", e)
        return ""


def _is_rate_limit_error(e: BaseException) -> bool:
    """True for any flavor of Anthropic 429 / rate-limit error."""
    if isinstance(e, anthropic.RateLimitError):
        return True
    msg = str(e).lower()
    return ("rate_limit_error" in msg) or ("429" in msg and "rate" in msg)

_JUNIOR_KEYWORDS = re.compile(
    r"\b(junior|berufseinsteiger|absolvent|graduate|trainee|praktikum|einstieg|entry)\b",
    re.IGNORECASE,
)
# Markers that suggest a role is open to fresh graduates / full-time entry even
# when the title doesn't say "Junior". Used to exempt Vollzeit/Festanstellung
# roles from the no-junior-keyword score cap.
_VOLLZEIT_OR_ENTRY = re.compile(
    r"\b(vollzeit|festanstellung|direkteinstieg|berufseinstieg|anwendungsentwickler|"
    r"young\s+professional|nachwuchs|associate)\b",
    re.IGNORECASE,
)
_EXPERIENCE_HARD = re.compile(
    r"\b([3-9]\+?\s*jahre?|[3-9]\s*years?|min\w*\.?\s*[3-9]\s*jahre?|mehrjährige)\b",
    re.IGNORECASE,
)
_SAP_TITLE = re.compile(
    r"\b(sap|abap|s/4hana|btp|hana|dynamics\s*365|business\s*central|erp)\b",
    re.IGNORECASE,
)
_TRAINEE_PROGRAM = re.compile(
    r"\b(trainee|graduate\s*programme|absolventenprogramm|getstartted|direkteinstieg|"
    r"young\s+professional|nachwuchsprogramm|einsteigerprogramm)\b",
    re.IGNORECASE,
)


_WERKSTUDENT_TITLE = re.compile(r"\bwerkstudent\w*\b", re.IGNORECASE)


def _apply_experience_cap(job: dict) -> dict:
    """Hard-cap scores that bypass the LLM's experience rules."""
    title = job.get("title", "")
    desc  = job.get("description", "")
    text  = f"{title} {desc}"

    # Werkstudent roles are no longer targeted — hard-cap any straggler
    if _WERKSTUDENT_TITLE.search(title):
        if job["score"] > 40:
            job["score"] = 40
            job.setdefault("missing", []).insert(0, "Werkstudent role — no longer targeted, score capped at 40")
        return job

    # Flag set by validator after reading the full page body
    if job.get("_requires_experience") or _EXPERIENCE_HARD.search(text):
        if job["score"] > 40:
            job["score"] = 40
            job.setdefault("missing", []).insert(0, "Requires experience (detected in page body) — hard cap applied")

    elif not _JUNIOR_KEYWORDS.search(title) and not _VOLLZEIT_OR_ENTRY.search(text):
        if job["score"] > 60:
            job["score"] = 60
            job.setdefault("missing", []).insert(0, "No junior/entry/Vollzeit indicator — score capped at 60")

    # SAP/ERP roles: cap at 55% (no SAP experience, but user is willing to apply)
    # Trainee/graduate programs are exempt — they are designed for fresh graduates
    category = job.get("job_category", "")
    if category == "SAP/ERP" and not _TRAINEE_PROGRAM.search(title):
        if _SAP_TITLE.search(title) and job["score"] > 55:
            job["score"] = 55
            job.setdefault("missing", []).insert(0, "SAP/ERP role — no prior SAP experience, score capped at 55")

    return job


_SCORING_RULES = """
TOP PRIORITY — boost these aggressively (these are the candidate's PREFERRED targets):
- TRAINEE programs (Trainee, Graduate Programme, Absolventenprogramm, Direkteinstieg,
  Nachwuchsprogramm, Young Professional, Einsteigerprogramm) — score 85+ if tech-aligned
- VOLLZEIT / Festanstellung entry-level positions — score 80+ if tech-aligned and no
  senior/lead qualifier in title (even if title doesn't say "Junior")
- Junior / Berufseinsteiger / Absolvent / Graduate titles
- PRAKTIKUM (internships) — score 75+ if tech-aligned and in NRW

NOT WANTED — actively deprioritize:
- WERKSTUDENT positions — the candidate is no longer pursuing Werkstudent roles.
  Cap any Werkstudent posting at 40 regardless of skill match.

Score HIGHER (boost) if:
- Location is in NRW, Hessen, Saarland, Rheinland-Pfalz, Niedersachsen, Hamburg, Bremen
- Role uses any of the candidate's core stack:
    * Backend: Java, Kotlin, Spring Boot, Spring Security, FastAPI, Flask, Node.js, Express
    * Frontend: TypeScript, Angular, Vue 3, React, Next.js, Tailwind
    * Databases: MySQL, PostgreSQL, MongoDB, SQLite, Prisma
    * DevOps: Docker, Docker Compose, GitHub Actions, Azure DevOps, Linux, CI/CD
    * AI/ML: Anthropic API (Claude), LangGraph, MCP, FastMCP, TensorFlow/Keras,
             OpenCV, Pandas, NumPy, Streamlit
    * Mobile/IoT: Android (Kotlin/Java), CameraX
    * Workflow: n8n, REST APIs, WebSocket
- Role mentions onboarding, mentorship, or junior-friendly environment
- Role is software engineering focused (backend, full-stack, web, API, DevOps, AI/ML)
- Role is remote within Germany or hybrid in target regions
- Role is open to recent graduates or students
- Job mentions Schnellbewerbung, Quick Apply, or easy application process

Score LOWER (deprioritize) if:
- Role requires Senior / Lead / Principal / Staff level
- Role is purely sales, recruiting, customer support, call center
- Role is purely manual testing with no engineering path
- Role is purely ERP customizing with no software development
- Role is outside Germany and not fully remote
- Role requires 3+ years mandatory experience

HARD RULES (must be respected regardless of skill match):
- A Vollzeit/Festanstellung role without "Junior" in the title is still a STRONG match if
  it has no senior qualifier and is tech-aligned. Do NOT cap such roles below 75 just
  because the title omits "Junior".
- If the job description or title explicitly states 3+ years of experience required →
  score MUST NOT exceed 40.
- If the title has a clear senior qualifier (Senior, Lead, Principal, Staff, Head of,
  Architect, Manager, Director) and NO trainee/junior counter-indicator → score MUST NOT
  exceed 35.
- The candidate is a FRESH GRADUATE seeking full-time entry-level work. A high skill-match
  score does NOT override hard experience requirements, but neutral Vollzeit titles should
  be treated as graduate-friendly by default.

IMPORTANT:
- Do not reject a job only because one framework differs
- If role matches location + (juniority OR Vollzeit entry) + core software engineering,
  keep it

Respond ONLY with this JSON, no other text:
{
    "score": <integer 0-100>,
    "match_reasons": [<2-3 specific reasons why this fits the candidate>],
    "missing": [<1-2 gaps or concerns, or empty list>],
    "recommendation": "<one of: Strong Match, Good Match, Weak Match, Skip>",
    "contract_type": "<Full-time / Werkstudent / Praktikum / Trainee / Unknown>",
    "work_mode": "<On-site / Hybrid / Remote / Unknown>",
    "suggested_language": "<German or English>",
    "is_quick_apply": <true/false>,
    "has_official_link": <true/false>,
    "job_category": "<one of: AI/ML, Backend, Frontend, FullStack, DevOps/Cloud, QA/Testing, SAP/ERP, ITConsulting, DataEngineering, Mobile, Other>"
}
"""


def _system_content(cv: str) -> list:
    profile_text = _load_profile_text()
    profile_block = (
        f"\nMASTER SKILLS & PROJECT POOL (config/profile.yaml — pick a subset per job,\n"
        f"never invent skills the candidate doesn't have):\n{profile_text}\n"
        if profile_text else ""
    )
    return [{
        "type": "text",
        "text": (
            "You are an expert technical recruiter helping a candidate find the right job.\n\n"
            f"CANDIDATE PROFILE (CV):\n{cv}\n"
            f"{profile_block}\n"
            f"SCORING RULES:{_SCORING_RULES}"
        ),
        "cache_control": {"type": "ephemeral"},
    }]


@retry(
    stop=stop_after_attempt(8),
    wait=wait_exponential(multiplier=2, min=15, max=120),
    retry=retry_if_exception(_is_rate_limit_error),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def _call_llm(system: str, job_text: str):
    """LLM call with exponential backoff on rate-limit (429)."""
    return llm.invoke([SystemMessage(content=system), HumanMessage(content=job_text)])


def score_job(cv: str, job: dict) -> dict:
    desc = (job.get('description', '') or '')[:800]
    job_text = (
        f"JOB POSTING:\n"
        f"Title: {job.get('title', '')}\n"
        f"Company: {job.get('company', '')}\n"
        f"Location: {job.get('location', '')}\n"
        f"Platform: {job.get('platform', '')}\n"
        f"Description: {desc}"
    )

    try:
        response = _call_llm(_system_content(cv), job_text)
        text  = re.sub(r"```json|```", "", response.content.strip()).strip()
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise ValueError("No JSON object found in response")
        result = json.loads(match.group())

        job["score"]          = result.get("score", 0)
        job["match_reasons"]  = result.get("match_reasons", [])
        job["missing"]        = result.get("missing", [])
        job["recommendation"] = result.get("recommendation", "Unknown")
        job["contract_type"]  = result.get("contract_type", "Unknown")
        job["work_mode"]      = result.get("work_mode", "Unknown")
        job["language"]       = result.get("suggested_language", "German")
        job["is_quick_apply"] = result.get("is_quick_apply", False) or job.get("quick_apply", False)
        job["job_category"]   = result.get("job_category", "Other")

        job = _apply_experience_cap(job)

        # Sync recommendation with capped score
        if job["score"] >= 85:
            job["recommendation"] = "Strong Match"
        elif job["score"] >= 70:
            job["recommendation"] = "Good Match"
        elif job["score"] >= 50:
            job["recommendation"] = "Weak Match"
        else:
            job["recommendation"] = "Skip"

    except Exception as e:
        logger.warning(
            "Scoring failed for %s / %s: %s",
            job.get("company", "?"), job.get("title", "?"), e
        )
        job["score"]          = 0
        job["match_reasons"]  = []
        job["missing"]        = ["Scoring failed — could not evaluate this job"]
        job["recommendation"] = "Unknown"
        job["contract_type"]  = "Unknown"
        job["work_mode"]      = "Unknown"
        job["is_quick_apply"] = job.get("quick_apply", False)
        job["job_category"]   = "Other"
        job["_score_failed"]  = True

    return job


_SENIOR_TITLE = re.compile(
    r"\b(senior|sr\.|lead|principal|staff|head\s+of|director|cto|vp\s+of|chief|architect|manager|teamleiter|abteilungsleiter)\b",
    re.IGNORECASE,
)
_JUNIOR_TITLE = re.compile(
    r"\b(junior|jr\.|berufseinsteiger|absolvent|graduate|trainee|praktikum|einstieg|entry|berufseinstieg)\b",
    re.IGNORECASE,
)
_NON_TECH_TITLE = re.compile(
    r"\b(vertrieb|verkauf|sales|kundenberater|recruiter|buchhalter|buchführung|steuer|logistik|lager|fahrer|pflege|arzt|arzthelfer|sekretär|verwaltung|marketing\s+manager|pr\s+manager)\b",
    re.IGNORECASE,
)
_EXPERIENCE_EXTREME = re.compile(
    r"\b([5-9]\+?\s*jahre?|[5-9]\s*years?|1[0-9]\+?\s*jahre?|min\w*\.?\s*[5-9]\s*jahre?)\b",
    re.IGNORECASE,
)
_GERMANY_LOCATION = re.compile(
    r"(germany|deutschland|nordrhein|bayern|berlin|hamburg|hessen|nrw|bochum|dortmund|cologne|köln|düsseldorf|münchen|frankfurt|stuttgart|essen|remote)",
    re.IGNORECASE,
)


def _quick_reject(job: dict) -> str | None:
    """Return a rejection reason string if the job can be skipped without LLM scoring, else None."""
    title = job.get("title", "")
    desc  = job.get("description", "") or ""
    loc   = job.get("location", "") or ""
    text  = f"{title} {desc[:300]}"

    # Vollzeit / Trainee / Direkteinstieg roles get the benefit of the doubt — never
    # pre-reject them on title alone, even if they look ambiguous. Hard experience
    # requirements (5+ yrs) still apply below.
    is_vollzeit_or_trainee = bool(
        _VOLLZEIT_OR_ENTRY.search(text) or _TRAINEE_PROGRAM.search(text)
    )

    # Drop senior/lead titles that have no junior qualifier
    if _SENIOR_TITLE.search(title) and not _JUNIOR_TITLE.search(title) and not is_vollzeit_or_trainee:
        return "Senior/Lead title — not suitable for fresh graduate"

    # Drop clearly non-tech roles
    if _NON_TECH_TITLE.search(title):
        return "Non-tech role (sales/admin/logistics)"

    # Drop roles needing 5+ years experience (applies even to Vollzeit/Trainee — a
    # "Trainee" needing 5+ years isn't a real trainee role)
    if _EXPERIENCE_EXTREME.search(text):
        return "Requires 5+ years experience"

    # Drop roles clearly outside Germany with no remote indicator
    if loc and not _GERMANY_LOCATION.search(loc) and "remote" not in loc.lower():
        return f"Outside Germany ({loc})"

    return None


def score_and_filter_jobs(cv: str, jobs: list, min_score: int = 70) -> tuple:
    """
    Score jobs against the CV. Saves results to the DB in small batches as it
    goes, so a Ctrl+C or rate-limit timeout still preserves partial progress.

    Concurrency is set to 1 worker — Claude Haiku has a 50K input-token/minute
    rate limit on Tier 1, and the @retry on _call_llm handles transient 429s.
    """
    # Local import avoids a hard module-level cycle if tracker ever grows imports
    from nodes.tracker import save_matched_jobs, save_not_matched_jobs

    # ── Fast keyword pre-filter — no API call needed ──
    to_score, pre_rejected = [], []
    for job in jobs:
        reason = _quick_reject(job)
        if reason:
            job["score"]          = 0
            job["recommendation"] = "Skip"
            job["match_reasons"]  = []
            job["missing"]        = [reason]
            job["contract_type"]  = job.get("contract_type", "Unknown")
            job["work_mode"]      = job.get("work_mode", "Unknown")
            job["is_quick_apply"] = job.get("quick_apply", False)
            job["job_category"]   = "Other"
            pre_rejected.append(job)
        else:
            to_score.append(job)

    print(f"\n🔍 Pre-filter: {len(pre_rejected)} jobs rejected instantly | {len(to_score)} sent to LLM")
    print(f"🧠 Scoring {len(to_score)} jobs against your profile (1 worker, retry-on-429)...")

    # Persist pre-rejected immediately — they won't appear again next run
    if pre_rejected:
        save_not_matched_jobs(pre_rejected)

    # ── Incremental scoring loop ──
    scored: list = []
    pending_matched: list = []
    pending_not_matched: list = []
    BATCH_SIZE = 5
    interrupted = False

    def _flush_batch():
        nonlocal pending_matched, pending_not_matched
        if pending_matched:
            save_matched_jobs(pending_matched)
            pending_matched = []
        if pending_not_matched:
            save_not_matched_jobs(pending_not_matched)
            pending_not_matched = []

    score_fn = functools.partial(score_job, cv)
    executor = ThreadPoolExecutor(max_workers=1)
    futures = {}
    try:
        futures = {executor.submit(score_fn, j): j for j in to_score}
        for future in as_completed(futures):
            try:
                job = future.result()
            except Exception as e:
                logger.warning("Score future failed unexpectedly: %s", e)
                continue
            scored.append(job)

            if not job.get("_score_failed"):
                if job["score"] >= min_score:
                    pending_matched.append(job)
                elif job["score"] > 0:
                    pending_not_matched.append(job)

            icon       = "✅" if job["score"] >= min_score else "❌"
            quick_icon = "⚡" if job.get("is_quick_apply") or job.get("quick_apply") else ""
            print(
                f"{icon} {job['score']}% {quick_icon}[{job['recommendation']}] "
                f"{job['title']} @ {job['company']} "
                f"| {job['work_mode']} | {job['contract_type']}"
            )

            if len(pending_matched) + len(pending_not_matched) >= BATCH_SIZE:
                _flush_batch()

    except KeyboardInterrupt:
        interrupted = True
        print("\n⚠️  Interrupted — saving partial results before exit...")
        for f in futures:
            f.cancel()
    finally:
        _flush_batch()
        executor.shutdown(wait=False, cancel_futures=True)

    failed = sum(1 for j in scored if j.get("_score_failed"))
    if failed:
        print(f"  ⚠️  {failed} job(s) failed to score and were excluded")

    matched = [j for j in scored if j["score"] >= min_score and not j.get("_score_failed")]
    not_matched = [j for j in scored if 0 < j["score"] < min_score and not j.get("_score_failed")]

    matched.sort(key=lambda x: (
        not (x.get("is_quick_apply") or x.get("quick_apply")),
        -x["score"],
    ))

    print(f"\n📊 {len(matched)} jobs above {min_score}% threshold  |  {len(not_matched)} below threshold (saved for review)")
    quick_count = sum(1 for j in matched if j.get("is_quick_apply") or j.get("quick_apply"))
    if quick_count:
        print(f"⚡ {quick_count} jobs with Schnellbewerbung (Quick Apply)")

    if interrupted:
        print(f"⚠️  Run interrupted — {len(scored)} of {len(to_score)} jobs scored. Partial results are saved.")
        raise KeyboardInterrupt

    return matched, not_matched
