import { useApi } from '../hooks/useApi';
import { api } from '../lib/api';

const DIRECTION_STYLES: Record<string, { text: string; bg: string; border: string }> = {
  LONG: { text: 'text-gain', bg: 'bg-gain-dim', border: 'border-gain/30' },
  SHORT: { text: 'text-loss', bg: 'bg-loss-dim', border: 'border-loss/30' },
  FLAT: { text: 'text-amber', bg: 'bg-amber-dim', border: 'border-amber/30' },
};

function confidenceStyle(pct: number) {
  if (pct >= 70) return 'text-cyan border-cyan/30 bg-cyan/10';
  if (pct >= 50) return 'text-amber border-amber/30 bg-amber-dim';
  return 'text-muted border-border bg-panel';
}

export function SignalFeed() {
  const { data, loading } = useApi(() => api.strategies.mlSignals());
  const signals: any[] = data?.signals ?? [];

  return (
    <div className="space-y-3">
      <h3 className="font-mono text-[10px] uppercase tracking-wider text-muted">ML Signal Feed</h3>
      {loading ? (
        <div className="py-6 text-center font-mono text-xs text-muted">Loading signals...</div>
      ) : signals.length === 0 ? (
        <div className="py-6 text-center font-mono text-xs text-muted">No signals available</div>
      ) : (
        <div className="space-y-2">
          {signals.map((s: any, i: number) => {
            const dir = DIRECTION_STYLES[s.direction] ?? DIRECTION_STYLES.FLAT;
            const pct = Math.round(s.confidence * 100);
            return (
              <div
                key={`${s.symbol}-${i}`}
                className="flex items-center gap-3 rounded-lg border border-border bg-panel px-3 py-2"
              >
                <span className="font-mono text-sm font-semibold text-bright w-16">{s.symbol}</span>
                <span className={`rounded border px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider ${dir.text} ${dir.bg} ${dir.border}`}>
                  {s.direction}
                </span>
                <span className={`rounded border px-1.5 py-0.5 font-mono text-[9px] tracking-wider ${confidenceStyle(pct)}`}>
                  {pct}%
                </span>
                <span className="font-mono text-[10px] text-dim flex-1 truncate">{s.strategy}</span>
                <span className="font-mono text-[10px] text-muted shrink-0">{s.timestamp}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
