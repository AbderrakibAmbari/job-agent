import time
import re
import random
import logging
import json
import os
from datetime import datetime
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from playwright.sync_api import sync_playwright

LINKEDIN_COOKIE_FILE = "data/linkedin_cookies.json"

logger = logging.getLogger(__name__)

# Rotating log for scrape summaries
_scrape_log_handler = None


def _get_scrape_logger():
    global _scrape_log_handler
    sl = logging.getLogger("scrape_summary")
    if not sl.handlers:
        os.makedirs("data", exist_ok=True)
        from logging.handlers import RotatingFileHandler
        h = RotatingFileHandler(
            "data/scrape_log.txt", maxBytes=2_000_000, backupCount=5, encoding="utf-8"
        )
        h.setFormatter(logging.Formatter("%(message)s"))
        sl.addHandler(h)
        sl.setLevel(logging.INFO)
        sl.propagate = False
    return sl


# ── Pre-compiled filters ────────────────────────────
_EXPERIENCE_RE = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\b[3-9]\+?\s*jahre?\b",
        r"\bmin\w*\.?\s*[3-9]\s*jahre?\b",
        r"\b[3-9]\s*years?\b",
        r"\bminimum\s*[3-9]\s*years?\b",
        r"\b[3-9]\+\s*years?\b",
        r"\bmehrjährige\b",
        r"\bberufserfahrung\s*von\s*mind\w*\.?\s*[3-9]\b",
    ]
]
_POSTCODE_RE    = re.compile(r'\b[A-Z]-?\d{5}\b|\b\d{5}\b')
_TRAILING_RE    = re.compile(r'\s+\d+.*$')
_DISTRICT_RE    = re.compile(r'\s+gebiet$', re.IGNORECASE)
_PARENS_RE      = re.compile(r'\s*\(.*?\)\s*')

DEPRIORITIZE_TITLES = [
    "senior", "lead", "principal", "staff", "head of",
    "manager", "director", "architect",
    "sales", "recruiting", "customer support", "call center",
    "callcenter", "sachbearbeiter", "vertrieb",
]

# "consultant"/"berater" are only deprioritized when there's no junior/entry indicator
_JUNIOR_INDICATOR = re.compile(
    r"\b(junior|trainee|berufseinsteiger|absolvent|graduate|praktikum|werkstudent|einstieg|entry)\b",
    re.IGNORECASE,
)
_CONSULTANT_WORDS = re.compile(r"\b(consultant|berater|consulting|beratung)\b", re.IGNORECASE)

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
]

# Max seconds to spend on one platform before moving on
PLATFORM_TIMEOUT = 600


def requires_experience(text: str) -> bool:
    t = text.lower()
    return any(p.search(t) for p in _EXPERIENCE_RE)


def is_deprioritized(title: str) -> bool:
    t = title.lower()
    if any(w in t for w in DEPRIORITIZE_TITLES):
        return True
    # Consultant/Berater roles are only filtered when there's no junior/trainee indicator
    if _CONSULTANT_WORDS.search(t) and not _JUNIOR_INDICATOR.search(t):
        return True
    return False


def extract_city(location: str) -> str:
    if not location:
        return "Unknown"
    loc = _POSTCODE_RE.sub('', location).strip()
    for sep in [',', '•', '|', '-', '(']:
        if sep in loc:
            parts = [p.strip() for p in loc.split(sep) if p.strip()]
            if parts:
                city = _TRAILING_RE.sub('', parts[0])
                city = _DISTRICT_RE.sub('', city).strip()
                if city and len(city) > 1:
                    return city
    return _PARENS_RE.sub('', loc).strip() or "Unknown"


def _url_key(url: str) -> str:
    """Normalise a URL for dedup: strip query params, trailing slash, lowercase."""
    return url.split("?")[0].rstrip("/").lower() if url else ""


def _title_key(job: dict) -> str:
    """
    Merge key for cross-platform dedup.
    Ignores company when it is Unknown so XING and LinkedIn entries for the
    same role still merge even when one platform didn't extract the company.
    Strips gender suffixes like (m/w/d), (w/m/d), (all genders) before comparing.
    """
    import re
    title = re.sub(r"\s*\(.*?\)\s*", "", job.get("title", "")).lower().strip()
    company = job.get("company", "").lower().strip()
    if company in ("unknown", "", "n/a"):
        return title
    return f"{title}_{company}"


