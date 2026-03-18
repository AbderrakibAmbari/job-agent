import sys
import os
from datetime import datetime

# Make sure we're in the right directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Log file to track runs
LOG_FILE = "data/scheduler_log.txt"

def log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def main():
    log("🤖 Daily job agent started")

    try:
        from dotenv import load_dotenv
        from nodes.scraper import scrape_jobs
        from nodes.cover_letter import generate_cover_letter
        from nodes.tracker import init_db, save_application, get_all_applications
        import sqlite3

        load_dotenv()
        init_db()

        # ── Scrape jobs ────────────────────────────────
        log("🔍 Scraping jobs...")
        jobs = scrape_jobs(
            job_title="Backend Developer",
            location="Bochum",
            max_jobs=10
        )
        log(f"📋 Found {len(jobs)} jobs")

        if not jobs:
            log("⚠️ No jobs found today. Stopping.")
            return

        # ── Load already applied jobs ──────────────────
        conn = sqlite3.connect("data/applications.db")
        cursor = conn.cursor()
        cursor.execute("SELECT job_url FROM applications")
        already_applied = set(row[0] for row in cursor.fetchall())
        conn.close()

        # ── Load CV ────────────────────────────────────
        with open("my_cv.txt", "r", encoding="utf-8") as f:
            cv = f.read()

        # ── Process each new job ───────────────────────
        new_jobs = [j for j in jobs if j["url"] not in already_applied]
        log(f"🆕 New jobs (not yet applied): {len(new_jobs)}")

        saved_count = 0
        for job in new_jobs:
            try:
                log(f"✍️  Writing cover letter for {job['company']}...")
                letter = generate_cover_letter(
                    cv=cv,
                    job_description=job["description"],
                    company=job["company"],
                    language="German"
                )

                # Save as PENDING — you review in dashboard
                conn = sqlite3.connect("data/applications.db")
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO applications
                    (company, job_title, platform, date_applied,
                     cover_letter, job_url, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    job["company"],
                    job["title"],
                    job["platform"],
                    datetime.now().strftime("%Y-%m-%d"),
                    letter,
                    job["url"],
                    "Pending Review"   # ← you review these in dashboard
                ))
                conn.commit()
                conn.close()

                saved_count += 1
                log(f"✅ Saved: {job['title']} @ {job['company']}")

            except Exception as e:
                log(f"❌ Error processing {job['company']}: {e}")
                continue

        log(f"🎯 Done! {saved_count} new applications ready for your review.")
        log("👉 Open dashboard to review: streamlit run dashboard.py")

    except Exception as e:
        log(f"💥 Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()