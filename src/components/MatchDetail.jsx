import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  AlertTriangle,
  TrendingUp,
  Info,
} from 'lucide-react';
import EdgeBadge from './EdgeBadge';
import TriangulationTable from './TriangulationTable';

/* ---------- helpers ---------- */
function edgeClass(edge) {
  if (edge > 20) return 'text-accent-green font-bold';
  if (edge >= 5) return 'text-green-400';
  if (edge >= -5) return 'text-muted';
  return 'text-accent-red';
}

function edgeStatusLabel(edge) {
  if (edge > 20) return { badge: '🚀', label: 'KELLY' };
  if (edge >= 5) return { badge: '✅', label: 'VALUE' };
  if (edge >= -5) return { badge: '⚪', label: 'PASS' };
  return { badge: '❌', label: 'AVOID' };
}

function fmtLocal(isoString) {
  return new Date(isoString).toLocaleTimeString('en-MY', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: true,
  });
}

export default function MatchDetail() {
  const { matchId } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [maxBankrollPct, setMaxBankrollPct] = useState(10);

  useEffect(() => {
    fetch('/data.json')
      .then((r) => r.json())
      .then((d) => setData(d))
      .catch(() => {});
  }, []);

  if (!data)
    return (
      <div className="flex items-center justify-center h-screen bg-dark-900">
        <div className="text-accent-cyan text-sm animate-pulse">
          LOADING...
        </div>
      </div>
    );

  const match = data.matches.find((m) => m.id === matchId);
  if (!match)
    return (
      <div className="flex items-center justify-center h-screen bg-dark-900">
        <div className="text-accent-red text-sm">MATCH NOT FOUND</div>
      </div>
    );

  const { analysis, home_team, away_team, date, venue, stage } = match;
  const bankroll = data.system_status.bankroll_rm;

  // best edge for the header badge
  const bestEdge =
    analysis.edge_summary?.length
      ? [...analysis.edge_summary].sort((a, b) => b.edge - a.edge)[0]
      : null;

  return (
    <div className="max-w-6xl mx-auto px-2 sm:px-4 py-4 sm:py-6 pb-20 sm:pb-6">
      {/* ---- Back + Header ---- */}
      <div className="mb-4 sm:mb-6">
        <button
          onClick={() => navigate('/')}
          className="flex items-center gap-1.5 text-muted hover:text-white text-xs mb-3 sm:mb-4 transition-colors mobile-touch"
        >
          <ArrowLeft className="w-3.5 h-3.5" /> BACK TO DASHBOARD
        </button>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <h1 className="text-lg sm:text-xl font-bold text-white tracking-tight">
              {home_team}{' '}
              <span className="text-muted mx-1 sm:mx-2">vs</span> {away_team}
            </h1>
            <div className="flex flex-wrap gap-x-3 gap-y-1 text-[0.6rem] text-muted mt-1">
              <span>{date}</span>
              {venue && (
                <>
                  <span className="hidden sm:inline">·</span>
                  <span className="truncate max-w-[200px]">{venue}</span>
                </>
              )}
              <span>·</span>
              <span className="text-accent-yellow">{stage}</span>
            </div>
          </div>
          <EdgeBadge edge={bestEdge?.edge ?? null} />
        </div>
      </div>

      {/* ---- 1. Asian Handicap Odds (Kau bet kat sini) ---- */}
      <div className="mb-4 sm:mb-6">
        <h2 className="section-header">1. 12SPORT MY — Asian Handicap Odds</h2>

        {/* AH odds — 2-column: home -0.5 | away +0.5 */}
        <div className="card mb-3">
          <div className="text-[0.55rem] sm:text-[0.6rem] text-accent-green mb-3 uppercase tracking-wider font-bold">
            ⚡ 12play.my — Your Betting Odds
          </div>
          <div className="grid grid-cols-2 gap-2 sm:gap-3 text-center">
            <div className="bg-dark-800 rounded-lg p-2.5 sm:p-3 border border-dark-600">
              <div className="text-[0.5rem] sm:text-[0.55rem] text-muted uppercase truncate mb-1">{home_team} -0.5</div>
              <div className="text-xl sm:text-2xl font-bold text-white num-mono">{match.home_odds?.toFixed(2)}</div>
              <div className="text-[0.45rem] sm:text-[0.5rem] text-muted mt-1">
                Implied: <span className="text-white/70">{match.home_odds ? ((1 / match.home_odds) * 100).toFixed(1) : '-'}%</span>
              </div>
            </div>
            <div className="bg-dark-800 rounded-lg p-2.5 sm:p-3 border border-dark-600">
              <div className="text-[0.5rem] sm:text-[0.55rem] text-muted uppercase truncate mb-1">{away_team} +0.5</div>
              <div className="text-xl sm:text-2xl font-bold text-white num-mono">{match.away_odds?.toFixed(2)}</div>
              <div className="text-[0.45rem] sm:text-[0.5rem] text-muted mt-1">
                Implied: <span className="text-white/70">{match.away_odds ? ((1 / match.away_odds) * 100).toFixed(1) : '-'}%</span>
              </div>
            </div>
          </div>
          <div className="mt-2 text-[0.5rem] sm:text-[0.55rem] text-muted text-center">
            Total implied: <span className="text-white/70">
              {match.home_odds && match.away_odds
                ? ((1/match.home_odds + 1/match.away_odds) * 100).toFixed(2)
                : '-'}%</span>
            · Vig: <span className="text-accent-yellow">
              {match.home_odds && match.away_odds
                ? ((1/match.home_odds + 1/match.away_odds - 1) * 100).toFixed(2)
                : '-'}%</span>
          </div>
        </div>

        {/* Edge Analysis — Now only AH + O/U markets */}
        <div className="card">
          <div className="text-[0.55rem] sm:text-[0.6rem] text-muted mb-3 uppercase tracking-wider">
            📊 Edge Analysis — AH &amp; O/U (12SPORT vs Polymarket)
          </div>
          <div className="overflow-x-auto scroll-hint">
            <table className="terminal-grid w-full min-w-[450px]">
              <thead>
                <tr>
                  <th className="text-left">Market</th>
                  <th className="text-right num-mono">12SPORT Implied</th>
                  <th className="text-right num-mono">Polymarket DV</th>
                  <th className="text-right num-mono">Edge %</th>
                  <th className="text-center">Call</th>
                </tr>
              </thead>
              <tbody>
                {analysis.edge_summary.map((e, i) => {
                  const edgePct = e.edge;

                  /* ---- Lookup Polymarket DV + back-calc 12SPORT implied ---- */
                  let twelvesportPct = null;
                  let polymarketPct = null;

                  // AH -0.5 / +0.5: from match.home_odds / match.away_odds + ah_analysis
                  if (e.market.includes('(AH)')) {
                    if (e.market.includes(home_team)) {
                      // Home -0.5: 12SPORT implied from odds, Poly from home_minus_05_prob
                      const ahAnalysis = analysis.ah_analysis || {};
                      twelvesportPct = match.home_odds ? (1 / match.home_odds) * 100 : null;
                      polymarketPct = ahAnalysis.home_minus_05_prob || null;
                    } else {
                      // Away +0.5
                      const ahAnalysis = analysis.ah_analysis || {};
                      twelvesportPct = match.away_odds ? (1 / match.away_odds) * 100 : null;
                      polymarketPct = ahAnalysis.away_plus_05_prob || null;
                    }
                  }

                  // O/U 2.5: triangulation_ou index 0 = Over, index 1 = Under
                  if (!polymarketPct && analysis.triangulation_ou?.polymarket) {
                    if (e.market.startsWith('O ')) {
                      polymarketPct = analysis.triangulation_ou.polymarket[0];
                    } else if (e.market.startsWith('U ')) {
                      polymarketPct = analysis.triangulation_ou.polymarket[1];
                    }
                  }

                  // Back-calculate 12SPORT implied from edge & Polymarket DV
                  if (twelvesportPct === null && polymarketPct !== null && edgePct !== 0) {
                    twelvesportPct = polymarketPct / (1 + edgePct / 100);
                  }
                  if (polymarketPct === null && twelvesportPct !== null && edgePct !== 0) {
                    polymarketPct = twelvesportPct * (1 + edgePct / 100);
                  }

                  const twelvesportDecimal = twelvesportPct !== null ? (100 / twelvesportPct) : null;

                  let cls, callLabel, callBadge;
                  if (edgePct > 20) {
                    cls = 'text-accent-green font-bold'; callLabel = '🚀 KELLY';
                    callBadge = 'edge-positive-pulse inline-block px-2 py-0.5 rounded text-[0.5rem] font-bold bg-accent-green/20 text-accent-green';
                  } else if (edgePct >= 5) {
                    cls = 'text-green-400'; callLabel = '✅ VALUE';
                    callBadge = 'inline-block px-2 py-0.5 rounded text-[0.5rem] font-bold bg-green-500/15 text-green-400';
                  } else if (edgePct >= -5) {
                    cls = 'text-muted'; callLabel = '⚪ PASS';
                    callBadge = 'inline-block px-2 py-0.5 rounded text-[0.5rem] font-bold bg-accent-gray/15 text-muted';
                  } else {
                    cls = 'text-accent-red'; callLabel = '❌ AVOID';
                    callBadge = 'inline-block px-2 py-0.5 rounded text-[0.5rem] font-bold bg-accent-red/15 text-accent-red';
                  }

                  return (
                    <tr key={i}>
                      <td className="text-left text-xs text-white/80">{e.market}</td>
                      <td className="text-right num-mono text-white/70">
                        {twelvesportPct !== null
                          ? <>{twelvesportPct.toFixed(1)}%<br /><span className="text-[0.5rem] text-muted">{twelvesportDecimal.toFixed(2)}</span></>
                          : '-'}
                      </td>
                      <td className="text-right num-mono text-accent-cyan">
                        {polymarketPct !== null ? polymarketPct.toFixed(1) + '%' : '-'}
                      </td>
                      <td className={`text-right num-mono ${cls}`}>
                        {edgePct > 0 ? '+' : ''}{edgePct.toFixed(1)}%
                      </td>
                      <td className="text-center">
                        <span className={callBadge}>{callLabel}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="mt-2 text-[0.55rem] text-muted text-center">
            Polymarket = zero-vig crowd consensus &middot; 12SPORT = real odds you bet at 12play.my
          </div>
        </div>
      </div>

      {/* ---- 2. System Decision Matrix (Gate 1-2-3) ---- */}
      <div className="mb-4 sm:mb-6">
        <h2 className="section-header">2. System Decision — 3-Gate Filter</h2>
        <div className="card">
          <div className="overflow-x-auto scroll-hint">
            <table className="terminal-grid w-full min-w-[400px]">
              <thead>
                <tr>
                  <th className="text-left">Market</th>
                  <th className="text-right num-mono">Edge %</th>
                  <th className="text-center num-mono">G1 Threshold</th>
                  <th className="text-center num-mono">G2 Consensus</th>
                  <th className="text-center num-mono">G3 History</th>
                  <th className="text-center">Decision</th>
                  <th className="text-right num-mono">Kelly</th>
                </tr>
              </thead>
              <tbody>
                {analysis.edge_summary.map((e, i) => {
                  // Re-run gates inline
                  const edge = e.edge;
                  const g1 = edge >= 3.2;
                  const hasTri = analysis.triangulation_1x2 || analysis.triangulation_ou || analysis.triangulation_btts;
                  const g2 = null; // simplified for detail view
                  const g3 = null;

                  let dBadge, dColor;
                  if (!g1) {
                    dBadge = 'SKIP'; dColor = 'bg-accent-red/15 text-accent-red border-accent-red/30';
                  } else {
                    dBadge = 'BET'; dColor = 'edge-positive-pulse bg-accent-green/20 text-accent-green border-accent-green/40';
                  }

                  return (
                    <tr key={i}>
                      <td className="text-left text-xs text-white/80">{e.market}</td>
                      <td className={`text-right num-mono text-xs ${edge > 20 ? 'text-accent-green font-bold' : edge >= 5 ? 'text-green-400' : edge >= -5 ? 'text-muted' : 'text-accent-red'}`}>
                        {edge > 0 ? '+' : ''}{edge.toFixed(1)}%
                      </td>
                      <td className={`text-center text-xs ${g1 ? 'text-accent-green' : 'text-accent-red'}`}>{g1 ? '✅' : '❌'}</td>
                      <td className={`text-center text-xs ${g2 === true ? 'text-accent-green' : g2 === false ? 'text-accent-red' : 'text-muted'}`}>
                        {g2 === true ? '✅' : g2 === false ? '❌' : '·'}
                      </td>
                      <td className={`text-center text-xs ${g3 === true ? 'text-accent-green' : g3 === false ? 'text-accent-red' : 'text-muted'}`}>
                        {g3 === true ? '✅' : g3 === false ? '❌' : '·'}
                      </td>
                      <td className="text-center">
                        <span className={`inline-block px-2 py-0.5 rounded text-[0.5rem] font-bold border ${dColor}`}>
                          {dBadge}
                        </span>
                      </td>
                      <td className={`text-right num-mono text-xs ${e.quarter_kelly_stake > 0 ? 'text-accent-green' : 'text-muted'}`}>
                        {e.quarter_kelly_stake > 0 ? `${e.quarter_kelly_stake.toFixed(2)}%` : '-'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="mt-2 text-[0.55rem] text-muted text-center">
            G1 = Edge &ge; 3.2% &nbsp;·&nbsp; G2 = Model std dev &lt; 10pp &nbsp;·&nbsp; G3 = Historical pattern ROI &gt; 0
            &nbsp;·&nbsp; · = insufficient data
          </div>
        </div>
      </div>

      {/* ---- 3-4. Triangulation Tables ---- */}
      <div className="mb-4 sm:mb-6">
        <h2 className="section-header">3-4. Triangulation Tables — AH (DNB) &amp; O/U</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 sm:gap-3">
          <TriangulationTable
            title="AH 0 (Draw No Bet)"
            sources={analysis.triangulation_ah}
            headers={[`${home_team} (DNB)`, `${away_team} (DNB)`]}
            decimals={1}
          />
          <TriangulationTable
            title="O/U 2.5 Total Goals"
            sources={analysis.triangulation_ou}
            headers={['Over 2.5', 'Under 2.5']}
            decimals={1}
          />
        </div>
      </div>

      {/* ---- 5. Narrative ---- */}
      <div className="mb-4 sm:mb-6">
        <h2 className="section-header">5. Narrative &amp; Key Factors</h2>
        <div className="card space-y-3">
          {analysis.narrative?.form && (
            <div className="flex gap-3">
              <TrendingUp className="w-4 h-4 text-accent-cyan shrink-0 mt-0.5" />
              <div>
                <div className="text-[0.6rem] text-muted uppercase tracking-wider mb-0.5">
                  Form
                </div>
                <div className="text-xs text-white/80">
                  {analysis.narrative.form}
                </div>
              </div>
            </div>
          )}
          {analysis.narrative?.injuries && (
            <div className="flex gap-3">
              <AlertTriangle className="w-4 h-4 text-accent-yellow shrink-0 mt-0.5" />
              <div>
                <div className="text-[0.6rem] text-muted uppercase tracking-wider mb-0.5">
                  Injuries
                </div>
                <div className="text-xs text-white/80">
                  {analysis.narrative.injuries}
                </div>
              </div>
            </div>
          )}
          {analysis.narrative?.tactical && (
            <div className="flex gap-3">
              <Info className="w-4 h-4 text-accent-green shrink-0 mt-0.5" />
              <div>
                <div className="text-[0.6rem] text-muted uppercase tracking-wider mb-0.5">
                  Tactical
                </div>
                <div className="text-xs text-white/80">
                  {analysis.narrative.tactical}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ---- 6. Edge Summary & Staking ---- */}
      <div className="mb-4 sm:mb-6">
        <h2 className="section-header">
         6. Edge Summary &amp; Staking
        </h2>
        <div className="card overflow-x-auto scroll-hint">
          <table className="terminal-grid w-full min-w-[500px]">
            <thead>
              <tr>
                <th className="text-left">Market</th>
                <th className="text-right num-mono">Edge %</th>
                <th className="text-center">Status</th>
                <th className="text-right num-mono">Q-Kelly Stake</th>
                <th className="text-right num-mono">Amount (RM)</th>
              </tr>
            </thead>
            <tbody>
              {analysis.edge_summary.map((e, i) => {
                const stakeAmount =
                  bankroll *
                  (maxBankrollPct / 100) *
                  (e.quarter_kelly_stake / 100);
                const stakePct = e.quarter_kelly_stake;
                const sl = edgeStatusLabel(e.edge);
                return (
                  <tr key={i}>
                    <td className="text-left text-xs text-white/80">
                      {e.market}
                    </td>
                    {/* Edge % — coloured by classification */}
                    <td
                      className={`text-right num-mono ${edgeClass(e.edge)}`}
                    >
                      {e.edge > 0 ? '+' : ''}
                      {e.edge.toFixed(1)}%
                    </td>
                    {/* Status badge — computed from edge */}
                    <td className="text-center">
                      {e.edge > 20 && (
                        <span className="edge-positive-pulse inline-block px-2 py-0.5 rounded text-[0.55rem] font-bold bg-accent-green/20 text-accent-green">
                          KELLY
                        </span>
                      )}
                      {e.edge >= 5 && e.edge <= 20 && (
                        <span className="inline-block px-2 py-0.5 rounded text-[0.55rem] font-bold bg-green-500/15 text-green-400">
                          VALUE
                        </span>
                      )}
                      {e.edge >= -5 && e.edge < 5 && (
                        <span className="inline-block px-2 py-0.5 rounded text-[0.55rem] font-bold bg-accent-gray/15 text-muted">
                          PASS
                        </span>
                      )}
                      {e.edge < -5 && (
                        <span className="inline-block px-2 py-0.5 rounded text-[0.55rem] font-bold bg-accent-red/15 text-accent-red">
                          AVOID
                        </span>
                      )}
                    </td>
                    <td className="text-right num-mono text-white/80">
                      {stakePct > 0
                        ? `${stakePct.toFixed(2)}%`
                        : '-'}
                    </td>
                    <td
                      className={`text-right num-mono font-bold ${stakeAmount > 0 ? 'text-accent-green' : 'text-muted'}`}
                    >
                      {stakeAmount > 0
                        ? `RM${stakeAmount.toFixed(2)}`
                        : '-'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-[0.5rem] sm:text-[0.55rem] text-muted">
            <span>
              Max stake per bet: {maxBankrollPct}% of RM{bankroll} = RM
              {(bankroll * (maxBankrollPct / 100)).toFixed(2)}
            </span>
            <div className="flex items-center gap-1.5 sm:gap-2">
              <span className="hidden xs:inline">Max %</span>
              <input
                type="range"
                min={5}
                max={25}
                value={maxBankrollPct}
                onChange={(e) =>
                  setMaxBankrollPct(parseInt(e.target.value))
                }
                className="w-16 sm:w-20 h-1.5 bg-dark-600 rounded-full appearance-none cursor-pointer accent-accent-cyan"
              />
              <span className="text-white num-mono w-5 text-center">
                {maxBankrollPct}%
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* ---- Footer ---- */}
      <div className="text-[0.55rem] text-muted text-center">
        Match ID: {match.id} &middot; Cron data &middot; 6-Layer Ensemble
        &middot; {fmtLocal(data.system_status.last_updated)}
      </div>
    </div>
  );
}
