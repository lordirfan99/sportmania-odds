"""
auto_scraper.py — Fully automated odds scraper (no AI needed).

Three data sources:
  1. 1xBet Malaysia (cloudscraper → API) ← fastest, most reliable
  2. the-odds-api  (HTTP, reliable backup — Pinnacle / Matchbook)

Pipeline: scrape → merge → compute edges → write data.json → deploy

Usage:
  python pipeline/auto_scraper.py              # scrape all + update
  python pipeline/auto_scraper.py --dry-run     # print only, no write
  python pipeline/auto_scraper.py --skip-1xbet  # skip 1xBet
  python pipeline/auto_scraper.py --deploy      # scrape + build + deploy
  python pipeline/auto_scraper.py --force       # force even if data is fresh
"""

import json
import os
import re
import subprocess
import sys
import time
import zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests as req_lib
import cloudscraper
from bs4 import BeautifulSoup

# ─── Real statistical models ───
sys.path.insert(0, str(Path(__file__).resolve().parent))
from models import compute_dixon_coles, extract_pinnacle_probs, fetch_polymarket_probs

# ─── Config ───
BASE_DIR = Path(__file__).resolve().parent.parent
PUBLIC_DIR = BASE_DIR / "public"
DATA_FILE = PUBLIC_DIR / "data.json"
DIST_DIR = BASE_DIR / "dist"

# Load .env file manually if it exists
env_path = BASE_DIR / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip()

# 1xBet credentials
XBET_USERNAME = os.environ.get("XBET_USERNAME", "1733712589")
XBET_PASSWORD = os.environ.get("XBET_PASSWORD", "Tapestry1Constrict1raking.")
XBET_BASE = "https://1xbet-malaysia.mobi"

# the-odds-api
ODDS_API_KEY = os.environ.get("ODDS_API_KEY", "b45c8f0693e8a7912baf2449e98d6fb8")
PREFERRED_BOOKMAKERS = ["Pinnacle", "Matchbook", "BetOnline.ag"]

# ─── Match DB (stable IDs) ───
MATCH_DB = {
    "esp_bel_01": {
        "home_team": "Spain", "away_team": "Belgium",
        "venue": "SoFi Stadium, Los Angeles", "stage": "Quarterfinal",
        "date": "2026-07-10", "time": "03:00 MYT",
    },
    "eng_nor_03": {
        "home_team": "Norway", "away_team": "England",
        "venue": "Stadium", "stage": "Quarterfinal",
        "date": "2026-07-11", "time": "22:00 MYT",
    },
    "arg_sui_04": {
        "home_team": "Argentina", "away_team": "Switzerland",
        "venue": "Stadium", "stage": "Quarterfinal",
        "date": "2026-07-11", "time": "03:00 MYT",
    },
    "fra_spa_05": {
        "home_team": "France", "away_team": "Spain",
        "venue": "Stadium", "stage": "Semifinal",
        "date": "2026-07-14", "time": "03:00 MYT",
    },
}

# 1xBet match ID mapping (from expressDay API)
XBET_MATCH_IDS = {
    "eng_nor_03": 734357671,    # Norway vs England
    "arg_sui_04": 734782375,    # Argentina vs Switzerland
    "fra_spa_05": 735504550,    # France vs Spain
}

# Team synonyms
TEAM_SYNONYMS = {
    "spain": "Spain", "espana": "Spain",
    "belgium": "Belgium", "belgie": "Belgium",
    "england": "England",
    "norway": "Norway", "norge": "Norway",
    "argentina": "Argentina",
    "switzerland": "Switzerland", "swiss": "Switzerland",
    "france": "France",
}


# ─── Helpers ───
def fmt_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def normalize_team(name):
    n = name.lower().strip().replace("-", " ").replace("_", " ")
    return TEAM_SYNONYMS.get(n, name.strip())

def find_match_id(home, away):
    h = normalize_team(home)
    a = normalize_team(away)
    for mid, mdata in MATCH_DB.items():
        mh = normalize_team(mdata["home_team"])
        ma = normalize_team(mdata["away_team"])
        if {h, a} == {mh, ma}:
            return mid
    return None

def vig_free(odds_list):
    imp_total = sum(1 / o for o in odds_list if o > 0)
    if imp_total <= 0:
        return [0] * len(odds_list)
    return [(1 / o) / imp_total if o > 0 else 0 for o in odds_list]

def compute_vig(odds_list):
    """Returns overround as a raw multiplier (e.g. 1.0157 = 1.57% vig).
    1.00 = perfect fair book. Frontend displays as (val-1)*100 = vig%."""
    imp = sum(1 / o for o in odds_list if o > 0)
    return round(imp, 4)


# ═══════════════════════════════════════════
# SOURCE 1: 1xBet Malaysia (API, no browser)
# ═══════════════════════════════════════════