def deduplicate(jobs: list) -> list:
    seen_urls: set = set()
    merged: dict = {}

    for job in jobs:
        url = job.get("url", "")
        ukey = _url_key(url)

        # Skip exact URL duplicates
        if ukey and ukey in seen_urls:
            # Still try to add this platform URL to the existing merged entry
            tkey = _title_key(job)
            if tkey in merged:
                entry = {"platform": job.get("platform", ""), "url": url}
                existing = merged[tkey]["urls"]
                if url and entry not in existing and not any(_url_key(e["url"]) == ukey for e in existing):
                    existing.append(entry)
            continue
        if ukey:
            seen_urls.add(ukey)

        tkey = _title_key(job)
        if tkey not in merged:
            job["urls"] = [{"platform": job.get("platform", ""), "url": url}]
            merged[tkey] = job
        else:
            # Same job, different platform — append URL and prefer the richer record
            entry = {"platform": job.get("platform", ""), "url": url}
            existing_urls = merged[tkey]["urls"]
            if url and not any(_url_key(e["url"]) == ukey for e in existing_urls):
                existing_urls.append(entry)
            # Upgrade Unknown company/location with real values if available
            if merged[tkey].get("company", "Unknown") in ("Unknown", "", "N/A"):
                if job.get("company", "Unknown") not in ("Unknown", "", "N/A"):
                    merged[tkey]["company"] = job["company"]
            if merged[tkey].get("location", "") in ("", "Unknown"):
                if job.get("location", "") not in ("", "Unknown"):
                    merged[tkey]["location"] = job["location"]

    return list(merged.values())


# ── Search Terms ───────────────────────────────────
# Ordered by priority so front-loaded slices in _scrape_platform hit the best terms first.
JUNIOR_TERMS = [
    # Tier 1 — highest recall German compounds
    "Junior Softwareentwickler",
    "Junior Backend Entwickler",
    "Junior Software Engineer",
    "Junior Backend Developer",
    # Tier 1 — AI/GenAI (fastest-growing category, top candidate fit)
    "Junior AI Engineer",
    "Junior Generative AI Engineer",
    "Junior NLP Engineer",
    "AI Software Engineer",
    # Tier 1 — QA/Test Automation (candidate has direct Werkstudent experience)
    "Junior QA Engineer",
    "Junior Test Automation Engineer",
    "Junior Software Tester",
    "Junior SDET",
    # Tier 1 — IT Consulting / Trainee Programs
    "Junior IT Consultant",
    "IT Trainee",
    "Trainee IT Consulting",
    "Trainee Softwareentwicklung",
    # Tier 1 — Full Stack / Cloud / DevOps
    "Junior Full Stack Developer",
    "Junior Full Stack Entwickler",
    "Junior DevOps Engineer",
    "Junior Cloud Engineer",
    "Junior Platform Engineer",
    # Tier 1 — Data
    "Junior Data Engineer",
    "Junior Data Analyst",
    "Junior Data Scientist",
    "Junior BI Developer",
    # Tier 2 — Language-specific English
    "Junior Python Developer",
    "Junior Java Developer",
    "Junior Machine Learning Engineer",
    "Junior LLM Engineer",
    # Tier 2 — Language-specific German
    "Junior Python Entwickler",
    "Junior Java Entwickler",
    "Junior Full Stack Entwickler",
    "Junior Webentwickler",
    "Junior Frontend Entwickler",
    "Junior Kotlin Entwickler",
    "Junior TypeScript Entwickler",
    # Tier 2 — ERP / SAP / Dynamics
    "Junior SAP Berater",
    "Junior SAP Consultant",
    "Junior ERP Consultant",
    "Junior Dynamics 365 Consultant",
    "Junior ABAP Entwickler",
    # Tier 2 — Broader entry-level
    "Junior KI Engineer",
    "Junior Analytics Engineer",
    "Junior SRE",
    "Direkteinstieg IT Beratung",
    "Young Professional IT",
    "Junior Anwendungsentwickler",
    "Junior Wirtschaftsinformatiker",
    # Tier 3 — German entry-level qualifiers
    "Trainee Software Engineer",
    "Berufseinsteiger Entwickler",
    "Berufseinsteiger Softwareentwicklung",
    "Softwareentwickler Berufseinsteiger",
    "Absolvent Informatik",
    "Quereinsteiger Softwareentwickler",
    "Trainee IT",
]

