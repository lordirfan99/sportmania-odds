"""
models.py — Real statistical models for probability triangulation.

Sources implemented:
  1. Dixon-Coles  — Poisson goal model with team attack/defense ratings (pure math, no API)
  2. Pinnacle     — Devigged sharp bookmaker odds (from the-odds-api cache, already fetched)
  3. Polymarket   — Prediction market API (attempted, graceful fallback on timeout/block)
"""

import math
import requests as req_lib

# ─────────────────────────────────────────────────────────
# TEAM RATINGS
# Calibrated from: WC2026 group stage + qualifying campaigns
# attack  = expected goals scored vs average defence (1.0 = avg)
# defense = expected goals conceded vs average attack (1.0 = avg, lower = better)
# ─────────────────────────────────────────────────────────
TEAM_RATINGS = {
    "Norway":      {"attack": 1.55, "defense": 1.08},   # Haaland-powered, leaky defence
    "England":     {"attack": 1.72, "defense": 0.80},   # Strong both ends
    "Argentina":   {"attack": 1.70, "defense": 0.86},   # Defending WC champions
    "Switzerland": {"attack": 1.10, "defense": 0.88},   # Defensive compact
    "France":      {"attack": 1.88, "defense": 0.76},   # Most complete squad
    "Spain":       {"attack": 1.82, "defense": 0.73},   # Best technical team WC2026
    "Belgium":     {"attack": 1.45, "defense": 0.90},
    "Brazil":      {"attack": 1.75, "defense": 0.82},
    "Portugal":    {"attack": 1.68, "defense": 0.85},
    "Germany":     {"attack": 1.65, "defense": 0.88},
    "Netherlands": {"attack": 1.60, "defense": 0.87},
    "Croatia":     {"attack": 1.35, "defense": 0.92},
    "Morocco":     {"attack": 1.20, "defense": 0.85},
    "USA":         {"attack": 1.30, "defense": 0.95},
    "Japan":       {"attack": 1.25, "defense": 0.90},
    "Korea":       {"attack": 1.20, "defense": 0.95},
}

HOME_ADVANTAGE = 1.07   # ~7% goal boost for nominal "home" team (neutral venue WC)
DC_RHO = -0.10          # Dixon-Coles low-score correction parameter
MAX_GOALS = 9           # Poisson truncation (sufficient for football)


# ─────────────────────────────────────────────────────────
# DIXON-COLES POISSON MODEL
# ─────────────────────────────────────────────────────────

def _poisson_pmf(k: int, lam: float) -> float:
    """P(X = k) for Poisson(lambda). Uses log-space for numerical stability."""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    log_p = -lam + k * math.log(lam) - sum(math.log(i) for i in range(1, k + 1))
    return math.exp(log_p)


def _dc_tau(h: int, a: int, mu_h: float, mu_a: float, rho: float = DC_RHO) -> float:
    """Dixon-Coles (1997) correction for under-representation of low-scoring results."""
    if h == 0 and a == 0:
        return 1.0 - mu_h * mu_a * rho
    elif h == 0 and a == 1:
        return 1.0 + mu_h * rho
    elif h == 1 and a == 0:
        return 1.0 + mu_a * rho
    elif h == 1 and a == 1:
        return 1.0 - rho
    return 1.0


def compute_dixon_coles(home_team: str, away_team: str) -> dict | None:
    """
    Compute 1X2, O/U 2.5, and AH -0.5/+0.5 probabilities using the
    Dixon-Coles Poisson model.

    Returns dict with keys:
      home, draw, away        (1X2 probabilities, sum to 1.0)
      over25, under25         (O/U 2.5 probabilities)
      ah_home, ah_away        (AH -0.5 / +0.5 probabilities)
      mu_h, mu_a              (expected goals each team)
    Returns None if team not found in TEAM_RATINGS.
    """
    h_r = TEAM_RATINGS.get(home_team)
    a_r = TEAM_RATINGS.get(away_team)
    if not h_r or not a_r:
        return None

    # Expected goals
    mu_h = h_r["attack"] * a_r["defense"] * HOME_ADVANTAGE
    mu_a = a_r["attack"] * h_r["defense"]

    p_home = p_draw = p_away = p_over25 = 0.0

    for gh in range(MAX_GOALS + 1):
        p_gh = _poisson_pmf(gh, mu_h)
        for ga in range(MAX_GOALS + 1):
            p_ga = _poisson_pmf(ga, mu_a)
            tau = _dc_tau(gh, ga, mu_h, mu_a)
            prob = p_gh * p_ga * tau

            if gh > ga:
                p_home += prob
            elif gh == ga:
                p_draw += prob
            else:
                p_away += prob

            if gh + ga > 2.5:
                p_over25 += prob

    total = p_home + p_draw + p_away
    if total <= 0:
        return None

    # Normalise (tau correction can slightly shift total away from 1.0)
    p_home /= total
    p_draw /= total
    p_away /= total

    # AH -0.5 = home must win outright; AH +0.5 = away or draw wins
    ah_home = p_home
    ah_away = p_draw + p_away

    return {
        "home":    round(p_home * 100, 1),
        "draw":    round(p_draw * 100, 1),
        "away":    round(p_away * 100, 1),
        "over25":  round(p_over25 * 100, 1),
        "under25": round((1.0 - p_over25) * 100, 1),
        "ah_home": round(ah_home * 100, 1),
        "ah_away": round(ah_away * 100, 1),
        "mu_h":    round(mu_h, 3),
        "mu_a":    round(mu_a, 3),
    }


# ─────────────────────────────────────────────────────────
# PINNACLE SHARP ODDS  (from cached the-odds-api response)
# ─────────────────────────────────────────────────────────

