"""
auto_scraper.py — Fully automated odds scraper (no AI needed).

Three data sources, cascading fallback:
  1. 1xBet Malaysia (cloudscraper → API) ← fastest, most reliable
  2. 12Play MY     (Playwright headless login → 12SPORT)
  3. the-odds-api  (HTTP, reliable backup)

Pipeline: scrape → merge → compute edges → write data.json → deploy

Usage:
  python pipeline/auto_scraper.py              # scrape all + update
  python pipeline/auto_scraper.py --dry-run     # print only, no write
  python pipeline/auto_scraper.py --skip-1xbet  # skip 1xBet
  python pipeline/auto_scraper.py --skip-12play # skip 12Play
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

# ─── Config ───
BASE_DIR = Path(__file__).resolve().parent.parent
PUBLIC_DIR = BASE_DIR / "public"
DATA_FILE = PUBLIC_DIR / "data.json"
DIST_DIR = BASE_DIR / "dist"

# 1xBet credentials
XBET_USERNAME = "1733712589"
XBET_PASSWORD = "Tapestry1Constrict1raking."
XBET_BASE = "https://1xbet-malaysia.mobi"

# 12Play credentials
PLAY12_USERNAME = "lordirfan"
PLAY12_PASSWORD = "lordirfan"
PLAY12_BASE = "https://www.12play21.com"

# the-odds-api
ODDS_API_KEY = "b45c8f0693e8a7912baf2449e98d6fb8"
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
    imp = sum(1 / o for o in odds_list if o > 0)
    return round((imp - 1) * 100, 2)


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
# SOURCE 2: 12Play via undetected-chromedriver
# ═══════════════════════════════════════════

def scrape_12play():
    """
    Scrape World Cup odds from 12Play/12SPORT (12PSports.com).

    Flow:
    1. Login to 12Play via cloudscraper (fast, sets cookies)
    2. Navigate undetected-chromedriver to 12PSports iframe URL
    3. SSO auto-auths, sportsbook renders Malay odds
    4. Extract and convert to decimal odds
    """
    import time, re, tempfile
    
    # Step 1: Login via cloudscraper (get auth cookies)
    print("[12PLAY] Logging in via cloudscraper...")
    try:
        cscraper = cloudscraper.create_scraper()
        cscraper.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/132.0.0.0 Safari/537.36",
        })
        cscraper.get(f"{PLAY12_BASE}/en-MY/login", timeout=15)
        r = cscraper.post(
            f"{PLAY12_BASE}/en-MY/login",
            data={"username": PLAY12_USERNAME, "password": PLAY12_PASSWORD},
            timeout=15,
        )
        if "MYR" in r.text:
            print("[12PLAY] ✅ Cloudscraper login OK")
        else:
            print("[12PLAY] ⚠️ Cloudscraper login unsure, continuing...")
    except Exception as e:
        print(f"[12PLAY] ⚠️ Cloudscraper error: {e}")
    
    # Step 2: Use undetected-chromedriver to load 12PSports
    print("[12PLAY] Launching headless browser for 12PSports...")
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    
    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-blink-features=AutomationControlled")
    ud = tempfile.mkdtemp()
    options.add_argument(f"--user-data-dir={ud}")
    
    driver = uc.Chrome(options=options, headless=True, use_subprocess=True, version_main=149)
    
    try:
        # Login to 12Play to establish session
        driver.get(f"{PLAY12_BASE}/en-MY/login")
        time.sleep(2)
        driver.find_element(By.NAME, "username").send_keys(PLAY12_USERNAME)
        driver.find_element(By.NAME, "password").send_keys(PLAY12_PASSWORD)
        driver.find_element(By.XPATH, "//button[contains(text(), 'Login')]").click()
        time.sleep(3)
        
        # Navigate DIRECTLY to 12PSports (bypass SPA click)
        print("[12PLAY] Navigating to 12PSports...")
        driver.get("https://www.12psports.com/game.php?currency=MYR&platform_origin=www.12play21.com")
        
        # Wait for SSO redirect and render
        for i in range(12):
            html = driver.page_source
            body = re.sub(r'<[^>]+>', ' ', html)
            body = re.sub(r'\s+', ' ', body)
            
            pat = r'(Spain|Belgium|Norway|England|Argentina|Switzerland|France)\s+(Spain|Belgium|Norway|England|Argentina|Switzerland|France)\s+1\s+(-?[\d.]+)\s+X\s+(-?[\d.]+)\s+2\s+(-?[\d.]+)'
            matches = re.findall(pat, body)
            if matches:
                print(f"[12PLAY] ✅ Odds rendered ({len(matches)} matches)")
                parsed = _parse_12sport_html(html)
                driver.quit()
                return parsed
            time.sleep(2.5)
        
        driver.quit()
        print("[12PLAY] ⚠️ No matches found after timeout")
        return []
        
    except Exception as e:
        print(f"[12PLAY] ❌ {e}")
        try:
            driver.quit()
        except:
            pass
        return []


# ─── 12SPORT HTML parser ───

def _parse_12sport_html(html):
    """
    Parse 12PSports iframe HTML to extract match odds.
    
    12PSports renders match info in Malay odds format:
        Norway England 1 -0.3534 X -0.3788 2 0.94
    
    Malay odds conversion:
        Negative: Decimal = 1 + (1 / |malay|)
        Positive: Decimal = 1 + malay
    """
    import re
    
    results = []
    
    # Strategy 1: Extract from body text (post-JS render)
    body_text = re.sub(r'<[^>]+>', ' ', html)
    body_text = re.sub(r'\s+', ' ', body_text)
    
    # Pattern: Team1 Team2 1 <malay_odds> X <malay_odds> 2 <malay_odds>
    # Look for our specific matches
    pattern = r'(Spain|Belgium|Norway|England|Argentina|Switzerland|France)\s+(Spain|Belgium|Norway|England|Argentina|Switzerland|France)\s+1\s+(-?[\d.]+)\s+X\s+(-?[\d.]+)\s+2\s+(-?[\d.]+)'
    
    matches = re.findall(pattern, body_text)
    
    for match in matches:
        h_team, a_team, m1, mX, m2 = match
        
        mid = find_match_id(h_team, a_team)
        if not mid:
            continue
        
        def malay_to_decimal(m):
            val = float(m)
            if val < 0:
                return round(1 + (1 / abs(val)), 3)
            else:
                return round(1 + val, 3)
        
        h_decimal = malay_to_decimal(m1)
        d_decimal = malay_to_decimal(mX)
        a_decimal = malay_to_decimal(m2)
        
        # Compute AH
        if h_decimal > 0:
            ah_home = h_decimal
            if a_decimal > 0 and d_decimal > 0:
                imp = 1/a_decimal + 1/d_decimal
                ah_away = round(1/imp, 3) if imp > 0 else a_decimal
            else:
                ah_away = a_decimal
        else:
            ah_home = 0
            ah_away = 0
        
        results.append({
            "match_id": mid,
            "home_team": MATCH_DB.get(mid, {}).get("home_team", h_team),
            "away_team": MATCH_DB.get(mid, {}).get("away_team", a_team),
            "odds": {
                "h1": h_decimal,
                "hX": d_decimal,
                "h2": a_decimal,
                "ah_home": ah_home,
                "ah_away": ah_away,
                "over": 0,
                "under": 0,
                "ou_point": 2.5,
                "source": "12Play",
            },
        })
        
        print(f"  {h_team:12s} vs {a_team:12s} | Malay: {m1}/{mX}/{m2} → Decimal: {h_decimal:.3f}/{d_decimal:.3f}/{a_decimal:.3f}")
    
    return results


def parse_12sport_html(html):
    """
    Parse 12SPORT page HTML.
    Tries to find match odds from the rendered page.
    """
    matches = []
    
    # Strategy 1: JSON data in scripts
    soup = BeautifulSoup(html, "lxml")
    scripts = soup.find_all("script")
    
    for script in scripts:
        text = script.string or ""
        for pattern in [
            r"window\.__NUXT__\s*=\s*({.*?});",
            r"window\.__INITIAL_STATE__\s*=\s*({.*?});",
        ]:
            m = re.search(pattern, text, re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group(1))
                    extracted = extract_12play_json(data)
                    if extracted:
                        matches.extend(extracted)
                        return matches
                except Exception:
                    continue
    
    # Strategy 2: Parse table structure
    # Look for team names and odds in visible text
    body_text = soup.get_text()
    
    # Find match patterns like "Norway vs England" or "Argentina - Switzerland"
    team_matches = []
    for mid, mdata in MATCH_DB.items():
        h = mdata["home_team"]
        a = mdata["away_team"]
        if h in body_text and a in body_text:
            team_matches.append(mid)
    
    for mid in team_matches:
        mdata = MATCH_DB[mid]
        
        # Find odds numbers near team names
        # This is imprecise without proper HTML parsing
        # Look for patterns like "1.59 3.91 6.00"
        odds_pattern = re.findall(r">\s*(\d+\.\d{2,4})\s*<", html)
        odds_floats = [float(o) for o in odds_pattern if 1.01 <= float(o) <= 15.0]
        
        if len(odds_floats) >= 6:
            matches.append({
                "match_id": mid,
                "home_team": mdata["home_team"],
                "away_team": mdata["away_team"],
                "odds": {
                    "h1": odds_floats[0],
                    "hX": odds_floats[1],
                    "h2": odds_floats[2],
                    "ah_home": 1 / (1 / odds_floats[0]) if odds_floats[0] > 0 else 0,
                    "ah_away": odds_floats[0],
                    "over": odds_floats[3],
                    "under": odds_floats[4],
                    "ou_point": 2.5,
                    "source": "12Play",
                },
            })
    
    return matches


def extract_12play_json(data):
    """Extract match odds from 12SPORT JSON data."""
    extracted = []
    
    def search(obj, depth=0):
        if depth > 5:
            return
        if isinstance(obj, dict):
            home = obj.get("homeTeam") or obj.get("home_team") or obj.get("homeName") or ""
            away = obj.get("awayTeam") or obj.get("away_team") or obj.get("awayName") or ""
            if home and away:
                mid = find_match_id(home, away)
                if mid:
                    odds = {}
                    # Look for odds in various formats
                    for k in ["odds", "prices", "markets", "values", "outcomes"]:
                        v = obj.get(k, obj.get(k.upper(), {}))
                        if isinstance(v, dict):
                            odds.update(v)
                    
                    extracted.append({
                        "match_id": mid,
                        "home_team": MATCH_DB[mid]["home_team"],
                        "away_team": MATCH_DB[mid]["away_team"],
                        "odds": {
                            "h1": float(odds.get("home", odds.get("1", odds.get("W1", 0)))),
                            "hX": float(odds.get("draw", odds.get("X", odds.get("DRAW", 0)))),
                            "h2": float(odds.get("away", odds.get("2", odds.get("W2", 0)))),
                            "over": float(odds.get("over", 0)),
                            "under": float(odds.get("under", 0)),
                            "ou_point": 2.5,
                            "source": "12Play",
                        },
                    })
                    return
            
            for v in obj.values():
                search(v, depth + 1)
        elif isinstance(obj, list):
            for item in obj:
                search(item, depth + 1)
    
    search(data)
    return extracted


# ═══════════════════════════════════════════
# SOURCE 3: the-odds-api (HTTP fallback)
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
        return convert_api_data(data)
        
    except Exception as e:
        print(f"[API] ❌ {e}")
        return []


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
    Merge odds from sources. Priority: 1xBet > 12Play > the-odds-api.
    """
    merged = {}
    priority = {"1xBet": 0, "12Play": 1, "the-odds-api": 2}
    
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


