#!/usr/bin/env python3
"""
pipeline/transform_ah.py — Transform data.json to AH + O/U focus.

Changes:
  1. Compute Asian Handicap probabilities from polymarket_devig
  2. Add triangulation_ah section to each match
  3. Trim edge_summary to ONLY AH + O/U markets
  4. Replace home_odds → AH -0.5 odds, away_odds → AH +0.5 odds
  5. Remove BTTS from everything
  6. Write updated data.json

Usage:
  python pipeline/transform_ah.py                    # transform data.json in place
  python pipeline/transform_ah.py --input path       # read from specific file
"""
import json
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_FILE = BASE_DIR / "public" / "data.json"

# ─── Constants ───
AH_VIG = 0.04       # 4% vig on Asian Handicap (lower than 1X2)
OU_VIG = 0.045      # 4.5% vig on O/U


def compute_ah(home_p, draw_p, away_p):
    """Compute Asian Handicap probabilities from 1X2 fair probabilities.
    
    Returns dict with:
      - home_minus_05: P(home covers -0.5) = P(home win)
      - away_plus_05: P(away covers +0.5) = 1 - P(home win)
      - home_0: P(home covers 0 / DNB) = P(home) / (P(home) + P(away))
      - away_0: P(away covers 0 / DNB) = P(away) / (P(home) + P(away))
    """
    home_minus_05 = home_p
    away_plus_05 = 1 - home_p  # includes draw
    
    total_no_draw = home_p + away_p
    if total_no_draw > 0:
        home_0 = home_p / total_no_draw
        away_0 = away_p / total_no_draw
    else:
        home_0 = 0.5
        away_0 = 0.5
    
    return {
        "home_minus_05_prob": round(home_minus_05 * 100, 1),  # %
        "away_plus_05_prob": round(away_plus_05 * 100, 1),    # %
        "home_0_prob": round(home_0 * 100, 1),                # %
        "away_0_prob": round(away_0 * 100, 1),                # %
    }


def prob_to_odds(prob_pct, vig=AH_VIG):
    """Convert fair probability (%) to bookmaker odds with vig."""
    p = prob_pct / 100.0
    implied_p = p * (1 + vig)
    if implied_p >= 1:
        return 1.01  # minimum odds
    return round(1.0 / implied_p, 2)


def compute_edge(fair_prob_pct, book_odds):
    """Compute edge % from fair probability and bookmaker odds.
    
    Edge = (fair_prob × book_odds) - 1, expressed as %
    """
    p = fair_prob_pct / 100.0
    edge = (p * book_odds - 1) * 100
    return round(edge, 1)


def edge_status(edge):
    """Classify edge into status label."""
    if edge > 20:
        return "🚀"
    elif edge >= 5:
        return "✅"
    elif edge >= -5:
        return "⚪"
    else:
        return "❌"


def kelly_pct(edge, book_odds):
    """Compute quarter-Kelly stake as % of bankroll using bookmaker odds.
    
    Kelly % = (edge / (odds-1)) * 0.25  [quarter Kelly]
    0 if edge < 3.2% or edge < 0
    """
    if edge < 3.2 or book_odds <= 1:
        return 0.0
    kelly_full = (edge / 100.0) / (book_odds - 1)  # full Kelly
    quarter = max(0, kelly_full * 0.25 * 100)
    return round(quarter, 2)


