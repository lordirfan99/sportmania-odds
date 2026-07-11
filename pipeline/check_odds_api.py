"""Fetch and display World Cup odds from the-odds-api.com"""
import json, subprocess, sys

API_KEY = "b45c8f0693e8a7912baf2449e98d6fb8"
URL = (
    "https://api.the-odds-api.com/v4/sports/soccer_fifa_world_cup/odds/"
    f"?apiKey={API_KEY}"
    "&regions=asia,eu"
    "&markets=h2h,spreads,totals"
    "&oddsFormat=decimal"
    "&dateFormat=iso"
)

data = json.loads(subprocess.check_output(["curl", "-s", URL]))
print(f"Matches: {len(data)}")

for m in data:
    print(f"\n{'='*70}")
    print(f"  {m['home_team']:25s} vs {m['away_team']:25s}")
    print(f"  KO: {m['commence_time']}")
    print(f"  Bookmakers: {len(m['bookmakers'])}")

    for b in m['bookmakers']:
        print(f"\n  ── {b['title']} ──")
        for mk in b['markets']:
            key = mk['key']
            outcomes = ' | '.join(
                f"{o['name']}: {o['price']}" for o in mk['outcomes']
            )
            print(f"    {key:10s}  {outcomes}")

print(f"\n\n✅ Total matches: {len(data)}")