def scrape_1xbet():
    """
    Scrape World Cup odds from 1xBet using direct API calls.
    NO browser needed — uses cloudscraper to bypass Cloudflare.
    
    Returns list of match dicts with odds.
    """
    print("[1XBET] Fetching via cloudscraper API...")
    
    try:
        scraper = cloudscraper.create_scraper()
    except Exception as e:
        print(f"[1XBET] ⚠️ cloudscraper error: {e}")
        return []
    
    scraper.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/132.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
        "Referer": f"{XBET_BASE}/en/line/football",
    })
    
    results = []
    
    for mid, api_id in XBET_MATCH_IDS.items():
        match_base = MATCH_DB.get(mid, {})
        if not match_base:
            continue
        
        url = f"{XBET_BASE}/service-api/LineFeed/GetGameZip?id={api_id}&lng=en"
        
        try:
            r = scraper.get(url, timeout=15)
            if r.status_code != 200:
                print(f"[1XBET] Match {mid}: HTTP {r.status_code}")
                continue
            
            d = r.json()
            if not d.get("Success"):
                print(f"[1XBET] Match {mid}: API error: {d.get('Error', '?')}")
                continue
            
            value = d.get("Value", {})
            odds = parse_xbet_game(value)
            
            if odds:
                odds['match_id'] = mid
                odds['home_team'] = match_base['home_team']
                odds['away_team'] = match_base['away_team']
                # Wrap in odds key for merge_odds compatibility
                result_entry = {
                    'match_id': mid,
                    'home_team': match_base['home_team'],
                    'away_team': match_base['away_team'],
                    'odds': odds,
                }
                results.append(result_entry)
                print(f"[1XBET] ✅ {match_base['home_team']:12s} vs {match_base['away_team']:12s} | "
                      f"1X2: {odds['h1']:.3f}/{odds['hX']:.3f}/{odds['h2']:.3f} | "
                      f"O/U: {odds.get('over', 0):.3f}/{odds.get('under', 0):.3f}")
            
        except Exception as e:
            print(f"[1XBET] Match {mid}: ❌ {e}")
            continue
    
    if results:
        print(f"[1XBET] ✅ Got {len(results)} matches")
    else:
        print("[1XBET] ❌ No matches scraped")
    
    return results


def parse_xbet_game(value):
    """
    Parse 1xBet GetGameZip response Value into our odds format.
    
    1X2 odds: E[] items with T=1(home), T=2(draw), T=3(away), G=1
    O/U 2.5: E[] items with P=2.5, T=9(under), T=10(over)
    AH -0.5/+0.5: derived from 1X2 (home = -0.5, away+draw = +0.5)
    """
    e_arr = value.get("E", [])
    if not e_arr:
        return None
    
    result = {
        "h1": 0, "hX": 0, "h2": 0,
        "ah_home": 0, "ah_away": 0,
        "over": 0, "under": 0, "ou_point": 2.5,
        "source": "1xBet",
    }
    
    # Extract 1X2 odds
    for item in e_arr:
        t = item.get("T")
        g = item.get("G")
        c = item.get("C", 0)
        
        if g == 1 and t in (1, 2, 3):
            if t == 1:
                result["h1"] = c  # Home win
            elif t == 2:
                result["hX"] = c  # Draw
            elif t == 3:
                result["h2"] = c  # Away win
    
    # If no 1X2 odds found, try WP (win probabilities)
    if result["h1"] == 0:
        wp = value.get("WP", {})
        p1 = float(wp.get("P1", 0))
        px = float(wp.get("PX", 0))
        p2 = float(wp.get("P2", 0))
        if p1 > 0 and p2 > 0:
            result["h1"] = round(1 / p1, 3)
            result["hX"] = round(1 / px, 3) if px > 0 else 0
            result["h2"] = round(1 / p2, 3)
    
    # Derive AH -0.5 / +0.5 from 1X2
    h = result["h1"]
    d = result["hX"]
    a = result["h2"]
    
    if h > 0:
        result["ah_home"] = h  # AH -0.5 = home win
    if a > 0 and d > 0:
        # AH +0.5 = implied odds for away + draw
        imp = 1 / a + 1 / d
        result["ah_away"] = round(1 / imp, 3) if imp > 0 else 0
    elif a > 0:
        result["ah_away"] = a
    
    # Extract O/U 2.5
    for item in e_arr:
        t = item.get("T")
        p = item.get("P")
        c = item.get("C", 0)
        
        if p == 2.5:
            if t == 9:   # Under 2.5
                result["under"] = c
            elif t == 10:  # Over 2.5
                result["over"] = c
    
    return result


# ═══════════════════════════════════════════
# SOURCE 2: the-odds-api (HTTP fallback)
# ═══════════════════════════════════════════

def scrape_api():
    """Fetch World Cup odds from the-odds-api.com."""
    print("[API] Fetching from the-odds-api...")
    
    url = (
        f"https://api.the-odds-api.com/v4/sports/soccer_fifa_world_cup/odds/"
        f"?apiKey={ODDS_API_KEY}"
        f"&regions=eu"
        f"&markets=h2h,spreads,totals"
        f"&oddsFormat=decimal"
    )
    
    try:
        r = req_lib.get(url, timeout=30)
        if r.status_code != 200:
            print(f"[API] HTTP {r.status_code}")
            return []
        
        data = r.json()
        if isinstance(data, dict) and "message" in data:
            print(f"[API] Error: {data['message']}")
            return []
        
        print(f"[API] ✅ Got {len(data)} raw matches")
        converted = convert_api_data(data)
        # Return both converted odds AND raw API data for Pinnacle extraction
        return converted, data
        
    except Exception as e:
        print(f"[API] ❌ {e}")
        return [], []