def transform_match(match):
    """Transform a single match entry to AH + O/U focus.
    
    Returns updated match or None if match should be removed.
    """
    analysis = match.get("analysis", {})
    
    # Get devigged probabilities
    devig = analysis.get("polymarket_devig", {})
    home_p = devig.get("home", 0)
    draw_p = devig.get("draw", 0)
    away_p = devig.get("away", 0)
    
    if home_p == 0 and away_p == 0:
        # No probabilities — keep as-is but trim edge_summary
        # Remove BTTS entries
        old_edges = analysis.get("edge_summary", [])
        new_edges = [e for e in old_edges if "AH" in e["market"] or e["market"].startswith("O ") or e["market"].startswith("U ")]
        if not new_edges:
            # Add placeholder AH + O/U
            team = match.get("home_team", "Home")
            new_edges = [
                {"market": f"{team} -0.5 (AH)", "edge": 0, "status": "⚪", "quarter_kelly_stake": 0},
                {"market": f"Away +0.5 (AH)", "edge": 0, "status": "⚪", "quarter_kelly_stake": 0},
                {"market": "O 2.5", "edge": 0, "status": "⚪", "quarter_kelly_stake": 0},
                {"market": "U 2.5", "edge": 0, "status": "⚪", "quarter_kelly_stake": 0},
            ]
        match["analysis"]["edge_summary"] = new_edges
        # Remove BTTS from analysis
        match["analysis"].pop("triangulation_btts", None)
        return match
    
    # Compute AH probabilities
    ah = compute_ah(home_p, draw_p, away_p)
    
    # Estimate 12SPORT AH odds (from fair prob + vig)
    ah_home_odds = prob_to_odds(ah["home_minus_05_prob"], AH_VIG)
    ah_away_odds = prob_to_odds(100 - ah["home_minus_05_prob"], AH_VIG)
    
    # Compute edges
    home_ah_edge = compute_edge(ah["home_minus_05_prob"], ah_home_odds)
    away_ah_edge = compute_edge(100 - ah["home_minus_05_prob"], ah_away_odds)
    
    # O/U edges — from existing triangulation_ou
    ou = analysis.get("triangulation_ou", {})
    ou_ensemble = ou.get("ensemble", [50, 50])
    ou_polymarket = ou.get("polymarket", [50, 50])
    
    over_fair = ou_polymarket[0] if ou_polymarket else 50
    under_fair = ou_polymarket[1] if ou_polymarket else 50
    
    # Estimate O/U odds
    over_odds = prob_to_odds(over_fair, OU_VIG)
    under_odds = prob_to_odds(under_fair, OU_VIG)
    
    over_edge = compute_edge(over_fair, over_odds)
    under_edge = compute_edge(under_fair, under_odds)
    
    # Build triangulation_ah
    # For AH -0.5, polymarket fair = home win prob (polymarket_devig.home * 100)
    poly_ah_home = round(home_p * 100, 1)
    poly_ah_away = round(100 - poly_ah_home, 1)
    
    # Also compute from ensemble / other models if available
    tri_1x2 = analysis.get("triangulation_1x2", {})
    
    ah_models = {}
    for source_key, vals in tri_1x2.items():
        if len(vals) >= 3:
            h, d, a = vals[0], vals[1], vals[2]
            # AH 0 prob (DNB): h / (h + a) — values are in %, so multiply by 100
            if h + a > 0:
                ah_0_h = round(h / (h + a) * 100, 1)
                ah_0_a = round(100 - ah_0_h, 1)
            else:
                ah_0_h, ah_0_a = 50, 50
            ah_models[source_key] = [ah_0_h, ah_0_a]
    
    # Add polymarket devig as another model (values in decimal, multiply by 100)
    if home_p + away_p > 0:
        ah_poly_0_h = round(home_p / (home_p + away_p) * 100, 1)
        ah_poly_0_a = round(100 - ah_poly_0_h, 1)
    else:
        ah_poly_0_h, ah_poly_0_a = 50, 50
    
    ah_models["polymarket"] = [ah_poly_0_h, ah_poly_0_a]
    
    # Ensemble: average of all models (exclude ensemble itself if present)
    model_vals_h = [v[0] for k, v in ah_models.items() if k != "ensemble" and len(v) >= 2 and isinstance(v[0], (int, float))]
    model_vals_a = [v[1] for k, v in ah_models.items() if k != "ensemble" and len(v) >= 2 and isinstance(v[1], (int, float))]
    
    if model_vals_h:
        ensemble_h = round(sum(model_vals_h) / len(model_vals_h), 1)
        ensemble_a = round(100 - ensemble_h, 1) if len(model_vals_a) else 50
        ah_models["ensemble"] = [ensemble_h, ensemble_a]
    
    # Build new edge_summary — ONLY AH + O/U
    home_team = match.get("home_team", "Home")
    away_team = match.get("away_team", "Away")
    
    new_edges = [
        {
            "market": f"{home_team} -0.5 (AH)",
            "edge": home_ah_edge,
            "status": edge_status(home_ah_edge),
            "quarter_kelly_stake": kelly_pct(home_ah_edge, ah_home_odds),
        },
        {
            "market": f"{away_team} +0.5 (AH)",
            "edge": away_ah_edge,
            "status": edge_status(away_ah_edge),
            "quarter_kelly_stake": kelly_pct(away_ah_edge, ah_away_odds),
        },
        {
            "market": "O 2.5",
            "edge": over_edge,
            "status": edge_status(over_edge),
            "quarter_kelly_stake": kelly_pct(over_edge, over_odds),
        },
        {
            "market": "U 2.5",
            "edge": under_edge,
            "status": edge_status(under_edge),
            "quarter_kelly_stake": kelly_pct(under_edge, under_odds),
        },
    ]
    
    # Update match
    match["home_odds"] = ah_home_odds
    match["draw_odds"] = 0   # no draw in AH
    match["away_odds"] = ah_away_odds
    
    # Add ah_analysis
    match["analysis"]["ah_analysis"] = ah
    match["analysis"]["ah_odds"] = {
        "home_minus_05": ah_home_odds,
        "away_plus_05": ah_away_odds,
    }
    
    # Add triangulation_ah
    match["analysis"]["triangulation_ah"] = ah_models
    
    # Remove BTTS
    match["analysis"].pop("triangulation_btts", None)
    
    # Replace edge_summary
    match["analysis"]["edge_summary"] = new_edges
    
    return match


def transform_all(data):
    """Transform entire data.json in place."""
    matches = data.get("matches", [])
    transformed = []
    for m in matches:
        t = transform_match(m)
        if t is not None:
            transformed.append(t)
    data["matches"] = transformed
    data["system_status"]["last_updated"] = data["system_status"].get("last_updated", "2026-07-10T00:00:00Z")
    return data


def main():
    input_path = DATA_FILE
    
    # Parse args
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--input" and i + 1 < len(args):
            input_path = Path(args[i + 1])
    
    # Read
    print(f"[transform] Reading: {input_path}")
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    print(f"[transform] Read {len(data.get('matches', []))} matches")
    
    # Transform
    data = transform_all(data)
    
    # Remove old triangulation keys from analysis
    for m in data.get("matches", []):
        # Keep triangulation_1x2 for reference, remove btts already done
        pass
    
    # Write back
    with open(input_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"[transform] ✅ Written {len(data['matches'])} matches back to {input_path}")
    
    # Show summary of changes
    for m in data["matches"]:
        edges = m.get("analysis", {}).get("edge_summary", [])
        ah = m.get("analysis", {}).get("ah_analysis", {})
        print(f"  {m['home_team']} vs {m['away_team']}:")
        print(f"    AH: -0.5 @ {m['home_odds']} | +0.5 @ {m['away_odds']}")
        if ah:
            print(f"    Fair: -0.5={ah.get('home_minus_05_prob', '?')}% | 0(DNB)={ah.get('home_0_prob', '?')}%")
        for e in edges:
            print(f"    {e['market']}: edge {e['edge']:+.1f}% → {e['status']} | kelly={e['quarter_kelly_stake']:.2f}%")


if __name__ == "__main__":
    main()