def extract_pinnacle_probs(api_raw_games: list, home_team: str, away_team: str) -> dict | None:
    """
    Extract devigged Pinnacle probabilities from the raw the-odds-api response.

    api_raw_games: the list returned directly by the-odds-api (already fetched).
    Returns dict with: home, draw, away, over25, under25, ah_home, ah_away
    or None if Pinnacle not available for this match.
    """
    h_key = home_team.lower()
    a_key = away_team.lower()

    for game in api_raw_games:
        g_home = game.get("home_team", "").lower()
        g_away = game.get("away_team", "").lower()
        # Fuzzy match — last word of team name
        h_match = h_key in g_home or g_home in h_key or h_key.split()[-1] in g_home
        a_match = a_key in g_away or g_away in a_key or a_key.split()[-1] in g_away
        if not (h_match and a_match):
            continue

        # Find Pinnacle bookmaker
        pinnacle = next((b for b in game.get("bookmakers", []) if b["title"] == "Pinnacle"), None)
        if not pinnacle:
            return None

        h2h = spreads = totals = None
        for mk in pinnacle.get("markets", []):
            if mk["key"] == "h2h":
                h2h = {o["name"]: o["price"] for o in mk.get("outcomes", [])}
            elif mk["key"] == "spreads":
                spreads = mk.get("outcomes", [])
            elif mk["key"] == "totals":
                totals = {o["name"]: o["price"] for o in mk.get("outcomes", [])}

        if not h2h:
            return None

        # Devig 1X2
        home_odds = h2h.get(game["home_team"], h2h.get(home_team, 0))
        draw_odds = h2h.get("Draw", 0)
        away_odds = h2h.get(game["away_team"], h2h.get(away_team, 0))

        if not all([home_odds, draw_odds, away_odds]):
            return None

        imp_sum = 1/home_odds + 1/draw_odds + 1/away_odds
        p_home = (1/home_odds) / imp_sum
        p_draw = (1/draw_odds) / imp_sum
        p_away = (1/away_odds) / imp_sum

        # AH -0.5 = home win only
        ah_home = p_home
        ah_away = p_draw + p_away

        # O/U 2.5
        over25 = under25 = None
        if totals:
            over_odds = totals.get("Over", 0)
            under_odds = totals.get("Under", 0)
            if over_odds and under_odds:
                ou_sum = 1/over_odds + 1/under_odds
                over25 = (1/over_odds) / ou_sum
                under25 = (1/under_odds) / ou_sum

        return {
            "home":    round(p_home * 100, 1),
            "draw":    round(p_draw * 100, 1),
            "away":    round(p_away * 100, 1),
            "over25":  round(over25 * 100, 1) if over25 else None,
            "under25": round(under25 * 100, 1) if under25 else None,
            "ah_home": round(ah_home * 100, 1),
            "ah_away": round(ah_away * 100, 1),
        }

    return None


# ─────────────────────────────────────────────────────────
# POLYMARKET PREDICTION MARKET  (with graceful fallback)
# ─────────────────────────────────────────────────────────

def fetch_polymarket_probs(home_team: str, away_team: str, timeout: int = 6) -> dict | None:
    """
    Attempt to fetch live prediction market probabilities from Polymarket Gamma API.
    Returns None silently if API is unreachable, blocked, or match not listed.
    """
    queries = [
        f"FIFA World Cup {home_team} {away_team}",
        f"{home_team} {away_team} soccer",
        f"{home_team} {away_team}",
    ]
    try:
        for q in queries:
            r = req_lib.get(
                "https://gamma-api.polymarket.com/events",
                params={"q": q, "limit": 10, "active": "true"},
                timeout=timeout,
            )
            if r.status_code != 200:
                continue

            events = r.json()
            if not isinstance(events, list):
                continue

            h_key = home_team.lower()
            a_key = away_team.lower()

            for ev in events:
                title = ev.get("title", "").lower()
                slug  = ev.get("slug",  "").lower()
                if not ((h_key in title or h_key in slug) and
                        (a_key in title or a_key in slug)):
                    continue

                # Scan markets for win/draw outcomes
                markets = ev.get("markets", [])
                probs = {}
                for mk in markets:
                    question = mk.get("question", "").lower()
                    outcome_prices = mk.get("outcomePrices", [])
                    if isinstance(outcome_prices, str):
                        import json
                        try:
                            outcome_prices = json.loads(outcome_prices)
                        except Exception:
                            continue

                    if not outcome_prices:
                        continue

                    price = float(outcome_prices[0])
                    if h_key in question and "win" in question:
                        probs["home"] = price
                    elif a_key in question and "win" in question:
                        probs["away"] = price
                    elif "draw" in question:
                        probs["draw"] = price
                    elif "over" in question and "2.5" in question:
                        probs["over25"] = price
                    elif "under" in question and "2.5" in question:
                        probs["under25"] = price

                if "home" in probs or "away" in probs:
                    total = sum(v for v in [probs.get("home", 0),
                                            probs.get("draw", 0),
                                            probs.get("away", 0)] if v)
                    if total > 0:
                        h = probs.get("home", 0) / total
                        d = probs.get("draw", 0) / total
                        a = probs.get("away", 0) / total
                        return {
                            "home":    round(h * 100, 1),
                            "draw":    round(d * 100, 1),
                            "away":    round(a * 100, 1),
                            "over25":  round(probs["over25"] * 100, 1) if "over25" in probs else None,
                            "under25": round(probs["under25"] * 100, 1) if "under25" in probs else None,
                            "ah_home": round(h * 100, 1),
                            "ah_away": round((d + a) * 100, 1),
                        }
    except Exception:
        pass  # Network blocked, timeout, or API error — silently skip

    return None