WERKSTUDENT_TERMS = [
    "Werkstudent Softwareentwicklung",
    "Werkstudent Backend",
    "Werkstudent Full Stack",
    "Werkstudent Python",
    "Werkstudent Java",
    "Werkstudent IT",
    "Werkstudent DevOps",
    "Werkstudent Cloud",
    "Werkstudent Data Science",
    "Werkstudent Machine Learning",
    "Werkstudent Webentwicklung",
    "Werkstudent Kotlin",
    "Werkstudent TypeScript",
    "Werkstudent QA",
    "Werkstudent AI",
]

PRAKTIKUM_TERMS = [
    "Praktikum Softwareentwicklung",
    "Praktikum Backend",
    "Praktikum Webentwicklung",
    "Praktikum IT",
    "Praktikum Informatik",
    "Praktikum Python",
    "Praktikum Java",
    "Praktikum DevOps",
    "Praktikum Cloud",
    "Praktikum Data Science",
    "Praktikum SAP",
    "Praktikum SAP HANA",
    "Praktikum AI",
    "Praktikum Machine Learning",
    "Praktikum QA",
]

# Used primarily for the Arbeitsagentur API (many SAP/training roles only listed there)
SAP_TRAINING_TERMS = [
    "SAP Praktikant",
    "Junior SAP Berater",
    "Junior SAP Consultant",
    "Trainee SAP Beratung",
    "SAP Trainee",
    "adesso Trainee",
    "Capgemini Junior",
    "Materna Trainee",
    "Sopra Steria Junior",
    "msg Trainee",
    "Trainee IT Beratung",
    "Absolventenprogramm IT",
]

SEARCH_TERMS = JUNIOR_TERMS + WERKSTUDENT_TERMS + PRAKTIKUM_TERMS + SAP_TRAINING_TERMS

# Subset used by each Playwright platform — front-loaded by priority
PLATFORM_SEARCH_TERMS = JUNIOR_TERMS[:15] + WERKSTUDENT_TERMS[:5] + PRAKTIKUM_TERMS[:5]

# ── Target Regions ─────────────────────────────────
REGIONS = [
    "Nordrhein-Westfalen",
    "Hessen",
    "Saarland",
    "Rheinland-Pfalz",
    "Thüringen",
    "Niedersachsen",
    "Bremen",
    "Hamburg",
    "Sachsen",
]

