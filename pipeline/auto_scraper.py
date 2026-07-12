"""auto_scraper.py — Multi-league football odds scraper.

Dynamically discovers and scrapes all active football leagues from the-odds-api.
Supports rotation for API quota management.

Sources:
  1. the-odds-api  (Pinnacle / Matchbook — primary, covers 30+ leagues)
  2. 1xBet Malaysia (cloudscraper → API — selective fallback)

Pipeline: scrape → merge → compute edges → write data.json → deploy
"""

import json
import os
import sys
import time
import zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests as req_lib

# ─── Real statistical models ───
sys.path.insert(0, str(Path(__file__).resolve().parent))
from models import compute_dixon_coles, extract_pinnacle_probs, fetch_polymarket_probs

# ─── Config ───
BASE_DIR = Path(__file__).resolve().parent.parent
PUBLIC_DIR = BASE_DIR / "public"
DATA_FILE = PUBLIC_DIR / "data.json"
DIST_DIR = BASE_DIR / "dist"

ODDS_API_KEY = os.environ.get("ODDS_API_KEY", "b45c8f0693e8a7912baf2449e98d6fb8")

# Active summer leagues (July 2026)
# Each cron run queries a subset based on rotation index
ALL_LEAGUES = [
    ("soccer_sweden_allsvenskan",       "Allsvenskan - Sweden"),
    ("soccer_norway_eliteserien",       "Eliteserien - Norway"),
    ("soccer_usa_mls",                  "MLS - USA"),
    ("soccer_brazil_campeonato",        "Brazil Série A"),
    ("soccer_brazil_serie_b",           "Brazil Série B"),
    ("soccer_korea_kleague1",           "K League 1 - Korea"),
    ("soccer_finland_veikkausliiga",    "Veikkausliiga - Finland"),
    ("soccer_argentina_primera_division","Primera División - Argentina"),
    ("soccer_mexico_ligamx",            "Liga MX - Mexico"),
    ("soccer_china_superleague",        "Super League - China"),
    ("soccer_fifa_world_cup",           "FIFA World Cup"),
    ("soccer_england_league1",          "League 1 - England"),
    ("soccer_england_league2",          "League 2 - England"),
    ("soccer_efl_champ",                "Championship - England"),
    ("soccer_switzerland_superleague",  "Swiss Superleague"),
    ("soccer_denmark_superliga",        "Denmark Superliga"),
    ("soccer_japan_j_league",           "J1 League - Japan"),
]

# For rotation: how many leagues to query per cron run
LEAGUES_PER_RUN = 6


# ─── Helpers ───
def fmt_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def vig_free(odds_list):
    imp_total = sum(1 / o for o in odds_list if o > 0)
    if imp_total <= 0:
        return [0] * len(odds_list)
    return [(1 / o) / imp_total if o > 0 else 0 for o in odds_list]


def compute_vig(odds_list):
    imp = sum(1 / o for o in odds_list if o > 0)
    return round(imp, 4)


def parse_iso_date(iso_str):
    """Parse ISO date string safely, returning None if invalid."""
    if not iso_str:
        return None
    try:
        return datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    except Exception:
        return None


# ═══════════════════════════════════════════
# SOURCE 1: the-odds-api (primary)
# ═══════════════════════════════════════════

def scrape_api_leagues(league_keys):
    """Fetch odds for specified leagues from the-odds-api.
    
    Returns dict: league_key -> list of match dicts
    """
    results = {}
    for league_key, league_name in league_keys:
        print(f"[API] Fetching {league_name}...", end=" ")
        try:
            r = req_lib.get(
                f"https://api.the-odds-api.com/v4/sports/{league_key}/odds/",
                params={
                    "apiKey": ODDS_API_KEY,
                    "regions": "eu,us",
                    "markets": "h2h,spreads,totals",
                    "oddsFormat": "decimal",
                },
                timeout=20,
            )
            if r.status_code != 200:
                print(f"HTTP {r.status_code}")
                continue

            matches = r.json()
            if not matches:
                print("0 matches")
                continue

            # Parse into our format
            parsed = []
            for m in matches:
                entry = _parse_api_match(m, league_key, league_name)
                if entry:
                    parsed.append(entry)

            print(f"{len(parsed)} matches")
            results[league_key] = parsed

        except Exception as e:
            print(f"ERROR: {e}")

    return results


