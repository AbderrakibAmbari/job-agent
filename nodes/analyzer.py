from langchain_anthropic import ChatAnthropic
from dotenv import load_dotenv
import json
import re

load_dotenv()
llm = ChatAnthropic(model="claude-sonnet-4-20250514")

def score_job(cv: str, job: dict) -> dict:
    prompt = f"""
You are an expert recruiter. Analyze how well this candidate matches this job.

CANDIDATE CV:
{cv}

JOB:
Title: {job['title']}
Company: {job['company']}
Location: {job['location']}
Description: {job['description']}

Respond ONLY with a JSON object, no other text:
{{
    "score": <integer 0-100>,
    "match_reasons": [<list of 2-3 reasons why they match>],
    "missing": [<list of 1-2 things the candidate lacks, or empty list>],
    "recommendation": "<one of: Strong Match, Good Match, Weak Match, Skip>",
    "suggested_language": "<German or English based on job posting>"
}}
"""
    try:
        response = llm.invoke(prompt)
        text = response.content.strip()
        text = re.sub(r"```json|```", "", text).strip()
        result = json.loads(text)

        job["score"]          = result.get("score", 0)
        job["match_reasons"]  = result.get("match_reasons", [])
        job["missing"]        = result.get("missing", [])
        job["recommendation"] = result.get("recommendation", "Unknown")
        job["language"]       = result.get("suggested_language", "German")

    except Exception as e:
        print(f"⚠️  Scoring error for {job['company']}: {e}")
        job["score"]          = 50
        job["match_reasons"]  = []
        job["missing"]        = []
        job["recommendation"] = "Unknown"

    return job


def score_and_filter_jobs(cv: str, jobs: list, min_score: int = 70) -> list:
    print(f"\n🧠 Scoring {len(jobs)} jobs against your profile...")

    scored = []
    for job in jobs:
        job = score_job(cv, job)
        icon = "✅" if job["score"] >= min_score else "❌"
        print(
            f"{icon} {job['score']}% — {job['title']} @ {job['company']}"
            f" [{job['recommendation']}]"
        )
        scored.append(job)

    filtered = [j for j in scored if j["score"] >= min_score]
    filtered.sort(key=lambda x: x["score"], reverse=True)

    print(f"\n📊 {len(filtered)} jobs above {min_score}% match threshold")
    return filtered