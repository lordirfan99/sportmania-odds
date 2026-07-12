/**
 * betStore.js — Persistent Bet Store via Netlify Functions
 *
 * All bets + bankroll stored in Netlify Blobs (server-side).
 * Falls back to localStorage cache gracefully when offline or in local development.
 */
const STORAGE_URL = '/.netlify/functions/storage';

/* ─── Local Storage Cache Helpers ─── */

function getLocalFallback() {
  try {
    const bets = JSON.parse(localStorage.getItem('sportmania_bets') || '[]');
    const bankroll = Number(localStorage.getItem('sportmania_bankroll') || '34.2');
    return { bets, bankroll };
  } catch {
    return { bets: [], bankroll: 34.2 };
  }
}

function saveLocalFallback(bets, bankroll) {
  try {
    localStorage.setItem('sportmania_bets', JSON.stringify(bets));
    localStorage.setItem('sportmania_bankroll', String(bankroll));
  } catch {
    // Fail silently
  }
}

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
  match_id = '',
  home_team,
  away_team,
  market,
  odds_decimal,
  stake_rm,
  predicted_edge = null,
  ensemble_prob = null,
  kelly_pct = null,
  notes = '',
}) {
  const bet = {
    id: `net_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
    match_id,
    home_team,
    away_team,
    market,
    odds_decimal: Number(odds_decimal),
    stake_rm: Number(stake_rm),
    predicted_edge: predicted_edge !== null ? Number(predicted_edge) : null,
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

  try {
    await apiFetch('POST', { action: 'add-bet', bet });
    // Keep local cache fresh
    const local = getLocalFallback();
    local.bets.push(bet);
    saveLocalFallback(local.bets, local.bankroll);
  } catch (err) {
    console.warn("Storage fallback active: failed to post bet to Netlify.", err);
    const local = getLocalFallback();
    local.bets.push(bet);
    saveLocalFallback(local.bets, local.bankroll);
  }
  return bet;
}

/**
 * Settle a bet (after match result known).
 */
export async function settleBet(id, outcome, profit_rm, score = '') {
  const updates = {
    id,
    outcome,
    profit_rm: Number(profit_rm),
    settled: true,
    date_settled: new Date().toISOString(),
    score,
  };

  try {
    await apiFetch('POST', { action: 'settle-bet', bet: updates });
    const local = getLocalFallback();
    local.bets = local.bets.map((b) => (b.id === id ? { ...b, ...updates } : b));
    local.bankroll = Number((local.bankroll + updates.profit_rm).toFixed(2));
    saveLocalFallback(local.bets, local.bankroll);
  } catch (err) {
    console.warn("Storage fallback active: failed to settle bet on Netlify.", err);
    const local = getLocalFallback();
    local.bets = local.bets.map((b) => (b.id === id ? { ...b, ...updates } : b));
    local.bankroll = Number((local.bankroll + updates.profit_rm).toFixed(2));
    saveLocalFallback(local.bets, local.bankroll);
  }
  return updates;
}

/**
 * Delete a bet by ID.
 */
export async function deleteBet(id) {
  try {
    await apiFetch('POST', { action: 'delete-bet', betId: id });
    const local = getLocalFallback();
    local.bets = local.bets.filter((b) => b.id !== id);
    saveLocalFallback(local.bets, local.bankroll);
  } catch (err) {
    console.warn("Storage fallback active: failed to delete bet on Netlify.", err);
    const local = getLocalFallback();
    local.bets = local.bets.filter((b) => b.id !== id);
    saveLocalFallback(local.bets, local.bankroll);
  }
}

/**
 * Deposit to bankroll.
 */
export async function depositBankroll(amount, note = '') {
  const numAmount = Number(amount);
  try {
    const state = await apiFetch('POST', {
      action: 'deposit',
      amount: numAmount,
      note,
    });
    // Update local cache
    const local = getLocalFallback();
    local.bankroll = state.bankroll;
    saveLocalFallback(local.bets, local.bankroll);
    return state.bankroll;
  } catch (err) {
    console.warn("Storage fallback active: failed to deposit to Netlify.", err);
    const local = getLocalFallback();
    local.bankroll = Number((local.bankroll + numAmount).toFixed(2));
    saveLocalFallback(local.bets, local.bankroll);
    return local.bankroll;
  }
}

/**
 * Withdraw from bankroll.
 */
export async function withdrawBankroll(amount, note = '') {
  const numAmount = Number(amount);
  try {
    const state = await apiFetch('POST', {
      action: 'withdraw',
      amount: numAmount,
      note,
    });
    // Update local cache
    const local = getLocalFallback();
    local.bankroll = state.bankroll;
    saveLocalFallback(local.bets, local.bankroll);
    return state.bankroll;
  } catch (err) {
    console.warn("Storage fallback active: failed to withdraw from Netlify.", err);
    const local = getLocalFallback();
    local.bankroll = Number((local.bankroll - numAmount).toFixed(2));
    saveLocalFallback(local.bets, local.bankroll);
    return local.bankroll;
  }
}

/**
 * Get full state: { bets, bankroll }
 */
export async function getFullState() {
  try {
    const data = await apiFetch('GET');
    const state = { bets: data.bets || [], bankroll: data.bankroll || 0 };
    saveLocalFallback(state.bets, state.bankroll);
    return state;
  } catch (err) {
    console.warn("Storage fallback active: failed to fetch state from Netlify.", err);
    return getLocalFallback();
  }
}

/**
 * Get all bets (merged from store).
 */
export async function getAllBets(serverBets = []) {
  const state = await getFullState();
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
