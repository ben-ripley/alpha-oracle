import {
  ShieldAlert, AlertTriangle, CheckCircle2, XCircle,
  Gauge, Timer, Zap,
} from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import { StatCard } from '../components/StatCard';
import { formatPct } from '../lib/format';

// Demo data
const DD_HISTORY = Array.from({ length: 60 }, (_, i) => ({
  date: new Date(Date.now() - (59 - i) * 86400000).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
  drawdown: -(Math.abs(Math.sin(i / 8) * 6 + Math.random() * 2)),
}));

const LIMITS = [
  { label: 'Drawdown', current: 4.2, max: 10, unit: '%' },
  { label: 'Daily Loss', current: 0.8, max: 3, unit: '%' },
  { label: 'Positions', current: 5, max: 20, unit: '' },
  { label: 'Daily Trades', current: 3, max: 50, unit: '' },
  { label: 'Cash Reserve', current: 41.1, max: 10, unit: '%', inverted: true },
];

const BREAKERS = [
  { name: 'VIX Threshold', tripped: false, detail: 'VIX: 18.4 (limit: 35.0)' },
  { name: 'Stale Data', tripped: false, detail: 'Last update: 12s ago' },
  { name: 'Drawdown', tripped: false, detail: '4.2% (limit: 10.0%)' },
  { name: 'Daily Loss', tripped: false, detail: '0.8% (limit: 3.0%)' },
  { name: 'Reconciliation', tripped: false, detail: 'Drift: 0.02%' },
  { name: 'Dead Man Switch', tripped: false, detail: 'Last heartbeat: 2h ago' },
];

export function Risk() {
  const pdtUsed = 1;
  const pdtMax = 3;

  return (
    <div className="space-y-6">
      {/* PDT Counter — the hero element */}
      <div className="glow-border rounded-xl bg-surface p-6 animate-in">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="flex h-14 w-14 items-center justify-center rounded-xl border border-cyan/20 bg-cyan-dim">
              <ShieldAlert className="h-7 w-7 text-cyan" />
            </div>
            <div>
              <h2 className="font-mono text-xs uppercase tracking-wider text-muted">
                Pattern Day Trade Guard
              </h2>
              <p className="text-sm text-dim">
                Rolling 5-business-day window &middot; FINRA PDT Rule
              </p>
            </div>
          </div>

          {/* Big PDT counter */}
          <div className="flex items-baseline gap-1">
            <span className={`font-mono text-6xl font-bold tracking-tighter ${
              pdtUsed >= pdtMax ? 'text-loss' : pdtUsed >= 2 ? 'text-amber' : 'text-gain'
            }`}>
              {pdtUsed}
            </span>
            <span className="font-mono text-2xl text-muted">/</span>
            <span className="font-mono text-2xl text-muted">{pdtMax}</span>
          </div>
        </div>

        {/* PDT visual bar */}
        <div className="mt-4 flex gap-2">
          {Array.from({ length: pdtMax }).map((_, i) => (
            <div
              key={i}
              className={`h-2 flex-1 rounded-full transition-all ${
                i < pdtUsed
                  ? pdtUsed >= pdtMax ? 'bg-loss' : pdtUsed >= 2 ? 'bg-amber' : 'bg-gain'
                  : 'bg-border'
              }`}
            />
          ))}
        </div>
        <p className="mt-2 font-mono text-[10px] text-dim">
          {pdtMax - pdtUsed} day trade{pdtMax - pdtUsed !== 1 ? 's' : ''} remaining &middot;
          {' '}Window resets as oldest trade exits 5-day lookback
        </p>
      </div>

      <div className="grid grid-cols-3 gap-4">
        {/* Drawdown chart */}
        <div className="col-span-2 glow-border rounded-xl bg-surface p-4 animate-in animate-in-delay-1">
          <h3 className="mb-4 font-mono text-[10px] uppercase tracking-wider text-muted">
            Drawdown — 60 Days
          </h3>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={DD_HISTORY}>
              <defs>
                <linearGradient id="ddGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#ff1744" stopOpacity={0} />
                  <stop offset="100%" stopColor="#ff1744" stopOpacity={0.3} />
                </linearGradient>
              </defs>
              <XAxis dataKey="date" tickLine={false} axisLine={false} tick={{ fontSize: 10 }} />
              <YAxis
                tickLine={false}
                axisLine={false}
                tick={{ fontSize: 10 }}
                domain={[-12, 0]}
                tickFormatter={(v: number) => `${v}%`}
              />
              <ReferenceLine y={-10} stroke="#ff1744" strokeDasharray="4 4" strokeOpacity={0.5} />
              <Tooltip
                contentStyle={{
                  background: '#181c25',
                  border: '1px solid #232833',
                  borderRadius: 8,
                  fontFamily: 'JetBrains Mono',
                  fontSize: 11,
                }}
                formatter={(v: number) => [`${v.toFixed(2)}%`, 'Drawdown']}
              />
              <Area
                type="monotone"
                dataKey="drawdown"
                stroke="#ff1744"
                strokeWidth={1.5}
                fill="url(#ddGrad)"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Limit utilization bars */}
        <div className="glow-border rounded-xl bg-surface p-4 animate-in animate-in-delay-2">
          <h3 className="mb-4 font-mono text-[10px] uppercase tracking-wider text-muted">
            Limit Utilization
          </h3>
          <div className="space-y-4">
            {LIMITS.map((l) => {
              const pct = l.inverted
                ? Math.max(0, (l.max / l.current) * 100)
                : (l.current / l.max) * 100;
              const warn = l.inverted ? l.current <= l.max * 1.5 : pct >= 70;
              const danger = l.inverted ? l.current <= l.max : pct >= 90;

              return (
                <div key={l.label}>
                  <div className="mb-1 flex justify-between">
                    <span className="font-mono text-[10px] uppercase tracking-wider text-muted">{l.label}</span>
                    <span className={`font-mono text-xs font-medium ${danger ? 'text-loss' : warn ? 'text-amber' : 'text-text'}`}>
                      {l.current}{l.unit} / {l.max}{l.unit}
                    </span>
                  </div>
                  <div className="h-1.5 w-full rounded-full bg-border">
                    <div
                      className={`h-full rounded-full transition-all ${
                        danger ? 'bg-loss' : warn ? 'bg-amber' : 'bg-cyan'
                      }`}
                      style={{ width: `${Math.min(pct, 100)}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Circuit breakers */}
      <div className="glow-border rounded-xl bg-surface animate-in animate-in-delay-3">
        <div className="border-b border-border px-4 py-3 flex items-center justify-between">
          <h3 className="font-mono text-[10px] uppercase tracking-wider text-muted">Circuit Breakers</h3>
          <div className="flex items-center gap-1.5">
            <CheckCircle2 className="h-3.5 w-3.5 text-gain" />
            <span className="font-mono text-[10px] text-gain">All Clear</span>
          </div>
        </div>
        <div className="grid grid-cols-3 gap-px bg-border">
          {BREAKERS.map((b) => (
            <div key={b.name} className="flex items-center gap-3 bg-surface p-4">
              {b.tripped ? (
                <XCircle className="h-5 w-5 shrink-0 text-loss" />
              ) : (
                <CheckCircle2 className="h-5 w-5 shrink-0 text-gain/60" />
              )}
              <div>
                <div className={`font-mono text-xs font-medium ${b.tripped ? 'text-loss' : 'text-text'}`}>
                  {b.name}
                </div>
                <div className="font-mono text-[10px] text-muted">{b.detail}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