def convert_api_data(api_data):
    """Convert the-odds-api response to our format."""
    results = []
    
    for m in api_data:
        home = m.get("home_team", "")
        away = m.get("away_team", "")
        mid = find_match_id(home, away)
        
        if not mid:
            continue
        
        match_base = MATCH_DB[mid]
        odds = {"h1": 0, "hX": 0, "h2": 0, "over": 0, "under": 0, "ou_point": 2.5, "source": "the-odds-api"}
        
        for bm in m.get("bookmakers", []):
            if bm["title"] not in PREFERRED_BOOKMAKERS:
                continue
            for mk in bm.get("markets", []):
                key = mk["key"]
                outcomes = {o["name"]: o for o in mk["outcomes"]}
                
                if key == "h2h" and odds["h1"] == 0:
                    odds["h1"] = outcomes.get(home, {}).get("price", 0)
                    odds["hX"] = outcomes.get("Draw", {}).get("price", 0)
                    odds["h2"] = outcomes.get(away, {}).get("price", 0)
                
                elif key == "spreads":
                    hs = outcomes.get(home, {})
                    aws = outcomes.get(away, {})
                    odds["ah_home"] = hs.get("price", 0) if hs else 0
                    odds["ah_away"] = aws.get("price", 0) if aws else 0
                
                elif key == "totals":
                    ov = outcomes.get("Over", {})
                    ud = outcomes.get("Under", {})
                    odds["over"] = ov.get("price", 0) if ov else 0
                    odds["under"] = ud.get("price", 0) if ud else 0
                    odds["ou_point"] = ov.get("point", 2.5) if ov else 2.5
        
        # If no AH direct, derive from 1X2
        if odds["ah_home"] == 0 and odds["h1"] > 0:
            odds["ah_home"] = odds["h1"]
            if odds["h2"] > 0 and odds["hX"] > 0:
                imp = 1 / odds["h2"] + 1 / odds["hX"]
                odds["ah_away"] = round(1 / imp, 3) if imp > 0 else 0
        
        odd_entry = {
            "match_id": mid,
            "home_team": match_base["home_team"],
            "away_team": match_base["away_team"],
            "odds": odds,
        }
        results.append(odd_entry)
        
        print(f"[API] ✅ {match_base['home_team']:12s} vs {match_base['away_team']:12s}")
    
    return results


# ═══════════════════════════════════════════
# MERGE ENGINE
# ═══════════════════════════════════════════

def merge_odds(source_list):
    """
    Merge odds from sources. Priority: 1xBet > the-odds-api.
    """
    merged = {}
    priority = {"1xBet": 0, "the-odds-api": 1}
    
    for source_name, odds_list in source_list:
        for entry in odds_list:
            mid = entry.get("match_id")
            if not mid:
                continue
            
            if mid not in merged:
                mb = MATCH_DB.get(mid, {})
                merged[mid] = {
                    "id": mid,
                    "home_team": mb.get("home_team", ""),
                    "away_team": mb.get("away_team", ""),
                    "venue": mb.get("venue", "Stadium"),
                    "stage": mb.get("stage", "Quarterfinal"),
                    "date": mb.get("date", ""),
                    "time": mb.get("time", ""),
                    "highest_edge_status": "⚪",
                    "home_odds": 0,
                    "draw_odds": 0,
                    "away_odds": 0,
                    "analysis": {
                        "sport_raw": {"home": 0, "draw": 0, "away": 0, "vig": 0},
                        "polymarket_devig": {"home": 0, "draw": 0, "away": 0},
                        "triangulation_1x2": {},
                        "triangulation_ou": {},
                        "triangulation_ah": {},
                        "edge_summary": [],
                        "narrative": {"form": "", "injuries": "", "tactical": ""},
                    },
                }
            
            odds = entry.get("odds", {})
            source = odds.get("source", source_name)
            cur = merged[mid]
            sr = cur["analysis"]["sport_raw"]
            cur_priority = priority.get(sr.get("source", ""), 99)
            new_priority = priority.get(source, 99)
            
            if new_priority >= cur_priority and sr.get("home", 0) != 0:
                continue  # Skip lower priority if we already have odds
            
            # Set AH odds
            ah_home = odds.get("ah_home", 0) or 0
            ah_away = odds.get("ah_away", 0) or 0
            h1 = odds.get("h1", 0) or 0
            h2 = odds.get("h2", 0) or 0
            hX = odds.get("hX", 0) or 0
            
            if ah_home > 0 and ah_away > 0:
                cur["home_odds"] = ah_home
                cur["away_odds"] = ah_away
                cur["draw_odds"] = 0
                sr["home"] = ah_home
                sr["away"] = ah_away
                sr["draw"] = 0
                sr["vig"] = compute_vig([ah_home, ah_away])
            elif h1 > 0 and h2 > 0:
                cur["home_odds"] = h1
                cur["away_odds"] = h2
                cur["draw_odds"] = hX
                sr["home"] = h1
                sr["away"] = h2
                sr["draw"] = hX
                sr["vig"] = compute_vig([h1, hX, h2]) if hX > 0 else compute_vig([h1, h2])
            
            sr["source"] = source
            
            over = odds.get("over", 0) or 0
            under = odds.get("under", 0) or 0
            if over > 0 and under > 0:
                sr["over_odds"] = over
                sr["under_odds"] = under
                sr["ou_point"] = odds.get("ou_point", 2.5)
    
    return list(merged.values())


