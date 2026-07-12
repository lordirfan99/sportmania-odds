"""scraper_betfair.py — Betfair Exchange Scraper (free, no API key needed)

Scrapes Betfair exchange data via the public API without requiring
a developer app key. Uses Betfair's public/unauthorised endpoints.

Betfair Exchange is the world's largest betting exchange and is widely
considered the "true price" reference for +EV comparison.

Endpoints used:
  - /rest/v1/events/  — list soccer events
  - /rest/v1/market/  — get market prices (back/lay)

Rate limit: be gentle, max 1 req/sec.
"""

import json
import time
import requests
from datetime import datetime, timezone

BETFAIR_BASE = "https://www.betfair.com/www/sports/exchange/readonly/v1"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

# Known event type ID for soccer = 1
SOCCER_EVENT_TYPE = 1

# Cache for betfair data to avoid hammering the API
_cache = {}
_cache_time = 0
_CACHE_TTL = 120  # 2 minutes


def _get_session():
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def fetch_betfair_odds(match_name: str, home_team: str, away_team: str) -> dict | None:
    """Fetch Betfair exchange odds for a specific match.
    
    Returns dict with back/lay prices or None if not found.
    """
    now = time.time()
    if now - _cache_time < _CACHE_TTL and _cache:
        # Try cache first
        for cached in _cache.get("matches", []):
            if _match_name_match(cached, home_team, away_team):
                return cached
    
    try:
        session = _get_session()
        
        # Step 1: Get soccer events
        events_url = f"{BETFAIR_BASE}/events"
        params = {
            "eventTypeId": SOCCER_EVENT_TYPE,
            "locale": "en",
        }
        
        # Try to find the match
        market_data = _search_market(session, home_team, away_team)
        if market_data:
            back_prices = market_data.get("back_prices", [])
            lay_prices = market_data.get("lay_prices", [])
            
            if back_prices and lay_prices:
                # Best back (what you can bet to win)
                best_back = back_prices[0] if back_prices else 0
                # Best lay (what you can lay)
                best_lay = lay_prices[0] if lay_prices else 0
                # Midpoint = true price (Caan Berry method)
                midpoint = (best_back + best_lay) / 2 if best_back and best_lay else 0
                
                return {
                    "source": "Betfair",
                    "back_price": best_back,
                    "lay_price": best_lay,
                    "midpoint": midpoint,
                    "home_back": market_data.get("home_back"),
                    "home_lay": market_data.get("home_lay"),
                    "away_back": market_data.get("away_back"),
                    "away_lay": market_data.get("away_lay"),
                    "over_back": market_data.get("over_back"),
                    "under_back": market_data.get("under_back"),
                    "market_id": market_data.get("market_id"),
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                }
    except Exception as e:
        print(f"[BETFAIR] Error: {e}")
    
    return None


def _search_market(session, home_team, away_team):
    """Search for a match market on Betfair."""
    try:
        # Betfair's market catalogue endpoint
        url = f"{BETFAIR_BASE}/marketcat/markets"
        
        # Search by team names
        search_query = f"{home_team} v {away_team}"
        params = {
            "textQuery": search_query,
            "eventTypeId": SOCCER_EVENT_TYPE,
            "maxResults": 5,
            "locale": "en",
        }
        
        r = session.get(url, params=params, timeout=10)
        if r.status_code != 200:
            # Try alternative endpoint
            url = f"{BETFAIR_BASE}/marketcat/markets"
            params["textQuery"] = f"{home_team}"
            r = session.get(url, params=params, timeout=10)
            if r.status_code != 200:
                return None
        
        data = r.json()
        markets = data.get("markets", data.get("eventTypes", []))
        if not markets:
            return None
        
        # Find the correct match market (Over/Under 2.5 or Match Odds)
        for market in markets:
            market_name = market.get("marketName", "")
            desc = market.get("description", "")
            if "Over/Under" in market_name or "Over/Under" in desc or "Match Odds" in market_name:
                market_id = market.get("marketId")
                if market_id:
                    return _get_market_prices(session, market_id)
        
        # If no market found, try the first one
        first_id = markets[0].get("marketId")
        if first_id:
            return _get_market_prices(session, first_id)
            
    except Exception as e:
        print(f"[BETFAIR] Search error: {e}")
    
    return None


def _get_market_prices(session, market_id):
    """Get price data for a specific market."""
    try:
        url = f"{BETFAIR_BASE}/market/{market_id}/prices"
        params = {"locale": "en"}
        
        r = session.get(url, params=params, timeout=10)
        if r.status_code != 200:
            return None
        
        data = r.json()
        
        result = {"market_id": market_id}
        
        runners = data.get("runners", data.get("marketBooks", []))
        if not runners:
            # Try different response format
            runners = data.get("runnerBooks", data.get("selections", []))
        
        for runner in runners:
            name = runner.get("name", runner.get("selectionName", ""))
            prices = runner.get("prices", runner.get("exchangePrices", {}))
            
            back_prices = []
            lay_prices = []
            
            if isinstance(prices, dict):
                back_prices = prices.get("back", [])
                lay_prices = prices.get("lay", [])
            elif isinstance(prices, list):
                for p in prices:
                    if p.get("side") == "BACK":
                        back_prices.append(p)
                    elif p.get("side") == "LAY":
                        lay_prices.append(p)
            
            best_back = back_prices[0].get("price", 0) if back_prices else 0
            best_lay = lay_prices[0].get("price", 0) if lay_prices else 0
            
            if "home" in name.lower() or name.lower().startswith(home_team.lower()[:5]):
                result["home_back"] = best_back
                result["home_lay"] = best_lay
            elif "away" in name.lower() or name.lower().startswith(away_team.lower()[:5]):
                result["away_back"] = best_back
                result["away_lay"] = best_lay
            elif "over" in name.lower():
                result["over_back"] = best_back
                result["under_back"] = best_lay  # Under is the lay of over
        
        result["back_prices"] = [result.get("home_back", 0), result.get("away_back", 0)]
        result["lay_prices"] = [result.get("home_lay", 0), result.get("away_lay", 0)]
        
        return result
        
    except Exception as e:
        print(f"[BETFAIR] Price error: {e}")
    
    return None


def _match_name_match(cached, home, away):
    """Check if cached match matches our teams."""
    c_home = cached.get("home_team", "").lower()
    c_away = cached.get("away_team", "").lower()
    return home.lower()[:5] in c_home and away.lower()[:5] in c_away


def fetch_all_betfair_odds(matches: list) -> dict:
    """Fetch Betfair odds for a list of matches.
    
    Returns dict of match_id -> betfair_odds
    """
    results = {}
    count = 0
    
    for m in matches:
        mid = m.get("match_id") or m.get("id", "")
        home = m.get("home_team", "")
        away = m.get("away_team", "")
        
        if not mid or not home or not away:
            continue
        
        odds = fetch_betfair_odds(mid, home, away)
        if odds:
            results[mid] = odds
            count += 1
        
        # Be gentle with Betfair
        time.sleep(0.5)
        
        if count >= 30:  # Max 30 matches per run
            break
    
    return results


if __name__ == "__main__":
    # Test
    test = fetch_betfair_odds("test", "Spain", "Belgium")
    if test:
        print(f"✅ Betfair: {json.dumps(test, indent=2)}")
    else:
        print("⚠️ Betfair test returned None (may need different endpoint)")
