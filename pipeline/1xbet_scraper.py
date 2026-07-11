"""
1xbet_scraper.py — Scrape odds from 1xBet Malaysia using requests + parsing.
Logs in with credentials, extracts World Cup QF odds, updates data.json.

Usage:
  python pipeline/1xbet_scraper.py              # scrape + update
  python pipeline/1xbet_scraper.py --dry-run     # print only
"""
import json, os, re, sys, time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_FILE = BASE_DIR / "public" / "data.json"

USERNAME = "1733712589"
PASSWORD = "Tapestry1Constrict1raking."
BASE_URL = "https://1xbet-malaysia.mobi"

# Session with browser-like headers
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,ms;q=0.8",
})


def fmt_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def login():
    """Login to 1xBet and maintain session cookies."""
    print("[1] Logging in to 1xBet...")
    
    # Get login page (to get CSRF token / cookies)
    r = SESSION.get(f"{BASE_URL}/en/user/login", timeout=10)
    
    # Extract CSRF token if present
    csrf_match = re.search(r'name="_csrf"[^>]*value="([^"]+)"', r.text)
    csrf = csrf_match.group(1) if csrf_match else ""
    
    # Submit login
    login_data = {
        "LoginForm[username]": USERNAME,
        "LoginForm[password]": PASSWORD,
        "LoginForm[rememberMe]": "1",
    }
    if csrf:
        login_data["_csrf"] = csrf
    
    r2 = SESSION.post(f"{BASE_URL}/en/user/login", data=login_data, timeout=10,
                      allow_redirects=True)
    
    if "My account" in r2.text or "Deposit" in r2.text or "9 MYR" in r2.text:
        print("[1] ✅ Login successful")
        return True
    else:
        print("[1] ⚠️ Login may have failed — will try anyway")
        print(f"    Response: {r2.url}")
        return False


def fetch_line_page():
    # Fetch the football line page (shows World Cup in Top Sports)
    print("[2] Fetching football line page...")
    r = SESSION.get(f"{BASE_URL}/en/line/football", timeout=10)
    
    print(f"[2] Page: {r.url}")
    return r.text


def parse_odds_from_html(html):
    """Parse 1xBet line page HTML to extract match odds.
    
    The page has <article> elements with:
    - Team names in <li> elements
    - Odds buttons in <sectionfooter>
    - Each button has format: "MARKET_NAME ODDS_VALUE"
    """
    matches = []
    
    # Find all match articles
    # Structure: <article> -> <li> teams, <sectionfooter> -> <li> -> <button>
    
    # Split by article
    articles = re.split(r'<article[^>]*>', html)[1:]  # skip first
    
    for art_html in articles:
        # Extract team names from list items (first two li elements before any button)
        team_section = art_html.split("<sectionfooter")[0] if "<sectionfooter" in art_html else art_html
        
        # Find team names
        team_matches = re.findall(r'<li[^>]*>(?:<a[^>]*>)?\s*<span[^>]*>\s*([^<]+)\s*</span>', team_section)
        
        if len(team_matches) < 2:
            # Try alternative pattern - just text inside li after StaticText
            team_matches = re.findall(r'StaticText\s+"([^"]+)"', team_section)
            # Filter to likely team names (not dates, leagues, etc.)
            team_matches = [t for t in team_matches if not re.match(r'^\d', t) and len(t) > 2]
        
        if len(team_matches) < 2:
            continue
        
        home_team = team_matches[0].strip() if len(team_matches) > 0 else ""
        away_team = team_matches[1].strip() if len(team_matches) > 1 else ""
        
        # Extract league/stage
        stage_match = re.search(r'<span[^>]*>\s*([^<]+(?:Round|Play-off|Group|Qualifier)[^<]*)</span>', art_html)
        stage = stage_match.group(1).strip() if stage_match else "Quarterfinal"
        
        # Extract header section for league name
        league_match = re.search(r'StaticText\s+"([^"]*World Cup[^"]*)"', art_html)
        
        # Skip if not World Cup
        if league_match and "World Cup" not in league_match.group(1):
            # It might still be World Cup but a different tournament name
            pass
        
        # Extract odds from sectionfooter buttons
        odds = {}
        if "<sectionfooter" in art_html:
            footer_section = art_html.split("<sectionfooter")[1]
            # Find all buttons with odds
            # Pattern: button text like "W1 1.639" or "HANDICAP 1 (-1.5) 2.682"
            btn_matches = re.findall(
                r'<button[^>]*>\s*(?:<span[^>]*>([^<]+)</span>\s*)?<span[^>]*>\s*([\d.]+)\s*</span>',
                footer_section
            )
            for label, price in btn_matches:
                price_f = float(price)
                if "W1" == label.strip():
                    odds["home_win"] = price_f
                elif "W2" == label.strip():
                    odds["away_win"] = price_f
                elif "DRAW" == label.strip():
                    odds["draw"] = price_f
                elif "HANDICAP 1" in label:
                    # Extract handicap value
                    hcap = re.search(r'\(([^)]+)\)', label)
                    hcap_val = hcap.group(1) if hcap else ""
                    # Store as home handicap
                    odds["handicap_home"] = {"point": hcap_val, "price": price_f}
                elif "HANDICAP 2" in label:
                    hcap = re.search(r'\(([^)]+)\)', label)
                    hcap_val = hcap.group(1) if hcap else ""
                    odds["handicap_away"] = {"point": hcap_val, "price": price_f}
                elif "TOTAL" in label and "O" in label.split()[-2:] if len(label.split()) >= 2 else False:
                    # Total over: "TOTAL 2.5 O" or "ASIAN TOTAL 2.75 O"
                    total_match = re.search(r'TOTAL\s+([\d.]+)\s+O', label)
                    if total_match:
                        total_val = total_match.group(1)
                        odds["over"] = {"point": total_val, "price": price_f}
                elif "TOTAL" in label and "U" in label:
                    total_match = re.search(r'TOTAL\s+([\d.]+)\s+U', label)
                    if total_match:
                        total_val = total_match.group(1)
                        odds["under"] = {"point": total_val, "price": price_f}
                elif "ASIAN HANDICAP" in label:
                    ah_match = re.search(r'ASIAN HANDICAP\s+(-?[\d.]+)\s+([12])', label)
                    if ah_match:
                        ah_point = ah_match.group(1)
                        ah_team = ah_match.group(2)
                        odds[f"ah_{ah_team}"] = {"point": ah_point, "price": price_f}
                elif label.strip() in ("1X", "12", "2X"):
                    odds[label.strip()] = price_f
        
        match = {
            "home_team": home_team,
            "away_team": away_team,
            "stage": stage,
            "odds": odds,
        }
        matches.append(match)
        print(f"  {home_team:12} v {away_team:12} | 1X2: {odds.get('home_win','-')}/{odds.get('draw','-')}/{odds.get('away_win','-')} | "
              f"O/U: {odds.get('over',{}).get('price','-')}/{odds.get('under',{}).get('price','-')}")
    
    return matches