# ── Platform Configurations ────────────────────────
PLATFORM_CONFIGS = {
    "Indeed": {
        "build_url": lambda term, region, n: (
            f"https://de.indeed.com/jobs"
            f"?q={term.replace(' ', '+')}"
            f"&l={region.replace(' ', '+')}"
            f"&limit={n}"
        ),
        "cookie_selector": "button#onetrust-accept-btn-handler",
        "card_selector": "div.job_seen_beacon",
        "selectors": {
            "title":   [
                "[data-testid='jobTitle'] span",
                "[data-testid='jobTitle']",
                "h2.jobTitle span[id]",
                "h2 a span",
                "h2 span",
            ],
            "company": [
                "[data-testid='company-name']",
                "span[data-testid='company-name']",
                "span.companyName",
                "span[class*='company']",
            ],
            "location": [
                "[data-testid='text-location']",
                "div.companyLocation",
                "div[class*='location']",
            ],
            "link": [
                "h2.jobTitle a",
                "a[data-jk]",
                "a[href*='/rc/clk']",
                "a[href*='indeed']",
            ],
            "snippet": [
                "[data-testid='snippet']",
                "div.job-snippet",
                "div[class*='snippet']",
                "ul.job-snippet",
            ],
        },
        "link_base": "https://de.indeed.com",
        "login_indicators": [],
        "quick_apply_selector": "[data-testid='indeedApply']",
    },
    "Stepstone": {
        "build_url": lambda term, region, n: (
            f"https://www.stepstone.de/jobs"
            f"/{term.replace(' ', '-')}"
            f"/in-{region.replace(' ', '-')}"
        ),
        "cookie_selector": "button[id='ccmgt_explicit_accept']",
        "card_selector": "article[data-at='job-item'], article[class*='job'], div[class*='JobCard'], article",
        "selectors": {
            "title": [
                "[data-at='job-item-title']",
                "h2[class*='title']",
                "h3[class*='title']",
                "h2", "h3",
            ],
            "company": [
                "[data-at='job-item-company-name']",
                "span[class*='company']",
                "div[class*='company']",
            ],
            "location": [
                "[data-at='job-item-location']",
                "span[class*='location']",
                "div[class*='location']",
            ],
            "link": [
                "a[href*='stellenangebote']",
                "a[data-at='job-item-title']",
                "a[href*='stepstone.de']",
                "h2 a", "h3 a",
            ],
            "snippet": [
                "[data-at='job-item-description']",
                "div[class*='description']",
                "p[class*='description']",
                "span[class*='description']",
            ],
        },
        "link_base": "https://www.stepstone.de",
        "login_indicators": [],
        "quick_apply_selector": "[data-testid='quick-apply'], .quick-apply",
    },
    "XING": {
        "build_url": lambda term, region, n: (
            f"https://www.xing.com/jobs/search"
            f"?keywords={term.replace(' ', '+')}"
            f"&location={region.replace(' ', '+')}"
            f"&radius=50"
        ),
        "cookie_selector": None,
        "card_selector": "[data-testid='job-posting-item'], article",
        "selectors": {
            "title":   ["h2", "h3", "[data-testid='job-title']", "a[data-testid='job-posting-title']"],
            "company": [
                "[data-testid='company-name']",
                "a[data-testid='company-link']",
                "span[class*='company']",
                "div[class*='company'] span",
                "span[class*='employer']",
                "a[class*='company']",
                "[class*='CompanyName']",
                "span.company-name",
            ],
            "location": ["[data-testid='location']", "span[class*='location']", "div[class*='location']"],
            "link":     ["a[href*='/jobs/']", "a[data-testid='job-posting-title']"],
            "snippet": [
                "[data-testid='job-description-preview']",
                "p[class*='description']",
                "div[class*='description']",
                "span[class*='description']",
            ],
        },
        "link_base": "https://www.xing.com",
        "login_indicators": [],
        "quick_apply_selector": "[data-testid='quick-apply'], .quick-apply",
    },
    "LinkedIn": {
        "build_url": lambda term, region, n: (
            f"https://www.linkedin.com/jobs/search/"
            f"?keywords={term.replace(' ', '%20')}"
            f"&location={region.replace(' ', '%20')}%2C%20Deutschland"
            f"&f_TPR=r86400"
        ),
        "cookie_selector": None,
        "card_selector": "div.base-card",
        "selectors": {
            "title":   ["h3.base-search-card__title", "span.sr-only"],
            "company": ["h4.base-search-card__subtitle", "a.hidden-nested-link"],
            "location":["span.job-search-card__location"],
            "link":    ["a.base-card__full-link", "a[href*='/jobs/view/']"],
            "snippet": [
                "p.job-search-card__snippet",
                "div[class*='snippet']",
                "p[class*='description']",
            ],
        },
        "link_base": "",
        "login_indicators": [
            "linkedin.com/login",
            "linkedin.com/authwall",
            "linkedin.com/checkpoint",
        ],
        "quick_apply_selector": None,
    },
    "Glassdoor": {
        "build_url": lambda term, region, n: (
            f"https://www.glassdoor.de/Job/jobs.htm"
            f"?sc.keyword={term.replace(' ', '+')}"
            f"&locT=N&locName={region.replace(' ', '+')}"
        ),
        "cookie_selector": "button[data-test='accept-btn']",
        "card_selector": "li[data-test='jobListing'], li.react-job-listing",
        "selectors": {
            "title":   ["a[data-test='job-title']", "a[class*='jobTitle']"],
            "company": [
                "span.EmployerProfile_compactEmployerName__9MGcV",
                "div.EmployerProfile_employerInfo__VS3IM span",
                "span[class*='employerName']",
            ],
            "location":["div[data-test='emp-location']", "span[class*='location']"],
            "link":    ["a[data-test='job-title']", "a[class*='jobTitle']"],
            "snippet": [
                "span[data-test='descSnippet']",
                "div[data-test='description']",
                "div[class*='snippet']",
                "p[class*='description']",
            ],
        },
        "link_base": "https://www.glassdoor.de",
        "login_indicators": [
            "glassdoor.de/profile/login",
            "glassdoor.com/profile/login",
        ],
        "quick_apply_selector": None,
    },
}


def _selector_broken(s: dict) -> bool:
    """True when a platform returned cards but extracted nothing — likely broken selectors."""
    return (
        s["cards_found"] > 0
        and s["added"] == 0
        and s["exp_filtered"] == 0
        and s["deprioritized"] == 0
    )


