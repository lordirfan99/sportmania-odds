export default function TriangulationTable({ title, sources, headers, decimals = 1 }) {
  const colorMap = {
    'market_devig': 'text-accent-cyan',
    'dixon_coles':  'text-accent-yellow',
    'pinnacle':     'text-purple-400',
    'polymarket':   'text-green-400',
    'dataset':      'text-blue-400',    // legacy fallback
    'opta':         'text-purple-400',  // legacy fallback
    'xgscore':      'text-accent-yellow', // legacy fallback
    'ensemble':     'text-white font-bold',
  };
  const labelMap = {
    'market_devig': '1xBet Devigged',
    'dixon_coles':  'Dixon-Coles (Poisson)',
    'pinnacle':     'Pinnacle (Sharp)',
    'polymarket':   'Polymarket',
    'dataset':      'Dataset 49K',
    'opta':         'Opta Analyst',
    'xgscore':      'xGscore',
    'ensemble':     'ENSEMBLE',
  };

  return (
    <div className="card">
      <div className="section-header">{title}</div>
      <table className="terminal-grid w-full">
        <thead>
          <tr>
            <th className="text-left">Source</th>
            {headers.map(h => <th key={h} className="text-right num-mono">{h}</th>)}
          </tr>
        </thead>
        <tbody>
          {Object.entries(sources).map(([key, vals]) => (
            <tr key={key}>
              <td className={`text-left text-xs ${colorMap[key] || 'text-muted'}`}>
                {labelMap[key] || key}
              </td>
              {vals.map((v, i) => (
                <td key={i} className={`text-right num-mono ${colorMap[key] || 'text-white/90'}`}>
                  {v.toFixed(decimals)}%
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
