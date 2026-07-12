"""Convert pre-scraped the-odds-api data into data.json format.
Run this once since the API quota is exhausted."""
import json, sys, os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PUBLIC_DIR = BASE_DIR / "public"
DATA_FILE = PUBLIC_DIR / "data.json"

sys.path.insert(0, str(BASE_DIR / "pipeline"))
from auto_scraper import _parse_api_match, compute_edges, merge_with_existing, ALL_LEAGUES, fmt_now

# Load pre-scraped raw data
raw_path = BASE_DIR / "pipeline" / "_all_matches.json"
if not raw_path.exists():
    print("❌ No _all_matches.json found")
    sys.exit(1)

raw_matches = json.loads(raw_path.read_text(encoding="utf-8"))
print(f"Loaded {len(raw_matches)} raw matches")

# Build league key map
league_map = {k: n for k, n in ALL_LEAGUES}

# Parse each match
parsed = []
for m in raw_matches:
    league_key = m.get("_league", "")
    league_name = m.get("_league_name", league_map.get(league_key, league_key))
    entry = _parse_api_match(m, league_key, league_name)
    if entry:
        parsed.append(entry)

print(f"Parsed {len(parsed)} matches")

# Compute edges
compute_edges(parsed)

# Merge with existing (preserves narratives)
result = merge_with_existing(parsed)

# Sort by commence_time (most recent first)
result["matches"].sort(key=lambda m: m.get("commence_time", m.get("date", "")), reverse=True)

# Write
DATA_FILE.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\n✅ Written {len(result['matches'])} matches to {DATA_FILE}")

# Show summary
leagues = {}
for m in result["matches"]:
    ln = m.get("league_name", "?")
    leagues[ln] = leagues.get(ln, 0) + 1
print("\nSummary by league:")
for l, c in sorted(leagues.items(), key=lambda x: -x[1]):
    print(f"  {l:35s} | {c} matches")
