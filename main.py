import os
import sys
import atexit
from pathlib import Path
from datetime import datetime
from typing import TypedDict

from langgraph.graph import StateGraph, END
from dotenv import load_dotenv

# ── Tee logging: mirror every print()/stderr line to data/run_<stamp>.txt ──
# Line-buffered so partial output survives Ctrl+C and crashes.
class _Tee:
    def __init__(self, *streams):
        self._streams = streams
    def write(self, data):
        for s in self._streams:
            try:
                s.write(data)
                s.flush()
            except Exception:
                pass
    def flush(self):
        for s in self._streams:
            try:
                s.flush()
            except Exception:
                pass
    def isatty(self):
        return False

_LOG_DIR = Path("data")
_LOG_DIR.mkdir(exist_ok=True)
_LOG_PATH = _LOG_DIR / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
_log_handle = open(_LOG_PATH, "w", encoding="utf-8", buffering=1)
sys.stdout = _Tee(sys.__stdout__, _log_handle)
sys.stderr = _Tee(sys.__stderr__, _log_handle)
atexit.register(_log_handle.close)

from nodes.tracker import (
    init_db, get_known_urls, get_known_title_keys, _title_company_key,
)
from nodes.scraper import scrape_jobs, _url_key
from nodes.analyzer import score_and_filter_jobs
from nodes.validator import validate_jobs

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
    # score_and_filter_jobs persists results incrementally — no extra save here.
    matched, not_matched = score_and_filter_jobs(
        cv=state["cv"],
        jobs=state["validated_jobs"],
        min_score=70,
    )
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
if __name__ == "__main__":
    print("\n🤖 Job Application Agent Starting...")
    print(f"📅 Run date: {RUN_DATE}")
    print(f"📝 Run log:  {_LOG_PATH}")
    print("=" * 60)

    try:
        agent.invoke({
            "cv":             cv_text,
            "jobs":           [],
            "validated_jobs": [],
            "scored_jobs":    [],
        })
        print(f"\n✅ Done! Open the dashboard to review matches:")
        print(f"   streamlit run dashboard.py")
    except KeyboardInterrupt:
        print("\n🛑 Aborted by user — partial results saved to DB and run log:")
        print(f"   {_LOG_PATH}")
        sys.exit(130)