def generate_triangulation_probs(baseline_probs, model_name, seed_str, is_ou=False):
    import hashlib
    h = hashlib.sha256((seed_str + "_" + model_name).encode("utf-8")).hexdigest()
    val = int(h[:8], 16) / 0xffffffff * 2.0 - 1.0  # value in [-1, 1]
    
    bias = 0.0
    if model_name == "xgscore":
        bias = 0.03 if is_ou else 0.015
    elif model_name == "dixon_coles":
        bias = -0.03 if is_ou else -0.015
    elif model_name == "opta":
        bias = 0.01
    elif model_name == "dataset":
        bias = -0.01
        
    max_dev = 0.04
    scaled_dev = val * max_dev + bias
    
    if len(baseline_probs) == 2:
        p0 = baseline_probs[0] + scaled_dev
        p0 = max(0.1, min(0.9, p0))
        return [round(p0 * 100, 1), round((1.0 - p0) * 100, 1)]
    elif len(baseline_probs) == 3:
        p0 = baseline_probs[0] + scaled_dev
        p2 = baseline_probs[2] - scaled_dev * 0.8
        p1 = 1.0 - p0 - p2
        if p1 < 0.05:
            p1 = 0.05
            remaining = 0.95
            p0_ratio = p0 / (p0 + p2 + 0.001)
            p0 = remaining * p0_ratio
            p2 = remaining * (1.0 - p0_ratio)
        total = p0 + p1 + p2
        return [round(p0/total * 100, 1), round(p1/total * 100, 1), round(p2/total * 100, 1)]
        
    return [round(x * 100, 1) for x in baseline_probs]


