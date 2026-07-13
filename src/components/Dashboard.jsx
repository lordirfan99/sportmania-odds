import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Activity,
  DollarSign,
  Clock,
  TrendingUp,
  BarChart3,
  BrainCircuit,
  Target,
  GitBranch,
  Plus,
} from 'lucide-react';
import EdgeBadge from './EdgeBadge';
import BetLogForm from './BetLogForm';
import { evaluateMatch } from '../lib/simulator';
import {
  computeStats, settleBet,
  getFullState, depositBankroll, withdrawBankroll,
} from '../lib/betStore';

/* ---------- time helpers ---------- */
function fmtLocal(isoString) {
  if (!isoString) return '--';
  const d = new Date(isoString);
  return d.toLocaleTimeString('en-MY', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: true,
  });
}
function fmtLocalDate(isoString) {
  if (!isoString) return '--';
  const d = new Date(isoString);
  return d.toLocaleDateString('en-MY', {
    day: 'numeric',
    month: 'short',
  });
}

/* ---------- inline badge ---------- */
function DecisionBadge({ decision, confidence }) {
  if (decision === 'BET') {
    const neon = confidence === 'HIGH'
      ? 'edge-positive-pulse bg-accent-green/20 text-accent-green border-accent-green/40'
      : 'bg-green-500/15 text-green-400 border-green-500/30';
    return (
      <span className={`inline-block px-2 py-0.5 rounded text-[0.55rem] font-bold border ${neon}`}>
        ✅ BET ({confidence})
      </span>
    );
  }
  return (
    <span className="inline-block px-2 py-0.5 rounded text-[0.55rem] font-bold border bg-accent-red/15 text-accent-red border-accent-red/30">
      ❌ SKIP
    </span>
  );
}