def _parse_api_match(m, league_key, league_name):
    """Convert a the-odds-api match dict into our internal format."""
    match_id = m.get("id", "")
    home_team = m.get("home_team", "")
    away_team = m.get("away_team", "")
    commence_time = m.get("commence_time", "")

    if not match_id or not home_team or not away_team:
        return None

    # Find Pinnacle odds for "true price"
    pinnacle_h2h = None
    pinnacle_spread = None
    pinnacle_totals = None
    bookies = []

    for bm in m.get("bookmakers", []):
        bm_key = bm.get("key", "")
        bm_title = bm.get("title", "")
        bookies.append(bm_title)

        # Store all bookmaker odds
        for market in bm.get("markets", []):
            market_key = market.get("key", "")
            outcomes = market.get("outcomes", [])

            if market_key == "h2h" and len(outcomes) >= 3:
                h_odds = outcomes[0].get("price", 0)
                d_odds = outcomes[1].get("price", 0) if len(outcomes) > 1 else 0
                a_odds = outcomes[2].get("price", 0) if len(outcomes) > 2 else 0

                if bm_key == "pinnacle":
                    pinnacle_h2h = {"home": h_odds, "draw": d_odds, "away": a_odds, "source": "Pinnacle"}

            elif market_key == "spreads" and len(outcomes) >= 2:
                if bm_key == "pinnacle":
                    h_point = outcomes[0].get("point", 0)
                    h_price = outcomes[0].get("price", 0)
                    a_point = outcomes[1].get("point", 0)
                    a_price = outcomes[1].get("price", 0)
                    pinnacle_spread = {
                        "home_point": h_point, "home_price": h_price,
                        "away_point": a_point, "away_price": a_price,
                        "source": "Pinnacle",
                    }

            elif market_key == "totals" and len(outcomes) >= 2:
                if bm_key == "pinnacle":
                    point = outcomes[0].get("point", 2.5)
                    over = outcomes[0].get("price", 0)
                    under = outcomes[1].get("price", 0)
                    pinnacle_totals = {
                        "point": point, "over": over, "under": under, "source": "Pinnacle",
                    }

    # Derive AH from 1X2
    if pinnacle_h2h:
        h = pinnacle_h2h["home"]
        d = pinnacle_h2h["draw"]
        a = pinnacle_h2h["away"]
        ah_home = h if h > 0 else 0
        if a > 0 and d > 0:
            imp = 1/a + 1/d
            ah_away = round(1/imp, 3) if imp > 0 else a
        else:
            ah_away = a if a > 0 else 0
    else:
        ah_home = 0
        ah_away = 0

    # Get the best non-Pinnacle odds for comparison (sportsbook odds)
    sport_raw = {"home": 0, "draw": 0, "away": 0, "vig": 0, "source": "the-odds-api"}
    for bm in m.get("bookmakers", []):
        if bm.get("key") == "pinnacle":
            continue
        for market in bm.get("markets", []):
            if market.get("key") == "h2h":
                outcomes = market.get("outcomes", [])
                if len(outcomes) >= 3:
                    h_val = outcomes[0].get("price", 0)
                    d_val = outcomes[1].get("price", 0) if len(outcomes) > 1 else 0
                    a_val = outcomes[2].get("price", 0) if len(outcomes) > 2 else 0
                    if h_val > sport_raw["home"]:
                        sport_raw = {
                            "home": h_val, "draw": d_val, "away": a_val,
                            "vig": compute_vig([h_val, d_val, a_val]),
                            "source": bm.get("title", bm.get("key", "?")),
                            "over_odds": pinnacle_totals["over"] if pinnacle_totals else 0,
                            "under_odds": pinnacle_totals["under"] if pinnacle_totals else 0,
                            "ou_point": pinnacle_totals["point"] if pinnacle_totals else 2.5,
                        }
                    break

    # If no sportsbook found, use Pinnacle
    if sport_raw["home"] == 0 and pinnacle_h2h:
        sport_raw = {
            "home": pinnacle_h2h["home"], "draw": pinnacle_h2h["draw"], "away": pinnacle_h2h["away"],
            "vig": compute_vig([pinnacle_h2h["home"], pinnacle_h2h["draw"], pinnacle_h2h["away"]]),
            "source": "Pinnacle",
            "over_odds": pinnacle_totals["over"] if pinnacle_totals else 0,
            "under_odds": pinnacle_totals["under"] if pinnacle_totals else 0,
            "ou_point": pinnacle_totals["point"] if pinnacle_totals else 2.5,
        }

    # Compute fair probabilities from Pinnacle
    fair_probs = [0.33, 0.33, 0.34]  # default fallback
    if pinnacle_h2h:
        fair_probs = vig_free([pinnacle_h2h["home"], pinnacle_h2h["draw"], pinnacle_h2h["away"]])
        polymarket_devig = {"home": fair_probs[0], "draw": fair_probs[1], "away": fair_probs[2]}
    else:
        polymarket_devig = {"home": 0, "draw": 0, "away": 0}

    # AH probabilities from fair probs
    ah_home_prob = round(fair_probs[0] * 100, 1) if fair_probs else 0
    ah_away_prob = round((fair_probs[1] + fair_probs[2]) * 100, 1) if fair_probs else 0

    # Dixon-Coles via models.py
    dc = compute_dixon_coles(home_team, away_team)

    return {
        "match_id": match_id,
        "home_team": home_team,
        "away_team": away_team,
        "venue": "",
        "stage": league_name,
        "league_key": league_key,
        "league_name": league_name,
        "date": (commence_time[:10] if commence_time else ""),
        "time": "",
        "commence_time": commence_time,
        "bookmakers": bookies,
        "highest_edge_status": "⚪",
        "home_odds": sport_raw.get("home", 0),
        "draw_odds": sport_raw.get("draw", 0),
        "away_odds": sport_raw.get("away", 0),
        "analysis": {
            "sport_raw": sport_raw,
            "polymarket_devig": polymarket_devig,
            "ah_analysis": {
                "home_minus_05_prob": ah_home_prob,
                "away_plus_05_prob": ah_away_prob,
                "home_0_prob": ah_home_prob,
                "away_0_prob": ah_away_prob,
            },
            "edge_summary": [],
            "narrative": {
                "form": "",
                "injuries": "",
                "tactical": "",
            },
        },
    }