def compute_edges(matches, raw_api_data=None):
    """
    Compute edge analysis for each match.

    raw_api_data: the raw list from the-odds-api (used to extract Pinnacle odds).
    """
    raw_api_data = raw_api_data or []

    for m in matches:
        analysis = m["analysis"]
        sr = analysis["sport_raw"]
        home_team = m["home_team"]
        away_team = m["away_team"]
        match_id  = m["id"]

        home_odds  = sr.get("home", 0)
        away_odds  = sr.get("away", 0)
        draw_odds  = sr.get("draw", 0)
        over_odds  = sr.get("over_odds", 0)
        under_odds = sr.get("under_odds", 0)
        ou_point   = sr.get("ou_point", 2.5)

        # ── Devig (1xBet / primary source) ──
        if home_odds > 0 and away_odds > 0:
            if draw_odds > 0:
                probs = vig_free([home_odds, draw_odds, away_odds])
                analysis["polymarket_devig"] = {
                    "home": round(probs[0], 3),
                    "draw": round(probs[1], 3),
                    "away": round(probs[2], 3),
                }
            else:
                probs = vig_free([home_odds, away_odds])
                analysis["polymarket_devig"] = {
                    "home": round(probs[0], 3),
                    "draw": 0,
                    "away": round(probs[1], 3),
                }

        poly = analysis["polymarket_devig"]
        home_1x2_pct = poly.get("home", 0.5) * 100
        draw_pct     = poly.get("draw", 0.3)  * 100
        away_1x2_pct = poly.get("away", 0.2)  * 100

        # ── O/U devig baseline ──
        if over_odds > 0 and under_odds > 0:
            ou_vf    = vig_free([over_odds, under_odds])
            over_pct  = round(ou_vf[0] * 100, 1)
            under_pct = round(ou_vf[1] * 100, 1)
        else:
            over_pct = under_pct = 50.0

        # AH DNB baseline
        dnb_home = round(
            poly.get("home", 0.5) / (poly.get("home", 0.5) + poly.get("away", 0.5)) * 100, 1
        ) if poly.get("home", 0) + poly.get("away", 0) > 0 else 50.0
        dnb_away = round(100 - dnb_home, 1)

        # ══════════════════════════════════════════
        # REAL MODEL TRIANGULATION
        # ══════════════════════════════════════════

        # 1. Dixon-Coles Poisson model (pure math, always available)
        dc = compute_dixon_coles(home_team, away_team)
        print(f"  [DC] {home_team} vs {away_team}: mu_h={dc['mu_h'] if dc else '?'} mu_a={dc['mu_a'] if dc else '?'}")

        # 2. Pinnacle sharp odds (from raw API cache)
        pinnacle = extract_pinnacle_probs(raw_api_data, home_team, away_team)
        if pinnacle:
            print(f"  [PINNACLE] {home_team} vs {away_team}: home={pinnacle['home']}% away={pinnacle['away']}%")
        else:
            print(f"  [PINNACLE] {home_team} vs {away_team}: not available")

        # 3. Polymarket prediction market (attempt, graceful fallback)
        pm = fetch_polymarket_probs(home_team, away_team, timeout=5)
        if pm:
            print(f"  [POLYMARKET] {home_team} vs {away_team}: home={pm['home']}% away={pm['away']}%")
        else:
            print(f"  [POLYMARKET] {home_team} vs {away_team}: not available (network or no listing)")

        # ── Triangulation 1X2 ──
        probs_1x2 = {}

        # market_devig = 1xBet devigged (always present)
        probs_1x2["market_devig"] = [
            round(home_1x2_pct, 1),
            round(draw_pct, 1),
            round(away_1x2_pct, 1),
        ]

        # dixon_coles
        if dc:
            probs_1x2["dixon_coles"] = [dc["home"], dc["draw"], dc["away"]]

        # pinnacle
        if pinnacle:
            probs_1x2["pinnacle"] = [
                pinnacle["home"],
                pinnacle.get("draw", round(100 - pinnacle["home"] - pinnacle["away"], 1)),
                pinnacle["away"],
            ]

        # polymarket
        if pm:
            probs_1x2["polymarket"] = [pm["home"], pm.get("draw", 0), pm["away"]]

        # ensemble — average of whatever we have
        srcs_1x2 = [k for k in ["market_devig", "dixon_coles", "pinnacle", "polymarket"] if k in probs_1x2]
        ens_home = round(sum(probs_1x2[k][0] for k in srcs_1x2) / len(srcs_1x2), 1)
        ens_draw = round(sum(probs_1x2[k][1] for k in srcs_1x2) / len(srcs_1x2), 1)
        ens_away = round(100.0 - ens_home - ens_draw, 1)
        probs_1x2["ensemble"] = [ens_home, ens_draw, ens_away]
        analysis["triangulation_1x2"] = probs_1x2

        # ── Triangulation O/U ──
        probs_ou = {}
        probs_ou["market_devig"] = [over_pct, under_pct]

        if dc:
            probs_ou["dixon_coles"] = [dc["over25"], dc["under25"]]

        if pinnacle and pinnacle.get("over25") is not None:
            probs_ou["pinnacle"] = [pinnacle["over25"], pinnacle["under25"]]

        if pm and pm.get("over25") is not None:
            probs_ou["polymarket"] = [pm["over25"], pm["under25"]]

        srcs_ou = [k for k in ["market_devig", "dixon_coles", "pinnacle", "polymarket"] if k in probs_ou]
        ens_over  = round(sum(probs_ou[k][0] for k in srcs_ou) / len(srcs_ou), 1)
        ens_under = round(100.0 - ens_over, 1)
        probs_ou["ensemble"] = [ens_over, ens_under]
        analysis["triangulation_ou"] = probs_ou

        # ── Triangulation AH (DNB) ──
        probs_ah = {}
        probs_ah["market_devig"] = [dnb_home, dnb_away]

        if dc:
            probs_ah["dixon_coles"] = [dc["ah_home"], dc["ah_away"]]

        if pinnacle:
            probs_ah["pinnacle"] = [pinnacle["ah_home"], pinnacle["ah_away"]]

        if pm:
            probs_ah["polymarket"] = [pm["ah_home"], pm["ah_away"]]

        srcs_ah = [k for k in ["market_devig", "dixon_coles", "pinnacle", "polymarket"] if k in probs_ah]
        ens_home_ah = round(sum(probs_ah[k][0] for k in srcs_ah) / len(srcs_ah), 1)
        ens_away_ah = round(100.0 - ens_home_ah, 1)
        probs_ah["ensemble"] = [ens_home_ah, ens_away_ah]
        analysis["triangulation_ah"] = probs_ah

        # ── AH analysis block ──
        analysis["ah_analysis"] = {
            "home_minus_05_prob": round(poly.get("home", 0.5) * 100, 1),
            "away_plus_05_prob":  round(poly.get("away", 0.5) * 100, 1),
            "home_0_prob":  dnb_home,
            "away_0_prob":  dnb_away,
        }
        analysis["ah_odds"] = {
            "home_minus_05": home_odds or 0,
            "away_plus_05":  away_odds or 0,
        }

        # ── Edge summary ──
        edges = []
        hp = round(poly.get("home", 0.5) * 100, 1)
        ap = round(poly.get("away", 0.5) * 100, 1)

        if home_odds > 0:
            he = round((hp / 100 * home_odds - 1) * 100, 1)
            edges.append({
                "market": f"{m['home_team']} -0.5 (AH)",
                "edge":   he,
                "status": "🚀" if he > 20 else "✅" if he >= 5 else "⚪" if he >= -5 else "❌",
                "quarter_kelly_stake": round(
                    max(0, (he / 100) / (home_odds - 1 + 0.001) * 0.25 * 100), 2
                ) if he >= 3.2 else 0,
            })

        if away_odds > 0:
            ae = round((ap / 100 * away_odds - 1) * 100, 1)
            edges.append({
                "market": f"{m['away_team']} +0.5 (AH)",
                "edge":   ae,
                "status": "🚀" if ae > 20 else "✅" if ae >= 5 else "⚪" if ae >= -5 else "❌",
                "quarter_kelly_stake": round(
                    max(0, (ae / 100) / (away_odds - 1 + 0.001) * 0.25 * 100), 2
                ) if ae >= 3.2 else 0,
            })

        if over_odds > 0:
            oe = round((over_pct / 100 * over_odds - 1) * 100, 1)
            edges.append({
                "market": f"O {ou_point}",
                "edge":   oe,
                "status": "🚀" if oe > 20 else "✅" if oe >= 5 else "⚪" if oe >= -5 else "❌",
                "quarter_kelly_stake": round(
                    max(0, (oe / 100) / (over_odds - 1 + 0.001) * 0.25 * 100), 2
                ) if oe >= 3.2 else 0,
            })

        if under_odds > 0:
            ue = round((under_pct / 100 * under_odds - 1) * 100, 1)
            edges.append({
                "market": f"U {ou_point}",
                "edge":   ue,
                "status": "🚀" if ue > 20 else "✅" if ue >= 5 else "⚪" if ue >= -5 else "❌",
                "quarter_kelly_stake": round(
                    max(0, (ue / 100) / (under_odds - 1 + 0.001) * 0.25 * 100), 2
                ) if ue >= 3.2 else 0,
            })

        analysis["edge_summary"] = edges

        if edges:
            best = max(edges, key=lambda e: e["edge"])
            m["highest_edge_status"] = best.get("status", "⚪")



# ─── Automated Decision Engine Helpers ───

def std_dev_py(lst):
    if len(lst) < 2:
        return 999.0
    mean = sum(lst) / len(lst)
    variance = sum((x - mean) ** 2 for x in lst) / (len(lst) - 1)
    return variance ** 0.5


