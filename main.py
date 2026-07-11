"""
Entry point for an interactive run of the job-matching pipeline.
Mirrors the scheduled run in run_daily.py but with a different log target
(per-run tee file in data/run_<stamp>.txt) and friendlier banners.
"""
import os
import sys
import atexit
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv


def _stale_run_logs(log_dir: Path, keep: int = 30) -> list[Path]:
    """Return `data/run_*.txt` files past the `keep` newest, sorted oldest first.

    Pure: does not delete anything. Caller is responsible for `.unlink()`.
    Sorted by mtime descending; the oldest overflow files are returned.
    """
    files = sorted(
        log_dir.glob("run_*.txt"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return files[keep:]


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

load_dotenv()

# Import the pipeline AFTER load_dotenv() so ANTHROPIC_API_KEY is available.
from nodes.pipeline import run_pipeline


RUN_DATE = datetime.now().strftime("%Y-%m-%d")


if __name__ == "__main__":
    print("\n🤖 Job Application Agent Starting...")
    print(f"📅 Run date: {RUN_DATE}")
    print(f"📝 Run log:  {_LOG_PATH}")
    print("=" * 60)

    for stale in _stale_run_logs(_LOG_DIR, keep=30):
        try:
            stale.unlink()
        except OSError:
            pass  # File may have been rotated by a concurrent run — safe to ignore.

    try:
        matched = run_pipeline(min_score=70)
        if matched:
            print(f"\n🏆 Top matches today:")
            for job in matched[:5]:
                print(f"   {job['score']}% {job['title']} @ {job['company']}")
        print(f"\n✅ Done! Open the dashboard to review matches:")
        print(f"   streamlit run dashboard.py")
    except KeyboardInterrupt:
        print("\n🛑 Aborted by user — partial results saved to DB and run log:")
        print(f"   {_LOG_PATH}")
        sys.exit(130)
