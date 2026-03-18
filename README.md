# 🤖 Job Application Agent

A semi-autonomous AI agent that scrapes real German job listings,
scores them against your profile, writes tailored cover letters,
and tracks your applications — all powered by LangGraph and Claude AI.

## ✨ Features

- 🔍 **Real job scraper** — fetches listings from Arbeitsagentur API
- 🧠 **AI job scoring** — ranks jobs by match % against your CV
- ✍️ **Cover letter generator** — tailored letter for each job using Claude
- 👤 **Human-in-the-loop** — you approve or reject before anything is saved
- 📊 **Dashboard UI** — visual tracker built with Streamlit
- ⏰ **Auto-scheduler** — runs every morning at 10:00 AM automatically

## 🛠️ Tech Stack

| Layer | Tool |
|---|---|
| Agent framework | LangGraph |
| LLM | Claude API (Anthropic) |
| Job data | Arbeitsagentur REST API |
| Database | SQLite |
| Dashboard | Streamlit |
| Language | Python 3.11+ |

## 📐 Architecture
```
Scraper → Scorer → Cover Letter Writer → Human Review → Tracker
```

The agent is built as a LangGraph state graph where each step
is a node, and the human approval step acts as a breakpoint
before anything is saved.

## 🚀 Getting Started

### 1. Clone the repo
```bash
git clone https://github.com/YOUR_USERNAME/job-agent.git
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
```

### 4. Add your API key
Create a `.env` file:
```
ANTHROPIC_API_KEY=your_key_here
```

### 5. Add your CV
Paste your CV as plain text in `my_cv.txt`

### 6. Run the agent
```bash
python main.py
```

### 7. Open the dashboard
```bash
streamlit run dashboard.py
```

## 📁 Project Structure
```
job-agent/
├── main.py              # LangGraph agent — main entry point
├── dashboard.py         # Streamlit dashboard UI
├── run_daily.py         # Scheduled daily runner
├── my_cv.txt            # Your CV (not committed)
├── .env                 # API key (not committed)
├── nodes/
│   ├── scraper.py       # Arbeitsagentur API scraper
│   ├── analyzer.py      # Job scoring with Claude
│   ├── cover_letter.py  # Cover letter generation
│   └── tracker.py       # SQLite application tracker
└── data/
    └── applications.db  # Local database (not committed)
```

## ⚙️ Configuration

In `main.py` you can adjust:
- `job_title` — what role to search for
- `location` — city or region
- `max_jobs` — how many jobs to scrape per run
- `min_score` — minimum match % to show (default: 70)

## 📄 License

MIT