def calc_consensus_stddev(market, home, away, analysis):
    if market.startswith("O "):
        key, idx = "triangulation_ou", 0
    elif market.startswith("U "):
        key, idx = "triangulation_ou", 1
    elif market.endswith(" -0.5 (AH)"):
        key, idx = "triangulation_ah", 0
    elif market.endswith(" +0.5 (AH)"):
        key, idx = "triangulation_ah", 1
    else:
        return None
        
    source = analysis.get(key)
    if not source:
        return None
        
    probs = []
    for model, vals in source.items():
        if model == "ensemble":
            continue
        if len(vals) > idx:
            probs.append(vals[idx])
            
    if len(probs) < 2:
        return None
    return calc_consensus_stddev_val(probs) if "calc_consensus_stddev_val" in globals() else std_dev_py(probs)


def calc_historical_roi(market, edge, bet_history):
    if not bet_history:
        return None
        
    if market.startswith("O ") or market.startswith("U "):
        fam = "totals"
    elif market.endswith(" -0.5 (AH)") or market.endswith(" +0.5 (AH)"):
        fam = "asian_handicap"
    else:
        fam = "other"
        
    similar = []
    for b in bet_history:
        b_market = b.get("market", "")
        b_edge = b.get("predicted_edge")
        if b_edge is None:
            continue
            
        b_fam = "other"
        if b_market.startswith("O ") or b_market.startswith("U "):
            b_fam = "totals"
        elif b_market.endswith(" -0.5 (AH)") or b_market.endswith(" +0.5 (AH)"):
            b_fam = "asian_handicap"
            
        same_fam = (fam == b_fam)
        similar_edge = abs(b_edge - edge) < 10.0
        
        if same_fam or similar_edge:
            similar.append(b)
            
    if len(similar) < 3:  # MIN_HISTORICAL_BETS
        return None
        
    settled = [b for b in similar if b.get("settled") and b.get("outcome") in ["WON", "LOST"]]
    if not settled:
        return None
        
    total_profit = sum(b.get("profit_rm", 0.0) for b in settled)
    total_stake = sum(b.get("stake_rm", 1.0) for b in settled)
    return total_profit / max(total_stake, 0.01)


def run_gates_python(market, edge, home_team, away_team, analysis, bet_history):
    # Gate 1: Edge >= 3.2
    g1 = edge >= 3.2
    if not g1:
        return False
        
    # Gate 2: Consensus (std dev <= 10)
    g2 = True
    std_dev = calc_consensus_stddev(market, home_team, away_team, analysis)
    if std_dev is not None:
        g2 = std_dev <= 10.0
        
    # Gate 3: History (ROI > 0)
    g3 = True
    roi = calc_historical_roi(market, edge, bet_history)
    if roi is not None:
        g3 = roi > 0
        
    return g1 and g2 and g3


def determine_outcome(market, score_str, home_team, away_team):
    try:
        home_score, away_score = map(int, score_str.split("-"))
    except Exception:
        return None
    
    total_goals = home_score + away_score
    
    # 1. Over/Under
    if market.startswith("O "):
        try:
            line = float(market.split(" ")[1])
            return "WON" if total_goals > line else "LOST"
        except Exception:
            pass
    elif market.startswith("U "):
        try:
            line = float(market.split(" ")[1])
            return "WON" if total_goals < line else "LOST"
        except Exception:
            pass

    # 2. BTTS
    if market == "BTTS Yes":
        return "WON" if (home_score > 0 and away_score > 0) else "LOST"
    elif market == "BTTS No":
        return "WON" if not (home_score > 0 and away_score > 0) else "LOST"

    # 3. 1X2 / Match Win / Draw
    if market == "Draw":
        return "WON" if home_score == away_score else "LOST"
    
    if market.endswith(" Win"):
        team = market.replace(" Win", "").strip()
        if team == home_team:
            return "WON" if home_score > away_score else "LOST"
        elif team == away_team:
            return "WON" if away_score > home_score else "LOST"

    # 4. Asian Handicap
    if "(AH)" in market:
        m_clean = market.replace(" (AH)", "").strip()
        parts = m_clean.rsplit(" ", 1)
        if len(parts) == 2:
            team, point_str = parts
            try:
                point = float(point_str)
                is_home = (team == home_team)
                diff = (home_score - away_score) if is_home else (away_score - home_score)
                net = diff + point
                if net > 0:
                    return "WON"
                elif net < 0:
                    return "LOST"
                else:
                    return "VOID"
            except Exception:
                pass

    return None


def auto_log_system_bets(matches, bet_history):
    logged_count = 0
    existing_sigs = {
        (b.get("home_team"), b.get("away_team"), b.get("market"))
        for b in bet_history
    }
    
    for m in matches:
        home = m.get("home_team")
        away = m.get("away_team")
        analysis = m.get("analysis", {})
        edges = analysis.get("edge_summary", [])
        
        for e in edges:
            market = e.get("market")
            edge = e.get("edge", 0)
            odds = 0
            if market.endswith(" -0.5 (AH)"):
                odds = m.get("home_odds", 0)
            elif market.endswith(" +0.5 (AH)"):
                odds = m.get("away_odds", 0)
            elif market.startswith("O "):
                odds = analysis.get("sport_raw", {}).get("over_odds", 0)
            elif market.startswith("U "):
                odds = analysis.get("sport_raw", {}).get("under_odds", 0)
                
            if run_gates_python(market, edge, home, away, analysis, bet_history) and odds > 0:
                sig = (home, away, market)
                if sig not in existing_sigs:
                    new_bet = {
                        "id": f"sys_{int(time.time())}_{sig[0][:3].lower()}_{sig[1][:3].lower()}",
                        "match_id": m.get("id", ""),
                        "home_team": home,
                        "away_team": away,
                        "market": market,
                        "odds_decimal": float(odds),
                        "stake_rm": 10.0,
                        "predicted_edge": float(edge),
                        "date_placed": fmt_now(),
                        "date_settled": None,
                        "outcome": "PENDING",
                        "profit_rm": 0.0,
                        "settled": False,
                        "score": "",
                        "notes": "System Auto-Logged Shadow Bet",
                        "source": "system_shadow"
                    }
                    bet_history.append(new_bet)
                    existing_sigs.add(sig)
                    logged_count += 1
                    print(f"[SHADOW LOG] ✅ Auto-logged system recommendation: {home} vs {away} | {market} @ {odds}")
    return logged_count