def update_data_json(matches, dry_run=False):
    """Update data.json with 1xBet odds."""
    if not DATA_FILE.exists():
        print(f"[!] data.json not found at {DATA_FILE}")
        return False
    
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    now_iso = fmt_now()
    data["system_status"]["last_updated"] = now_iso
    
    updated = 0
    for match in matches:
        ht = match["home_team"].lower().strip()
        at = match["away_team"].lower().strip()
        
        # Find corresponding match in data.json
        for dm in data.get("matches", []):
            dmh = dm["home_team"].lower().strip()
            dma = dm["away_team"].lower().strip()
            if {dmh, dma} == {ht, at}:
                odds = match["odds"]
                
                # Set 1X2 odds (used for draw_no_bet computation)
                if odds.get("home_win"):
                    dm["home_odds"] = odds["home_win"]
                if odds.get("away_win"):
                    dm["away_odds"] = odds["away_win"]
                if odds.get("draw"):
                    dm["draw_odds"] = odds["draw"]
                
                # Update sport_raw with 1xBet data
                sr = dm["analysis"].get("sport_raw", {})
                sr["source"] = "1xBet"
                sr["vig"] = 0
                if odds.get("home_win") and odds.get("away_win") and odds.get("draw"):
                    sr["home"] = odds["home_win"]
                    sr["draw"] = odds["draw"]
                    sr["away"] = odds["away_win"]
                    # Compute vig
                    imp = 1/odds["home_win"] + 1/odds["draw"] + 1/odds["away_win"]
                    sr["vig"] = round((imp - 1) * 100, 2)
                
                # Set AH odds from 1X2 (convert to -0.5/+0.5)
                # For AH -0.5: implied prob = home_win / (home_win + draw + away_win)
                # For the handicap odds, use the actual handicap values
                ah_home = odds.get("handicap_home", {})
                ah_away = odds.get("handicap_away", {})
                if ah_home and ah_away:
                    sr["point_home"] = ah_home.get("point")
                    sr["point_away"] = ah_away.get("point")
                    sr["home_ah"] = ah_home["price"]
                    sr["away_ah"] = ah_away["price"]
                
                # O/U odds
                over = odds.get("over", {})
                under = odds.get("under", {})
                if over and under:
                    sr["over_odds"] = over["price"]
                    sr["under_odds"] = under["price"]
                    sr["ou_point"] = over.get("point")
                
                updated += 1
                break
    
    if dry_run:
        print(f"\n[Dry run] Would update {updated}/{len(matches)} matches")
        return True
    
    DATA_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"\n[3] ✅ Updated {updated}/{len(matches)} matches in data.json")
    return True


def main():
    dry_run = "--dry-run" in sys.argv
    print(f"{'='*60}")
    print(f"1XBET SCRAPER — {fmt_now()}")
    print(f"{'='*60}")
    
    # Login
    if not login():
        print("[!] Login failed — exiting")
        return
    
    # Fetch line page
    html = fetch_line_page()
    if not html or len(html) < 1000:
        print("[!] Empty page received")
        return
    
    # Parse odds
    print("[3] Parsing odds...")
    matches = parse_odds_from_html(html)
    print(f"\n[3] Found {len(matches)} matches")
    
    if not matches:
        print("[!] No matches parsed — page structure may have changed")
        # Save HTML for debugging
        debug_path = BASE_DIR / "pipeline" / "1xbet_debug.html"
        debug_path.write_text(html[:10000], encoding="utf-8")
        print(f"    Saved first 10KB to {debug_path}")
        return
    
    # Update data.json
    update_data_json(matches, dry_run=dry_run)
    
    print(f"\n{'='*60}")
    print(f"✅ DONE — {fmt_now()}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