def _query_first(card, selectors: list):
    """Return first element matched by any selector in the list."""
    for sel in selectors:
        try:
            el = card.query_selector(sel)
            if el:
                return el
        except Exception:
            continue
    return None


def _build_job(card, config: dict, region: str, platform: str) -> tuple:
    """Build a job dict from a card element. Returns (job|None, reason)."""
    selectors  = config["selectors"]
    title_el   = _query_first(card, selectors["title"])
    company_el = _query_first(card, selectors["company"])
    loc_el     = _query_first(card, selectors["location"])
    link_el    = _query_first(card, selectors["link"])
    snippet_el = _query_first(card, selectors.get("snippet", []))

    title   = title_el.inner_text().strip() if title_el else ""
    company = company_el.inner_text().strip() if company_el else "Unknown"
    loc     = loc_el.inner_text().strip() if loc_el else region
    snippet = snippet_el.inner_text().strip() if snippet_el else ""

    desc = f"Job Title: {title}\nCompany: {company}\nLocation: {loc}"
    if snippet:
        desc += f"\nDescription: {snippet[:500]}"

    job_url = ""
    if link_el:
        href = link_el.get_attribute("href") or ""
        if href:
            base = config["link_base"]
            job_url = f"{base}{href}" if href.startswith("/") and base else href

    if not title or not job_url:
        return None, "no_data"
    if requires_experience(title + desc):
        return None, "exp_filter"
    if is_deprioritized(title):
        return None, "deprioritized"

    quick_apply = False
    qs = config.get("quick_apply_selector")
    if qs:
        try:
            if card.query_selector(qs) or "schnell" in desc.lower():
                quick_apply = True
        except Exception:
            pass

    return {
        "title":       title,
        "company":     company,
        "location":    loc,
        "city":        extract_city(loc),
        "region":      region,
        "platform":    platform,
        "url":         job_url,
        "description": desc,
        "language":    "German",
        "quick_apply": quick_apply,
        "scraped_at":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }, "ok"


def _scrape_platform(platform: str, max_per_search: int = 25) -> tuple:
    """Generic platform scraper. Returns (jobs_list, search_stats_list)."""
    config      = PLATFORM_CONFIGS[platform]
    jobs        = []
    search_stats = []
    start_time  = time.time()

    terms = PLATFORM_SEARCH_TERMS

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(user_agent=random.choice(_USER_AGENTS))

            if platform == "LinkedIn" and os.path.exists(LINKEDIN_COOKIE_FILE):
                try:
                    with open(LINKEDIN_COOKIE_FILE, "r", encoding="utf-8") as f:
                        cookies = json.load(f)
                    context.add_cookies(cookies)
                    print(f"  [cookie] LinkedIn: loaded saved session cookies")
                except Exception as e:
                    print(f"  [warn] LinkedIn: could not load cookies -- {e}")
                    print(f"      Run: python login_linkedin.py")

            page = context.new_page()
            page.set_extra_http_headers({"User-Agent": random.choice(_USER_AGENTS)})

            platform_dead = False
            for region in REGIONS:
                if platform_dead:
                    break
                if time.time() - start_time > PLATFORM_TIMEOUT:
                    print(f"  [timeout] {platform}: timeout reached, stopping early")
                    break

                for term in terms:
                    # Werkstudent and Praktikum: NRW only
                    if term.startswith(("Werkstudent", "Praktikum")) and region != "Nordrhein-Westfalen":
                        continue

                    added = exp_filtered = deprioritized = parse_errors = no_data = 0
                    cards_found = 0

                    try:
                        url = config["build_url"](term, region, max_per_search)
                        page.goto(url, timeout=20000)

                        for indicator in config.get("login_indicators", []):
                            if indicator in page.url:
                                print(f"  [login] {platform} requires login -- skipping")
                                return jobs, search_stats

                        if config.get("cookie_selector"):
                            try:
                                page.click(config["cookie_selector"], timeout=3000)
                                time.sleep(0.5)
                            except Exception:
                                pass

                        time.sleep(random.uniform(1.5, 3.5))

                        cards = page.query_selector_all(config["card_selector"])
                        cards_found = len(cards)

                        for card in cards[:max_per_search]:
                            try:
                                job, reason = _build_job(card, config, region, platform)
                                if reason == "ok":
                                    jobs.append(job)
                                    added += 1
                                    print(f"  [+] {job['title']} @ {job['company']} -- {job['location']}")
                                    print(f"      {job['url']}")
                                elif reason == "exp_filter":
                                    exp_filtered += 1
                                elif reason == "deprioritized":
                                    deprioritized += 1
                                else:
                                    no_data += 1
                            except Exception as e:
                                parse_errors += 1
                                logger.debug("Card parse error (%s): %s", platform, e)

                    except Exception as e:
                        print(f"  [err] {platform} error ({term} / {region}): {e}")

                    # One-liner summary per search
                    print(
                        f"  {term[:32]:<32} | {region[:18]:<18} | "
                        f"cards={cards_found} added={added} exp_filtered={exp_filtered} depr={deprioritized}"
                    )

                    search_stats.append({
                        "platform":     platform,
                        "term":         term,
                        "region":       region,
                        "cards_found":  cards_found,
                        "added":        added,
                        "exp_filtered": exp_filtered,
                        "deprioritized":deprioritized,
                        "parse_errors": parse_errors,
                        "no_data":      no_data,
                    })

                    # Bail-out #1 — broken selectors: cards visible but nothing extracted.
                    if len(search_stats) >= 3 and all(_selector_broken(s) for s in search_stats[-3:]):
                        print(f"  [warn] {platform}: 3 consecutive broken-selector searches -- skipping platform")
                        platform_dead = True
                        break

                    # Bail-out #2 — platform truly dead (bot block, no DOM at all):
                    # 10 consecutive zero-card searches. Higher threshold so that terms
                    # that simply have no results (e.g. Praktikum on LinkedIn) don't
                    # kill the whole platform run.
                    if len(search_stats) >= 10 and all(s["cards_found"] == 0 for s in search_stats[-10:]):
                        print(f"  [warn] {platform}: 10 consecutive zero-card searches -- platform likely blocked, skipping")
                        platform_dead = True
                        break

                    time.sleep(random.uniform(2.0, 5.0))

            page.close()
        finally:
            browser.close()

    return jobs, search_stats


