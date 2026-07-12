"""scraper_oddsapi.py — Odds-API.io v3 integration.

Provides Betfair Exchange back/lay prices + 1xBet odds.
Free tier: 5,000 requests/hour.
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

API_KEY = os.environ.get("ODDSAPI_IO_KEY")
if not API_KEY:
    raise ValueError("ODDSAPI_IO_KEY environment variable not set. Create a .env file with your key.")
BASE_URL = "https://api.odds-api.io/v3"

# Active leagues to track (by slugs)
TRACKED_LEAGUES = [
    "sweden-allsvenskan",
    "norway-eliteserien",
    "usa-mls",
    "brazil-serie-a",
    "brazil-serie-b",
    "korea-k-league-1",
    "finland-veikkausliiga",
    "argentina-primera",
    "mexico-liga-mx",
    "china-super-league",
    "england-league-1",
    "england-league-2",
    "mls-next-pro",
    "denmark-superliga",
    "japan-j-league",
    "switzerland-super-league",
    "austria-bundesliga",
    "belgium-first-division",
    "czech-first-league",
    "poland-ekstraklasa",
    "portugal-primeira-liga",
    "netherlands-eredivisie",
    "turkey-super-league",
    "russia-premier-league",
    "croatia-hnl",
    "serbia-super-league",
    "romania-liga-1",
    "bulgaria-first-league",
    "hungary-nb-i",
    "slovakia-nike-league",
    "slovenia-prvaliga",
    "greece-super-league",
    "ukraine-premier-league",
    "cyprus-first-division",
    "kazakhstan-premier-league",
    "azerbaijan-premier-league",
    "georgia-erovnuli-liga",
    "estonia-meistriliiga",
    "latvia-virsliga",
    "lithuania-a-lyga",
    "belarus-premier-league",
    "moldova-divizia-nationala",
    "armenia-premier-league",
    "albania-superliga",
    "kosovo-superliga",
    "montenegro-prva-crnogorska",
    "north-macedonia-prva-liga",
    "bosnia-premier-league",
    "iceland-urkvalsdeild",
    "fifa-world-cup",
    "international-clubs",
    "concacaf",
    "copa-libertadores",
    "copa-sudamericana",
    "uefa-champions-league",
    "uefa-europa-league",
    "uefa-conference-league",
    "england-premier-league",
    "spain-la-liga",
    "italy-serie-a",
    "germany-bundesliga",
    "france-ligue-1",
    "england-championship",
    "spain-segunda-division",
    "italy-serie-b",
    "germany-2-bundesliga",
    "france-ligue-2",
    "scotland-premiership",
    "netherlands-eerste-divisie",
    "belgium-challenger-pro-league",
    "portugal-segunda-liga",
    "australia-a-league",
    "usa-usl-championship",
    "colombia-primera-a",
    "peru-liga-1",
    "chile-primera-division",
    "ecuador-serie-a",
    "paraguay-primera-division",
    "uruguay-primera-division",
    "bolivia-division-profesional",
    "venezuela-primera-division",
    "costa-rica-primera-division",
    "honduras-liga-nacional",
    "elsalvador-primera-division",
    "guatemala-liga-nacional",
    "panama-lpf",
    "trinidad-premier-league",
    "jamaica-premier-league",
    "south-africa-premier-division",
    "egypt-premier-league",
    "morocco-botola",
    "tunisia-ligue-1",
    "algeria-ligue-1",
    "nigeria-premier-league",
    "ghana-premier-league",
    "kenya-premier-league",
    "zambia-super-league",
    "zimbabwe-premier-league",
    "saudi-professional-league",
    "uae-arabian-gulf-league",
    "qatar-stars-league",
    "iran-persian-gulf-pro-league",
    "iraq-stars-league",
    "jordan-pro-league",
    "oman-professional-league",
    "bahrain-premier-league",
    "kuwait-premier-league",
    "lebanon-premier-league",
    "syria-premier-league",
    "yemen-yemeni-league",
    "palestine-west-bank-premier-league",
    "india-super-league",
    "pakistan-premier-league",
    "bangladesh-premier-league",
    "sri-lanka-super-league",
    "nepal-a-division-league",
    "maldives-dhivehi-premier-league",
    "bhutan-premier-league",
    "afghanistan-premier-league",
    "tajikistan-vysshaya-liga",
    "turkmenistan-yokary-liga",
    "uzbekistan-super-league",
    "kyrgyzstan-premier-league",
    "mongolia-premier-league",
    "indonesia-liga-1",
    "malaysia-super-league",
    "singapore-premier-league",
    "philippines-pfl",
    "vietnam-v-league",
    "thailand-league-1",
    "myanmar-national-league",
    "cambodia-cambodian-league",
    "laos-lao-league",
    "timor-leste-liga-futebol",
    "brunei-super-league",
    "hong-kong-premier-league",
    "macau-elite-league",
    "chinese-taipei-city-league",
    "south-korea-k-league-2",
    "japan-j2-league",
    "japan-j3-league",
    "australia-a-league-women",
    "new-zealand-national-league",
    "papua-new-guinea-premier-league",
    "fiji-premier-league",
    "solomon-islands-s-league",
    "vanuatu-premier-league",
    "samoa-national-league",
    "tahiti-ligue-1",
    "new-caledonia-super-ligue",
    "cook-islands-round-cup",
    "tuvalu-a-division",
    "kiribati-national-league",
    "northern-mariana-islands-league",
    "guam-league",
    "american-samoa-ffas-senior-league",
]

BOOKMAKERS = "Betfair Exchange,1xbet"

_league_cache = None
_league_cache_time = 0


def _get(session, path, params=None):
    """Make a GET request to the odds-api.io."""
    if params is None:
        params = {}
    params["apiKey"] = API_KEY
    r = session.get(f"{BASE_URL}{path}", params=params, timeout=15)
    if r.status_code == 200:
        return r.json()
    print(f"[ODDSAPI] ⚠️ {path}: HTTP {r.status_code} — {r.text[:100]}")
    return None


def list_leagues(session=None):
    """Get all football leagues."""
    global _league_cache, _league_cache_time
    now = time.time()
    if _league_cache and now - _league_cache_time < 3600:
        return _league_cache

    if not session:
        session = requests.Session()
    data = _get(session, "/leagues", {"sport": "football"})
    if data:
        _league_cache = data
        _league_cache_time = now
    return data


def get_upcoming_events(session, max_per_league=5):
    """Get upcoming football events with odds from Betfair Exchange and 1xBet."""
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    from_dt = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    to_dt = (now + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Get events for football
    events = _get(session, "/events", {
        "sport": "football",
        "from": from_dt,
        "to": to_dt,
        "limit": 200,
    })
    if not events:
        return []

    # Filter for pending/live events from tracked leagues
    league_slugs = set(TRACKED_LEAGUES)
    filtered = []
    for e in events:
        status = e.get("status", "")
        if status not in ("pending", "live"):
            continue
        league = e.get("league", {})
        league_slug = league.get("slug", "") if isinstance(league, dict) else ""
        if any(t in league_slug for t in TRACKED_LEAGUES):
            filtered.append(e)
        elif not league_slug:
            filtered.append(e)  # include if no league info

    return filtered[:100]


def fetch_odds_for_events(session, event_ids):
    """Fetch odds for multiple events (max 10 per call)."""
    results = {}
    for i in range(0, len(event_ids), 10):
        batch = event_ids[i:i + 10]
        ids_str = ",".join(str(eid) for eid in batch)
        data = _get(session, "/odds/multi", {
            "eventIds": ids_str,
            "bookmakers": BOOKMAKERS,
        })
        if data:
            for item in data if isinstance(data, list) else [data]:
                eid = item.get("id")
                if eid:
                    results[eid] = item
        time.sleep(0.25)  # rate limit
    return results


def extract_betfair_midpoint(odds_data):
    """Extract Betfair Exchange back/lay midpoint from odds response.

    Returns:
        dict with 'home', 'draw', 'away' midpoint prices,
        or None if Betfair data not available.
    """
    bms = odds_data.get("bookmakers", {})
    bf = bms.get("Betfair Exchange", [])
    if not bf:
        return None

    ml = None
    for m in bf:
        if m.get("name") == "ML":
            ml = m
            break

    if not ml or not ml.get("odds"):
        return None

    o = ml["odds"][0]
    home_back = float(o.get("home", 0))
    home_lay = float(o.get("layHome", 0))
    draw_back = float(o.get("draw", 0))
    draw_lay = float(o.get("layDraw", 0))
    away_back = float(o.get("away", 0))
    away_lay = float(o.get("layAway", 0))

    # Midpoint = (back + lay) / 2  (Caan Berry method)
    home_mid = (home_back + home_lay) / 2 if home_back and home_lay else home_back
    draw_mid = (draw_back + draw_lay) / 2 if draw_back and draw_lay else draw_back
    away_mid = (away_back + away_lay) / 2 if away_back and away_lay else away_back

    return {
        "home": home_mid,
        "draw": draw_mid,
        "away": away_mid,
        "home_back": home_back,
        "home_lay": home_lay,
        "draw_back": draw_back,
        "draw_lay": draw_lay,
        "away_back": away_back,
        "away_lay": away_lay,
        "source": "Betfair Exchange",
    }


def extract_1xbet_odds(odds_data):
    """Extract 1xbet odds from odds response."""
    bms = odds_data.get("bookmakers", {})
    xb = bms.get("1xbet", [])
    if not xb:
        return None

    ml = None
    for m in xb:
        if m.get("name") == "ML":
            ml = m
            break

    if not ml or not ml.get("odds"):
        return None

    o = ml["odds"][0]
    return {
        "home": float(o.get("home", 0)),
        "draw": float(o.get("draw", 0)),
        "away": float(o.get("away", 0)),
        "source": "1xbet",
    }


def extract_totals(odds_data, bookmaker="Betfair Exchange"):
    """Extract Over/Under odds from a bookmaker."""
    bms = odds_data.get("bookmakers", {})
    bm = bms.get(bookmaker, [])
    if not bm:
        return None

    for m in bm:
        if m.get("name") == "Totals":
            odds_list = m.get("odds", [])
            if odds_list:
                o = odds_list[0]
                return {
                    "point": float(o.get("hdp", 2.5)),
                    "over": float(o.get("over", 0)),
                    "under": float(o.get("under", 0)),
                    "lay_over": float(o.get("layOver", 0)),
                    "lay_under": float(o.get("layUnder", 0)),
                }
    return None


def scrape_all(session=None):
    """Main entry point: fetch all tracked events with odds."""
    if not session:
        session = requests.Session()
    session.headers.update({
        "User-Agent": "SportmaniaOdds/1.0",
    })

    print("[ODDSAPI] Fetching upcoming events...")
    events = get_upcoming_events(session)
    print(f"[ODDSAPI] {len(events)} upcoming events found")

    if not events:
        return []

    event_ids = [e["id"] for e in events]
    print(f"[ODDSAPI] Fetching odds for {len(event_ids)} events...")
    odds_map = fetch_odds_for_events(session, event_ids)
    print(f"[ODDSAPI] Got odds for {len(odds_map)} events")

    results = []
    for e in events:
        eid = e["id"]
        odds_data = odds_map.get(eid)
        if not odds_data:
            continue

        bf_mid = extract_betfair_midpoint(odds_data)
        xb_odds = extract_1xbet_odds(odds_data)
        totals = extract_totals(odds_data)

        if not bf_mid and not xb_odds:
            continue

        league = e.get("league", {})
        league_name = league.get("name", "") if isinstance(league, dict) else ""
        league_slug = league.get("slug", "") if isinstance(league, dict) else ""

        results.append({
            "match_id": f"oa_{eid}",
            "home_team": e.get("home", ""),
            "away_team": e.get("away", ""),
            "venue": "",
            "stage": league_name,
            "league_key": league_slug,
            "league_name": league_name,
            "date": (e.get("date", "")[:10] if e.get("date") else ""),
            "time": "",
            "commence_time": e.get("date", ""),
            "bookmakers": list(odds_data.get("bookmakers", {}).keys()),
            "highest_edge_status": "⚪",
            "home_odds": xb_odds["home"] if xb_odds else (bf_mid["home"] if bf_mid else 0),
            "draw_odds": xb_odds["draw"] if xb_odds else (bf_mid["draw"] if bf_mid else 0),
            "away_odds": xb_odds["away"] if xb_odds else (bf_mid["away"] if bf_mid else 0),
            "analysis": {
                "sport_raw": {
                    "home": xb_odds["home"] if xb_odds else 0,
                    "draw": xb_odds["draw"] if xb_odds else 0,
                    "away": xb_odds["away"] if xb_odds else 0,
                    "vig": 0,
                    "source": xb_odds["source"] if xb_odds else "Betfair Exchange",
                    "over_odds": totals["over"] if totals else 0,
                    "under_odds": totals["under"] if totals else 0,
                    "ou_point": totals["point"] if totals else 2.5,
                },
                "betfair_midpoint": bf_mid,
                "xbet_odds": xb_odds,
                "ah_analysis": {},
                "edge_summary": [],
                "narrative": {"form": "", "injuries": "", "tactical": ""},
            },
        })

    return results


def compute_vig(odds_list):
    """Compute bookmaker vig from a list of decimal odds."""
    imp = sum(1 / o for o in odds_list if o > 0)
    return imp if imp > 0 else 1


def compute_edges(matches):
    """Compute 1xBet vs Betfair Exchange edges for each match."""
    for m in matches:
        analysis = m.get("analysis", {})
        xb = analysis.get("xbet_odds", {})
        bf = analysis.get("betfair_midpoint", {})

        edges = []

        if xb and bf:
            for outcome, label, x_key, b_key in [
                ("home", m["home_team"], "home", "home"),
                ("draw", "Draw", "draw", "draw"),
                ("away", m["away_team"], "away", "away"),
            ]:
                x_o = xb.get(x_key, 0)
                b_o = bf.get(b_key, 0)
                if x_o > 0 and b_o > 0:
                    ev = (x_o - b_o) / b_o * 100
                    edges.append({
                        "market": f"{label} (1xBet vs Betfair)",
                        "edge": round(ev, 1),
                        "status": "🚀" if ev > 20 else ("✅" if ev > 5 else ("⚪" if ev > -5 else "❌")),
                        "quarter_kelly_stake": round(max(0, ev / 25) * 2.5, 2) if ev > 3 else 0,
                        "xbet_price": x_o,
                        "betfair_price": b_o,
                        "type": "xbet_vs_betfair",
                    })

        analysis["edge_summary"] = edges
        if edges:
            best = max(edges, key=lambda e: e["edge"])
            m["highest_edge_status"] = best["status"]

    return matches


if __name__ == "__main__":
    import json
    session = requests.Session()
    session.headers.update({"User-Agent": "SportmaniaOdds/1.0"})

    matches = scrape_all(session)
    matches = compute_edges(matches)
    print(f"\n✅ {len(matches)} matches with Betfair + 1xBet odds")
    for m in matches[:5]:
        xb = m["analysis"].get("xbet_odds", {})
        bf = m["analysis"].get("betfair_midpoint", {})
        edges = m["analysis"].get("edge_summary", [])
        print(f"  {m['home_team']} vs {m['away_team']}")
        if xb:
            print(f"    1xBet: {xb.get('home',0)}/{xb.get('draw',0)}/{xb.get('away',0)}")
        if bf:
            print(f"    Betfair: {bf.get('home',0):.3f}/{bf.get('draw',0):.3f}/{bf.get('away',0):.3f}")
        if edges:
            best = max(edges, key=lambda e: e["edge"])
            print(f"    Best edge: {best['market']} = {best['edge']:+.1f}%")

    # Save sample
    Path("/c/Users/irfan/betting-dashboard/pipeline/_oddsapi_sample.json").write_text(
        json.dumps(matches, indent=2), encoding="utf-8"
    )
    print(f"\n📁 Sample saved to _oddsapi_sample.json")
