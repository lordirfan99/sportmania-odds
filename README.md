# ⚽ Sportmania Odds — Real-Time Betting Dashboard

Multi-source odds comparison engine for **1xBet Malaysia**, **12Play MY**, and **the-odds-api** (Unibet). Live at [sportmania-betting.netlify.app](https://sportmania-betting.netlify.app).

## Pipeline (`pipeline/`)

| Script | Purpose |
|--------|---------|
| `auto_scraper.py` | Deterministic auto-scraper (all 3 sources, cascading priority) |
| `odds_pipeline.py` | Cron pipeline — merge, transform, deploy |
| `1xbet_scraper.py` | 1xBet `GetGameZip` API via cloudscraper |
| `scraper_12play.py` | 12Play via 12PSports.com (Selenium + undetected-chromedriver) |
| `odds_api_fetcher.py` | the-odds-api (Unibet) fallback |
| `transform_ah.py` | Malay odds → Decimal conversion |
| `show_odds.py` | CLI odds viewer |
| `check_1xbet_api.py` | API health check |
| `deploy_dashboard.sh` | Build + Netlify Drop deploy |

### Cron

Runs every 4 hours via `odds-monitor-wc-qf` cron job. Output: `data.json` → Netlify Drop.

## Frontend (`src/`)

React + Vite + Tailwind. Mobile-first. Key components:

- **Dashboard** — countdown, 1xBet vs 12Play columns, edge badges
- **MatchDetail** — Asian Handicap / Over-Under breakdown, vig analysis
- **BetLogForm** — bankroll tracker
- **EdgeBadge** — implied probability + edge visualisation

## Stack

- Pipeline: Python 3.11, cloudscraper, Selenium, undetected-chromedriver
- Frontend: React 18, Vite, Netlify Drop
- Live: [[sportmania-betting.netlify.app]](https://sportmania-betting.netlify.app)

## Quick Start

```bash
# Pipeline
pip install cloudscraper requests the-odds-api
python pipeline/auto_scraper.py --deploy --force

# Frontend dev
npm install
npm run dev
```