# ═══════════════════════════════════════════
# 1XBET (fallback for specific leagues)
# ═══════════════════════════════════════════

# Known working 1xBet match IDs (discovered dynamically or hardcoded)
# Format: match_id -> (1xBet API ID, home, away)
XBET_KNOWN = {}  # Will be populated from previous data or discovered

# 1xBet credentials
XBET_USERNAME = os.environ.get("XBET_USERNAME", "1733712589")
XBET_PASSWORD = os.environ.get("XBET_PASSWORD", "Tapestry1Constrict1raking.")
XBET_BASE = "https://1xbet-malaysia.mobi"

# Currently known match IDs (from previous World Cup tracking)
XBET_FALLBACK_IDS = {
    "fra_spa_05": 735504550,  # France vs Spain
}

import cloudscraper


def scrape_1xbet():
    """Fetch odds from 1xBet for known match IDs."""
    try:
        scraper = cloudscraper.create_scraper()
    except Exception:
        return []

    scraper.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/132.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Referer": f"{XBET_BASE}/en/line/football",
    })

    results = []
    # Try the known fallback IDs plus any discovered from previous runs
    all_ids = dict(XBET_FALLBACK_IDS)
    all_ids.update(XBET_KNOWN)

    for match_id, api_id in all_ids.items():
        try:
            r = scraper.get(
                f"{XBET_BASE}/service-api/LineFeed/GetGameZip?id={api_id}&lng=en",
                timeout=15,
            )
            if r.status_code != 200:
                continue
            d = r.json()
            if not d.get("Success"):
                continue
            value = d.get("Value", {})
            odds = _parse_xbet_game(value)
            if odds:
                odds["match_id"] = match_id
                odds["home_team"] = ""
                odds["away_team"] = ""
                results.append(odds)
                print(f"[1XBET] ✅ {match_id}: {odds.get('h1',0):.3f}/{odds.get('hX',0):.3f}/{odds.get('h2',0):.3f}")
        except Exception:
            continue

    if results:
        print(f"[1XBET] ✅ Got {len(results)} matches")
    return results


