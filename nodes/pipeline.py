"""
Shared pipeline: scrape -> validate -> score -> save.
Both run_daily.py (automated) and main.py (interactive) build on these steps.

`score_and_filter_jobs` persists results to the DB incrementally as each job
is scored, so a rate-limit timeout or Ctrl+C still keeps partial progress.
"""
from nodes.scraper import scrape_jobs, _url_key
from nodes.validator import validate_jobs
from nodes.analyzer import score_and_filter_jobs
from nodes.tracker import (
    init_db, get_known_urls, get_known_title_keys, _title_company_key,
)


def _job_title_key(job: dict) -> str:
    return _title_company_key(job.get("title", ""), job.get("company", ""))


def run_pipeline(min_score: int = 70) -> list:
    """
    Run the full job-matching pipeline. Persistence happens inside
    score_and_filter_jobs (incremental). Returns the matched list for logging.
    """
    init_db()

    with open("my_cv.txt", "r", encoding="utf-8") as f:
        cv = f.read()

    jobs = scrape_jobs()
    if not jobs:
        print("[pipeline] Scraper returned 0 jobs.")
        return []

    jobs = validate_jobs(jobs)
    alive = [j for j in jobs if j.get("link_status") != "expired"]
    expired = len(jobs) - len(alive)

    known_urls = get_known_urls()
    after_url = [j for j in alive if _url_key(j.get("url", "")) not in known_urls]

    known_titles = get_known_title_keys()
    new_jobs = [j for j in after_url if _job_title_key(j) not in known_titles]

    url_dupes   = len(alive) - len(after_url)
    title_dupes = len(after_url) - len(new_jobs)

    print(
        f"[pipeline] Scraped: {len(jobs)}  |  Alive: {len(alive)}  |  "
        f"Expired: {expired}  |  URL-known: {url_dupes}  |  "
        f"Title-known: {title_dupes}  |  New: {len(new_jobs)}"
    )

    if not new_jobs:
        print("[pipeline] Nothing new to score today.")
        return []

    try:
        matched, not_matched = score_and_filter_jobs(cv=cv, jobs=new_jobs, min_score=min_score)
    except KeyboardInterrupt:
        print("[pipeline] Interrupted — partial results already persisted in DB.")
        raise

    print(f"[pipeline] Scored: {len(new_jobs)}  |  Matched (>={min_score}%): {len(matched)}  |  Below threshold: {len(not_matched)}")
    return matched
