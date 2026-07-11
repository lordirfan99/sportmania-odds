import { useState } from 'react';
import { X, Send } from 'lucide-react';
import { addBet } from '../lib/betStore';

export default function BetLogForm({ match, onClose, onLogged }) {
  const [form, setForm] = useState({
    home_team: match?.home_team || '',
    away_team: match?.away_team || '',
    market: '',
    odds_decimal: '',
    stake_rm: '',
    predicted_edge: '',
    notes: '',
  });
  const [saving, setSaving] = useState(false);

  // If match is provided, suggest markets from edge_summary
  const suggestedMarkets = match?.analysis?.edge_summary
    ? match.analysis.edge_summary.map((e) => e.market)
    : [];

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!form.market || !form.odds_decimal || !form.stake_rm) return;

    setSaving(true);
    const bet = addBet({
      match_id: match?.id || '',
      home_team: form.home_team,
      away_team: form.away_team,
      market: form.market,
      odds_decimal: parseFloat(form.odds_decimal),
      stake_rm: parseFloat(form.stake_rm),
      predicted_edge: form.predicted_edge ? parseFloat(form.predicted_edge) : null,
      notes: form.notes,
    });

    setSaving(false);
    onLogged?.(bet);
    onClose?.();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60 backdrop-blur-sm px-0 sm:px-3"
      onClick={(e) => { if (e.target === e.currentTarget) onClose?.(); }}>
      <div className="w-full sm:max-w-md bg-dark-800 border border-dark-500 rounded-t-2xl sm:rounded-xl shadow-2xl max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between px-4 sm:px-5 py-3.5 sm:py-4 border-b border-dark-600 sticky top-0 bg-dark-800 z-10">
          <div className="flex items-center gap-2">
            <div className="w-8 h-1 rounded-full bg-dark-500 sm:hidden mx-auto absolute left-1/2 -translate-x-1/2 top-1.5" />
            <h3 className="text-sm font-bold text-white tracking-wider uppercase">Log Bet</h3>
          </div>
          <button onClick={onClose} className="text-muted hover:text-white transition-colors p-1 mobile-touch">
            <X className="w-4 h-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-4 sm:p-5 space-y-3 sm:space-y-4">
          {/* Teams */}
          <div className="grid grid-cols-2 gap-2 sm:gap-3">
            <div>
              <label className="text-[0.5rem] sm:text-[0.55rem] text-muted uppercase tracking-wider block mb-1">Home</label>
              <input
                value={form.home_team}
                onChange={(e) => setForm({ ...form, home_team: e.target.value })}
                className="w-full bg-dark-900 border border-dark-500 rounded px-3 py-2.5 sm:py-2 text-xs sm:text-xs text-white num-mono focus:border-accent-cyan outline-none mobile-touch"
                placeholder="e.g. England"
              />
            </div>
            <div>
              <label className="text-[0.5rem] sm:text-[0.55rem] text-muted uppercase tracking-wider block mb-1">Away</label>
              <input
                value={form.away_team}
                onChange={(e) => setForm({ ...form, away_team: e.target.value })}
                className="w-full bg-dark-900 border border-dark-500 rounded px-3 py-2.5 sm:py-2 text-xs sm:text-xs text-white num-mono focus:border-accent-cyan outline-none mobile-touch"
                placeholder="e.g. Norway"
              />
            </div>
          </div>

          {/* Market — Dropdown with AH + O/U */}
          <div>
            <label className="text-[0.5rem] sm:text-[0.55rem] text-muted uppercase tracking-wider block mb-1">Market</label>
            <select
              value={form.market}
              onChange={(e) => setForm({ ...form, market: e.target.value })}
              className="w-full bg-dark-900 border border-dark-500 rounded px-3 py-2.5 sm:py-2 text-xs text-white num-mono focus:border-accent-cyan outline-none appearance-none cursor-pointer mobile-touch"
            >
              <option value="" disabled>— Select market —</option>
              {suggestedMarkets.length > 0 ? (
                suggestedMarkets.map((m) => (
                  <option key={m} value={m} className="bg-dark-800 text-white">{m}</option>
                ))
              ) : (
                <>
                  <option value="" disabled className="bg-dark-800 text-muted">No suggestions — type below</option>
                  <option value="" className="bg-dark-800 text-muted">──────────</option>
                </>
              )}
              <option value="" disabled className="bg-dark-800 text-muted">──────────</option>
              <option value="O 2.5" className="bg-dark-800 text-white">O 2.5</option>
              <option value="U 2.5" className="bg-dark-800 text-white">U 2.5</option>
              <option value="Home -0.5 (AH)" className="bg-dark-800 text-white">Home -0.5 (AH)</option>
              <option value="Away +0.5 (AH)" className="bg-dark-800 text-white">Away +0.5 (AH)</option>
            </select>
          </div>

          {/* Odds + Stake */}
          <div className="grid grid-cols-2 gap-2 sm:gap-3">
            <div>
              <label className="text-[0.5rem] sm:text-[0.55rem] text-muted uppercase tracking-wider block mb-1">
                Odds
              </label>
              <input
                type="number"
                step="0.01"
                min="1.01"
                value={form.odds_decimal}
                onChange={(e) => setForm({ ...form, odds_decimal: e.target.value })}
                className="w-full bg-dark-900 border border-dark-500 rounded px-3 py-2.5 sm:py-2 text-xs text-white num-mono focus:border-accent-cyan outline-none mobile-touch"
                placeholder="1.84"
              />
            </div>
            <div>
              <label className="text-[0.5rem] sm:text-[0.55rem] text-muted uppercase tracking-wider block mb-1">
                Stake (RM)
              </label>
              <input
                type="number"
                step="0.50"
                min="1"
                value={form.stake_rm}
                onChange={(e) => setForm({ ...form, stake_rm: e.target.value })}
                className="w-full bg-dark-900 border border-dark-500 rounded px-3 py-2.5 sm:py-2 text-xs text-white num-mono focus:border-accent-cyan outline-none mobile-touch"
                placeholder="5.00"
              />
            </div>
          </div>

          {/* Edge (optional) */}
          <div>
            <label className="text-[0.5rem] sm:text-[0.55rem] text-muted uppercase tracking-wider block mb-1">
              Edge % <span className="text-muted/50">(optional)</span>
            </label>
            <input
              type="number"
              step="0.1"
              value={form.predicted_edge}
              onChange={(e) => setForm({ ...form, predicted_edge: e.target.value })}
              className="w-full bg-dark-900 border border-dark-500 rounded px-3 py-2.5 sm:py-2 text-xs text-white num-mono focus:border-accent-cyan outline-none mobile-touch"
              placeholder="-4.1"
            />
          </div>

          {/* Notes */}
          <div>
            <label className="text-[0.5rem] sm:text-[0.55rem] text-muted uppercase tracking-wider block mb-1">
              Notes <span className="text-muted/50">(optional)</span>
            </label>
            <input
              value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
              className="w-full bg-dark-900 border border-dark-500 rounded px-3 py-2.5 sm:py-2 text-xs text-white focus:border-accent-cyan outline-none mobile-touch"
              placeholder="Manual bet via 12play"
            />
          </div>

          {/* Potential Win Preview */}
          {form.odds_decimal && form.stake_rm && (
            <div className="bg-dark-900 rounded px-3 py-2 text-[0.6rem] text-muted flex justify-between">
              <span>Potential Win:</span>
              <span className="text-accent-green font-bold num-mono">
                RM{(parseFloat(form.odds_decimal) * parseFloat(form.stake_rm)).toFixed(2)}
              </span>
            </div>
          )}

          {/* Submit */}
          <button
            type="submit"
            disabled={saving || !form.market || !form.odds_decimal || !form.stake_rm}
            className="w-full flex items-center justify-center gap-2 py-3 sm:py-2.5 rounded-lg text-xs font-bold tracking-wider uppercase bg-accent-cyan/20 text-accent-cyan border border-accent-cyan/30 hover:bg-accent-cyan/30 disabled:opacity-40 disabled:cursor-not-allowed transition-all mobile-touch"
          >
            <Send className="w-3.5 h-3.5" />
            {saving ? 'Logging...' : 'Log Bet'}
          </button>
        </form>
      </div>
    </div>
  );
}