/* ---------- main component ---------- */
export default function Dashboard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [now, setNow] = useState(new Date());
  const [showBetForm, setShowBetForm] = useState(false);
  const [betFormMatch, setBetFormMatch] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [settleBetId, setSettleBetId] = useState(null);
  const [settleScoreHome, setSettleScoreHome] = useState('');
  const [settleScoreAway, setSettleScoreAway] = useState('');
  const [settleError, setSettleError] = useState('');
  const [mergedBets, setMergedBets] = useState([]);
  const [liveStatus, setLiveStatus] = useState({ bankroll_rm: 34.2, total_profit_rm: 0, total_bets: 0, won_bets: 0 });
  const [showBankrollForm, setShowBankrollForm] = useState(false);
  const [bankrollAmount, setBankrollAmount] = useState('');
  const [bankrollNote, setBankrollNote] = useState('');
  const [bankrollAction, setBankrollAction] = useState('deposit');
  const [showHelp, setShowHelp] = useState(false);
  const [activeLeague, setActiveLeague] = useState('all');
  const navigate = useNavigate();

  // ── Load data.json + stored bets ──
  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        // Fetch data.json
        const dataRes = await fetch('/data.json');
        const d = await dataRes.json();

        // Fetch persistent store (resilient — don't crash if 404)
        let storedBets = [], storeBankroll = 0;
        try {
          const store = await getFullState();
          storedBets = store.bets || [];
          storeBankroll = store.bankroll || 0;
        } catch (storeErr) {
          console.warn('Storage function unavailable, using data.json only:', storeErr.message);
          // Fallback: use bankroll from data.json
          storeBankroll = d.system_status?.bankroll_rm || 0;
        }

        if (cancelled) return;

        // Merge server bets + stored bets, dedup
        const allBets = [...(d.bet_history || [])];
        for (const sb of storedBets) {
          if (!allBets.some((b) => b.id === sb.id)) {
            allBets.push(sb);
          }
        }
        allBets.sort((a, b) => new Date(b.date_placed) - new Date(a.date_placed));

        setData({ ...d, bet_history: allBets });
        setMergedBets(allBets);

        // Compute live stats
        const stats = computeStats(allBets, storeBankroll);
        setLiveStatus(stats);
        setLoading(false);
      } catch (err) {
        console.error('Load error:', err);
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [refreshKey]);

  // ── Clock tick ──
  useEffect(() => {
    const tick = setInterval(() => setNow(new Date()), 60_000);
    return () => clearInterval(tick);
  }, []);

  if (loading) return (
    <div className="flex items-center justify-center h-screen bg-dark-900">
      <div className="text-accent-cyan text-sm animate-pulse">LOADING SYSTEM...</div>
    </div>
  );
  if (!data) return (
    <div className="flex items-center justify-center h-screen bg-dark-900">
      <div className="text-accent-red text-sm">DATA UNAVAILABLE</div>
    </div>
  );

  const { system_status, matches: allMatches } = data;

  // mergedBets + liveStatus already loaded from persistent store in useEffect
  const allBets = mergedBets;

  // Extract unique leagues
  const leagues = [...new Set(allMatches.map(m => m.league_name || m.stage || 'Other'))].sort();

  // Filter upcoming matches — exclude women's leagues and club friendlies
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const excludePatterns = ['women', 'friendly', 'club friendly'];
  // Only show matches with both bookmakers (need 1xBet + Betfair for edge comparison)
  const matches = allMatches.filter((m) => {
    const leagueStr = (m.league_name || m.stage || '').toLowerCase();
    if (excludePatterns.some(p => leagueStr.includes(p))) return false;
    // Skip matches missing either bookmaker
    const bms = (m.bookmakers || []).map(b => b.toLowerCase());
    if (!bms.some(b => b.includes('1xbet')) || !bms.some(b => b.includes('betfair'))) return false;
    const dateStr = m.date || (m.commence_time ? m.commence_time.slice(0,10) : '');
    if (!dateStr) return activeLeague === 'all' || (m.league_name || m.stage || 'Other') === activeLeague;
    const matchDate = new Date(dateStr + 'T23:59:59');
    const leagueMatch = activeLeague === 'all' || (m.league_name || m.stage || 'Other') === activeLeague;
    return matchDate >= today && !m.settled && leagueMatch;
  });

  // Group by league for display
  const grouped = {};
  matches.forEach(m => {
    const league = m.league_name || m.stage || 'Other';
    if (!grouped[league]) grouped[league] = [];
    grouped[league].push(m);
  });

  const bankroll = liveStatus.bankroll_rm;
  const lastUpdated = system_status.last_updated;
  const nextRun = new Date(new Date(lastUpdated).getTime() + 4 * 60 * 60 * 1000);
  const isStale = now.getTime() - new Date(lastUpdated).getTime() > 4.5 * 60 * 60 * 1000;

  /* ---------- helpers ---------- */
  function bestEdge(match) {
    if (!match.analysis?.edge_summary?.length) return null;
    return [...match.analysis.edge_summary].sort((a, b) => b.edge - a.edge)[0];
  }

  // Pre-compute system evaluations for each match
  const matchEvals = Object.fromEntries(
    matches.map((m) => [m.match_id || m.id, evaluateMatch(m, allBets || [])])
  );

  // Divergence tracking
  const systemBets = [];
  const userBets = allBets;
  matches.forEach((m) => {
    const mid = m.match_id || m.id;
    const evalResult = matchEvals[mid];
    if (!evalResult) return;
    evalResult.decisions.forEach((d) => {
      if (d.decision === 'BET') {
        systemBets.push({ 
          matchId: mid, 
          home_team: m.home_team,
          away_team: m.away_team,
          ...d 
        });
      }
    });
  });

  // How many system bets has the user NOT placed?
  const divergedBets = systemBets.filter((sb) => {
    return !userBets.some(
      (ub) =>
        (ub.match_id === sb.matchId || 
         ub.home_team === sb.home_team || 
         (ub.home_team && sb.market.includes(ub.home_team))) && 
        ub.market === sb.market
    );
  });

  // System stats
  const sysStats = {
    total: systemBets.length,
    pending: systemBets.length,
    totalKelly: systemBets.reduce((s, b) => s + b.kellyPct, 0),
  };

  /* ─── Settle Bet Handler ─── */
  function handleSettleBet(bet, isWon = true) {
    const hScore = parseInt(settleScoreHome);
    const aScore = parseInt(settleScoreAway);
    if (isNaN(hScore) || isNaN(aScore)) {
      setSettleError('Enter both scores');
      return;
    }
    setSettleError('');
    const scoreStr = `${hScore}-${aScore}`;
    const profit = isWon
      ? parseFloat((bet.stake_rm * (bet.odds_decimal - 1)).toFixed(2))
      : -bet.stake_rm;

    settleBet(bet.id, isWon ? 'WON' : 'LOST', profit, scoreStr);
    setSettleBetId(null);
    setSettleScoreHome('');
    setSettleScoreAway('');
    setRefreshKey((k) => k + 1);
  }

  return (
    <div className="transition-all duration-500">
      <div className="max-w-7xl mx-auto px-2 sm:px-4 py-4 sm:py-6 pb-20 sm:pb-6">
        {/* ---- Header ---- */}
        <div className="mb-4 sm:mb-6 flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <BarChart3 className={`w-5 h-5 shrink-0 text-accent-cyan`} />
              <h1 className={`text-base sm:text-lg font-bold tracking-wider text-white`}>BETTING ENGINE v2.0</h1>
            </div>
            <div className="text-[0.55rem] sm:text-[0.6rem] text-muted tracking-[0.2em] uppercase">
              {matches.length} Matches · {leagues.length} Leagues · Cron every 3h
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            <button
              onClick={() => setShowHelp(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[0.6rem] font-bold tracking-wider bg-dark-700 text-muted hover:text-white border border-dark-500 hover:border-accent-cyan/30 transition-all mobile-touch cursor-pointer"
            >
              ❓ GUIDE
            </button>
          </div>
        </div>

      {/* ---- Status Bar ---- */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-1.5 sm:gap-3 mb-6 sm:mb-8">
        <div className="card mobile-touch flex flex-row items-center justify-between gap-1 sm:gap-3 py-3 sm:py-4">
          <div className="flex items-center gap-1.5 sm:gap-2 min-w-0">
            <Activity className="w-4 h-4 text-accent-green shrink-0" />
            <div className="min-w-0">
              <div className="text-[0.5rem] sm:text-[0.6rem] text-muted uppercase tracking-wider truncate">Last Cron</div>
              <div className="text-xs sm:text-sm font-bold text-white tracking-tight">{fmtLocal(lastUpdated)}</div>
            </div>
          </div>
          <span className="text-[0.45rem] sm:text-[0.5rem] text-muted shrink-0 hidden xs:inline">{fmtLocalDate(lastUpdated)}</span>
        </div>
        <div className="card mobile-touch flex flex-row items-center justify-between gap-1 sm:gap-3 py-3 sm:py-4">
          <div className="flex items-center gap-1.5 sm:gap-2 min-w-0">
            <Clock className="w-4 h-4 text-accent-yellow shrink-0" />
            <div className="min-w-0">
              <div className="text-[0.5rem] sm:text-[0.6rem] text-muted uppercase tracking-wider truncate">Next Run</div>
              <div className="text-xs sm:text-sm font-bold text-white tracking-tight">{fmtLocal(nextRun.toISOString())}</div>
            </div>
          </div>
          {isStale && <span className="text-[0.45rem] sm:text-[0.5rem] text-accent-red font-bold shrink-0 animate-pulse">STALE</span>}
        </div>
        <div className="card mobile-touch flex flex-row items-center justify-between gap-1 sm:gap-3 py-3 sm:py-4 cursor-pointer hover:border-accent-cyan/30 transition-all"
          onClick={() => setShowBankrollForm(true)}>
          <div className="flex items-center gap-1.5 sm:gap-2 min-w-0">
            <DollarSign className="w-4 h-4 text-accent-green shrink-0" />
            <div className="min-w-0">
              <div className="text-[0.5rem] sm:text-[0.6rem] text-muted uppercase tracking-wider truncate">Bankroll</div>
              <div className="text-xs sm:text-sm font-bold text-white tracking-tight">RM{bankroll?.toFixed(2)}</div>
            </div>
          </div>
          <span className="text-[0.45rem] text-accent-cyan/60 shrink-0">💳</span>
        </div>
        <div className="card mobile-touch flex flex-row items-center justify-between gap-1 sm:gap-3 py-3 sm:py-4">
          <div className="flex items-center gap-1.5 sm:gap-2 min-w-0">
            <TrendingUp className="w-4 h-4 text-accent-cyan shrink-0" />
            <div className="min-w-0">
              <div className="text-[0.5rem] sm:text-[0.6rem] text-muted uppercase tracking-wider truncate">Matches</div>
              <div className="text-xs sm:text-sm font-bold text-white tracking-tight">{matches.length}</div>
            </div>
          </div>
        </div>
      </div>

      {/* ── League Filter ── */}
      <div className="mb-4 sm:mb-6 overflow-x-auto scroll-hint -mx-2 sm:mx-0">
        <div className="flex gap-1.5 px-2 sm:px-0 min-w-max">
          <button
            onClick={() => setActiveLeague('all')}
            className={`px-3 py-1.5 rounded-full text-[0.55rem] font-bold tracking-wider transition-all cursor-pointer whitespace-nowrap ${
              activeLeague === 'all'
                ? 'bg-accent-cyan/20 text-accent-cyan border border-accent-cyan/40'
                : 'bg-dark-700 text-muted hover:text-white border border-dark-500 hover:border-accent-cyan/30'
            }`}
          >
            🏆 All ({matches.length})
          </button>
          {leagues.map(l => {
            const count = allMatches.filter(m => (m.league_name || m.stage || 'Other') === l).length;
            return (
              <button
                key={l}
                onClick={() => setActiveLeague(l)}
                className={`px-3 py-1.5 rounded-full text-[0.55rem] font-bold tracking-wider transition-all cursor-pointer whitespace-nowrap ${
                  activeLeague === l
                    ? 'bg-accent-cyan/20 text-accent-cyan border border-accent-cyan/40'
                    : 'bg-dark-700 text-muted hover:text-white border border-dark-500 hover:border-accent-cyan/30'
                }`}
              >
                {l} ({count})
              </button>
            );
          })}
        </div>
      </div>

      {/* ════════════════════════════════════════ */}
      {/* 🔬 DIVERGENCE TRACKER — You vs System   */}
      {/* ════════════════════════════════════════ */}
      <div className="mb-6">
        <div className="flex items-center gap-2 mb-3">
          <GitBranch className="w-4 h-5 text-accent-yellow" />
          <h2 className="section-header mb-0">Divergence Tracker — You vs System</h2>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
          {/* System stats */}
          <div className="card">
            <div className="flex items-center gap-2 mb-2">
              <BrainCircuit className="w-4 h-4 text-accent-cyan" />
              <span className="text-[0.6rem] text-muted uppercase tracking-wider">System (Shadow)</span>
            </div>
            <div className="grid grid-cols-2 gap-2 text-center text-xs">
              <div>
                <div className="text-[0.55rem] text-muted uppercase">Bets</div>
                <div className="text-lg font-bold text-white">{sysStats.total}</div>
              </div>
              <div>
                <div className="text-[0.55rem] text-muted uppercase">Pending</div>
                <div className="text-lg font-bold text-accent-yellow">{sysStats.pending}</div>
              </div>
              <div>
                <div className="text-[0.55rem] text-muted uppercase">Total Kelly</div>
                <div className="text-lg font-bold text-white">{sysStats.totalKelly.toFixed(2)}%</div>
              </div>
              <div>
                <div className="text-[0.55rem] text-muted uppercase">Status</div>
                <div className="text-lg font-bold text-accent-yellow">⏳ Waiting</div>
              </div>
            </div>
          </div>

          {/* User stats */}
          <div className="card">
            <div className="flex items-center gap-2 mb-2">
              <Target className="w-4 h-4 text-accent-green" />
              <span className="text-[0.6rem] text-muted uppercase tracking-wider">You (Actual)</span>
            </div>
            <div className="grid grid-cols-2 gap-2 text-center text-xs">
              <div>
                <div className="text-[0.55rem] text-muted uppercase">Bets</div>
                <div className="text-lg font-bold text-white">{userBets.length}</div>
              </div>
              <div>
                <div className="text-[0.55rem] text-muted uppercase">Settled</div>
                <div className="text-lg font-bold text-accent-green">{userBets.filter((b) => b.settled).length}</div>
              </div>
              <div>
                <div className="text-[0.55rem] text-muted uppercase">Profit</div>
                <div className="text-lg font-bold text-accent-green">+RM{liveStatus.total_profit_rm?.toFixed(2) || '0.00'}</div>
              </div>
              <div>
                <div className="text-[0.55rem] text-muted uppercase">Win Rate</div>
                <div className="text-lg font-bold text-accent-green">{(liveStatus.won_bets / Math.max(liveStatus.total_bets, 1) * 100).toFixed(0)}%</div>
              </div>
            </div>
          </div>
        </div>

        {/* Divergence detail */}
        {divergedBets.length > 0 && (
          <div className="card">
            <div className="text-[0.55rem] text-muted mb-2 uppercase tracking-wider">
              ⚡ System says BET — You haven't placed these yet
            </div>
            <div className="overflow-x-auto">
              <table className="terminal-grid w-full min-w-[350px]">
                <thead>
                  <tr>
                    <th className="text-left">Match</th>
                    <th className="text-left">Market</th>
                    <th className="text-right num-mono">Edge</th>
                    <th className="text-center">Confidence</th>
                    <th className="text-right num-mono">Kelly</th>
                  </tr>
                </thead>
                <tbody>
                  {divergedBets.map((sb, i) => {
                    const match = matches.find((m) => (m.match_id || m.id) === sb.matchId);
                    return (
                      <tr key={i}>
                        <td className="text-left text-xs text-white/80">
                          {match ? `${match.home_team} v ${match.away_team}` : sb.matchId}
                        </td>
                        <td className="text-left text-xs text-white/80">{sb.market}</td>
                        <td className="text-right num-mono text-xs text-accent-green">{sb.edge > 0 ? '+' : ''}{sb.edge.toFixed(1)}%</td>
                        <td className="text-center text-xs">{sb.confidence}</td>
                        <td className="text-right num-mono text-xs text-white/80">{sb.kellyPct > 0 ? `${sb.kellyPct.toFixed(2)}%` : '-'}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className="mt-2 text-[0.55rem] text-muted">
              💡 Consider: system found {divergedBets.length} opportunities you haven't acted on
            </div>
          </div>
        )}

        {/* When you agreed */}
        {userBets.filter((b) => b.settled).length > 0 && (
          <div className="card mt-2">
            <div className="text-[0.55rem] text-muted mb-2 uppercase tracking-wider">Record — When you agreed with system</div>
            <div className="overflow-x-auto">
              <table className="terminal-grid w-full min-w-[350px]">
                <thead>
                  <tr>
                    <th className="text-left">Match</th>
                    <th className="text-left">Market</th>
                    <th className="text-right num-mono">Odds</th>
                    <th className="text-center">Outcome</th>
                    <th className="text-right num-mono">P&amp;L</th>
                  </tr>
                </thead>
                <tbody>
                  {userBets.filter((b) => b.settled).map((b, i) => (
                    <tr key={i}>
                      <td className="text-left text-xs text-white/80">{b.home_team} v {b.away_team}</td>
                      <td className="text-left text-xs text-white/80">{b.market}</td>
                      <td className="text-right num-mono text-xs">{b.odds_decimal.toFixed(2)}</td>
                      <td className={`text-center text-xs font-bold ${b.outcome === 'WON' ? 'text-accent-green' : 'text-accent-red'}`}>{b.outcome === 'WON' ? '✅ WON' : '❌ LOST'}</td>
                      <td className={`text-right num-mono text-xs font-bold ${b.profit_rm >= 0 ? 'text-accent-green' : 'text-accent-red'}`}>
                        {b.profit_rm >= 0 ? '+' : ''}RM{b.profit_rm.toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {userBets.length === 0 && systemBets.length === 0 && (
          <div className="card text-center text-[0.65rem] text-muted">
            No bets yet. Start placing bets to see divergence data.
          </div>
        )}
      </div>

      {/* ════════════════════════════════════════ */}
      {/* 📊 UPCOMING MATCHES — Odds + Edge Analysis */}
      {/* ════════════════════════════════════════ */}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 className="section-header mb-0">Upcoming Matches</h2>
        <div className="flex flex-wrap gap-2 sm:gap-3 text-[0.55rem] sm:text-[0.6rem] text-muted">
          <span>🚀 Kelly</span><span>✅ Value</span><span>⚪ Neutral</span><span>❌ Avoid</span>
        </div>
      </div>

      {Object.entries(grouped).map(([league, leagueMatches]) => {
        const sorted = [...leagueMatches].sort((a, b) => {
          const ea = matchEvals[a.match_id || a.id];
          const eb = matchEvals[b.match_id || b.id];
          const topA = ea?.summary?.topPick?.edge ?? -999;
          const topB = eb?.summary?.topPick?.edge ?? -999;
          return topB - topA;
        });
        return (
        <div key={league} className="mb-6">
          <div className="flex items-center gap-2 mb-3 mt-2">
            <span className="text-[0.65rem] font-bold text-accent-cyan uppercase tracking-wider">{league}</span>
            <span className="text-[0.5rem] text-muted">({leagueMatches.length} matches)</span>
            <div className="flex-1 h-px bg-dark-600/50 ml-2" />
          </div>
          <div className="grid gap-3">
            {sorted.map((m) => {
              const mid = m.match_id || m.id;
              const ev = matchEvals[mid];
              if (!ev) return null;
              const top = ev.summary?.topPick;
              return (
                <div key={mid} className="card cursor-pointer hover:border-accent-cyan/20 transition-all"
                  onClick={() => navigate(`/match/${mid}`)}>
                  {/* Row 1: Teams + BET/SKIP */}
                  <div className="flex flex-wrap items-center justify-between gap-2 mb-1">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="font-bold text-sm text-white truncate">{m.home_team}</span>
                      <span className="text-muted text-xs shrink-0">v</span>
                      <span className="font-bold text-sm text-white truncate">{m.away_team}</span>
                    </div>
                    <div className="flex gap-2 text-[0.55rem] shrink-0">
                      <span className="text-accent-green">{ev.summary.bet} BET</span>
                      <span className="text-muted">/</span>
                      <span className="text-accent-red">{ev.summary.skip} SKIP</span>
                    </div>
                  </div>

                  {/* Row 2: League + Date */}
                  <div className="text-[0.55rem] text-muted mb-2">{m.stage || m.league_name} · {m.date || '--'}</div>

                  {/* Row 3: Market grid — O/U 2.5 + Asian Handicap only */}
                  <div className="overflow-x-auto -mx-2 px-2 mb-2">
                    <div className="grid grid-cols-[1fr_auto_auto_auto] gap-x-2 gap-y-1 text-[0.55rem] min-w-[280px]">
                      <div className="text-muted text-left font-bold uppercase tracking-wider">Market</div>
                      <div className="text-right text-accent-cyan font-bold">1xBet</div>
                      <div className="text-right text-purple-400 font-bold">Betfair</div>
                      <div className="text-right font-bold text-muted">Edge</div>
                      {(() => {
                        const ouEdges = ev.decisions.filter(d => d.market?.startsWith('Over ') || d.market?.startsWith('Under '));
                        const ahEdges = ev.decisions.filter(d => d.market?.includes('(AH)'));
                        const allEdges = [...ouEdges, ...ahEdges];
                        return allEdges.length > 0 ? allEdges.map((d, i) => {
                          const label = d.market.replace(/\s*\(1xBet vs Betfair\)/, '');
                          const xb = d.xbet_price || d.xbetPrice || null;
                          const bf = d.betfair_price || d.betfairPrice || null;
                          const ec = d.edge > 5 ? 'text-accent-green' : d.edge > -5 ? 'text-muted' : 'text-accent-red';
                          return (
                            <div key={i} className="contents">
                              <div className={`text-white/80 truncate ${d.market?.startsWith('Over') || d.market?.startsWith('Under') ? 'font-bold' : ''}`}>{label}</div>
                              <div className="text-right text-accent-cyan num-mono">{xb?.toFixed(2) ?? '-'}</div>
                              <div className="text-right text-purple-400 num-mono">{bf?.toFixed(2) ?? '-'}</div>
                              <div className={`text-right num-mono ${ec}`}>{d.edge > 0 ? '+' : ''}{d.edge.toFixed(1)}%</div>
                            </div>
                          );
                        }) : (
                          <div className="col-span-4 text-center text-muted py-1 text-[0.5rem]">No Betfair data</div>
                        );
                      })()}
                    </div>
                  </div>

                  {/* Row 4: Summary bar — O/U spread + EdgeBadge */}
                  <div className="flex flex-wrap items-center justify-between gap-2 mt-1">
                    <div className="text-[0.55rem] text-muted">
                      O/U {m.analysis?.sport_raw?.ou_point?.toFixed(1) || '2.5'}:{' '}
                      <span className="num-mono text-white/70">{m.analysis?.sport_raw?.over_odds?.toFixed(2) ?? '-'}</span>
                      <span className="text-muted"> / </span>
                      <span className="num-mono text-white/70">{m.analysis?.sport_raw?.under_odds?.toFixed(2) ?? '-'}</span>
                      <span className="ml-2">AH:</span>
                      <span className="num-mono text-white/70 ml-1">{m.home_odds?.toFixed(2) ?? '-'}</span>
                      <span className="text-muted"> / </span>
                      <span className="num-mono text-white/70">{m.away_odds?.toFixed(2) ?? '-'}</span>
                    </div>
                    <EdgeBadge edge={top?.edge ?? null} />
                  </div>

                  {/* Row 5: Top pick recommendation */}
                  {top && (
                    <div className="mt-1 text-[0.5rem] text-accent-green font-bold">
                      ⭐ {top.market.replace(/\s*\(1xBet vs (Betfair|Pinnacle)\)/, '')} @ {top.edge > 0 ? '+' : ''}{top.edge.toFixed(1)}%
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      );
      })}

      {matches.length > 0 && systemBets.length === 0 && (
        <div className="card text-center text-[0.65rem] text-muted">
          ⚪ No markets pass all 3 gates — system recommends PASS on all upcoming matches.
        </div>
      )}

      {/* ════════════════════════════════════════ */}
      {/* 📊 O/U 2.5 MARKET — All Matches Combined */}
      {/* ════════════════════════════════════════ */}
      {(() => {
        const ouRows = [];
        matches.forEach(m => {
          const ev = matchEvals[m.match_id || m.id];
          if (!ev) return;
          let over = null, under = null;
          ev.decisions.forEach(d => {
            if (!d.market?.includes('(1xBet vs Betfair)')) return;
            if (d.market?.startsWith('Over ')) over = d;
            if (d.market?.startsWith('Under ')) under = d;
          });
          if (over || under) {
            ouRows.push({ home: m.home_team, away: m.away_team, league: m.stage || m.league_name || '', over, under });
          }
        });
        if (ouRows.length === 0) return null;
        ouRows.sort((a, b) => Math.max(b.over?.edge ?? -999, b.under?.edge ?? -999) - Math.max(a.over?.edge ?? -999, a.under?.edge ?? -999));
        return (
          <div className="mb-6 mt-6">
            <div className="flex items-center gap-2 mb-3">
              <span className="section-header mb-0">📊 O/U 2.5 Market ({ouRows.length} matches)</span>
            </div>
            <div className="grid gap-1.5">
              <div className="hidden md:grid grid-cols-[1fr_2fr_0.8fr_0.8fr_0.8fr_0.8fr_0.8fr_0.8fr] gap-2 px-3 py-1.5 text-[0.5rem] text-muted uppercase tracking-wider">
                <span>#</span><span>Match</span><span>Over 1xBet</span><span>Over Bf</span><span>Over Edge</span><span>Under 1xBet</span><span>Under Bf</span><span>Under Edge</span>
              </div>
              {ouRows.map((row, i) => (
                <div key={i} className="card flex flex-wrap items-center gap-x-3 gap-y-0.5 py-2 px-3">
                  <span className="text-[0.55rem] text-muted w-4 shrink-0">{i + 1}.</span>
                  <span className="font-bold text-sm text-white min-w-0 flex-1 truncate">{row.home} vs {row.away}</span>
                  <span className="text-[0.5rem] text-muted w-full sm:w-auto hidden sm:block">{row.league}</span>
                  {/* Over */}
                  <div className="flex items-center gap-1.5 text-[0.55rem]">
                    <span className="text-muted uppercase hidden md:inline" />
                    <span className="text-accent-cyan num-mono">{row.over?.xbet_price?.toFixed(2) ?? '-'}</span>
                    <span className="text-purple-400 num-mono">{row.over?.betfair_price?.toFixed(2) ?? '-'}</span>
                    <span className={`num-mono font-bold ${(row.over?.edge ?? -999) > 0 ? 'text-accent-green' : (row.over?.edge ?? -999) > -5 ? 'text-muted' : 'text-accent-red'}`}>
                      {row.over ? `${row.over.edge > 0 ? '+' : ''}${row.over.edge.toFixed(1)}%` : '-'}
                    </span>
                  </div>
                  {/* Under */}
                  <div className="flex items-center gap-1.5 text-[0.55rem]">
                    <span className="text-muted uppercase hidden md:inline" />
                    <span className="text-accent-cyan num-mono">{row.under?.xbet_price?.toFixed(2) ?? '-'}</span>
                    <span className="text-purple-400 num-mono">{row.under?.betfair_price?.toFixed(2) ?? '-'}</span>
                    <span className={`num-mono font-bold ${(row.under?.edge ?? -999) > 0 ? 'text-accent-green' : (row.under?.edge ?? -999) > -5 ? 'text-muted' : 'text-accent-red'}`}>
                      {row.under ? `${row.under.edge > 0 ? '+' : ''}${row.under.edge.toFixed(1)}%` : '-'}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })()}

      {/* ════════════════════════════════════════ */}
      {/* BET HISTORY */}
      {/* ════════════════════════════════════════ */}
      {mergedBets.length > 0 && (
        <div className="mt-8">
          <div className="flex items-center justify-between mb-3">
            <h2 className="section-header mb-0">Bet History</h2>
            <button
              onClick={() => { setBetFormMatch(null); setShowBetForm(true); }}
              className="flex items-center gap-1 px-2.5 py-1 rounded text-[0.55rem] font-bold tracking-wider uppercase bg-accent-cyan/15 text-accent-cyan border border-accent-cyan/30 hover:bg-accent-cyan/25 transition-all"
            >
              <Plus className="w-3 h-3" /> Log Bet
            </button>
          </div>
          <div className="grid gap-2">
            {mergedBets.map((bet) => {
              const won = bet.outcome === 'WON';
              const isBankroll = bet.source === 'bankroll';
              const isPending = (bet.outcome === 'PENDING' || !bet.settled) && !isBankroll;
              const showSettle = settleBetId === bet.id;
              return (
                <div key={bet.id} className={`card grid grid-cols-2 sm:grid-cols-[1.5fr_1fr_1fr_0.8fr_0.6fr_0.6fr_0.4fr] gap-1.5 sm:gap-3 items-center py-3 sm:py-3 ${won ? 'border-accent-green/20' : isBankroll ? 'border-accent-cyan/20' : isPending ? 'border-dark-500 cursor-pointer hover:border-accent-cyan/30' : 'border-accent-red/20'}`}
                  onClick={() => !isBankroll && isPending && setSettleBetId(settleBetId === bet.id ? null : bet.id)}>
                  <div className="col-span-2 sm:col-span-1 flex items-center gap-2 min-w-0">
                    <span className={`text-xs font-bold ${won ? 'text-accent-green' : isBankroll ? 'text-accent-cyan' : isPending ? 'text-accent-yellow' : 'text-accent-red'}`}>
                      {isBankroll ? '💳' : won ? 'W' : isPending ? '?' : 'L'}
                    </span>
                    <span className="font-bold text-sm text-white truncate">{bet.home_team}</span>
                    <span className="text-muted text-xs">v</span>
                    <span className="font-bold text-sm text-white truncate">{bet.away_team}</span>
                    {bet.source === 'user_logged' && <span className="text-[0.45rem] text-accent-cyan ml-1">📱</span>}
                  </div>
                  <div className="text-xs text-muted"><span className="sm:hidden text-[0.55rem] uppercase tracking-wider text-muted block">Market</span>{bet.market}</div>
                  <div className="text-xs num-mono text-white/80 text-right sm:text-left"><span className="sm:hidden text-[0.55rem] uppercase tracking-wider text-muted block">Odds</span>{bet.odds_decimal?.toFixed(2)}</div>
                  <div className="text-xs text-right"><span className="sm:hidden text-[0.55rem] uppercase tracking-wider text-muted block">Stake</span><span className="num-mono text-white/80">RM{bet.stake_rm?.toFixed(2)}</span></div>
                  <div className={`text-xs font-bold num-mono text-right ${won ? 'text-accent-green' : isBankroll ? 'text-accent-cyan' : isPending ? 'text-accent-yellow' : 'text-accent-red'}`}>
                    <span className="sm:hidden text-[0.55rem] uppercase tracking-wider text-muted block">P&amp;L</span>
                    {isBankroll ? '💳' : isPending ? '⏳' : `${won ? '+' : ''}RM${bet.profit_rm?.toFixed(2)}`}
                  </div>
                  <div className="text-[0.55rem] text-muted text-right truncate hidden sm:block">
                    {bet.score ? `${bet.score} · ` : ''}{(bet.date_placed || '').slice(0, 10)}
                  </div>
                  {/* Settle button for pending bets (not bankroll) */}
                  {isPending && !isBankroll && (
                    <div className="text-center" onClick={(e) => e.stopPropagation()}>
                      <span className="inline-block px-1.5 py-0.5 rounded text-[0.45rem] font-bold bg-accent-yellow/20 text-accent-yellow border border-accent-yellow/30 cursor-pointer hover:bg-accent-yellow/30"
                        onClick={() => setSettleBetId(settleBetId === bet.id ? null : bet.id)}>
                        SETTLE
                      </span>
                    </div>
                  )}

                  {/* ── Inline Settle Form ── */}
                  {showSettle && (
                    <div className="col-span-full mt-2 pt-3 border-t border-dark-600" onClick={(e) => e.stopPropagation()}>
                      <div className="text-[0.55rem] text-muted mb-2 uppercase tracking-wider">Settle Bet — {bet.market}</div>
                      <div className="flex flex-wrap items-end gap-2">
                        <div className="w-16">
                          <label className="text-[0.45rem] text-muted block mb-0.5">Home</label>
                          <input type="number" min="0" max="20" className="w-full bg-dark-900 border border-dark-500 rounded px-2 py-1 text-xs text-white num-mono"
                            value={settleScoreHome}
                            onChange={(e) => setSettleScoreHome(e.target.value)}
                            placeholder="0" />
                        </div>
                        <span className="text-muted text-xs pb-1.5">-</span>
                        <div className="w-16">
                          <label className="text-[0.45rem] text-muted block mb-0.5">Away</label>
                          <input type="number" min="0" max="20" className="w-full bg-dark-900 border border-dark-500 rounded px-2 py-1 text-xs text-white num-mono"
                            value={settleScoreAway}
                            onChange={(e) => setSettleScoreAway(e.target.value)}
                            placeholder="0" />
                        </div>
                        <button className="px-3 py-1 rounded text-[0.55rem] font-bold bg-accent-green/20 text-accent-green border border-accent-green/30 hover:bg-accent-green/30"
                          onClick={() => handleSettleBet(bet)}>
                          ✅ WON
                        </button>
                        <button className="px-3 py-1 rounded text-[0.55rem] font-bold bg-accent-red/20 text-accent-red border border-accent-red/30 hover:bg-accent-red/30"
                          onClick={() => handleSettleBet(bet, false)}>
                          ❌ LOST
                        </button>
                        <button className="px-3 py-1 rounded text-[0.55rem] font-bold bg-dark-600 text-muted border border-dark-500 hover:text-white"
                          onClick={() => setSettleBetId(null)}>
                          Cancel
                        </button>
                      </div>
                      {settleError && <div className="text-[0.5rem] text-accent-red mt-1">{settleError}</div>}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
          <div className="mt-2 text-[0.55rem] text-muted text-center">
            Total P&amp;L: <span className={`font-bold ${liveStatus.total_profit_rm >= 0 ? 'text-accent-green' : 'text-accent-red'}`}>
              {liveStatus.total_profit_rm >= 0 ? '+' : ''}RM{liveStatus.total_profit_rm?.toFixed(2) || '0.00'}
            </span>
            &middot; {liveStatus.won_bets || 0}/{liveStatus.total_bets || 0} bets won
            &middot; Win Rate: <span className="text-white/70">{liveStatus.win_rate_pct?.toFixed(1)}%</span>
            &middot; Bankroll: <span className="text-white/70">RM{liveStatus.bankroll_rm?.toFixed(2)}</span>
          </div>
        </div>
      )}
 
      {/* ---- Bet Log Form Modal ---- */}
      {showBetForm && (
        <BetLogForm
          match={betFormMatch}
          onClose={() => setShowBetForm(false)}
          onLogged={() => {
            setRefreshKey((k) => k + 1);
          }}
        />
      )}

      {/* ---- Bankroll Deposit/Withdraw Modal ---- */}
      {showBankrollForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm px-3">
          <div className="w-full max-w-xs bg-dark-800 border border-dark-500 rounded-xl shadow-2xl">
            <div className="flex items-center justify-between px-5 py-4 border-b border-dark-600">
              <h3 className="text-sm font-bold text-white tracking-wider uppercase">Bankroll</h3>
              <button onClick={() => setShowBankrollForm(false)} className="text-muted hover:text-white transition-colors">
                ✕
              </button>
            </div>
            <div className="p-5 space-y-4">
              {/* Current balance */}
              <div className="text-center">
                <div className="text-[0.55rem] text-muted uppercase tracking-wider">Current</div>
                <div className="text-2xl font-bold text-white num-mono">RM{bankroll?.toFixed(2)}</div>
              </div>

              {/* Toggle deposit/withdraw */}
              <div className="flex rounded-lg overflow-hidden border border-dark-500">
                <button
                  className={`flex-1 py-2 text-xs font-bold tracking-wider uppercase transition-all ${bankrollAction === 'deposit' ? 'bg-accent-green/20 text-accent-green' : 'bg-dark-900 text-muted'}`}
                  onClick={() => setBankrollAction('deposit')}
                >
                  💰 Deposit
                </button>
                <button
                  className={`flex-1 py-2 text-xs font-bold tracking-wider uppercase transition-all ${bankrollAction === 'withdraw' ? 'bg-accent-red/20 text-accent-red' : 'bg-dark-900 text-muted'}`}
                  onClick={() => setBankrollAction('withdraw')}
                >
                  🏦 Withdraw
                </button>
              </div>

              {/* Amount */}
              <div>
                <label className="text-[0.55rem] text-muted uppercase tracking-wider block mb-1.5">Amount (RM)</label>
                <input
                  type="number"
                  step="0.50"
                  min="1"
                  value={bankrollAmount}
                  onChange={(e) => setBankrollAmount(e.target.value)}
                  className="w-full bg-dark-900 border border-dark-500 rounded px-3 py-2.5 text-sm text-white num-mono focus:border-accent-cyan outline-none"
                  placeholder="10.00"
                  autoFocus
                />
                {/* Quick amount buttons */}
                <div className="quick-amount-grid mt-2">
                  {[10, 20, 50, 100, 500].map((amt) => (
                    <button
                      key={amt}
                      type="button"
                      onClick={() => setBankrollAmount(String(amt))}
                      className={`py-1.5 rounded text-[0.55rem] font-bold border transition-all ${
                        bankrollAmount === String(amt)
                          ? 'bg-accent-cyan/20 text-accent-cyan border-accent-cyan/40'
                          : 'bg-dark-700 text-muted border-dark-500 hover:border-accent-cyan/30'
                      }`}
                    >
                      RM{amt}
                    </button>
                  ))}
                </div>
              </div>

              {/* Note */}
              <div>
                <label className="text-[0.55rem] text-muted uppercase tracking-wider block mb-1">Note <span className="text-muted/50">(optional)</span></label>
                <input
                  value={bankrollNote}
                  onChange={(e) => setBankrollNote(e.target.value)}
                  className="w-full bg-dark-900 border border-dark-500 rounded px-3 py-2 text-xs text-white focus:border-accent-cyan outline-none"
                  placeholder={bankrollAction === 'deposit' ? 'Deposit from bank' : 'Withdraw to bank'}
                />
              </div>

              {/* Preview */}
              {bankrollAmount && (
                <div className="bg-dark-900 rounded px-3 py-2 text-[0.6rem] text-muted flex justify-between">
                  <span>New Balance:</span>
                  <span className={`font-bold num-mono ${bankrollAction === 'deposit' ? 'text-accent-green' : 'text-accent-red'}`}>
                    RM{(bankrollAction === 'deposit'
                      ? (bankroll || 0) + parseFloat(bankrollAmount)
                      : Math.max(0, (bankroll || 0) - parseFloat(bankrollAmount))
                    ).toFixed(2)}
                  </span>
                </div>
              )}

              {/* Submit */}
              <button
                disabled={!bankrollAmount || parseFloat(bankrollAmount) <= 0}
                onClick={async () => {
                  const amount = parseFloat(bankrollAmount);
                  if (!amount || amount <= 0) return;
                  try {
                    if (bankrollAction === 'deposit') {
                      await depositBankroll(amount, bankrollNote);
                    } else {
                      await withdrawBankroll(amount, bankrollNote);
                    }
                    setShowBankrollForm(false);
                    setBankrollAmount('');
                    setBankrollNote('');
                    setRefreshKey((k) => k + 1);
                  } catch (err) {
                    console.error('Bankroll error:', err);
                  }
                }}
                className={`w-full flex items-center justify-center gap-2 py-2.5 rounded-lg text-xs font-bold tracking-wider uppercase transition-all ${
                  bankrollAction === 'deposit'
                    ? 'bg-accent-green/20 text-accent-green border border-accent-green/30 hover:bg-accent-green/30'
                    : 'bg-accent-red/20 text-accent-red border border-accent-red/30 hover:bg-accent-red/30'
                } disabled:opacity-40 disabled:cursor-not-allowed`}
              >
                {bankrollAction === 'deposit' ? '💰 Confirm Deposit' : '🏦 Confirm Withdraw'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ---- Guide Modal ---- */}
      {showHelp && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-md px-3 py-4"
          onClick={() => setShowHelp(false)}>
          <div className="w-full max-w-2xl bg-dark-800 border border-dark-500 rounded-xl shadow-2xl max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}>
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-dark-600 sticky top-0 bg-dark-800 z-10">
              <div className="flex items-center gap-2">
                <BrainCircuit className="w-5 h-5 text-accent-cyan" />
                <h3 className="text-sm font-bold text-white tracking-wider uppercase">BMAD Betting System Guide</h3>
              </div>
              <button onClick={() => setShowHelp(false)} className="text-muted hover:text-white transition-colors p-1">
                ✕
              </button>
            </div>
            
            {/* Content */}
            <div className="p-5 space-y-6 text-xs text-white/80 leading-relaxed">
              <div>
                <h4 className="text-white font-bold mb-2 uppercase tracking-wide text-xs">🧠 1. The 3-Gate Verification System</h4>
                <p className="text-muted mb-3">To minimize risk, every potential bet must clear three independent verification gates before receiving a <strong className="text-accent-green">BET</strong> recommendation:</p>
                <div className="space-y-3 pl-2">
                  <div className="border-l-2 border-accent-cyan pl-3">
                    <span className="text-accent-cyan font-bold block uppercase tracking-wider text-[0.6rem]">Gate 1: Edge Threshold (G1)</span>
                    We compare our ensemble model's fair probability against the bookmaker's implied odds. A bet must have at least a <strong className="text-white">3.2% edge</strong> to pass.
                  </div>
                  <div className="border-l-2 border-accent-yellow pl-3">
                    <span className="text-accent-yellow font-bold block uppercase tracking-wider text-[0.6rem]">Gate 2: Consensus Agreement (G2)</span>
                    Measures the deviation (disagreement) between our independent models (Opta, Dixon-Coles, xGscore, etc.). If standard deviation is <strong className="text-white">≤ 10%</strong>, the models agree and the gate passes.
                  </div>
                  <div className="border-l-2 border-accent-green pl-3">
                    <span className="text-accent-green font-bold block uppercase tracking-wider text-[0.6rem]">Gate 3: Historical ROI (G3)</span>
                    A dynamic self-correcting feedback loop. It checks similar wagers in your betting history. If those past bets have a negative net ROI, Gate 3 fails to prevent repeating losing patterns.
                  </div>
                </div>
              </div>

              <hr className="border-dark-600" />

              <div>
                <h4 className="text-white font-bold mb-2 uppercase tracking-wide text-xs">⚖️ 2. Triangulation Models</h4>
                <p className="text-muted mb-2">Rather than relying on one predictor, our engine synthesizes probabilities from 6 sources:</p>
                <ul className="list-disc pl-4 space-y-1 text-muted">
                  <li><strong className="text-white/90">Betfair Exchange</strong>: Midpoint price — true market probability.</li>
                  <li><strong className="text-white/90">Dataset 49K</strong>: Historical outcomes from a 49,000-match historical database.</li>
                  <li><strong className="text-white/90">Opta Analyst</strong>: Professional sports analytics and team statistics.</li>
                  <li><strong className="text-white/90">xGscore</strong>: Mathematical expected goals models.</li>
                  <li><strong className="text-white/90">Dixon-Coles</strong>: Bivariate Poisson process distribution models.</li>
                  <li><strong className="text-white/90">ENSEMBLE</strong>: The weighted mathematical average of all active models.</li>
                </ul>
              </div>

              <hr className="border-dark-600" />

              <div>
                <h4 className="text-white font-bold mb-2 uppercase tracking-wide text-xs">📈 3. Staking & Kelly Criterion</h4>
                <p className="text-muted mb-2">We apply the **Kelly Criterion** to calculate optimal bet sizing based on your edge size:</p>
                <div className="bg-dark-900 rounded p-3 font-mono text-center text-accent-cyan text-xs">
                  Fraction = (Edge / 100) / (Bookmaker Odds - 1) * 0.25 (Quarter-Kelly)
                </div>
                <p className="text-muted mt-2">
                  Using a <strong>Quarter-Kelly factor</strong> reduces volatility and safeguards your bankroll against variance. The final stake amount is capped at your **Max stake %** slider setting.
                </p>
              </div>
            </div>
            
            {/* Footer */}
            <div className="px-5 py-3.5 bg-dark-900/50 border-t border-dark-600 text-center">
              <button onClick={() => setShowHelp(false)} className="px-4 py-2 bg-accent-cyan/10 hover:bg-accent-cyan/20 border border-accent-cyan/30 rounded text-accent-cyan font-bold text-[0.65rem] tracking-wider uppercase transition-all">
                Understood
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── FAB — Floating Action Button (mobile only) ── */}
      <button
        onClick={() => { setBetFormMatch(null); setShowBetForm(true); }}
        className="fab-bet sm:hidden bg-accent-cyan/90 text-white border border-accent-cyan/50"
        aria-label="Log Bet"
      >
        <Plus className="w-6 h-6" />
      </button>

      {/* ---- Footer ---- */}
      <div className="mt-8 text-[0.45rem] sm:text-[0.55rem] text-muted text-center">
        Data refreshes every hour &middot; Last sync: {fmtLocal(lastUpdated)} <span className="opacity-50">({fmtLocalDate(lastUpdated)})</span>
      </div>
    </div>
  </div>
  );
}
