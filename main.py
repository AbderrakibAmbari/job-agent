from langgraph.graph import StateGraph, END
from typing import TypedDict, Optional
from nodes.cover_letter import generate_cover_letter
from nodes.tracker import init_db, save_application
from nodes.scraper import scrape_jobs
from nodes.analyzer import score_and_filter_jobs
from dotenv import load_dotenv

load_dotenv()
init_db()

# ── State ──────────────────────────────────────────
class AgentState(TypedDict):
    cv: str
    jobs: list
    scored_jobs: list
    current_job_index: int
    current_job: dict
    cover_letter: str
    approved: Optional[bool]

# ── Load CV ────────────────────────────────────────
with open("my_cv.txt", "r", encoding="utf-8") as f:
    cv_text = f.read()

# ── Nodes ──────────────────────────────────────────
def fetch_jobs(state):
    print("\n🔍 Scraping real jobs from Arbeitsagentur...")
    jobs = scrape_jobs(
        job_title="Backend Developer",
        location="Bochum",
        max_jobs=10
    )
    print(f"📋 Found {len(jobs)} jobs")
    return {"jobs": jobs}

def analyze_jobs(state):
    scored = score_and_filter_jobs(
        cv=state["cv"],
        jobs=state["jobs"],
        min_score=70           # only show 70%+ matches
    )
    if not scored:
        print("⚠️  No strong matches found today. Try again tomorrow.")
    return {"scored_jobs": scored, "current_job_index": 0}

def prepare_job(state):
    index = state["current_job_index"]
    job = state["scored_jobs"][index]
    total = len(state["scored_jobs"])

    print(f"\n{'='*55}")
    print(f"📌 Job {index + 1} of {total}")
    print(f"🏢 {job['company']} — {job['title']}")
    print(f"📍 {job['location']}")
    print(f"🎯 Match Score: {job['score']}% [{job['recommendation']}]")

    if job.get("match_reasons"):
        print("✅ Why you match:")
        for r in job["match_reasons"]:
            print(f"   • {r}")

    if job.get("missing"):
        print("⚠️  Potential gaps:")
        for m in job["missing"]:
            print(f"   • {m}")

    return {"current_job": job}

def write_cover_letter(state):
    job = state["current_job"]
    print(f"\n✍️  Writing tailored cover letter...")
    letter = generate_cover_letter(
        cv=state["cv"],
        job_description=job["description"],
        company=job["company"],
        language=job.get("language", "German")
    )
    return {"cover_letter": letter}

def human_review(state):
    job = state["current_job"]
    print(f"\n📝 Cover Letter:\n{state['cover_letter']}")
    print(f"\n🔗 Apply here: {job['url']}")
    print("="*55)
    decision = input("\n➡️  Approve this application? (y/n): ")
    return {"approved": decision.lower() == "y"}

def save_or_skip(state):
    if state["approved"]:
        job = state["current_job"]
        save_application(
            company=job["company"],
            job_title=job["title"],
            platform=job["platform"],
            cover_letter=state["cover_letter"],
            job_url=job["url"]
        )
        print("✅ Saved to tracker!")
    else:
        print("⏭️  Skipped.")
    return {}

def route_next(state):
    next_index = state["current_job_index"] + 1
    if next_index < len(state["scored_jobs"]):
        return "next"
    return "done"

def increment_index(state):
    return {
        "current_job_index": state["current_job_index"] + 1,
        "approved": None
    }

def no_jobs(state):
    return END

# ── Build Graph ────────────────────────────────────
workflow = StateGraph(AgentState)

workflow.add_node("fetch_jobs",         fetch_jobs)
workflow.add_node("analyze_jobs",       analyze_jobs)
workflow.add_node("prepare_job",        prepare_job)
workflow.add_node("write_cover_letter", write_cover_letter)
workflow.add_node("human_review",       human_review)
workflow.add_node("save_or_skip",       save_or_skip)
workflow.add_node("increment_index",    increment_index)

workflow.set_entry_point("fetch_jobs")
workflow.add_edge("fetch_jobs",         "analyze_jobs")
workflow.add_conditional_edges(
    "analyze_jobs",
    lambda s: "prepare_job" if s["scored_jobs"] else END
)
workflow.add_edge("prepare_job",        "write_cover_letter")
workflow.add_edge("write_cover_letter", "human_review")
workflow.add_edge("human_review",       "save_or_skip")
workflow.add_edge("save_or_skip",       "increment_index")
workflow.add_conditional_edges(
    "increment_index",
    route_next,
    {
        "next": "prepare_job",
        "done": END
    }
)

agent = workflow.compile()

# ── Run ────────────────────────────────────────────
print("\n🤖 Job Application Agent Starting...")
print("="*55)

agent.invoke({
    "cv":                cv_text,
    "jobs":              [],
    "scored_jobs":       [],
    "current_job_index": 0,
    "current_job":       {},
    "cover_letter":      "",
    "approved":          None
})

print("\n🎯 Session complete!")
print("Open your dashboard: streamlit run dashboard.py")