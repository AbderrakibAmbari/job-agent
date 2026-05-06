from langgraph.graph import StateGraph, END
from typing import TypedDict
from nodes.tracker import init_db, save_matched_jobs, save_not_matched_jobs, get_known_urls, get_known_title_keys, _title_company_key
from nodes.scraper import scrape_jobs, _url_key
from nodes.analyzer import score_and_filter_jobs
from nodes.validator import validate_jobs
from dotenv import load_dotenv
from datetime import datetime
import os

load_dotenv()
init_db()

# ── State ──────────────────────────────────────────
class AgentState(TypedDict):
    cv: str
    jobs: list
    validated_jobs: list
    scored_jobs: list

# ── Load CV ────────────────────────────────────────
with open("my_cv.txt", "r", encoding="utf-8") as f:
    cv_text = f.read()

RUN_DATE = datetime.now().strftime("%Y-%m-%d")

# ── Nodes ──────────────────────────────────────────
def fetch_jobs(state):
    print("\n🔍 Scraping jobs from all platforms...")
    jobs = scrape_jobs()
    print(f"📋 Found {len(jobs)} unique jobs")
    return {"jobs": jobs}

def validate_job_links(state):
    validated = validate_jobs(state["jobs"])
    alive = [j for j in validated if j.get("link_status") != "expired"]
    expired_count = len(validated) - len(alive)
    if expired_count:
        print(f"  ❌ Removed {expired_count} expired jobs")

    # Skip jobs already scored and saved in the DB
    known_urls   = get_known_urls()
    known_titles = get_known_title_keys()
    new_jobs = [
        j for j in alive
        if _url_key(j.get("url", "")) not in known_urls
        and _title_company_key(j.get("title", ""), j.get("company", "")) not in known_titles
    ]
    skipped = len(alive) - len(new_jobs)
    if skipped:
        print(f"  ⏭️  Skipped {skipped} jobs already in DB (won't re-score)")
    return {"validated_jobs": new_jobs}

def analyze_jobs(state):
    matched, not_matched = score_and_filter_jobs(
        cv=state["cv"],
        jobs=state["validated_jobs"],
        min_score=70
    )
    if matched:
        save_matched_jobs(matched)
    if not_matched:
        save_not_matched_jobs(not_matched)
    if not matched:
        print("⚠️  No strong matches found today.")
    else:
        print(f"\n🏆 Top matches today:")
        for job in matched[:5]:
            print(f"   {job['score']}% {job['title']} @ {job['company']}")
    return {"scored_jobs": matched}

# ── Build Graph ────────────────────────────────────
workflow = StateGraph(AgentState)
workflow.add_node("fetch_jobs",         fetch_jobs)
workflow.add_node("validate_job_links", validate_job_links)
workflow.add_node("analyze_jobs",       analyze_jobs)

workflow.set_entry_point("fetch_jobs")
workflow.add_edge("fetch_jobs",         "validate_job_links")
workflow.add_edge("validate_job_links", "analyze_jobs")
workflow.add_edge("analyze_jobs",       END)

agent = workflow.compile()

# ── Run ────────────────────────────────────────────
print("\n🤖 Job Application Agent Starting...")
print(f"📅 Run date: {RUN_DATE}")
print("="*60)

agent.invoke({
    "cv":             cv_text,
    "jobs":           [],
    "validated_jobs": [],
    "scored_jobs":    [],
})

print(f"\n✅ Done! Open the dashboard to review matches:")
print(f"   streamlit run dashboard.py")
