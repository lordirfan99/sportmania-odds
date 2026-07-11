export default function TriangulationTable({ title, sources, headers, decimals = 1 }) {
  const colorMap = {
    'polymarket': 'text-accent-cyan',
    'dataset': 'text-blue-400',
    'opta': 'text-purple-400',
    'xgscore': 'text-accent-yellow',
    'dixon_coles': 'text-orange-400',
    'ensemble': 'text-white font-bold',
  };
  const labelMap = {
    'polymarket': 'Polymarket',
    'dataset': 'Dataset 49K',
    'opta': 'Opta Analyst',
    'xgscore': 'xGscore',
    'dixon_coles': 'Dixon-Coles',
    'ensemble': 'ENSEMBLE',
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