def _print_summary(all_stats: list) -> None:
    """Print and log a post-scrape summary table."""
    by_platform: dict = defaultdict(lambda: {
        "terms": set(), "cards": 0, "added": 0,
        "exp": 0, "depr": 0, "errors": 0,
    })

    term_totals: dict = defaultdict(int)

    for s in all_stats:
        p = s["platform"]
        by_platform[p]["terms"].add(s["term"])
        by_platform[p]["cards"]  += s["cards_found"]
        by_platform[p]["added"]  += s["added"]
        by_platform[p]["exp"]    += s["exp_filtered"]
        by_platform[p]["depr"]   += s["deprioritized"]
        by_platform[p]["errors"] += s["parse_errors"]
        term_totals[s["term"]]   += s["added"]

    totals = {
        "terms": set(s["term"] for s in all_stats),
        "cards": sum(v["cards"] for v in by_platform.values()),
        "added": sum(v["added"] for v in by_platform.values()),
        "exp":   sum(v["exp"]   for v in by_platform.values()),
        "depr":  sum(v["depr"]  for v in by_platform.values()),
    }

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "",
        f"╔{'═'*70}╗",
        f"║  Scrape Summary — {now}{' '*(70 - 21 - len(now))}║",
        f"╠{'═'*16}╦{'═'*8}╦{'═'*10}╦{'═'*8}╦{'═'*11}╦{'═'*13}╣",
        f"║ {'Platform':<14} ║ {'Terms':>6} ║ {'Cards':>8} ║ {'Added':>6} ║ {'Exp ❌':>9} ║ {'Depr ❌':>11} ║",
        f"╠{'═'*16}╬{'═'*8}╬{'═'*10}╬{'═'*8}╬{'═'*11}╬{'═'*13}╣",
    ]
    for plat, d in sorted(by_platform.items()):
        lines.append(
            f"║ {plat:<14} ║ {len(d['terms']):>6} ║ {d['cards']:>8} ║ "
            f"{d['added']:>6} ║ {d['exp']:>9} ║ {d['depr']:>11} ║"
        )
    lines += [
        f"╠{'═'*16}╬{'═'*8}╬{'═'*10}╬{'═'*8}╬{'═'*11}╬{'═'*13}╣",
        f"║ {'TOTAL':<14} ║ {len(totals['terms']):>6} ║ {totals['cards']:>8} ║ "
        f"{totals['added']:>6} ║ {totals['exp']:>9} ║ {totals['depr']:>11} ║",
        f"╚{'═'*16}╩{'═'*8}╩{'═'*10}╩{'═'*8}╩{'═'*11}╩{'═'*13}╝",
    ]

    top_terms = sorted(term_totals.items(), key=lambda x: -x[1])[:3]
    if top_terms:
        top_str = ", ".join(f"{t} ({n})" for t, n in top_terms)
        lines.append(f"  Top terms by jobs added: {top_str}")

    output = "\n".join(lines)
    print(output)
    _get_scrape_logger().info(output)


