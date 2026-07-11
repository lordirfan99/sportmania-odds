/**
 * EdgeBadge — computes classification from edge % value.
 * Ignores the `status` prop from JSON; uses hard mathematical rules:
 *
 *   edge > 20  → 🚀 KELLY STAKE  (neon green pulse)
 *   edge >= 5  → ✅ VALUE         (solid green)
 *   edge >= -5 → ⚪ NEUTRAL       (muted gray)
 *   edge < -5  → ❌ AVOID         (red)
 */
export default function EdgeBadge({ edge }) {
  // --- compute classification from edge value ---
  const numericEdge =
    edge !== undefined && edge !== null ? Number(edge) : null;

  let status, label, className;

  if (numericEdge === null) {
    status = '⚪';
    label = 'N/A';
    className =
      'bg-accent-gray/15 text-muted border-accent-gray/30';
  } else if (numericEdge > 20) {
    status = '🚀';
    label = 'KELLY STAKE';
    className =
      'bg-accent-green/20 text-accent-green border-accent-green/40 edge-positive-pulse';
  } else if (numericEdge >= 5) {
    status = '✅';
    label = 'VALUE';
    className =
      'bg-green-500/15 text-green-400 border-green-500/30';
  } else if (numericEdge >= -5) {
    status = '⚪';
    label = 'NEUTRAL';
    className =
      'bg-accent-gray/15 text-muted border-accent-gray/30';
  } else {
    status = '❌';
    label = 'AVOID';
    className =
      'bg-accent-red/15 text-accent-red border-accent-red/30';
  }

  const edgeText =
    numericEdge !== null
      ? `${numericEdge > 0 ? '+' : ''}${numericEdge.toFixed(1)}%`
      : '';

  return (
    <div
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-[0.6rem] font-bold tracking-wider border ${className}`}
    >
      <span>{status}</span>
      <span>{label}</span>
      {edgeText && <span className="num-mono opacity-70">{edgeText}</span>}
    </div>
  );
}
