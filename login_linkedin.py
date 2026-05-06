"""
Run this once to save your LinkedIn session cookies.
The scraper will reuse them on every run.

Usage:
    python login_linkedin.py
"""
import json
import os
from playwright.sync_api import sync_playwright

COOKIE_FILE = "data/linkedin_cookies.json"
os.makedirs("data", exist_ok=True)

print("Opening LinkedIn in a real browser window.")
print("Log in normally, then come back here and press Enter.")
print()

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context()
    page    = context.new_page()
    page.goto("https://www.linkedin.com/login")

    input(">>> Press Enter AFTER you have fully logged in to LinkedIn...")

    cookies = context.cookies()
    with open(COOKIE_FILE, "w", encoding="utf-8") as f:
        json.dump(cookies, f, indent=2)

    browser.close()

print(f"\n✅ Cookies saved to {COOKIE_FILE}")
print("The scraper will now use these cookies automatically.")
print("Re-run this script if LinkedIn asks you to log in again.")