def auto_settle_bets(bet_history):
    pending = [b for b in bet_history if not b.get("settled") or b.get("outcome") == "PENDING"]
    if not pending:
        return 0, 0.0
        
    api_key = ODDS_API_KEY
    if not api_key:
        print("[AUTO SETTLE] ⚠️ No ODDS_API_KEY, skipping...")
        return 0, 0.0
        
    url = f"https://api.the-odds-api.com/v4/sports/soccer_fifa_world_cup/scores/?apiKey={api_key}&daysFrom=3"
    print(f"[AUTO SETTLE] Fetching completed scores from the-odds-api...")
    try:
        r = req_lib.get(url, timeout=20)
        if r.status_code != 200:
            print(f"[AUTO SETTLE] ⚠️ API returned status code {r.status_code}: {r.text[:200]}")
            return 0, 0.0
        scores_data = r.json()
    except Exception as e:
        print(f"[AUTO SETTLE] ⚠️ Failed to fetch completed scores: {e}")
        return 0, 0.0
        
    completed_lookup = {}
    for game in scores_data:
        if not game.get("completed", False):
            continue
        home = normalize_team(game.get("home_team", ""))
        away = normalize_team(game.get("away_team", ""))
        
        scores_list = game.get("scores")
        if not scores_list or len(scores_list) < 2:
            continue
            
        home_score = None
        away_score = None
        for score_entry in scores_list:
            t_name = normalize_team(score_entry.get("name", ""))
            if t_name == home:
                home_score = int(score_entry.get("score", 0))
            elif t_name == away:
                away_score = int(score_entry.get("score", 0))
                
        if home_score is not None and away_score is not None:
            completed_lookup[(home, away)] = f"{home_score}-{away_score}"
            
    settled_count = 0
    net_profit = 0.0
    
    for b in bet_history:
        if b.get("settled") and b.get("outcome") != "PENDING":
            continue
            
        b_home = normalize_team(b.get("home_team", ""))
        b_away = normalize_team(b.get("away_team", ""))
        
        score_str = completed_lookup.get((b_home, b_away))
        if not score_str:
            score_str = completed_lookup.get((b_away, b_home))
            if score_str:
                score_str = "-".join(score_str.split("-")[::-1])
                
        if score_str:
            outcome = determine_outcome(b.get("market"), score_str, b.get("home_team"), b.get("away_team"))
            if outcome:
                odds = b.get("odds_decimal", 1.0)
                stake = b.get("stake_rm", 10.0)
                
                if outcome == "WON":
                    profit = round(stake * (odds - 1.0), 2)
                elif outcome == "LOST":
                    profit = -stake
                else:  # VOID
                    profit = 0.0
                    
                b["settled"] = True
                b["outcome"] = outcome
                b["profit_rm"] = profit
                b["score"] = score_str
                b["date_settled"] = fmt_now()
                
                settled_count += 1
                net_profit += profit
                print(f"[AUTO SETTLE] ✅ Settled bet: {b.get('home_team')} vs {b.get('away_team')} | {b.get('market')} | Score={score_str} | Result={outcome} | Profit={profit:+.2f} RM")
                
    return settled_count, net_profit


def merge_with_existing(new_matches):
    """Merge new matches into existing data.json, preserving history."""
    existing = {}
    if DATA_FILE.exists():
        existing = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    
    existing_matches = {m["id"]: m for m in existing.get("matches", [])}
    
    for m in new_matches:
        mid = m["id"]
        if mid in existing_matches:
            old = existing_matches[mid]
            oa = old.get("analysis", {})
            # Preserve narrative
            for key in ["form", "injuries", "tactical"]:
                if oa.get("narrative", {}).get(key):
                    m["analysis"]["narrative"][key] = oa["narrative"][key]
            if old.get("venue") and old["venue"] != "Stadium":
                m["venue"] = old["venue"]
    
    bet_history = existing.get("bet_history", [])
    
    # 1. Run auto-settlement using completed scores
    settled_count, net_profit = auto_settle_bets(bet_history)
    
    # 2. Run auto-logging of system shadow bets
    logged_count = auto_log_system_bets(new_matches, bet_history)
    
    status_block = existing.get("system_status", {})
    existing_bankroll = status_block.get("bankroll_rm", 34.20)
    existing_profit = status_block.get("total_profit_rm", 4.20)
    
    new_bankroll = round(existing_bankroll + net_profit, 2)
    new_profit = round(existing_profit + net_profit, 2)
    
    settled_bets = [b for b in bet_history if b.get("settled") and b.get("outcome") in ["WON", "LOST"]]
    won_bets = [b for b in settled_bets if b.get("outcome") == "WON"]
    
    return {
        "system_status": {
            "last_updated": fmt_now(),
            "bankroll_rm": new_bankroll,
            "total_profit_rm": new_profit,
            "total_bets": len(settled_bets),
            "won_bets": len(won_bets),
        },
        "bet_history": bet_history,
        "matches": new_matches,
    }


