import sys
import os
import logging
import logging.handlers
from datetime import datetime

os.chdir(os.path.dirname(os.path.abspath(__file__)))
os.makedirs("data", exist_ok=True)

LOG_FILE = "data/scheduler_log.txt"
RUN_LOG  = f"data/run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"


class _Tee:
    """Write every print() to both stdout and a file."""
    def __init__(self, stream, path):
        self._stream = stream
        self._file   = open(path, "w", encoding="utf-8", buffering=1)

    def write(self, data):
        self._stream.write(data)
        self._file.write(data)

    def flush(self):
        self._stream.flush()
        self._file.flush()

    def close(self):
        self._file.close()

    # forward everything else (isatty, fileno, …) to the real stream
    def __getattr__(self, name):
        return getattr(self._stream, name)


sys.stdout = _Tee(sys.stdout, RUN_LOG)
sys.stderr = _Tee(sys.stderr, RUN_LOG)

# ── Logging setup ──────────────────────────────────
_handler = logging.handlers.RotatingFileHandler(
    LOG_FILE, maxBytes=1_000_000, backupCount=10, encoding="utf-8"
)
_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(message)s"))

logging.basicConfig(
    level=logging.INFO,
    handlers=[
        _handler,
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)


def log(message: str):
    """Console + file log (also captured by rotating handler above)."""
    logger.info(message)


def main():
    log("Daily job agent started")
    try:
        from dotenv import load_dotenv
        from nodes.pipeline import run_pipeline
        from nodes.tracker import backup_db
        load_dotenv()

        backup_db()

        log("Running pipeline: scrape (Indeed/Stepstone/XING/LinkedIn/Glassdoor) → validate → score → save...")
        scored = run_pipeline(min_score=50)

        if scored:
            log(f"{len(scored)} strong matches found and saved.")
            log("Open dashboard: streamlit run dashboard.py")
        else:
            log("No strong matches today.")

    except Exception as e:
        logger.exception("Fatal error: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
