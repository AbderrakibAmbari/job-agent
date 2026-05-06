import logging
import json
import re
import functools
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

load_dotenv()
logger = logging.getLogger(__name__)
llm = ChatAnthropic(model="claude-haiku-4-5-20251001")

_JUNIOR_KEYWORDS = re.compile(
    r"\b(junior|berufseinsteiger|absolvent|graduate|trainee|werkstudent|praktikum|einstieg|entry)\b",
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
    r"\b(trainee|graduate\s*programme|absolventenprogramm|getstartted|direkteinstieg)\b",
    re.IGNORECASE,
)


def _apply_experience_cap(job: dict) -> dict:
    """Hard-cap scores that bypass the LLM's experience rules."""
    title = job.get("title", "")
    desc  = job.get("description", "")
    text  = f"{title} {desc}"

    # Flag set by validator after reading the full page body
    if job.get("_requires_experience") or _EXPERIENCE_HARD.search(text):
        if job["score"] > 40:
            job["score"] = 40
            job.setdefault("missing", []).insert(0, "Requires experience (detected in page body) — hard cap applied")

    elif not _JUNIOR_KEYWORDS.search(title):
        if job["score"] > 60:
            job["score"] = 60
            job.setdefault("missing", []).insert(0, "No junior/entry indicator in title — score capped at 60")

    # SAP/ERP roles: cap at 55% (no SAP experience, but user is willing to apply)
    # Trainee/graduate programs are exempt — they are designed for fresh graduates
    category = job.get("job_category", "")
    if category == "SAP/ERP" and not _TRAINEE_PROGRAM.search(title):
        if _SAP_TITLE.search(title) and job["score"] > 55:
            job["score"] = 55
            job.setdefault("missing", []).insert(0, "SAP/ERP role — no prior SAP experience, score capped at 55")

    return job


_SCORING_RULES = """
Score HIGHER (boost) if:
- Role is Junior / Berufseinsteiger / Absolvent / Graduate / Trainee / Werkstudent / Praktikum
- Location is in NRW, Hessen, Saarland, or Rheinland-Pfalz
- Role uses Java, Kotlin, Python, TypeScript, Backend, API, REST, Docker, CI/CD, Node.js, Vue, Angular
- Role mentions onboarding, mentorship, or junior-friendly environment
- Role is software engineering focused (backend, full-stack, web, API, DevOps)
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
- If the job title has NO junior/entry-level indicator (Junior, Berufseinsteiger, Absolvent,
  Graduate, Trainee, Werkstudent, Praktikum, Entry, Einstieg) AND no explicit mention of being
  open to graduates or beginners is visible → score MUST NOT exceed 60.
- If the job description or title explicitly states 3+ years of experience required → score MUST
  NOT exceed 40.
- The candidate is a FRESH GRADUATE. A high skill-match score does NOT override experience
  requirements. A job that requires experienced professionals is a bad match even if the
  technologies align perfectly.

IMPORTANT:
- Do not reject a job only because one framework differs
- If role matches location + juniority + core software engineering, keep it

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
    return [{
        "type": "text",
        "text": (
            "You are an expert technical recruiter helping a candidate find the right job.\n\n"
            f"CANDIDATE PROFILE:\n{cv}\n\n"
            f"SCORING RULES:{_SCORING_RULES}"
        ),
        "cache_control": {"type": "ephemeral"},
    }]


def _call_llm(system: str, job_text: str):
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
    r"\b(junior|jr\.|berufseinsteiger|absolvent|graduate|trainee|werkstudent|praktikum|einstieg|entry|berufseinstieg)\b",
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

    # Drop senior/lead titles that have no junior qualifier
    if _SENIOR_TITLE.search(title) and not _JUNIOR_TITLE.search(title):
        return "Senior/Lead title — not suitable for fresh graduate"

    # Drop clearly non-tech roles
    if _NON_TECH_TITLE.search(title):
        return "Non-tech role (sales/admin/logistics)"

    # Drop roles needing 5+ years experience
    if _EXPERIENCE_EXTREME.search(text):
        return "Requires 5+ years experience"

    # Drop roles clearly outside Germany with no remote indicator
    if loc and not _GERMANY_LOCATION.search(loc) and "remote" not in loc.lower():
        return f"Outside Germany ({loc})"

    return None


def score_and_filter_jobs(cv: str, jobs: list, min_score: int = 70) -> tuple:
    # Fast keyword pre-filter — no API call needed
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
    print(f"🧠 Scoring {len(to_score)} jobs against your profile...")

    score_fn = functools.partial(score_job, cv)
    with ThreadPoolExecutor(max_workers=2) as executor:
        scored = list(executor.map(score_fn, to_score))

    failed = sum(1 for j in scored if j.get("_score_failed"))
    if failed:
        print(f"  ⚠️  {failed} job(s) failed to score and were excluded")

    for job in scored:
        icon       = "✅" if job["score"] >= min_score else "❌"
        quick_icon = "⚡" if job.get("is_quick_apply") or job.get("quick_apply") else ""
        print(
            f"{icon} {job['score']}% {quick_icon}[{job['recommendation']}] "
            f"{job['title']} @ {job['company']} "
            f"| {job['work_mode']} | {job['contract_type']}"
        )

    matched = [
        j for j in scored
        if j["score"] >= min_score and not j.get("_score_failed")
    ]
    not_matched = [
        j for j in scored
        if 0 < j["score"] < min_score and not j.get("_score_failed")
    ]

    matched.sort(key=lambda x: (
        not (x.get("is_quick_apply") or x.get("quick_apply")),
        -x["score"],
    ))

    print(f"\n📊 {len(matched)} jobs above {min_score}% threshold  |  {len(not_matched)} below threshold (saved for review)")
    quick_count = sum(1 for j in matched if j.get("is_quick_apply") or j.get("quick_apply"))
    if quick_count:
        print(f"⚡ {quick_count} jobs with Schnellbewerbung (Quick Apply)")

    return matched, not_matched
