# ⚽ Sportmania Odds Engine v2.0

> Multi-source value betting dashboard — **1xBet Malaysia vs Betfair Exchange**  
> Live: [sportmania-betting.netlify.app](https://sportmania-betting.netlify.app)  
> GitHub: [lordirfan99/sportmania-odds](https://github.com/lordirfan99/sportmania-odds)

## 📊 System Overview

A real-time value betting engine that compares **1xBet Malaysia** odds against **Betfair Exchange** midpoint prices to identify +EV (positive expected value) opportunities. Focuses exclusively on two high-liquidity markets:

- **Asian Handicap -0.5 / +0.5** — derived from 1X2 odds
- **Over / Under 2.5** — direct totals comparison

### Core Logic

```
+EV% = (1xBet Price - Betfair Midpoint) / Betfair Midpoint × 100
```

When 1xBet offers higher odds than Betfair's true probability (back-lay midpoint), the market is mispriced → **+EV opportunity**.

### Bankroll & Staking

| Parameter | Value |
|-----------|-------|
| **Bankroll** | RM70.00 |
| **Kelly Fraction** | ¼ Quarter Kelly |
| **Formula** | `(edge% / 100) / (odds - 1) / 4 × bankroll` |
| **Min Edge** | > 3% triggers stake calculation |

#### Quarter Kelly Example

```
Edge +10%, Odds 2.50
  Full Kelly = (0.10 / 1.50) × 100 = 6.67%
  Quarter Kelly = 6.67% / 4 = 1.67% = RM1.17 from RM70
```

---

## 🏗️ Architecture

```
betting-dashboard/
├── pipeline/                  # Data pipeline (Python)
│   ├── scraper_oddsapi.py    # 🔥 Main: Odds-API.io v3 + Betfair + 1xBet
│   ├── auto_scraper.py       # Legacy: the-odds-api v4 (Pinnacle)
│   ├── models.py             # Dixon-Coles, Poisson, Markov models
│   ├── _all_matches.json     # Scraper output (intermediate)
│   └── deploy_dashboard.sh   # Shell deploy script
├── src/                       # React frontend
│   ├── components/
│   │   ├── Dashboard.jsx     # Main dashboard: matches, edges, divergence
│   │   ├── MatchDetail.jsx   # Per-match deep analysis
│   │   ├── EdgeBadge.jsx     # Edge indicator component
│   │   ├── BetLogForm.jsx    # Bet logging modal
│   │   └── TriangulationTable.jsx  # 3-source probability comparison
│   ├── lib/
│   │   ├── simulator.js      # Gate Decision Engine (3 gates)
│   │   └── betStore.js       # Persistent bet store (Netlify Blobs)
│   ├── App.jsx               # Router setup
│   ├── main.jsx              # Entry point + Error Boundary
│   └── index.css             # Tailwind 4 + custom styles
├── public/
│   ├── data.json             # 🎯 Live data feed (auto-updated)
│   └── index.html
├── netlify.toml              # Netlify config
├── vite.config.js            # Vite + React + Tailwind
└── package.json
```

---

## 🔧 Data Sources

### Primary: Odds-API.io v3
- **Endpoint:** `api.odds-api.io/v3`
- **Bookmakers:** `Betfair Exchange`, `1xbet`
- **Markets:** 1X2 (AH derived), Totals (O/U 2.5 filtered)
- **Quota:** Free tier — 100 req/hr
- **Caching:** 60s event cache, 1h league cache
- **Coverage:** 100+ football leagues globally

### Legacy: the-odds-api v4 (`auto_scraper.py`)
- **True price source:** Pinnacle
- **Sportsbook:** 1xBet, Pinnacle (fallback)
- **Quota:** 500 req/month free tier
- **Rotation:** 6 leagues per run (out of 17 active summer leagues)

### Market Filters
| Filter | Reason |
|--------|--------|
| ❌ Women's leagues | Volatile liquidity, false signals |
| ❌ Club Friendlies | Unreliable odds, no competitive intensity |
| ❌ Matches missing Betfair or 1xBet | Can't compute edge without both sources |

---

## 📐 Edge Computation

### For each match, 4 markets are evaluated:

| Market | 1xBet Price | Betfair Price | Edge Formula |
|--------|------------|---------------|--------------|
| Over 2.5 | `xbt[0].over` | `bft[0].over` | `(x - bf) / bf × 100` |
| Under 2.5 | `xbt[0].under` | `bft[0].under` | `(x - bf) / bf × 100` |
| Home -0.5 AH | Derived from 1X2 home | Derived from Betfair midpoint | `(x - bf) / bf × 100` |
| Away +0.5 AH | Derived from 1X2 draw+away | Derived from Betfair midpoint | `(x - bf) / bf × 100` |

### Asian Handicap Derivation
Asian Handicap -0.5/+0.5 is derived from 1X2 odds:

```
Home -0.5 AH = 1X2 Home odds
Away +0.5 AH = 1 / (1/Draw + 1/Away)  [implied probability method]
```

### Vig-Free Probabilities (Betfair)
Betfair midpoint = `(back + lay) / 2` per outcome — the Caan Berry method for true market probability.

---

## 🧠 Frontend: Gate Decision Engine

The Dashboard uses a **3-Gate Decision Engine** (`simulator.js`) to determine system recommendations:

| Gate | Condition | Purpose |
|------|-----------|---------|
| **Gate 1** | Edge > 3.2% | Minimum value threshold |
| **Gate 2** | Model std dev < 10% | Consensus across triangulation models |
| **Gate 3** | ≥ 3 historical similar bets | Track record validation |

Passing all 3 gates → **BET** recommendation with confidence (HIGH/MEDIUM/LOW).  
Failing any gate → **SKIP**.

### UI Sections

1. **Divergence Tracker** — System (shadow) vs You (actual) comparison
   - Bets the system wants vs bets you've placed
   - Diverged opportunities highlighted
   - Kelly %, win rate, profit tracking
2. **Upcoming Matches** — Sorted by highest edge %. Each card shows:
   - O/U 2.5 prices (1xBet vs Betfair)
   - AH -0.5/+0.5 prices
   - Edge % for each market
   - Top pick with decision badge
3. **O/U Market Table** — All lines across all matches
4. **Bet History** — Track placed bets, settle outcomes, P&L
5. **Bankroll Management** — Deposit/withdraw modal

---

## ⏱️ Automation

### Cron Job: `odds-monitor`
- **Schedule:** Every 2 minutes (`*/2 * * * *`)
- **Script:** `~/.hermes/scripts/odds-monitor.sh`
- **Workflow:**
  1. Run `python scraper_oddsapi.py` (silent, stderr only)
  2. Check for +EV opportunities
  3. If +EV found → print alerts (captured by cron → Telegram)
  4. If `data.json` SHA changed → `npm run build` → Netlify deploy
- **Deploy guard:** SHA hash comparison prevents unnecessary builds

### Telegram Alerts
When +EV found, sends to this chat:
```
🚀 +EV ALERT (N opportunities)
⚽ Team A vs Team B
   Over 2.5: Edge=+8.2% | 1xBet=2.10 | Betfair=1.94
   ...
```

---

## 🚀 Quick Start

```bash
# Clone
git clone https://github.com/lordirfan99/sportmania-odds.git
cd sportmania-odds

# Environment
export ODDSAPI_IO_KEY="your_key_from_odds-api.io"

# Pipeline (Python 3.11+)
cd pipeline
pip install requests
python scraper_oddsapi.py

# Frontend dev
cd ..
npm install
npm run dev
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ODDSAPI_IO_KEY` | ✅ Yes | Odds-API.io API key |
| `NETLIFY_AUTH_TOKEN` | For deploy | Netlify personal access token |
| `ODDS_API_KEY` | Legacy | the-odds-api key (auto_scraper.py) |

### Deploy

```bash
# Manual deploy
cd betting-dashboard
npm run build
python deploy_netlify.py

# Or via script
bash pipeline/deploy_dashboard.sh
```

---

## 📊 Data Format (`data.json`)

```json
{
  "system_status": {
    "last_updated": "2026-07-13T10:42:00Z",
    "bankroll_rm": 70.0,
    "total_profit_rm": 0,
    "total_bets": 0,
    "won_bets": 0
  },
  "bet_history": [],
  "matches": [
    {
      "match_id": "oa_12345",
      "home_team": "Djurgardens IF",
      "away_team": "Halmstads BK",
      "league_name": "Allsvenskan - Sweden",
      "home_odds": 1.26,
      "away_odds": 3.56,
      "analysis": {
        "betfair_midpoint": { "home": 1.265, "draw": 5.2, "away": 4.827 },
        "xbet_odds": { "home": 1.26, "draw": 5.1, "away": 3.56 },
        "xbet_totals": [{ "point": 2.5, "over": 1.44, "under": 2.46 }],
        "betfair_totals": [{ "point": 2.5, "over": 1.5, "under": 2.9 }],
        "edge_summary": [
          { "market": "Over 2.5 (1xBet vs Betfair)", "edge": -4.0, "quarter_kelly_stake": 0, "xbet_price": 1.44, "betfair_price": 1.5 },
          { "market": "UA Claypole -0.5 (AH) (1xBet vs Betfair)", "edge": -0.4, ... }
        ]
      }
    }
  ]
}
```

---

## 🔬 Statistical Models (`pipeline/models.py`)

| Model | Purpose |
|-------|---------|
| **Dixon-Coles** | Goal-based prediction from historical match data |
| **Poisson** | Expected goals → match outcome probabilities |
| **Markov Chain** | League form streak analysis |
| **Polymarket** | Market-implied probabilities from prediction markets |

---

## 🎯 Strategy

1. **True Price = Betfair Exchange midpoint** (not Pinnacle)
2. **Compare 1xBet Malaysia against true price**
3. **When 1xBet > Betfair midpoint → +EV**
4. **Stake = Quarter Kelly** for bankroll preservation
5. **Only AH -0.5/+0.5 and O/U 2.5** — highest liquidity, lowest vig
6. **Exit women's leagues + friendlies** — unreliable data
7. **Divergence tracking** — system tells you what to bet, you log your actual bets, compare performance

### Edge Thresholds
| Edge Range | Label | Action |
|-----------|-------|--------|
| > +20% | 🚀 Kelly | Maximum confidence |
| +5% to +20% | ✅ Value | Strong bet signal |
| -5% to +5% | ⚪ Neutral | No action |
| < -5% | ❌ Avoid | Negative expected value |

---

## 📈 Live Dashboard Features

- **Real-time odds comparison** (updated every 2 min)
- **Quarter Kelly staking** for every +EV opportunity
- **Divergence analysis** — system vs your actual bets
- **Bankroll tracker** with deposit/withdraw
- **Settle bets** with score input → automatic P&L
- **Party mode** 🎉 gradient theme toggle
- **Mobile-first** responsive design

---

## 🔄 Recent Updates (v2.0)

- [x] **Odds-API.io v3** integration (replaced the-odds-api)
- [x] **Betfair Exchange** as true price source (not Pinnacle)
- [x] **1xBet Malaysia** direct comparison
- [x] **Quarter Kelly** proper formula
- [x] **Bankroll RM70**
- [x] **Cron every 2 min** (100 req/hr quota)
- [x] **Divergence Tracker** — You vs System
- [x] **Gate Decision Engine** — 3-gate bet/skip logic
- [x] **Persistent bet store** (Netlify Blobs + localStorage)
- [x] **O/U 2.5 + AH only** — focused markets
- [x] **Women/friendly league filter**
- [x] **SHA deploy guard** — no wasted builds

---

## 🔗 Links

- **Live Site:** [sportmania-betting.netlify.app](https://sportmania-betting.netlify.app)
- **GitHub:** [lordirfan99/sportmania-odds](https://github.com/lordirfan99/sportmania-odds)
- **Data Source:** [Odds-API.io](https://odds-api.io)
- **Exchange:** [Betfair Exchange](https://www.betfair.com/exchange)
- **Bookmaker:** [1xBet Malaysia](https://1xbet-malaysia.mobi)

---

> ⚠️ **Disclaimer:** This tool is for educational and research purposes. Sports betting involves financial risk. Never bet more than you can afford to lose. Quarter Kelly does not guarantee profit.
