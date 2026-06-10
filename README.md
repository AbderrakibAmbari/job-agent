# 🤖 Job Application Agent

A LangGraph-powered job-matching agent that scrapes German job boards in parallel,
scores every posting against your CV with Claude, deduplicates across platforms,
and persists the matches to a local SQLite-backed dashboard.

## ✨ Features

- 🔍 **Multi-platform scraper** — Indeed, Stepstone, XING, LinkedIn, Glassdoor (Playwright) + Arbeitsagentur (REST API), all run in parallel
- 🧹 **Smart pre-filter** — keyword reject pass kills senior/non-tech/extreme-experience postings before any LLM call
- 🔗 **Live link validation** — checks each posting is still alive and reads the page body for hidden experience requirements
- 🧠 **LLM scoring** — Claude Haiku 4.5 with prompt caching; hard caps for experience, seniority, and SAP roles
- 🪢 **Cross-platform dedup** — URL + normalized title+company (handles `(m/w/d)` suffixes, `GmbH`/`AG` variants, etc.)
- 📊 **Streamlit dashboard** — review matches, mark applied / not-applied, browse near-misses, add feedback notes
- 💾 **Rolling DB backups** — 30 days of `applications.db` snapshots
- 🖐️ **Manual run** — kick off the pipeline whenever you want; no background scheduler

## 🛠️ Tech Stack

| Layer | Tool |
|---|---|
| Agent framework | LangGraph |
| LLM | Claude Haiku 4.5 via `langchain-anthropic` |
| Job sources | Indeed, Stepstone, XING, LinkedIn, Glassdoor, Arbeitsagentur |
| Scraping | Playwright (headless Chromium) + Requests |
| Database | SQLite |
| Dashboard | Streamlit |
| Language | Python 3.11+ |

## 📐 Pipeline

```
        ┌──────────────────────────────────────────┐
        │  scrape_jobs  (5 Playwright + BA API)    │
        │  → parallel ThreadPoolExecutor           │
        └──────────────────────────────────────────┘
                            ↓
        ┌──────────────────────────────────────────┐
        │  deduplicate  (URL + title+company)      │
        └──────────────────────────────────────────┘
                            ↓
        ┌──────────────────────────────────────────┐
        │  validate_jobs  (live link + exp check)  │
        └──────────────────────────────────────────┘
                            ↓
        ┌──────────────────────────────────────────┐
        │  quick_reject pre-filter (no API call)   │
        └──────────────────────────────────────────┘
                            ↓
        ┌──────────────────────────────────────────┐
        │  score_job  (Claude Haiku 4.5, cached)   │
        └──────────────────────────────────────────┘
                            ↓
        ┌──────────────────────────────────────────┐
        │  save_matched_jobs / save_not_matched    │
        │  → SQLite (applications.db)              │
        └──────────────────────────────────────────┘
```

`main.py` wires this as a LangGraph `StateGraph` with three nodes
(`fetch_jobs → validate_job_links → analyze_jobs`).
`nodes/pipeline.py` is the shared implementation also used by `run_daily.py`.

## 🚀 Getting Started

### 1. Clone the repo
```bash
git clone https://github.com/AbderrakibAmbari/job-agent.git
cd job-agent
```

### 2. Create virtual environment
```bash
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Linux/Mac
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
playwright install chromium
```

### 4. Add your API key
Create a `.env` file:
```
ANTHROPIC_API_KEY=sk-ant-...
```
Get a key from the [Anthropic Console](https://console.anthropic.com/).

### 5. Add your CV
Paste your CV as plain text in `my_cv.txt` (used by the scorer as the candidate profile).

### 6. (Optional) Log into LinkedIn
LinkedIn blocks anonymous job searches behind an auth wall. To enable the LinkedIn scraper:
```bash
python login_linkedin.py
```
This saves session cookies to `data/linkedin_cookies.json` (gitignored). The scraper reuses them on every run.

### 7. Run the agent (manually)
```bash
python main.py
```

### 8. Open the dashboard
```bash
streamlit run dashboard.py
```

## 📁 Project Structure
```
job-agent/
├── main.py                  # LangGraph entry point (interactive run)
├── run_daily.py             # Scriptable runner (also invokable manually)
├── dashboard.py             # Streamlit dashboard UI
├── cleanup_duplicates.py    # One-off DB dedup utility
├── login_linkedin.py        # Saves LinkedIn session cookies
├── my_cv.txt                # Your CV (gitignored)
├── .env                     # API key (gitignored)
├── requirements.txt
├── nodes/
│   ├── scraper.py           # 5 Playwright scrapers + Arbeitsagentur API
│   ├── validator.py         # Live link + experience-in-body check
│   ├── analyzer.py          # Claude scoring + quick-reject pre-filter
│   ├── tracker.py           # SQLite persistence, dedup keys, backups
│   ├── pipeline.py          # Shared scrape→validate→score→save pipeline
│   └── feedback_log.py      # Append-only notes log for the dashboard
├── config/
│   └── profile.yaml         # Profile/search config
├── data/                    # (gitignored)
│   ├── applications.db      # SQLite store
│   ├── backups/             # Rolling 30-day DB snapshots
│   ├── linkedin_cookies.json
│   ├── feedback_log.txt
│   ├── scrape_log.txt       # Rotating scrape summaries
│   ├── scheduler_log.txt    # run_daily.py log
│   └── run_<stamp>.txt      # Full console log tee'd from each main.py run
└── research/                # Reference material
```

## ⚙️ Configuration

Search behavior is controlled in `nodes/scraper.py`:

- `REGIONS` — German Bundesländer to search
- `JUNIOR_TERMS`, `WERKSTUDENT_TERMS`, `PRAKTIKUM_TERMS`, `SAP_TRAINING_TERMS` — search keywords
- `PLATFORM_SEARCH_TERMS` — front-loaded subset used by the Playwright platforms
- `PLATFORM_TIMEOUT` — seconds per platform before bailing (default 600)
- `DEPRIORITIZE_TITLES` — titles to skip in the pre-filter

Scoring is controlled in `nodes/analyzer.py`:

- `_SCORING_RULES` — the prompt sent to Claude (boost / deprioritize / hard rules)
- Score caps applied in `_apply_experience_cap` (e.g. 40 for "3+ years required", 55 for SAP roles, 60 for titles with no junior indicator)
- `min_score` argument to `score_and_filter_jobs` — threshold for "matched" vs "near miss" (default 70 for `main.py`, 50 for `run_daily.py`)

## 🕙 Manual vs Scheduled

The Windows Scheduled Task `\JobAgent` exists but is currently **disabled** — runs are manual.

To re-enable daily scheduled runs at 10:00:
```bash
schtasks /Change /TN "\JobAgent" /ENABLE
```

To disable again:
```bash
schtasks /Change /TN "\JobAgent" /DISABLE
```

## 📄 License

MIT