def _parse_xbet_game(value):
    """Parse 1xBet GetGameZip response into odds format."""
    e_arr = value.get("E", [])
    if not e_arr:
        return None

    result = {
        "h1": 0, "hX": 0, "h2": 0,
        "ah_home": 0, "ah_away": 0,
        "over": 0, "under": 0, "ou_point": 2.5,
        "source": "1xBet",
    }

    for item in e_arr:
        t = item.get("T")
        g = item.get("G")
        c = item.get("C", 0)
        if g == 1 and t in (1, 2, 3):
            if t == 1: result["h1"] = c
            elif t == 2: result["hX"] = c
            elif t == 3: result["h2"] = c

    if result["h1"] == 0:
        wp = value.get("WP", {})
        p1 = float(wp.get("P1", 0))
        px = float(wp.get("PX", 0))
        p2 = float(wp.get("P2", 0))
        if p1 > 0:
            result["h1"] = round(1 / p1, 3)
            result["hX"] = round(1 / px, 3) if px > 0 else 0
            result["h2"] = round(1 / p2, 3) if p2 > 0 else 0

    # AH -0.5 / +0.5
    h, d, a = result["h1"], result["hX"], result["h2"]
    if h > 0: result["ah_home"] = h
    if a > 0 and d > 0:
        imp = 1/a + 1/d
        result["ah_away"] = round(1/imp, 3) if imp > 0 else a
    elif a > 0: result["ah_away"] = a

    for item in e_arr:
        t, p, c = item.get("T"), item.get("P"), item.get("C", 0)
        if p == 2.5:
            if t == 9: result["under"] = c
            elif t == 10: result["over"] = c

    return result


# ═══════════════════════════════════════════
# MERGE ENGINE
# ═══════════════════════════════════════════

def merge_odds(api_matches):
    """Merge API matches into a unified list. No de-duplication needed
    since the-odds-api returns each match once with multiple bookmakers."""
    return api_matches


def compute_edges(matches, raw_api_data=None):
    """Compute edges for each match using Pinnacle fair probabilities."""
    for m in matches:
        analysis = m.get("analysis", {})
        sr = analysis.get("sport_raw", {})
        pd = analysis.get("polymarket_devig", {})

        edges = []

        # Asian Handicap edge
        home_odds = sr.get("home", 0)
        away_odds = sr.get("away", 0)
        home_fair = pd.get("home", 0)
        away_draw_fair = pd.get("draw", 0) + pd.get("away", 0)

        if home_odds > 0 and home_fair > 0:
            imp_home = 1 / home_odds
            edge_h = (imp_home - home_fair) / home_fair * 100 if home_fair > 0 else 0
            edges.append({
                "market": f"{m['home_team']} -0.5 (AH)",
                "edge": round(edge_h, 1),
                "status": "✅" if edge_h > 5 else ("🚀" if edge_h > 20 else "⚪"),
                "quarter_kelly_stake": round(max(0, edge_h / 25) * 2.5, 2) if edge_h > 3 else 0,
            })

        if away_odds > 0 and away_draw_fair > 0:
            imp_away = 1 / away_odds
            edge_a = (imp_away - away_draw_fair) / away_draw_fair * 100 if away_draw_fair > 0 else 0
            edges.append({
                "market": f"{m['away_team']} +0.5 (AH)",
                "edge": round(edge_a, 1),
                "status": "✅" if edge_a > 5 else ("🚀" if edge_a > 20 else "⚪"),
                "quarter_kelly_stake": round(max(0, edge_a / 25) * 2.5, 2) if edge_a > 3 else 0,
            })

        # Over/Under edge
        over_odds = sr.get("over_odds", 0)
        under_odds = sr.get("under_odds", 0)
        ou_point = sr.get("ou_point", 2.5)

        if over_odds > 0 and under_odds > 0:
            vig_ou = compute_vig([over_odds, under_odds])
            fair_over = (1 / over_odds) / vig_ou if vig_ou > 0 else 0
            fair_under = (1 / under_odds) / vig_ou if vig_ou > 0 else 0

            edge_o = ((1 / over_odds) - fair_over) / fair_over * 100 if fair_over > 0 else 0
            edge_u = ((1 / under_odds) - fair_under) / fair_under * 100 if fair_under > 0 else 0

            edges.append({
                "market": f"O {ou_point}",
                "edge": round(edge_o, 1),
                "status": "✅" if edge_o > 5 else ("🚀" if edge_o > 20 else "⚪"),
                "quarter_kelly_stake": round(max(0, edge_o / 25) * 2.5, 2) if edge_o > 3 else 0,
            })
            edges.append({
                "market": f"U {ou_point}",
                "edge": round(edge_u, 1),
                "status": "✅" if edge_u > 5 else ("🚀" if edge_u > 20 else "⚪"),
                "quarter_kelly_stake": round(max(0, edge_u / 25) * 2.5, 2) if edge_u > 3 else 0,
            })

        analysis["edge_summary"] = edges

        # Highest edge status
        if edges:
            best = max(edges, key=lambda e: e["edge"])
            m["highest_edge_status"] = best["status"]

        # Home/draw/away odds (1X2) from sport_raw or Pinnacle
        m["home_odds"] = sr.get("home", 0)
        m["draw_odds"] = sr.get("draw", 0)
        m["away_odds"] = sr.get("away", 0)


