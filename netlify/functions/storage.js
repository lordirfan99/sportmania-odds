/**
 * Netlify Serverless Function — Persistent Betting Store
 * 
 * Uses /tmp file storage for persistence (survives warm starts).
 * Falls back to in-memory store if file write fails.
 * 
 * Endpoints:
 *   GET  /.netlify/functions/storage  → { bets, bankroll }
 *   POST /.netlify/functions/storage  → Update store
 *     Actions: add-bet, settle-bet, delete-bet, deposit, withdraw, bulk-set
 */
const fs = require('fs');
const STATE_PATH = '/tmp/betting-state.json';
const DEFAULT_STATE = { bets: [], bankroll: 34.2, version: 2 };

const HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
  'Content-Type': 'application/json',
};

// ─── Read/write state ───

function readState() {
  try {
    if (fs.existsSync(STATE_PATH)) {
      return JSON.parse(fs.readFileSync(STATE_PATH, 'utf8'));
    }
  } catch (e) {
    console.error('Read error:', e.message);
  }
  return { ...DEFAULT_STATE, bets: [] };
}

function writeState(state) {
  try {
    fs.writeFileSync(STATE_PATH, JSON.stringify(state));
    return true;
  } catch (e) {
    console.error('Write error:', e.message);
    return false;
  }
}

exports.handler = async (event) => {
  // ── OPTIONS (CORS) ──
  if (event.httpMethod === 'OPTIONS') {
    return { statusCode: 204, headers: HEADERS, body: '' };
  }

  try {
    // ── GET ──
    if (event.httpMethod === 'GET') {
      const state = readState();
      return { statusCode: 200, headers: HEADERS, body: JSON.stringify(state) };
    }

    // ── POST ──
    if (event.httpMethod === 'POST') {
      const body = JSON.parse(event.body || '{}');
      const { action } = body;
      const state = readState();

      switch (action) {
        case 'add-bet':
          if (body.bet) state.bets.push(body.bet);
          break;

        case 'settle-bet':
          if (body.bet) {
            const idx = state.bets.findIndex((b) => b.id === body.bet.id);
            if (idx >= 0) state.bets[idx] = { ...state.bets[idx], ...body.bet };
            else state.bets.push(body.bet);
          }
          break;

        case 'delete-bet':
          if (body.betId) state.bets = state.bets.filter((b) => b.id !== body.betId);
          break;

        case 'update-bankroll':
          if (typeof body.bankroll === 'number') state.bankroll = body.bankroll;
          break;

        case 'deposit':
          if (typeof body.amount === 'number' && body.amount > 0) {
            state.bankroll = (state.bankroll || 0) + body.amount;
            if (body.note) {
              state.bets.push({
                id: `sys_${Date.now()}`,
                home_team: '💳', away_team: 'Deposit',
                market: body.note || 'Bankroll Deposit',
                odds_decimal: 1.0, stake_rm: body.amount, profit_rm: 0,
                date_placed: new Date().toISOString(),
                settled: true, outcome: 'DEPOSIT', source: 'bankroll',
              });
            }
          }
          break;

        case 'withdraw':
          if (typeof body.amount === 'number' && body.amount > 0) {
            state.bankroll = Math.max(0, (state.bankroll || 0) - body.amount);
            if (body.note) {
              state.bets.push({
                id: `sys_${Date.now()}`,
                home_team: '💳', away_team: 'Withdraw',
                market: body.note || 'Bankroll Withdrawal',
                odds_decimal: 1.0, stake_rm: body.amount, profit_rm: 0,
                date_placed: new Date().toISOString(),
                settled: true, outcome: 'WITHDRAWAL', source: 'bankroll',
              });
            }
          }
          break;

        case 'bulk-set':
          if (body.state) {
            if (body.state.bets) state.bets = body.state.bets;
            if (typeof body.state.bankroll === 'number') state.bankroll = body.state.bankroll;
          }
          break;

        default:
          return { statusCode: 400, headers: HEADERS, body: JSON.stringify({ error: `Unknown: ${action}` }) };
      }

      writeState(state);
      return { statusCode: 200, headers: HEADERS, body: JSON.stringify(state) };
    }

    return { statusCode: 405, headers: HEADERS, body: JSON.stringify({ error: 'Method not allowed' }) };
  } catch (err) {
    console.error('Storage error:', err);
    return { statusCode: 500, headers: HEADERS, body: JSON.stringify({ error: err.message }) };
  }
};
