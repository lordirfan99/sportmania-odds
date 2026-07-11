"""odds_api_fetcher.py — Fetch real odds from the-odds-api.com

Replaces estimated 12SPORT odds with LIVE Pinnacle / Matchbook odds.
Focuses on Asian Handicap (spreads) and Over/Under (totals) only.

Usage:
  python pipeline/odds_api_fetcher.py              # fetch + update data.json
  python pipeline/odds_api_fetcher.py --dry-run     # print only, no write
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_FILE = BASE_DIR / "public" / "data.json"

API_KEY = "b45c8f0693e8a7912baf2449e98d6fb8"
# Pinnacle = sharpest bookmaker for AH + O/U
PREFERRED_BOOKMAKER = "Pinnacle"
FALLBACK_BOOKMAKERS = ["Matchbook", "BetOnline.ag", "Pinnacle"]


def fmt_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_odds():
    """Fetch World Cup odds from the-odds-api.com.
    
    Returns list of match dicts with bookmaker odds.
    """
    url = (
        f"https://api.the-odds-api.com/v4/sports/soccer_fifa_world_cup/odds/"
        f"?apiKey={API_KEY}"
        f"&regions=eu"
        f"&markets=h2h,spreads,totals"
        f"&oddsFormat=decimal"
    )
    
    for attempt in range(3):
        result = subprocess.run(
            ["curl", "-s", "-w", "\n%{http_code}", url],
            capture_output=True, text=True, timeout=30
        )
        
        if result.returncode == 0:
            break
        print(f"[!] curl attempt {attempt+1} failed, retrying...")
        import time
        time.sleep(2)
    else:
        print(f"[!] curl failed after 3 attempts")
        return None
    
    # Parse response (last line is HTTP code)
    lines = result.stdout.strip().split("\n")
    http_code = lines[-1] if lines else "000"
    body = "\n".join(lines[:-1]) if len(lines) > 1 else ""
    
    if http_code != "200":
        print(f"[!] API returned HTTP {http_code}: {body[:200]}")
        return None
    
    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        print(f"[!] JSON parse error: {e}")
        print(f"    Response: {body[:500]}")
        return None
    
    if isinstance(data, dict) and "message" in data:
        print(f"[!] API error: {data['message']}")
        return None
    
    return data


def find_best_odds(match, bookmaker_names=None):
    """Find the best bookmaker for spreads + totals.
    
    Returns dict with {bookmaker, h2h, spreads, totals} or None.
    """
    if bookmaker_names is None:
        bookmaker_names = FALLBACK_BOOKMAKERS
    
    for bm_name in bookmaker_names:
        for bm in match.get("bookmakers", []):
            if bm["title"] == bm_name:
                result = {"bookmaker": bm_name}
                
                for mk in bm.get("markets", []):
                    key = mk["key"]
                    outcomes = {}
                    for o in mk["outcomes"]:
                        name = o["name"]
                        price = o["price"]
                        point = o.get("point")
                        outcomes[name] = {"price": price, "point": point}
                    result[key] = outcomes
                
                if "spreads" in result or "totals" in result:
                    return result
    
    return None


def match_id_for(api_match):
    """Return a stable match ID for the JSON."""
    home = api_match.get("home_team", "").lower().replace(" ", "_")[:5]
    away = api_match.get("away_team", "").lower().replace(" ", "_")[:5]
    return f"{home}_{away}_api"


def api_to_db_match(api_match, existing_data):
    """Convert API match into data.json match format.
    
    Merges with existing match data (bet history, narrative, polymarket).
    """
    home = api_match["home_team"]
    away = api_match["away_team"]
    mid = match_id_for(api_match)
    
    # Find existing match data (for polymarket_devig, narrative, etc.)
    existing = None
    for m in existing_data.get("matches", []):
        # Match by ID
        if m["id"] == mid:
            existing = m
            break
        # Match by team names (order insensitive)
        m_home = m.get("home_team", "").lower().strip()
        m_away = m.get("away_team", "").lower().strip()
        a_home = api_match.get("home_team", "").lower().strip()
        a_away = api_match.get("away_team", "").lower().strip()
        if {m_home, m_away} == {a_home, a_away}:
            existing = m
            break
    
    # Create stable match ID using canonical order (alphabetical)
    teams_sorted = sorted([home, away])
    mid = f"{teams_sorted[0][:5]}_{teams_sorted[1][:5]}_api"
    
    # Get bet history for this match
    bet_history = [
        b for b in existing_data.get("bet_history", [])
        if b.get("match_id") == mid or (b.get("home_team") == home and b.get("away_team") == away)
    ]
    
    # Get odds from best bookmaker
    odds = find_best_odds(api_match)
    
    # Default match structure
    match = {
        "id": mid,
        "home_team": home,
        "away_team": away,
        "venue": api_match.get("venue", "Stadium"),
        "stage": "Quarterfinal",
        "date": api_match["commence_time"][:10],
        "time": api_match["commence_time"][11:16] + " UTC",
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
    
    # Merge existing polymarket data if available, oriented to current API teams
    if existing:
        existing_analysis = existing.get("analysis", {})
        existing_home = existing.get("home_team", "")
        existing_away = existing.get("away_team", "")
        
        # Oriented polymarket_devig
        old_poly = existing_analysis.get("polymarket_devig", {})
        if old_poly and any(old_poly.values()):
            # Map home/away from existing teams to API teams
            # Step 1: find which old team maps to which probability
            team_probs = {}
            if existing_home == home or existing_home == away:
                team_probs[existing_home] = old_poly.get("home", 0)
            if existing_away == home or existing_away == away:
                team_probs[existing_away] = old_poly.get("away", 0)
            
            poly_home = team_probs.get(home, 0)
            poly_away = team_probs.get(away, 0)
            match["analysis"]["polymarket_devig"] = {
                "home": poly_home,
                "draw": old_poly.get("draw", 0),
                "away": poly_away,
            }
        
        # Oriented triangulation_1x2
        old_1x2 = existing_analysis.get("triangulation_1x2", {})
        if old_1x2 and any(v for k, v in old_1x2.items()):
            new_1x2 = {}
            for model, vals in old_1x2.items():
                if isinstance(vals, (list, tuple)) and len(vals) >= 3:
                    h_val, d_val, a_val = vals[0], vals[1], vals[2]
                    # Re-orient by team
                    if existing_home == home and existing_away == away:
                        new_1x2[model] = [h_val, d_val, a_val]
                    elif existing_home == away and existing_away == home:
                        new_1x2[model] = [a_val, d_val, h_val]
                    else:
                        new_1x2[model] = vals
                else:
                    new_1x2[model] = vals
            match["analysis"]["triangulation_1x2"] = new_1x2
        
        # Copy other data (team-order independent)
        for key in ["triangulation_ou", "narrative", "triangulation_ah"]:
            if existing_analysis.get(key):
                match["analysis"][key] = existing_analysis[key]
    
    # Set real odds from API
    if odds:
        spreads = odds.get("spreads", {})
        totals = odds.get("totals", {})
        
        # Determine which side is home vs away in spreads
        # The API returns {home_name: {price, point}, away_name: {price, point}}
        spread_home = spreads.get(home)
        spread_away = spreads.get(away)
        
        if spread_home and spread_away:
            match["home_odds"] = spread_home["price"]
            match["away_odds"] = spread_away["price"]
            match["draw_odds"] = 0  # AH has no draw
            
            match["analysis"]["sport_raw"] = {
                "home": spread_home["price"],
                "away": spread_away["price"],
                "point_home": spread_home.get("point"),
                "point_away": spread_away.get("point"),
                "source": odds["bookmaker"],
                "vig": round(
                    (1/spread_home["price"] + 1/spread_away["price"] - 1) * 100, 2
                ),
            }
        
        # Set O/U odds
        if totals:
            over = totals.get("Over")
            under = totals.get("Under")
            if over and under:
                match["analysis"]["sport_raw"].update({
                    "over_odds": over["price"],
                    "under_odds": under["price"],
                    "ou_point": over.get("point"),
                })
                
                # Update triangulation_ou with real odds-implied probabilities
                ou_vig = (1/over["price"] + 1/under["price"] - 1)
                over_implied = (1/over["price"]) / (1 + ou_vig) * 100
                under_implied = (1/under["price"]) / (1 + ou_vig) * 100
                
                match["analysis"]["sport_raw"]["ou_vig"] = round(ou_vig * 100, 2)
                match["analysis"]["sport_raw"]["over_implied"] = round(over_implied, 1)
                match["analysis"]["sport_raw"]["under_implied"] = round(under_implied, 1)
    
    return match


def compute_edges(match, polymarket_devig):
    """Compute edges from real odds vs Polymarket. Returns edge_summary list."""
    edges = []
    home = match.get("home_team", "Home")
    away = match.get("away_team", "Away")
    analysis = match.get("analysis", {})
    
    home_p = polymarket_devig.get("home", 0)
    draw_p = polymarket_devig.get("draw", 0)
    away_p = polymarket_devig.get("away", 0)
    
    sport = analysis.get("sport_raw", {})
    
    # ── AH Edge ──
    home_ah_odds = match.get("home_odds", 0)
    away_ah_odds = match.get("away_odds", 0)
    
    if home_ah_odds > 0 and home_p > 0:
        # Get handicap point (handling float precision)
        point_raw = sport.get("point_home", -0.5)
        point = round(float(point_raw), 2) if point_raw else -0.5
        point_str = f"{point:+.2f}" if point else "-0.5"
        market_name = f"{home} {point_str} (AH)"
        
        # For -0.5, edge = (fair_home_prob * book_odds) - 1
        # For other lines, estimate from -0.5 with adjustment
        if abs(point - (-0.5)) < 0.01 or point is None:
            edge_prob = home_p
        elif abs(point - (-0.75)) < 0.01:
            # -0.75: 50% -0.5 + 50% -1
            win_by_2_ratio = min(0.7, max(0.4, home_p / (home_p + draw_p + 0.001)))
            p_win_by_2 = home_p * win_by_2_ratio
            edge_prob = home_p * 0.5 + p_win_by_2 * 0.5
        elif abs(point - (-1.0)) < 0.01:
            win_by_2_ratio = min(0.7, max(0.4, home_p / (home_p + draw_p + 0.001)))
            edge_prob = home_p * win_by_2_ratio
        elif abs(point) < 0.01:  # 0 / DNB
            total_no_draw = home_p + away_p
            edge_prob = home_p / total_no_draw if total_no_draw > 0 else home_p
        else:
            edge_prob = home_p  # fallback
        
        home_ah_edge = round((edge_prob * home_ah_odds - 1) * 100, 1)
        edges.append({
            "market": market_name,
            "edge": home_ah_edge,
            "status": "🚀" if home_ah_edge > 20 else "✅" if home_ah_edge >= 5 else "⚪" if home_ah_edge >= -5 else "❌",
            "quarter_kelly_stake": round(max(0, (home_ah_edge / 100) / (home_ah_odds - 1) * 0.25 * 100), 2) if home_ah_edge >= 3.2 else 0,
        })
    
    if away_ah_odds > 0 and away_p > 0:
        # Get away handicap point
        point_away_raw = sport.get("point_away", 0.5)
        point_away = round(float(point_away_raw), 2) if point_away_raw else 0.5
        
        if abs(point_away - 0.5) < 0.01 or point_away is None:
            # +0.5: covers draw + away win
            away_total_p = away_p + draw_p
        elif abs(point_away - 0.75) < 0.01:
            # +0.75: 50% +0.5 + 50% +1
            # P(+1) = 1 - P(home wins by 2+)
            win_by_2_ratio = min(0.7, max(0.4, home_p / (home_p + draw_p + 0.001)))
            p_home_win_by_2 = home_p * win_by_2_ratio
            p_away_plus_1 = 1 - p_home_win_by_2
            away_total_p = (away_p + draw_p) * 0.5 + p_away_plus_1 * 0.5
        elif abs(point_away - 1.0) < 0.01:
            # +1: win, draw, or lose by exactly 1
            # P(+1) ≈ 1 - P(home wins by 2+)
            win_by_2_ratio = min(0.7, max(0.4, home_p / (home_p + draw_p + 0.001)))
            p_home_win_by_2 = home_p * win_by_2_ratio
            away_total_p = 1 - p_home_win_by_2
        else:
            away_total_p = away_p + draw_p  # fallback
        
        away_ah_edge = round((away_total_p * away_ah_odds - 1) * 100, 1)
        point_str_away = f"{point_away:+.2f}"
        edges.append({
            "market": f"{away} {point_str_away} (AH)",
            "edge": away_ah_edge,
            "status": "🚀" if away_ah_edge > 20 else "✅" if away_ah_edge >= 5 else "⚪" if away_ah_edge >= -5 else "❌",
            "quarter_kelly_stake": round(max(0, (away_ah_edge / 100) / (away_ah_odds - 1) * 0.25 * 100), 2) if away_ah_edge >= 3.2 else 0,
        })
    
    # ── O/U Edge ──
    over_odds = sport.get("over_odds", 0)
    under_odds = sport.get("under_odds", 0)
    ou_point = sport.get("ou_point", 2.5)
    
    ou_ensemble = match.get("analysis", {}).get("triangulation_ou", {}).get("ensemble", [50, 50])
    over_fair = ou_ensemble[0] if len(ou_ensemble) > 0 else 50
    under_fair = ou_ensemble[1] if len(ou_ensemble) > 1 else 50
    
    if over_odds > 0 and over_fair < 100:
        over_edge = round((over_fair / 100 * over_odds - 1) * 100, 1)
        edges.append({
            "market": f"O {ou_point}",
            "edge": over_edge,
            "status": "🚀" if over_edge > 20 else "✅" if over_edge >= 5 else "⚪" if over_edge >= -5 else "❌",
            "quarter_kelly_stake": round(max(0, (over_edge / 100) / (over_odds - 1) * 0.25 * 100), 2) if over_edge >= 3.2 else 0,
        })
    
    if under_odds > 0 and under_fair < 100:
        under_edge = round((under_fair / 100 * under_odds - 1) * 100, 1)
        edges.append({
            "market": f"U {ou_point}",
            "edge": under_edge,
            "status": "🚀" if under_edge > 20 else "✅" if under_edge >= 5 else "⚪" if under_edge >= -5 else "❌",
            "quarter_kelly_stake": round(max(0, (under_edge / 100) / (under_odds - 1) * 0.25 * 100), 2) if under_edge >= 3.2 else 0,
        })
    
    return edges


def merge_into_data(existing, api_data):
    """Merge API odds into existing data.json structure."""
    now_iso = fmt_now()
    
    # Build new matches list
    new_matches = []
    for api_match in api_data:
        match = api_to_db_match(api_match, existing)
        
        # Compute edges from real odds
        polymarket = match["analysis"].get("polymarket_devig", {})
        if any(polymarket.values()):
            edges = compute_edges(match, polymarket)
            if edges:
                match["analysis"]["edge_summary"] = edges
        
        # Compute highest edge status
        edge_summary = match["analysis"].get("edge_summary", [])
        if edge_summary:
            best = max(edge_summary, key=lambda e: e["edge"])
            match["highest_edge_status"] = best.get("status", "⚪")
        else:
            match["highest_edge_status"] = "⚪"
        
        new_matches.append(match)
    
    # Update system
    existing["system_status"]["last_updated"] = now_iso
    existing["matches"] = new_matches
    
    return existing


def main():
    dry_run = "--dry-run" in sys.argv
    
    print(f"{'='*60}")
    print(f"ODDS API FETCHER — {fmt_now()}")
    print(f"{'='*60}")
    
    # Read existing data
    if not DATA_FILE.exists():
        print(f"[!] No existing data.json at {DATA_FILE}")
        return
    
    with open(DATA_FILE, "r") as f:
        existing = json.load(f)
    
    print(f"[1] Read {len(existing.get('matches', []))} existing matches")
    
    # Fetch API odds
    print(f"\n[2] Fetching from the-odds-api...")
    api_data = fetch_odds()
    
    if not api_data:
        print(f"[!] API failed — keeping existing data")
        return
    
    print(f"[2] Got {len(api_data)} matches from API")
    
    for m in api_data:
        bm = find_best_odds(m)
        if bm:
            sp = bm.get("spreads", {})
            to = bm.get("totals", {})
            print(f"  {m['home_team']:25s} vs {m['away_team']:25s}")
            print(f"    Bookie: {bm['bookmaker']}")
            if sp:
                for name, v in sp.items():
                    print(f"    Spread   {name}: {v['price']} (@ {v.get('point', '?')})")
            if to:
                for name, v in to.items():
                    print(f"    Total    {name}: {v['price']} (@ {v.get('point', '?')})")
    
    # Merge
    print(f"\n[3] Merging API odds into data.json...")
    merged = merge_into_data(existing, api_data)
    
    if dry_run:
        print(f"\n[DRY-RUN] Would write {len(merged['matches'])} matches")
        return
    
    # Write
    with open(DATA_FILE, "w") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
    
    print(f"[3] ✅ Written {len(merged['matches'])} matches to {DATA_FILE}")
    
    # Summary
    print(f"\n{'='*60}")
    print(f"EDGE SUMMARY:")
    for m in merged["matches"]:
        edges = m.get("analysis", {}).get("edge_summary", [])
        for e in edges:
            print(f"  {m['home_team']:15s} vs {m['away_team']:15s} | {e['market']:25s} | edge {e['edge']:+.1f}% → {e['status']}")


if __name__ == "__main__":
    main()