def merge_with_existing(new_matches):
    """Merge new matches into existing data.json, preserving history and narratives."""
    existing = {}
    if DATA_FILE.exists():
        try:
            existing = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    existing_match_map = {}
    for m in existing.get("matches", []):
        mid = m.get("match_id") or m.get("id", "")
        if mid:
            existing_match_map[mid] = m

    for m in new_matches:
        mid = m.get("match_id", "")
        if not mid:
            continue
        if mid in existing_match_map:
            old = existing_match_map[mid]
            oa = old.get("analysis", {})
            na = m.get("analysis", {})
            # Preserve narrative if exists
            for key in ["form", "injuries", "tactical"]:
                if oa.get("narrative", {}).get(key):
                    na["narrative"][key] = oa["narrative"][key]

    # Build new match list: latest data wins, but keep any old matches not in new data
    new_ids = {m["match_id"] for m in new_matches}
    preserved = [m for mid, m in existing_match_map.items() if mid not in new_ids and m.get("date", "") >= "2026-07-01"]

    all_matches = new_matches + preserved
    all_matches.sort(key=lambda m: m.get("commence_time", m.get("date", "")), reverse=True)

    bet_history = existing.get("bet_history", [])
    status_block = existing.get("system_status", {})
    bankroll = status_block.get("bankroll_rm", 34.20)
    profit = status_block.get("total_profit_rm", 4.20)

    return {
        "system_status": {
            "last_updated": fmt_now(),
            "bankroll_rm": bankroll,
            "total_profit_rm": profit,
            "total_bets": len(bet_history),
            "won_bets": sum(1 for b in bet_history if b.get("outcome") == "WON"),
        },
        "bet_history": bet_history,
        "matches": all_matches,
    }


# ═══════════════════════════════════════════
# DEPLOY
# ═══════════════════════════════════════════

