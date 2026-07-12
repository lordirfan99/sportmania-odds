import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import EdgeBadge from './EdgeBadge';
import { evaluateMarket } from '../lib/simulator';

/* ---------- helpers ---------- */
function edgeClass(edge) {
  if (edge > 20) return 'text-accent-green font-bold';
  if (edge >= 5) return 'text-green-400';
  if (edge >= -5) return 'text-muted';
  return 'text-accent-red';
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

  const match = data.matches.find((m) => (m.match_id || m.id) === matchId);
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
        <h2 className="section-header">1. 1xBet Malaysia — Asian Handicap Odds</h2>

        {/* AH odds — 2-column: home -0.5 | away +0.5 */}
        <div className="card mb-3">
          <div className="text-[0.55rem] sm:text-[0.6rem] text-accent-green mb-3 uppercase tracking-wider font-bold">⚡ 1xBet Malaysia — Best Odds</div>
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
            · Bookmaker vig: <span className="text-accent-yellow">
              {match.home_odds && match.away_odds
                ? ((1/match.home_odds + 1/match.away_odds - 1) * 100).toFixed(2)
                : '-'}%</span>
            <span className="ml-1 opacity-50">(bookie edge; 0% = fair odds)</span>
          </div>
        </div>

        {/* Edge Analysis — Now only AH + O/U markets */}
        <div className="card">
          <div className="text-[0.55rem] sm:text-[0.6rem] text-muted mb-3 uppercase tracking-wider">
            📊 Edge Analysis — AH &amp; O/U (1xBet vs Betfair)
          </div>
          <div className="overflow-x-auto -mx-2 px-2">
            <div className="grid grid-cols-[1fr_auto_auto_auto_auto] gap-x-2 gap-y-2 text-[0.55rem] min-w-[300px]">
              <div className="text-muted text-left text-[0.5rem] font-bold uppercase">Market</div>
              <div className="text-right text-accent-cyan font-bold text-[0.5rem] uppercase">1xBet</div>
              <div className="text-right text-purple-400 font-bold text-[0.5rem] uppercase">Betfair</div>
              <div className="text-right font-bold text-[0.5rem] uppercase text-muted">Edge</div>
              <div className="text-center font-bold text-[0.5rem] uppercase text-muted">Call</div>
              {analysis.edge_summary.map((e, i) => {
                const label = (e.market || '').replace(/\s*\(1xBet vs (Betfair)\)/, '');
                const xb = e.xbet_price;
                const bf = e.betfair_price;
                const edgePct = e.edge || 0;
                let ec, callLabel, callBadge;
                if (edgePct > 20) {
                  ec = 'text-accent-green font-bold'; callLabel = '🚀 KELLY';
                  callBadge = 'edge-positive-pulse inline-block px-1.5 py-0.5 rounded text-[0.5rem] font-bold bg-accent-green/20 text-accent-green';
                } else if (edgePct >= 5) {
                  ec = 'text-green-400'; callLabel = '✅ VALUE';
                  callBadge = 'inline-block px-1.5 py-0.5 rounded text-[0.5rem] font-bold bg-green-500/15 text-green-400';
                } else if (edgePct >= -5) {
                  ec = 'text-muted'; callLabel = '⚪ PASS';
                  callBadge = 'inline-block px-1.5 py-0.5 rounded text-[0.5rem] font-bold bg-accent-gray/15 text-muted';
                } else {
                  ec = 'text-accent-red'; callLabel = '❌ AVOID';
                  callBadge = 'inline-block px-1.5 py-0.5 rounded text-[0.5rem] font-bold bg-accent-red/15 text-accent-red';
                }
                return (
                  <div key={i} className="contents">
                    <div className="text-white/80 truncate text-left">{label}</div>
                    <div className="text-right text-accent-cyan num-mono">{xb ? xb.toFixed(2) : '-'}</div>
                    <div className="text-right text-purple-400 num-mono">{bf ? bf.toFixed(2) : '-'}</div>
                    <div className={`text-right num-mono ${ec}`}>{edgePct > 0 ? '+' : ''}{edgePct.toFixed(1)}%</div>
                    <div className="text-center"><span className={callBadge}>{callLabel}</span></div>
                  </div>
                );
              })}
            </div>
          </div>
          <div className="mt-2 text-[0.55rem] text-muted text-center">
            Betfair Exchange = back/lay midpoint (true price) · 1xBet = odds you bet
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
                  // Run full 3-gate evaluation via simulator
                  const eval_ = evaluateMarket(e, home_team, away_team, analysis, data.bet_history || []);
                  const { gates, consensus, historical, decision, reason } = eval_;
                  const g1 = gates.gate1;
                  const g2 = gates.gate2;
                  const g3 = gates.gate3;

                  let dBadge, dColor;
                  if (decision === 'BET') {
                    dBadge = 'BET'; dColor = 'edge-positive-pulse bg-accent-green/20 text-accent-green border-accent-green/40';
                  } else {
                    dBadge = 'SKIP'; dColor = 'bg-accent-red/15 text-accent-red border-accent-red/30';
                  }

                  const gateCell = (val, tooltip) => (
                    <td title={tooltip || ''} className={`text-center text-xs cursor-help ${
                      val === true ? 'text-accent-green' : val === false ? 'text-accent-red' : 'text-muted'
                    }`}>
                      {val === true ? '✅' : val === false ? '❌' : <span className="opacity-40">·</span>}
                    </td>
                  );

                  const g2Tip = consensus
                    ? `Model σ = ${consensus.stdDevPct.toFixed(1)}pp across ${consensus.models} models (limit: 10pp)`
                    : 'No triangulation data for this market';
                  const g3Tip = historical
                    ? `Historical ROI: ${historical.roi.toFixed(1)}% from ${historical.total} similar bets`
                    : 'Not enough historical bets yet (need ≥3 similar)';

                  return (
                    <tr key={i}>
                      <td className="text-left text-xs text-white/80">{e.market}</td>
                      <td className={`text-right num-mono text-xs ${e.edge > 20 ? 'text-accent-green font-bold' : e.edge >= 5 ? 'text-green-400' : e.edge >= -5 ? 'text-muted' : 'text-accent-red'}`}>
                        {e.edge > 0 ? '+' : ''}{e.edge.toFixed(1)}%
                      </td>
                      {gateCell(g1, `Edge ${e.edge.toFixed(1)}% vs threshold 3.2%`)}
                      {gateCell(g2, g2Tip)}
                      {gateCell(g3, g3Tip)}
                      <td className="text-center">
                        <span className={`inline-block px-2 py-0.5 rounded text-[0.5rem] font-bold border ${dColor}`}
                          title={reason || ''}>
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
            G1 = Edge ≥ 3.2% &nbsp;·&nbsp; G2 = Model σ &lt; 10pp (hover for value) &nbsp;·&nbsp; G3 = Historical ROI &gt; 0% &nbsp;·&nbsp; <span className="opacity-60">· = insufficient data</span>
          </div>
        </div>
      </div>

      {/* ---- 5. Key Market Data ---- */}
      {analysis.sport_raw?.home > 0 && (
        <div className="mb-4 sm:mb-6">
          <h2 className="section-header">5. Key Market Data</h2>
          <div className="card">
            <div className="text-[0.55rem] text-muted space-y-1">
              <div className="flex justify-between">
                <span>Home (AH -0.5):</span>
                <span className="text-accent-cyan font-bold">{analysis.sport_raw.home.toFixed(3)}</span>
              </div>
              {analysis.sport_raw.draw && (
                <div className="flex justify-between">
                  <span>Draw:</span>
                  <span className="text-accent-cyan font-bold">{analysis.sport_raw.draw.toFixed(3)}</span>
                </div>
              )}
              <div className="flex justify-between">
                <span>Away (AH +0.5):</span>
                <span className="text-accent-cyan font-bold">{analysis.sport_raw.away.toFixed(3)}</span>
              </div>
              {analysis.sport_raw.over_odds && (
                <div className="flex justify-between">
                  <span>Over {analysis.sport_raw.ou_point || 2.5}:</span>
                  <span className="text-accent-cyan font-bold">{analysis.sport_raw.over_odds.toFixed(3)}</span>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

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
                const rawKelly = e.quarter_kelly_stake;
                const cappedKelly = Math.min(rawKelly, maxBankrollPct);
                const stakeAmount = bankroll * (cappedKelly / 100);
                const stakePct = rawKelly;
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
