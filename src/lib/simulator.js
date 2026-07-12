/**
 * simulator.js — Gate Decision Engine (Gates 1-2-3)
 *
 * Decides whether the SYSTEM would bet a given market.
 * All logic runs client-side from the existing match/analysis data.
 */

/* ─── config ─── */
const CONFIG = {
  MIN_EDGE_THRESHOLD: 3.2,    // Gate 1: edge % minimum
  MAX_STD_DEV_PCT: 10,        // Gate 2: max model std dev
  MIN_HISTORICAL_BETS: 3,     // Gate 3: minimum similar bets to trust
};

/* ─── helpers ─── */

/** Standard deviation of an array of numbers */
function stdDev(arr) {
  if (arr.length < 2) return Infinity;
  const mean = arr.reduce((a, b) => a + b, 0) / arr.length;
  const sq = arr.map((v) => (v - mean) ** 2);
  return Math.sqrt(sq.reduce((a, b) => a + b, 0) / (arr.length - 1));
}

/**
 * Find which triangulation key + indices to use for a given market name.
 * Returns { sourceKey, indices } or null.
 */
function marketTriangulation(marketName, homeTeam, awayTeam) {
  // 1X2
  if (marketName === homeTeam + ' Win') return { key: 'triangulation_1x2', idx: 0 };
  if (marketName === 'Draw') return { key: 'triangulation_1x2', idx: 1 };
  if (marketName === awayTeam + ' Win') return { key: 'triangulation_1x2', idx: 2 };

  // O/U
  if (marketName.startsWith('O ')) return { key: 'triangulation_ou', idx: 0 };
  if (marketName.startsWith('U ')) return { key: 'triangulation_ou', idx: 1 };

  // BTTS
  if (marketName === 'BTTS Yes') return { key: 'triangulation_btts', idx: 0 };
  if (marketName === 'BTTS No') return { key: 'triangulation_btts', idx: 1 };

  // AH — use DNB (triangulation_ah)
  if (marketName.includes('(AH)')) {
    // Home -0.5 → idx 0 (DNB home prob), Away +0.5 → idx 1 (DNB away prob)
    return { key: 'triangulation_ah', idx: 0 };  // both sides use consensus on home strength
  }

  return null;
}

/**
 * Calculate the model standard deviation for a market from triangulation data.
 */
function calcConsensus(marketName, homeTeam, awayTeam, analysis) {
  const tri = marketTriangulation(marketName, homeTeam, awayTeam);
  if (!tri) return null; // no triangulation data (AH etc)

  const source = analysis[tri.key];
  if (!source) return null;

  // Gather all model probabilities for this specific index
  const probs = [];
  for (const [model, vals] of Object.entries(source)) {
    if (model === 'ensemble') continue; // ensemble is derived, skip for std dev
    const val = vals[tri.idx];
    if (val !== undefined) probs.push(val);
  }
  if (probs.length < 2) return null;

  return {
    stdDevPct: stdDev(probs),
    models: probs.length,
    probs,
  };
}

/**
 * Gate 3: check bet_history for similar markets & edge ranges.
 */
function calcHistorical(marketName, edge, betHistory) {
  if (!betHistory || betHistory.length === 0) return null;

  // Find bets on the same market type (e.g. "U 2.5" → "U *" pattern)
  const marketFamily = marketName.startsWith('U ') || marketName.startsWith('O ')
    ? 'totals'
    : marketName.includes('BTTS')
    ? 'btts'
    : marketName === 'Draw'
    ? 'draw'
    : marketName.includes('Win')
    ? 'moneyline'
    : marketName.includes('+') || marketName.includes('-')
    ? 'asian_handicap'
    : 'other';

  // Also find bets with similar edge (±10pp)
  const similar = betHistory.filter((b) => {
    const sameFamily =
      (marketFamily === 'totals' && (b.market.startsWith('U ') || b.market.startsWith('O '))) ||
      (marketFamily === 'btts' && b.market.includes('BTTS')) ||
      (marketFamily === 'moneyline' && b.market.includes('Win')) ||
      (marketFamily === 'draw' && b.market === 'Draw') ||
      (marketFamily === 'asian_handicap' && (b.market.includes('+') || b.market.includes('-')));
    const similarEdge = Math.abs(b.predicted_edge - edge) < 10;
    return sameFamily || similarEdge;
  });

  if (similar.length < CONFIG.MIN_HISTORICAL_BETS) return null;

  const won = similar.filter((b) => b.outcome === 'WON').length;
  const roi =
    similar.reduce((sum, b) => sum + (b.profit_rm || 0), 0) /
    Math.max(similar.reduce((sum, b) => sum + (b.stake_rm || 1), 0), 0.01);

  return {
    total: similar.length,
    won,
    roi: roi * 100,
    verdict: roi > 0 ? 'CONFIRMS' : 'CONTRADICTS',
  };
}