def deploy():
    """Build and deploy to Netlify."""
    print("\n[DEPLOY] Running npm build...")
    import subprocess
    build_result = subprocess.run(
        "node ./node_modules/vite/bin/vite.js build",
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
        timeout=120,
        shell=True,
    )
    if build_result.returncode != 0:
        print(f"[DEPLOY] ❌ Build failed: {build_result.stderr[:300]}")
        return False
    print("[DEPLOY] ✅ Build OK. Deploying via Netlify API...")

    deploy_token = os.environ.get("NETLIFY_AUTH_TOKEN", "nfp_fGAN5ehwsHaD87oZmJ24AF2Gvi473ZnQ216c")
    site_id = "3d225a22-04e0-40fa-9629-0fb0f9cb8d40"
    dist_dir = BASE_DIR / "dist"

    # Read all built files
    file_map = {}
    for root, dirs, fnames in os.walk(str(dist_dir)):
        for fname in fnames:
            fpath = os.path.join(root, fname)
            relpath = os.path.relpath(fpath, str(dist_dir)).replace("\\", "/")
            with open(fpath, "rb") as f:
                content = f.read()
            import hashlib
            sha1 = hashlib.sha1(content).hexdigest()
            file_map[relpath] = (content, sha1)

    # Create deploy
    files_manifest = {k: v[1] for k, v in file_map.items()}
    r = req_lib.post(
        f"https://api.netlify.com/api/v1/sites/{site_id}/deploys",
        headers={"Authorization": f"Bearer {deploy_token}", "Content-Type": "application/json"},
        json={"files": files_manifest},
        timeout=30,
    )
    d = r.json()
    deploy_id = d.get("id")
    if not deploy_id:
        print(f"[DEPLOY] ❌ Failed: {d.get('error_message', '?')}")
        return False

    # Upload required files
    required = d.get("required", [])
    if required:
        sha_to_path = {v[1]: k for k, v in file_map.items()}
        for sha in required:
            relpath = sha_to_path.get(sha)
            if not relpath:
                continue
            content = file_map[relpath][0]
            put_r = req_lib.put(
                f"https://api.netlify.com/api/v1/deploys/{deploy_id}/files/{relpath}",
                headers={"Authorization": f"Bearer {deploy_token}", "Content-Type": "application/octet-stream"},
                data=content,
                timeout=30,
            )
            if put_r.status_code != 200:
                print(f"  ⚠️ Upload {relpath}: HTTP {put_r.status_code}")

    # Lock
    req_lib.post(
        f"https://api.netlify.com/api/v1/deploys/{deploy_id}/lock",
        headers={"Authorization": f"Bearer {deploy_token}"},
        timeout=30,
    )

    print(f"[DEPLOY] ✅ Deploy successful! ID: {deploy_id}")
    print(f"          https://sportmania-betting.netlify.app")
    return True


# ═══════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════

