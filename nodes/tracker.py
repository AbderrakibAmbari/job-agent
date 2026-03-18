import sqlite3
from datetime import datetime

DB_PATH = "data/applications.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT,
            job_title TEXT,
            platform TEXT,
            date_applied TEXT,
            status TEXT DEFAULT 'Sent',
            cover_letter TEXT,
            job_url TEXT,
            follow_up_date TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_application(company, job_title, platform, 
                     cover_letter, job_url):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO applications 
        (company, job_title, platform, date_applied, 
         cover_letter, job_url, follow_up_date)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        company, job_title, platform,
        datetime.now().strftime("%Y-%m-%d"),
        cover_letter, job_url,
        datetime.now().strftime("%Y-%m-%d")
    ))
    conn.commit()
    conn.close()
    print(f"✅ Saved: {job_title} at {company}")

def get_all_applications():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM applications")
    rows = cursor.fetchall()
    conn.close()
    return rows

def update_status(application_id, new_status):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE applications SET status = ? WHERE id = ?
    """, (new_status, application_id))
    conn.commit()
    conn.close()
    print(f"✅ Updated status to: {new_status}")