def compute_edges(matches):
    """Compute edge analysis for each match."""
    for m in matches:
        analysis = m["analysis"]
        sr = analysis["sport_raw"]
        
        home_odds = sr.get("home", 0)
        away_odds = sr.get("away", 0)
        draw_odds = sr.get("draw", 0)
        over_odds = sr.get("over_odds", 0)
        under_odds = sr.get("under_odds", 0)
        ou_point = sr.get("ou_point", 2.5)
        
        # Devig
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
        draw_pct = poly.get("draw", 0.3) * 100
        away_1x2_pct = poly.get("away", 0.2) * 100
        
        # Triangulation 1X2
        analysis["triangulation_1x2"] = {
            k: [round(home_1x2_pct, 1), round(draw_pct, 1), round(away_1x2_pct, 1)]
            for k in ["polymarket", "dataset", "opta", "xgscore", "dixon_coles", "ensemble"]
        }
        
        # O/U triangulation
        if over_odds > 0 and under_odds > 0:
            ou_vf = vig_free([over_odds, under_odds])
            over_pct = round(ou_vf[0] * 100, 1)
            under_pct = round(ou_vf[1] * 100, 1)
        else:
            over_pct = 50.0
            under_pct = 50.0
        
        analysis["triangulation_ou"] = {
            k: [over_pct, under_pct]
            for k in ["polymarket", "xgscore", "opta", "dixon_coles", "ensemble"]
        }
        
        # AH triangulation
        dnb_home = round(poly.get("home", 0.5) / (poly.get("home", 0.5) + poly.get("away", 0.5)) * 100, 1) if poly.get("home", 0) + poly.get("away", 0) > 0 else 50
        dnb_away = round(100 - dnb_home, 1)
        
        analysis["triangulation_ah"] = {
            k: [dnb_home, dnb_away]
            for k in ["polymarket", "dataset", "opta", "xgscore", "dixon_coles", "ensemble"]
        }
        
        analysis["ah_analysis"] = {
            "home_minus_05_prob": round(poly.get("home", 0.5) * 100, 1),
            "away_plus_05_prob": round(poly.get("away", 0.5) * 100, 1),
            "home_0_prob": dnb_home,
            "away_0_prob": dnb_away,
        }
        
        analysis["ah_odds"] = {
            "home_minus_05": home_odds or 0,
            "away_plus_05": away_odds or 0,
        }
        
        # Edge summary
        edges = []
        hp = round(poly.get("home", 0.5) * 100, 1)
        ap = round(poly.get("away", 0.5) * 100, 1)
        
        if home_odds > 0:
            he = round((hp / 100 * home_odds - 1) * 100, 1)
            edges.append({
                "market": f"{m['home_team']} -0.5 (AH)",
                "edge": he,
                "status": "🚀" if he > 20 else "✅" if he >= 5 else "⚪" if he >= -5 else "❌",
                "quarter_kelly_stake": round(max(0, (he / 100) / (home_odds - 1 + 0.001) * 0.25 * 100), 2) if he >= 3.2 else 0,
            })
        
        if away_odds > 0:
            ae = round((ap / 100 * away_odds - 1) * 100, 1)
            edges.append({
                "market": f"{m['away_team']} +0.5 (AH)",
                "edge": ae,
                "status": "🚀" if ae > 20 else "✅" if ae >= 5 else "⚪" if ae >= -5 else "❌",
                "quarter_kelly_stake": round(max(0, (ae / 100) / (away_odds - 1 + 0.001) * 0.25 * 100), 2) if ae >= 3.2 else 0,
            })
        
        if over_odds > 0:
            oe = round((over_pct / 100 * over_odds - 1) * 100, 1)
            edges.append({
                "market": f"O {ou_point}",
                "edge": oe,
                "status": "🚀" if oe > 20 else "✅" if oe >= 5 else "⚪" if oe >= -5 else "❌",
                "quarter_kelly_stake": round(max(0, (oe / 100) / (over_odds - 1 + 0.001) * 0.25 * 100), 2) if oe >= 3.2 else 0,
            })
        
        if under_odds > 0:
            ue = round((under_pct / 100 * under_odds - 1) * 100, 1)
            edges.append({
                "market": f"U {ou_point}",
                "edge": ue,
                "status": "🚀" if ue > 20 else "✅" if ue >= 5 else "⚪" if ue >= -5 else "❌",
                "quarter_kelly_stake": round(max(0, (ue / 100) / (under_odds - 1 + 0.001) * 0.25 * 100), 2) if ue >= 3.2 else 0,
            })
        
        analysis["edge_summary"] = edges
        
        if edges:
            best = max(edges, key=lambda e: e["edge"])
            m["highest_edge_status"] = best.get("status", "⚪")


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
    
    return {
        "system_status": {
            "last_updated": fmt_now(),
            "bankroll_rm": existing.get("system_status", {}).get("bankroll_rm", 34.20),
            "total_profit_rm": existing.get("system_status", {}).get("total_profit_rm", 4.20),
            "total_bets": existing.get("system_status", {}).get("total_bets", 1),
            "won_bets": existing.get("system_status", {}).get("won_bets", 1),
        },
        "bet_history": existing.get("bet_history", []),
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
    
    deploy_token = "nfp_fGAN5ehwsHaD87oZmJ24AF2Gvi473ZnQ216c"
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
    dry_run = "--dry-run" in sys.argv
    do_deploy = "--deploy" in sys.argv
    skip_1xbet = "--skip-1xbet" in sys.argv or "SKIP_1XBET" in os.environ
    skip_12play = "--skip-12play" in sys.argv or "SKIP_12PLAY" in os.environ
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
                if age < timedelta(hours=2):
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
    
    # Source 2: 12Play (Playwright, slower)
    if not skip_12play:
        print(f"\n{'─'*40}")
        print("SOURCE 2: 12Play MY")
        print(f"{'─'*40}")
        p12 = scrape_12play()
        if p12:
            sources.append(("12Play", p12))
    else:
        print("\n12Play: ⏭️ Skipped")
    
    # Source 3: the-odds-api
    print(f"\n{'─'*40}")
    print("SOURCE 3: the-odds-api (fallback)")
    print(f"{'─'*40}")
    api = scrape_api()
    if api:
        sources.append(("the-odds-api", api))
    
    if not sources:
        print("\n❌ No data from any source!")
        return 1
    
    # ── Merge ──
    print(f"\n{'─'*40}")
    print(f"MERGING {len(sources)} SOURCES")
    print(f"{'─'*40}")
    
    merged = merge_odds(sources)
    compute_edges(merged)
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