/* ─── main export ─── */

/**
 * Run all 3 gates for a given market entry.
 *
 * @param {object}  marketEntry  — { market, edge, quarter_kelly_stake }
 * @param {string}  homeTeam
 * @param {string}  awayTeam
 * @param {object}  analysis     — match.analysis
 * @param {Array}   betHistory   — data.bet_history (optional)
 * @param {object}  config       — override CONFIG (optional)
 * @returns {object} { decision, gates, consensus, historical, reason }
 */
export function evaluateMarket(marketEntry, homeTeam, awayTeam, analysis, betHistory = [], config = {}) {
  const cfg = { ...CONFIG, ...config };
  const { market, edge, xbet_price, betfair_price, quarter_kelly_stake } = marketEntry;

  const gates = { gate1: null, gate2: null, gate3: null };
  let reason = '';

  // ── Gate 1: Threshold ──
  if (edge >= cfg.MIN_EDGE_THRESHOLD) {
    gates.gate1 = true;
  } else {
    gates.gate1 = false;
    reason = edge >= 0
      ? `Edge ${edge.toFixed(1)}% below threshold ${cfg.MIN_EDGE_THRESHOLD}%`
      : `Negative edge ${edge.toFixed(1)}%`;
  }

  // ── Gate 2: Consensus ──
  const consensus = calcConsensus(market, homeTeam, awayTeam, analysis);
  if (consensus) {
    gates.gate2 = consensus.stdDevPct <= cfg.MAX_STD_DEV_PCT;
    if (!gates.gate2 && gates.gate1) {
      reason = `Model std dev ${consensus.stdDevPct.toFixed(1)}pp > ${cfg.MAX_STD_DEV_PCT}pp — weak consensus`;
    }
  } else {
    gates.gate2 = null; // unknown (no triangulation data)
  }

  // ── Gate 3: Historical ──
  const historical = calcHistorical(market, edge, betHistory);
  if (historical) {
    gates.gate3 = historical.roi > 0;
    if (!gates.gate3 && gates.gate1 && gates.gate2 !== false) {
      reason = `Historical similar bets ROI ${historical.roi.toFixed(1)}% — pattern contradicts`;
    }
  } else {
    gates.gate3 = null; // insufficient data
  }

  // ── Final decision ──
  const gateResults = [gates.gate1, gates.gate2, gates.gate3];
  const passed = gateResults.filter((g) => g === true).length;
  const failed = gateResults.filter((g) => g === false).length;
  const unknown = gateResults.filter((g) => g === null).length;

  let decision, confidence;
  if (failed > 0) {
    decision = 'SKIP';
    confidence = failed >= 2 ? 'HIGH' : 'MEDIUM';
  } else if (passed === 3) {
    decision = 'BET';
    confidence = 'HIGH';
  } else if (passed >= 1 && unknown > 0) {
    decision = 'BET';
    confidence = 'LOW';
    reason = reason || `${unknown} gate(s) unknown (insufficient data)`;
  } else {
    decision = 'SKIP';
    confidence = 'MEDIUM';
    reason = reason || 'Did not pass enough gates';
  }

  // Edge-based override for strong signals even with unknowns
  if (edge > 15 && gates.gate1 && gates.gate2 !== false) {
    decision = 'BET';
    confidence = 'HIGH';
  }

  return {
    market,
    edge,
    xbet_price,
    betfair_price,
    kellyPct: marketEntry.quarter_kelly_stake || 0,
    decision,
    confidence,
    gates,
    consensus,
    historical,
    reason: decision === 'BET' ? '' : reason,
  };
}

/**
 * Evaluate ALL markets in a match's edge_summary.
 * Returns { decisions[], summary }
 */
export function evaluateMatch(match, betHistory = []) {
  if (!match?.analysis?.edge_summary) return { decisions: [], summary: null };

  const decisions = match.analysis.edge_summary.map((entry) =>
    evaluateMarket(entry, match.home_team, match.away_team, match.analysis, betHistory)
  );

  const betDecisions = decisions.filter((d) => d.decision === 'BET');
  const totalKelly = betDecisions.reduce((s, d) => s + d.kellyPct, 0);

  return {
    decisions,
    summary: {
      total: decisions.length,
      bet: betDecisions.length,
      skip: decisions.length - betDecisions.length,
      topPick: betDecisions.sort((a, b) => b.edge - a.edge)[0] || null,
      totalKellyPct: totalKelly,
    },
  };
}
