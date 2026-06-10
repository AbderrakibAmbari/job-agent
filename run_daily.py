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


def main():
    log("Daily job agent started")
    try:
        from dotenv import load_dotenv
        from nodes.pipeline import run_pipeline
        load_dotenv()

        log("Running pipeline: scrape (Indeed/Stepstone/XING/LinkedIn/Glassdoor) → validate → score → save...")
        scored = run_pipeline(max_jobs=40, min_score=50)

        if scored:
            log(f"{len(scored)} strong matches found and saved.")
            log("Open dashboard: streamlit run dashboard.py")
        else:
            log("No strong matches today.")

    except Exception as e:
        log(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