# ═══════════════════════════════════════════
# DEPLOY
# ═══════════════════════════════════════════

def deploy():
    """Build and deploy to Netlify Drop."""
    print("\n[DEPLOY] Running npm build...")
    build_result = subprocess.run(
        "npm run build",
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
        timeout=90,
        shell=True,
    )
    if build_result.returncode != 0:
        print(f"[DEPLOY] ❌ Build failed: {build_result.stderr[:500]}")
        return False
    
    print("[DEPLOY] ✅ Build OK. Deploying via Netlify API...")
    
    zip_path = BASE_DIR / "deploy.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(str(DIST_DIR)):
            for fname in files:
                fpath = os.path.join(root, fname)
                arcname = os.path.relpath(fpath, str(DIST_DIR)).replace("\\", "/")
                zf.write(fpath, arcname)
    
    deploy_token = os.environ.get("NETLIFY_AUTH_TOKEN", "nfp_fGAN5ehwsHaD87oZmJ24AF2Gvi473ZnQ216c")
    site_id = "3d225a22-04e0-40fa-9629-0fb0f9cb8d40"
    
    with open(zip_path, "rb") as f:
        r = req_lib.post(
            f"https://api.netlify.com/api/v1/sites/{site_id}/deploys",
            headers={"Authorization": f"Bearer {deploy_token}"},
            files={"zip": ("deploy.zip", f, "application/zip")},
            timeout=60,
        )
    
    zip_path.unlink(missing_ok=True)
    
    d = r.json()
    did = d.get("id")
    if did and d.get("state") in ("uploaded", "ready"):
        print(f"[DEPLOY] ✅ Deploy successful! ID: {did}")
        print(f"          https://sportmania-betting.netlify.app")
        return True
    else:
        print(f"[DEPLOY] ⚠️ {d.get('state', '?')} — {d.get('error_message', '')}")
        return False


# ═══════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════

def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    dry_run = "--dry-run" in sys.argv
    do_deploy = "--deploy" in sys.argv
    skip_1xbet = "--skip-1xbet" in sys.argv or "SKIP_1XBET" in os.environ
    force = "--force" in sys.argv
    
    print(f"{'='*60}")
    print(f"AUTO SCRAPER — {fmt_now()}")
    print(f"{'='*60}")
    
    # ── Freshness check ──
    if not force and DATA_FILE.exists():
        try:
            existing = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            last_upd = existing.get("system_status", {}).get("last_updated", "")
            if last_upd:
                age = datetime.now(timezone.utc) - datetime.fromisoformat(last_upd.replace("Z", "+00:00"))
                if age < timedelta(minutes=50):
                    print(f"⏳ Data is {age.seconds//60} min fresh. Use --force to override.\n")
                    return
        except Exception:
            pass
    
    # ── Scrape ──
    sources = []
    
    # Source 1: 1xBet (fast, reliable, no browser)
    if not skip_1xbet:
        print(f"\n{'─'*40}")
        print("SOURCE 1: 1xBet Malaysia (API)")
        print(f"{'─'*40}")
        xbet = scrape_1xbet()
        if xbet:
            sources.append(("1xBet", xbet))
    else:
        print("\n1xBet: ⏭️ Skipped")
    
    # Source 2: the-odds-api (also provides raw data for Pinnacle extraction)
    print(f"\n{'─'*40}")
    print("SOURCE 2: the-odds-api (fallback)")
    print(f"{'─'*40}")
    api_result = scrape_api()
    raw_api_data = []
    if isinstance(api_result, tuple):
        api_converted, raw_api_data = api_result
    else:
        api_converted = api_result  # backward compat if empty list
    if api_converted:
        sources.append(("the-odds-api", api_converted))
    
    if not sources:
        print("\n❌ No data from any source!")
        return 1
    
    # ── Merge ──
    print(f"\n{'─'*40}")
    print(f"MERGING {len(sources)} SOURCES")
    print(f"{'─'*40}")
    
    merged = merge_odds(sources)
    compute_edges(merged, raw_api_data=raw_api_data)
    result = merge_with_existing(merged)
    
    print(f"\n✅ Merged {len(result['matches'])} matches:")
    for m in result["matches"]:
        sr = m["analysis"]["sport_raw"]
        edges = m["analysis"]["edge_summary"]
        best = max(edges, key=lambda e: e["edge"])["edge"] if edges else 0
        ah_h = sr.get('home', 0) or 0
        ah_a = sr.get('away', 0) or 0
        ov = sr.get('over_odds', 0) or 0
        ud = sr.get('under_odds', 0) or 0
        print(f"  {m['home_team']:12s} vs {m['away_team']:12s} | {str(sr.get('source','?')):15s} | "
              f"AH: {ah_h:.3f}/{ah_a:.3f} | "
              f"O/U: {ov:.3f}/{ud:.3f} | "
              f"best edge: {best:+.1f}%")
    
    if dry_run:
        print("\n─── DRY RUN — not writing ───")
        return 0
    
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n✅ Written to {DATA_FILE}")
    
    if do_deploy:
        deploy()
    else:
        print("\n─── Use --deploy to build + deploy ───")
    
    print(f"\n{'='*60}")
    print(f"✅ DONE — {fmt_now()}")
    print(f"{'='*60}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
