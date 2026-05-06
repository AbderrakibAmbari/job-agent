"""
Feedback log for manual notes about jobs.
Appends notes with date/time, company, title, platform, result, action needed.
"""
import os
from datetime import datetime

FEEDBACK_LOG_PATH = "data/feedback_log.txt"

# Ensure data directory exists
os.makedirs("data", exist_ok=True)


def append_feedback(
    company: str,
    title: str,
    platform: str,
    result: str,
    action_needed: str = ""
):
    """
    Append a feedback entry to the log file.

    Args:
        company: Company name
        title: Job title
        platform: Job platform (Indeed, Stepstone, XING, etc.)
        result: What you found after checking (applied, not_interested, link_broken, etc.)
        action_needed: Next steps if any
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    entry = f"""
{'='*60}
[{timestamp}]
Company: {company}
Title: {title}
Platform: {platform}
Result: {result}
Action Needed: {action_needed if action_needed else 'None'}
{'='*60}
"""
    with open(FEEDBACK_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(entry)

    print(f"  📝 Feedback logged for: {title} @ {company}")


def get_feedback_for_job(company: str, title: str) -> list:
    """
    Retrieve all feedback entries for a specific job.
    """
    if not os.path.exists(FEEDBACK_LOG_PATH):
        return []

    entries = []
    with open(FEEDBACK_LOG_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # Split by entries
    blocks = content.split("=" * 60)
    for block in blocks:
        if company.lower() in block.lower() and title.lower() in block.lower():
            entries.append(block.strip())

    return entries


def list_recent_feedback(limit: int = 10) -> list:
    """Get the most recent feedback entries."""
    if not os.path.exists(FEEDBACK_LOG_PATH):
        return []

    with open(FEEDBACK_LOG_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    blocks = content.split("=" * 60)
    entries = []
    for block in blocks:
        block = block.strip()
        if block and "[" in block:
            entries.append(block)

    return entries[-limit:] if entries else []