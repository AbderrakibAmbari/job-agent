import sys
import os
from datetime import datetime

os.chdir(os.path.dirname(os.path.abspath(__file__)))

LOG_FILE = "data/scheduler_log.txt"


def log(message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


STRONG_MATCH_THRESHOLD = 85


def _select_strong_matches(jobs: list, threshold: int = STRONG_MATCH_THRESHOLD) -> list:
    """Return jobs with match_score >= threshold, sorted by score desc, capped at 5.

    Pure function — safe to unit-test.
    """
    strong = [j for j in (jobs or []) if int(j.get("score", 0)) >= threshold]
    strong.sort(key=lambda j: int(j.get("score", 0)), reverse=True)
    return strong[:5]


def _format_notification_body(jobs: list) -> str:
    """One line per job: score, title, company. Toast bodies wrap at ~5 lines."""
    return "\n".join(
        f"[{j.get('score', 0)}] {j.get('title', '?')} @ {j.get('company', '?')}"
        for j in jobs
    )


def _notify_strong_matches(jobs: list) -> int:
    """Raise one Windows toast if any strong matches exist. Returns count notified."""
    strong = _select_strong_matches(jobs)
    if not strong:
        return 0
    try:
        from winotify import Notification, audio
        n = Notification(
            app_id="Job Agent",
            title=f"{len(strong)} strong match{'es' if len(strong) > 1 else ''} today",
            msg=_format_notification_body(strong),
        )
        n.set_audio(audio.Default, loop=False)
        n.show()
    except Exception as e:
        log(f"[notify] toast failed: {e}")
    return len(strong)


def main():
    log("Daily job agent started")
    try:
        from dotenv import load_dotenv
        from nodes.pipeline import run_pipeline
        load_dotenv()

        log("Running pipeline: scrape (Indeed/Stepstone/XING/LinkedIn/Glassdoor) → validate → score → save...")
        scored = run_pipeline(min_score=50)

        if scored:
            log(f"{len(scored)} strong matches found and saved.")
            log("Open dashboard: streamlit run dashboard.py")
            n_notified = _notify_strong_matches(scored)
            if n_notified:
                log(f"[notify] raised toast for {n_notified} match(es) with score >= {STRONG_MATCH_THRESHOLD}")
        else:
            log("No strong matches today.")

    except Exception as e:
        log(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