def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    dry_run = "--dry-run" in sys.argv
    do_deploy = "--deploy" in sys.argv
    force = "--force" in sys.argv
    rotation_idx = 0  # Could be stored in a file for persistence

    print(f"{'='*60}")
    print(f"AUTO SCRAPER — {fmt_now()}")
    print(f"{'='*60}")

    # Freshness check
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

    # ── Determine which leagues to scrape ──
    # Simple rotation: use all leagues for first run, then rotate
    rotation_file = BASE_DIR / "pipeline" / ".rotation_idx"
    try:
        rotation_idx = int(rotation_file.read_text().strip())
    except Exception:
        rotation_idx = 0

    start_idx = (rotation_idx * LEAGUES_PER_RUN) % len(ALL_LEAGUES)
    selected = []
    for i in range(LEAGUES_PER_RUN):
        idx = (start_idx + i) % len(ALL_LEAGUES)
        selected.append(ALL_LEAGUES[idx])

    print(f"\nLeagues this run ({len(selected)}): {[s[1] for s in selected]}")

    # ── Scrape the-odds-api ──
    print(f"\n{'─'*40}")
    print("SOURCE 1: the-odds-api")
    print(f"{'─'*40}")

    all_matches = []

    # Use pre-scraped fallback file if API quota is exhausted
    fallback_file = BASE_DIR / "pipeline" / "_all_matches.json"
    use_fallback = False

    # Test if API has quota
    try:
        test_r = req_lib.get(
            "https://api.the-odds-api.com/v4/sports/?apiKey=" + ODDS_API_KEY,
            timeout=10,
        )
        remaining = int(test_r.headers.get("x-requests-remaining", 0))
        if remaining < len(selected):
            print(f"[API] ⚠️ Only {remaining} requests left, using cached data")
            use_fallback = True
        elif test_r.status_code != 200:
            use_fallback = True
    except Exception:
        use_fallback = True

    if use_fallback and fallback_file.exists():
        print("[API] Using cached _all_matches.json (API quota exhausted)")
        raw = json.loads(fallback_file.read_text(encoding="utf-8"))
        # Filter to selected leagues
        selected_keys = {s[0] for s in selected}
        raw = [m for m in raw if m.get("_league") in selected_keys]
        print(f"[API] {len(raw)} matches from cache (leagues: {len(selected_keys)})")

        # Parse cached data
        from importlib import import_module
        # Reload with fresh function access
        for m in raw:
            league_key = m.get("_league", "")
            league_name = m.get("_league_name", league_key)
            entry = _parse_api_match(m, league_key, league_name)
            if entry:
                all_matches.append(entry)
    else:
        league_data = scrape_api_leagues(selected)
        for league_key, matches in league_data.items():
            all_matches.extend(matches)

    print(f"\n[API] Total: {len(all_matches)} matches")

    # ── 1xBet fallback ──
    print(f"\n{'─'*40}")
    print("SOURCE 2: 1xBet Malaysia (fallback)")
    print(f"{'─'*40}")
    xbet = scrape_1xbet()
    if xbet:
        print(f"[1XBET] Converting {len(xbet)} matches...")
        # Convert 1xBet format to our match format
        for x in xbet:
            mid = x.get("match_id", "")
            home = x.get("home_team", "")
            away = x.get("away_team", "")
            # Check if match already exists
            if any(m["match_id"] == mid for m in all_matches):
                continue
            if not home or not away:
                continue
            all_matches.append({
                "match_id": mid,
                "home_team": home,
                "away_team": away,
                "venue": "",
                "stage": "1xBet",
                "league_key": "1xbet",
                "league_name": "1xBet Football",
                "date": "",
                "time": "",
                "commence_time": "",
                "bookmakers": ["1xBet"],
                "highest_edge_status": "⚪",
                "home_odds": x.get("h1", 0),
                "draw_odds": x.get("hX", 0),
                "away_odds": x.get("h2", 0),
                "analysis": {
                    "sport_raw": {
                        "home": x.get("ah_home", 0), "draw": 0, "away": x.get("ah_away", 0),
                        "vig": compute_vig([x.get("h1", 0), x.get("hX", 0), x.get("h2", 0)]),
                        "source": "1xBet",
                        "over_odds": x.get("over", 0), "under_odds": x.get("under", 0), "ou_point": 2.5,
                    },
                    "polymarket_devig": {"home": 0, "draw": 0, "away": 0},
                    "ah_analysis": {"home_minus_05_prob": 0, "away_plus_05_prob": 0, "home_0_prob": 0, "away_0_prob": 0},
                    "edge_summary": [],
                    "narrative": {"form": "", "injuries": "", "tactical": ""},
                },
            })

    # ── Compute edges ──
    print(f"\n{'─'*40}")
    print("COMPUTING EDGES")
    print(f"{'─'*40}")
    compute_edges(all_matches)

    # ── Merge with existing ──
    result = merge_with_existing(all_matches)

    if not result["matches"]:
        print("❌ No matches scraped!")
        return 1

    print(f"\n✅ Merged {len(result['matches'])} matches:")
    for m in result["matches"]:
        ln = m.get("league_name", "")[:20]
        edges = m.get("analysis", {}).get("edge_summary", [])
        best = max(edges, key=lambda e: e["edge"])["edge"] if edges else 0
        print(f"  {m['home_team']:20s} vs {m['away_team']:20s} | {ln:20s} | best edge: {best:+.1f}%")

    if dry_run:
        print("\n─── DRY RUN — not writing ───")
        return 0

    # ── Write data.json ──
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n✅ Written to {DATA_FILE}")

    # ── Save rotation index ──
    rotation_file.write_text(str((rotation_idx + 1) % 100))
    print(f"Rotation index: {rotation_idx} -> {rotation_idx + 1}")

    # ── Deploy ──
    if do_deploy:
        deploy()

    print(f"\n{'='*60}")
    print(f"✅ DONE — {fmt_now()}")
    print(f"{'='*60}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
