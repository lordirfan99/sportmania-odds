export default function TriangulationTable({ title, sources, headers, decimals = 1 }) {
  const colorMap = {
    'market_devig': 'text-accent-cyan',
    'dixon_coles':  'text-accent-yellow',
    'betfair':      'text-purple-400',
    'dataset':      'text-blue-400',
    'opta':         'text-purple-400',
    'xgscore':      'text-accent-yellow',
    'ensemble':     'text-white font-bold',
  };
  const labelMap = {
    'market_devig': '1xBet Devigged',
    'dixon_coles':  'Dixon-Coles (Poisson)',
    'betfair':      'Betfair Exchange',
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
          {sources ? Object.entries(sources).map(([key, vals]) => (
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
          )) : (
            <tr>
              <td colSpan={headers.length + 1} className="text-center text-muted text-xs py-3">
                No data available
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