def scrape_arbeitsagentur(terms: list, regions: list) -> tuple:
    """Scrape Bundesagentur für Arbeit via public REST API. No Playwright needed."""
    import requests

    BA_URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs"
    headers = {"X-API-Key": "jobboerse-jobsuche"}

    jobs: list = []
    stats: list = []
    seen_refnrs: set = set()

    for region in regions:
        for term in terms:
            # Werkstudent and Praktikum: NRW only
            if term.startswith(("Werkstudent", "Praktikum")) and region != "Nordrhein-Westfalen":
                continue

            added = exp_filtered = deprioritized = errors = 0
            cards_found = 0
            try:
                params = {
                    "was": term,
                    "wo": region,
                    "berufsfeld": "Informatik",
                    "page": 1,
                    "size": 25,
                }
                r = requests.get(BA_URL, headers=headers, params=params, timeout=10)
                r.raise_for_status()
                data = r.json()
                postings = data.get("stellenangebote", []) or []
                cards_found = len(postings)

                for item in postings:
                    refnr = item.get("refnr", "")
                    if not refnr or refnr in seen_refnrs:
                        continue
                    seen_refnrs.add(refnr)

                    title   = item.get("titel", "").strip()
                    company = item.get("arbeitgeber", "Unknown") or "Unknown"
                    ort     = (item.get("arbeitsort") or {}).get("ort", region)

                    if not title:
                        continue
                    if requires_experience(title):
                        exp_filtered += 1
                        continue
                    if is_deprioritized(title):
                        deprioritized += 1
                        continue

                    job_url = f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{refnr}"
                    jobs.append({
                        "title":       title,
                        "company":     company,
                        "location":    ort,
                        "city":        extract_city(ort),
                        "region":      region,
                        "platform":    "Arbeitsagentur",
                        "url":         job_url,
                        "description": f"Job Title: {title}\nCompany: {company}\nLocation: {ort}",
                        "language":    "German",
                        "quick_apply": False,
                        "scraped_at":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    })
                    added += 1

                time.sleep(0.3)

            except Exception as e:
                errors = 1
                logger.debug("Arbeitsagentur error (%s / %s): %s", term, region, e)

            stats.append({
                "platform":     "Arbeitsagentur",
                "term":         term,
                "region":       region,
                "cards_found":  cards_found,
                "added":        added,
                "exp_filtered": exp_filtered,
                "deprioritized": deprioritized,
                "parse_errors": errors,
                "no_data":      0,
            })

    print(f"  [OK] Arbeitsagentur finished: {len(jobs)} unique jobs")
    return jobs, stats


def _run_arbeitsagentur() -> tuple:
    ba_terms = SAP_TRAINING_TERMS + JUNIOR_TERMS[:10]
    print(f"\n[BA] Scraping Arbeitsagentur API ({len(ba_terms)} terms x {len(REGIONS)} regions)...")
    return scrape_arbeitsagentur(ba_terms, REGIONS)


def scrape_jobs() -> list:
    all_jobs: list = []
    all_stats: list = []
    platforms = list(PLATFORM_CONFIGS.keys())

    print(f"\n[scrape] Starting {len(platforms)} Playwright platforms + Arbeitsagentur API in parallel...")

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures: dict = {executor.submit(_scrape_platform, p): p for p in platforms}
        futures[executor.submit(_run_arbeitsagentur)] = "Arbeitsagentur"

        for future in as_completed(futures):
            platform = futures[future]
            try:
                result, stats = future.result()
                print(f"  [done] {platform}: {len(result)} jobs")
                all_jobs  += result
                all_stats += stats
            except Exception as e:
                print(f"  [err] {platform} crashed: {e}")
                logger.exception("Platform scraper crashed: %s", platform)

    all_jobs = deduplicate(all_jobs)
    print(f"\n[done] Total unique jobs after dedup: {len(all_jobs)}")

    _print_summary(all_stats)

    return all_jobs
