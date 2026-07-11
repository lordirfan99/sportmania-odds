/**
 * betStore.js — Persistent Bet Store via Netlify Functions
 *
 * All bets + bankroll stored in Netlify Blobs (server-side).
 * No more localStorage — data survives cache clears and device switches.
 */
const STORAGE_URL = '/.netlify/functions/storage';

/* ─── Internal: fetch wrapper ─── */

async function apiFetch(method, body = null) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (body) opts.body = JSON.stringify(body);

  const res = await fetch(STORAGE_URL, opts);
  if (!res.ok) {
    const err = await res.text().catch(() => '');
    throw new Error(`Storage error (${res.status}): ${err}`);
  }
  return res.json();
}

/* ─── Public API ─── */

/**
 * Log a new bet to the persistent store.
 */
export async function addBet({
  home_team,
  away_team,
  market,
  odds_decimal,
  stake_rm,
  predicted_edge = null,
  polymarket_dv = null,
  ensemble_prob = null,
  kelly_pct = null,
  notes = '',
}) {
  const bet = {
    id: `net_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
    match_id: '',
    home_team,
    away_team,
    market,
    odds_decimal: Number(odds_decimal),
    stake_rm: Number(stake_rm),
    predicted_edge: predicted_edge !== null ? Number(predicted_edge) : null,
    polymarket_dv,
    ensemble_prob,
    kelly_pct,
    date_placed: new Date().toISOString(),
    date_settled: null,
    outcome: 'PENDING',
    profit_rm: 0,
    settled: false,
    score: '',
    notes,
    source: 'user_logged',
  };

  await apiFetch('POST', { action: 'add-bet', bet });
  return bet;
}

/**
 * Settle a bet (after match result known).
 */
export async function settleBet(id, outcome, profit_rm, score = '') {
  const bet = {
    id,
    outcome,
    profit_rm: Number(profit_rm),
    settled: true,
    date_settled: new Date().toISOString(),
    score,
  };

  await apiFetch('POST', { action: 'settle-bet', bet });
  return bet;
}

/**
 * Delete a bet by ID.
 */
export async function deleteBet(id) {
  await apiFetch('POST', { action: 'delete-bet', betId: id });
}

/**
 * Deposit to bankroll.
 */
export async function depositBankroll(amount, note = '') {
  const state = await apiFetch('POST', {
    action: 'deposit',
    amount: Number(amount),
    note,
  });
  return state.bankroll;
}

/**
 * Withdraw from bankroll.
 */
export async function withdrawBankroll(amount, note = '') {
  const state = await apiFetch('POST', {
    action: 'withdraw',
    amount: Number(amount),
    note,
  });
  return state.bankroll;
}

/**
 * Get full state: { bets, bankroll }
 */
export async function getFullState() {
  const data = await apiFetch('GET');
  return { bets: data.bets || [], bankroll: data.bankroll || 0 };
}

/**
 * Get all bets (merged from store, no serverBets arg needed).
 */
export async function getAllBets(serverBets = []) {
  const state = await getFullState();
  // Merge with server bets (from data.json), dedup by id
  const merged = [...serverBets];
  for (const lb of state.bets) {
    if (!merged.some((sb) => sb.id === lb.id)) {
      merged.push(lb);
    }
  }
  merged.sort((a, b) => new Date(b.date_placed) - new Date(a.date_placed));
  return merged;
}

/**
 * Compute stats from a bet list.
 */
export function computeStats(bets, bankroll) {
  const settled = bets.filter((b) => b.settled && (b.outcome === 'WON' || b.outcome === 'LOST'));
  const won = settled.filter((b) => b.outcome === 'WON');
  const totalProfit = settled.reduce((s, b) => s + (b.profit_rm || 0), 0);
  const totalStake = settled.reduce((s, b) => s + (b.stake_rm || 0), 0);

  return {
    total_bets: settled.length,
    won_bets: won.length,
    total_profit_rm: totalProfit,
    total_stake_rm: totalStake,
    roi_pct: totalStake > 0 ? (totalProfit / totalStake) * 100 : 0,
    win_rate_pct: settled.length > 0 ? (won.length / settled.length) * 100 : 0,
    bankroll_rm: bankroll,
  };
}
