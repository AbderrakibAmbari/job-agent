import requests

def scrape_jobs(job_title: str = "Backend Developer",
                location: str = "Bochum",
                max_jobs: int = 5):

    print(f"🔍 Searching jobs: {job_title} in {location}...")

    headers = {
        "X-API-Key": "jobboerse-jobsuche",
        "User-Agent": "Mozilla/5.0"
    }

    params = {
        "was": job_title,
        "wo": location,
        "umkreis": 50,
        "size": max_jobs,
        "page": 1
    }

    url = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs"

    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"❌ API error: {e}")
        return []

    jobs = []
    stellenangebote = data.get("stellenangebote", [])

    if not stellenangebote:
        print("⚠️ No jobs found. Try different search terms.")
        return []

    for job in stellenangebote[:max_jobs]:
        try:
            title         = job.get("titel", "Unknown")
            company       = job.get("arbeitgeber", "Unknown")
            location_name = job.get("arbeitsort", {}).get("ort", location)
            job_id        = job.get("hashId", "")
            job_url       = f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{job_id}"

            description = f"""
Job Title: {title}
Company: {company}
Location: {location_name}
"""
            jobs.append({
                "title": title,
                "company": company,
                "location": location_name,
                "platform": "Arbeitsagentur",
                "url": job_url,
                "description": description.strip(),
                "language": "German"
            })

            print(f"✅ {title} @ {company} — {location_name}")

        except Exception as e:
            print(f"⚠️ Error reading job: {e}")
            continue

    return jobs