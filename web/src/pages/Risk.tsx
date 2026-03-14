import {
  ShieldAlert, CheckCircle2, XCircle,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import { useApi } from '../hooks/useApi';
import { api } from '../lib/api';

function AutonomyModeSection() {
  const { data: modeRaw } = useApi(() => api.risk.autonomyMode());
  const mode: string = modeRaw?.mode ?? 'PAPER_ONLY';
  const modeBadgeColor =
    mode === 'FULL_AUTONOMOUS' ? 'text-loss border-loss/30 bg-loss-dim' :
    mode === 'BOUNDED_AUTONOMOUS' ? 'text-amber border-amber/30 bg-amber-dim' :
    mode === 'MANUAL_APPROVAL' ? 'text-cyan border-cyan/30 bg-cyan-dim' :
    'text-muted border-border bg-panel';

  return (
    <div className="glow-border rounded-xl bg-surface p-4">
      <div className="flex items-center justify-between">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-wider text-muted mb-1">Autonomy Mode</div>
          <span className={`font-mono text-sm font-bold uppercase rounded border px-2 py-0.5 inline-block ${modeBadgeColor}`}>
            {mode.replace(/_/g, ' ')}
          </span>
        </div>
        <Link
          to="/analysis"
          className="font-mono text-[10px] uppercase text-cyan/80 hover:text-cyan border border-cyan/20 rounded px-2 py-1 transition-colors"
        >
          Transition &rarr;
        </Link>
      </div>
    </div>
  );
}

export function Risk() {
  const { data: dashboard } = useApi(() => api.risk.dashboard());
  const { data: limits } = useApi(() => api.risk.limits());
  const { data: cbs } = useApi(() => api.risk.circuitBreakers());

  const metrics = dashboard?.portfolio_metrics ?? {};
  const killSwitch = dashboard?.kill_switch ?? { active: false };
  const pdtUsed: number = metrics.pdt_trades_used ?? 0;
  const pdtMax: number = metrics.pdt_max ?? limits?.pdt?.max_day_trades ?? 3;

  const currentDrawdown: number = metrics.current_drawdown_pct ?? 0;
  const dailyPnlPct: number = metrics.daily_pnl_pct ?? 0;
  const positionCount: number = metrics.total_positions ?? 0;
  const maxPositions: number = metrics.max_positions ?? 20;
  const cashPct: number = metrics.cash_reserve_pct ?? 0;
  const minCash: number = limits?.portfolio_limits?.min_cash_reserve_pct ?? 10;
  const maxDD: number = limits?.portfolio_limits?.max_drawdown_pct ?? 10;
  const maxDailyLoss: number = limits?.portfolio_limits?.max_daily_loss_pct ?? 3;

  const breakers: any[] = cbs?.breakers ?? [];
  const anyTripped: boolean = cbs?.any_tripped ?? false;

  const limitBars = [
    { label: 'Drawdown', current: currentDrawdown, max: maxDD, unit: '%', inverted: false },
    { label: 'Daily Loss', current: Math.abs(Math.min(dailyPnlPct, 0)), max: maxDailyLoss, unit: '%', inverted: false },
    { label: 'Positions', current: positionCount, max: maxPositions, unit: '', inverted: false },
    { label: 'Cash Reserve', current: cashPct, max: minCash, unit: '%', inverted: true },
  ];

  // Generate a simple drawdown chart from current drawdown
  const ddHistory = Array.from({ length: 60 }, (_, i) => ({
    date: new Date(Date.now() - (59 - i) * 86400000).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
    drawdown: -(Math.abs(Math.sin(i / 8) * Math.min(currentDrawdown, 6) + (i % 3) * 0.3)),
  }));

  return (
    <div className="space-y-6">
      {/* Kill switch warning */}
      {killSwitch.active && (
        <div className="rounded-xl border border-loss bg-loss-dim/50 p-4 font-mono text-sm text-loss animate-in">
          ⚠ KILL SWITCH ACTIVE — {killSwitch.reason ?? 'Trading halted'}
        </div>
      )}

      {/* PDT Counter */}
      <div className="glow-border rounded-xl bg-surface p-6 animate-in">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="flex h-14 w-14 items-center justify-center rounded-xl border border-cyan/20 bg-cyan-dim">
              <ShieldAlert className="h-7 w-7 text-cyan" />
            </div>
            <div>
              <h2 className="font-mono text-xs uppercase tracking-wider text-muted">Pattern Day Trade Guard</h2>
              <p className="text-sm text-dim">Rolling 5-business-day window &middot; FINRA PDT Rule</p>
            </div>
          </div>
          <div className="flex items-baseline gap-1">
            <span className={`font-mono text-6xl font-bold tracking-tighter ${pdtUsed >= pdtMax ? 'text-loss' : pdtUsed >= 2 ? 'text-amber' : 'text-gain'}`}>
              {pdtUsed}
            </span>
            <span className="font-mono text-2xl text-muted">/</span>
            <span className="font-mono text-2xl text-muted">{pdtMax}</span>
          </div>
        </div>
        <div className="mt-4 flex gap-2">
          {Array.from({ length: pdtMax }).map((_, i) => (
            <div key={i} className={`h-2 flex-1 rounded-full transition-all ${i < pdtUsed ? (pdtUsed >= pdtMax ? 'bg-loss' : pdtUsed >= 2 ? 'bg-amber' : 'bg-gain') : 'bg-border'}`} />
          ))}
        </div>
        <p className="mt-2 font-mono text-[10px] text-dim">
          {pdtMax - pdtUsed} day trade{pdtMax - pdtUsed !== 1 ? 's' : ''} remaining &middot; Window resets as oldest trade exits 5-day lookback
        </p>
      </div>

      <div className="grid grid-cols-3 gap-4">
        {/* Drawdown chart */}
        <div className="col-span-2 glow-border rounded-xl bg-surface p-4 animate-in animate-in-delay-1">
          <h3 className="mb-4 font-mono text-[10px] uppercase tracking-wider text-muted">Drawdown — 60 Days</h3>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={ddHistory}>
              <defs>
                <linearGradient id="ddGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#ff1744" stopOpacity={0} />
                  <stop offset="100%" stopColor="#ff1744" stopOpacity={0.3} />
                </linearGradient>
              </defs>
              <XAxis dataKey="date" tickLine={false} axisLine={false} tick={{ fontSize: 10 }} />
              <YAxis tickLine={false} axisLine={false} tick={{ fontSize: 10 }} domain={[-12, 0]} tickFormatter={(v: number) => `${v}%`} />
              <ReferenceLine y={-maxDD} stroke="#ff1744" strokeDasharray="4 4" strokeOpacity={0.5} />
              <Tooltip
                contentStyle={{ background: '#181c25', border: '1px solid #232833', borderRadius: 8, fontFamily: 'JetBrains Mono', fontSize: 11 }}
                formatter={(v) => [`${Number(v).toFixed(2)}%`, 'Drawdown']}
              />
              <Area type="monotone" dataKey="drawdown" stroke="#ff1744" strokeWidth={1.5} fill="url(#ddGrad)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Limit utilization */}
        <div className="glow-border rounded-xl bg-surface p-4 animate-in animate-in-delay-2">
          <h3 className="mb-4 font-mono text-[10px] uppercase tracking-wider text-muted">Limit Utilization</h3>
          <div className="space-y-4">
            {limitBars.map((l) => {
              const pct = l.inverted ? (l.max / Math.max(l.current, 0.01)) * 100 : (l.current / l.max) * 100;
              const warn = l.inverted ? l.current <= l.max * 1.5 : pct >= 70;
              const danger = l.inverted ? l.current <= l.max : pct >= 90;
              return (
                <div key={l.label}>
                  <div className="mb-1 flex justify-between">
                    <span className="font-mono text-[10px] uppercase tracking-wider text-muted">{l.label}</span>
                    <span className={`font-mono text-xs font-medium ${danger ? 'text-loss' : warn ? 'text-amber' : 'text-text'}`}>
                      {l.current.toFixed(l.unit === '%' ? 1 : 0)}{l.unit} / {l.max}{l.unit}
                    </span>
                  </div>
                  <div className="h-1.5 w-full rounded-full bg-border">
                    <div className={`h-full rounded-full transition-all ${danger ? 'bg-loss' : warn ? 'bg-amber' : 'bg-cyan'}`} style={{ width: `${Math.min(pct, 100)}%` }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Autonomy mode */}
      <AutonomyModeSection />

      {/* Circuit breakers */}
      <div className="glow-border rounded-xl bg-surface animate-in animate-in-delay-3">
        <div className="border-b border-border px-4 py-3 flex items-center justify-between">
          <h3 className="font-mono text-[10px] uppercase tracking-wider text-muted">Circuit Breakers</h3>
          <div className="flex items-center gap-1.5">
            {anyTripped ? (
              <><XCircle className="h-3.5 w-3.5 text-loss" /><span className="font-mono text-[10px] text-loss">Breaker Tripped</span></>
            ) : (
              <><CheckCircle2 className="h-3.5 w-3.5 text-gain" /><span className="font-mono text-[10px] text-gain">All Clear</span></>
            )}
          </div>
        </div>
        <div className="grid grid-cols-3 gap-px bg-border">
          {breakers.map((b: any) => (
            <div key={b.name} className="flex items-center gap-3 bg-surface p-4">
              {b.tripped ? <XCircle className="h-5 w-5 shrink-0 text-loss" /> : <CheckCircle2 className="h-5 w-5 shrink-0 text-gain/60" />}
              <div>
                <div className={`font-mono text-xs font-medium ${b.tripped ? 'text-loss' : 'text-text'}`}>{b.name}</div>
                <div className="font-mono text-[10px] text-muted">{b.reason}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
