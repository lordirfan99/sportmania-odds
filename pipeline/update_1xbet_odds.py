"""Update data.json with 1xBet odds (extracted from browser)."""
import json, sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_FILE = BASE_DIR / "public" / "data.json"

# 1xBet odds extracted from live page
X1BET_ODDS = {
    "Spain": {
        "home_odds": 1.639, "draw_odds": 4.175, "away_odds": 6.03,
        "handicap_home": {"point": "-1.5", "price": 2.682},
        "handicap_away": {"point": "+1.5", "price": 1.507},
        "over_25": 1.768, "under_25": 2.124,
        "ah_home": {"point": "-1.25", "price": 2.366},
        "ah_away": {"point": "+1.25", "price": 1.629},
        "asian_total_275_o": 1.951, "asian_total_275_u": 1.909,
    },
    "Norway": {
        "home_odds": 4.29, "draw_odds": 3.805, "away_odds": 1.924,
        "handicap_home": {"point": "0", "price": 3.075},
        "handicap_away": {"point": "0", "price": 1.406},
        "over_25": 1.764, "under_25": 2.131,
        "ah_home": {"point": "+0.25", "price": 2.26},
        "ah_away": {"point": "-0.25", "price": 1.571},
        "asian_total_275_o": 1.946, "asian_total_275_u": 1.914,
    },
    "Argentina": {
        "home_odds": 1.737, "draw_odds": 3.7, "away_odds": 5.89,
        "handicap_home": {"point": "-1.5", "price": 3.285},
        "handicap_away": {"point": "+1.5", "price": 1.366},
        "over_25": 2.244, "under_25": 1.693,
        "asian_total_225_o": 1.967, "asian_total_225_u": 1.894,
    },
}

def find_team_key(match):
    """Find which team name in the match data corresponds to our keys."""
    home = match.get("home_team", "")
    away = match.get("away_team", "")
    for key in X1BET_ODDS:
        if key.lower() in home.lower() or home.lower() in key.lower():
            return key
    for key in X1BET_ODDS:
        if key.lower() in away.lower() or away.lower() in key.lower():
            return key
    return None

def update():
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    
    updated = 0
    for match in data.get("matches", []):
        team_key = find_team_key(match)
        if not team_key:
            continue
        
        o = X1BET_ODDS[team_key]
        
        # Determine if this team is home or in the match
        home = match["home_team"]
        is_home = team_key.lower() in home.lower() or home.lower() in team_key.lower()
        
        # Set 1X2 odds
        match["home_odds"] = o["home_odds"]
        match["draw_odds"] = o["draw_odds"]
        match["away_odds"] = o["away_odds"]
        
        # Update sport_raw
        sr = match["analysis"].get("sport_raw", {})
        sr["source"] = "1xBet"
        sr["home"] = o["home_odds"]
        sr["draw"] = o["draw_odds"]
        sr["away"] = o["away_odds"]
        
        # Compute vig
        vig = (1/o["home_odds"] + 1/o["draw_odds"] + 1/o["away_odds"] - 1) * 100
        sr["vig"] = round(vig, 2)
        
        # AH odds from handicap
        if o.get("handicap_home"):
            sr["point_home"] = o["handicap_home"]["point"]
            sr["home_ah"] = o["handicap_home"]["price"]
        if o.get("handicap_away"):
            sr["point_away"] = o["handicap_away"]["point"]
            sr["away_ah"] = o["handicap_away"]["price"]
        
        # O/U odds
        if o.get("over_25"):
            sr["over_odds"] = o["over_25"]
            sr["under_odds"] = o["under_25"]
            sr["ou_point"] = 2.5
        
        updated += 1
        print(f"  ✅ {match['home_team']:12} v {match['away_team']:12} | "
              f"1X2: {o['home_odds']}/{o['draw_odds']}/{o['away_odds']} | "
              f"O/U 2.5: {o['over_25']}/{o['under_25']}")
    
    if updated:
        DATA_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"\n✅ Updated {updated} matches with 1xBet odds")
    else:
        print("❌ No matches matched!")
        for m in data.get("matches", []):
            print(f"  Available: {m['home_team']} v {m['away_team']}")
    
    return updated

if __name__ == "__main__":
    update()
