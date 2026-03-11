import { Trophy, TrendingUp, ShieldCheck, BarChart3, Clock } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { formatPct, formatNumber } from '../lib/format';

const STRATEGIES = [
  {
    name: 'SwingMomentum',
    description: 'Multi-day momentum with MA crossover, RSI confirmation',
    hold: '3–10 days',
    sharpe: 1.42,
    sortino: 1.78,
    maxDD: 12.3,
    profitFactor: 1.82,
    winRate: 58.2,
    totalTrades: 247,
    compositeScore: 78.4,
    meets: true,
    equity: Array.from({ length: 50 }, (_, i) => ({ x: i, y: 20000 + i * 120 + Math.sin(i / 3) * 600 + Math.random() * 200 })),
  },
  {
    name: 'MeanReversion',
    description: 'Bollinger Band reversion with RSI oversold entry',
    hold: '2–5 days',
    sharpe: 1.28,
    sortino: 1.55,
    maxDD: 14.8,
    profitFactor: 1.67,
    winRate: 62.5,
    totalTrades: 312,
    compositeScore: 72.1,
    meets: true,
    equity: Array.from({ length: 50 }, (_, i) => ({ x: i, y: 20000 + i * 95 + Math.cos(i / 4) * 500 + Math.random() * 200 })),
  },
  {
    name: 'ValueFactor',
    description: 'Composite value score ranking, weekly rebalance',
    hold: '5–20 days',
    sharpe: 0.89,
    sortino: 1.02,
    maxDD: 18.5,
    profitFactor: 1.35,
    winRate: 54.8,
    totalTrades: 156,
    compositeScore: 55.2,
    meets: false,
    equity: Array.from({ length: 50 }, (_, i) => ({ x: i, y: 20000 + i * 60 + Math.sin(i / 5) * 800 + Math.random() * 300 })),
  },
];

function scoreColor(score: number): string {
  if (score >= 70) return 'text-gain';
  if (score >= 50) return 'text-amber';
  return 'text-loss';
}

function scoreBg(score: number): string {
  if (score >= 70) return 'bg-gain-dim border-gain/30';
  if (score >= 50) return 'bg-amber-dim border-amber/30';
  return 'bg-loss-dim border-loss/30';
}

export function Strategies() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between animate-in">
        <h2 className="font-mono text-xs uppercase tracking-wider text-muted">
          Strategy Rankings
        </h2>
        <div className="flex items-center gap-2 text-xs text-dim">
          <ShieldCheck className="h-3.5 w-3.5" />
          Thresholds: Sharpe &gt; 1.0 &middot; DD &lt; 20% &middot; PF &gt; 1.5 &middot; 100+ trades
        </div>
      </div>

      <div className="space-y-4">
        {STRATEGIES.map((s, idx) => (
          <div
            key={s.name}
            className={`glow-border rounded-xl bg-surface animate-in animate-in-delay-${idx + 1}`}
          >
            <div className="flex gap-6 p-5">
              {/* Left: score + info */}
              <div className="flex flex-col items-center gap-2 pr-6 border-r border-border">
                <div className={`flex h-16 w-16 items-center justify-center rounded-xl border ${scoreBg(s.compositeScore)}`}>
                  <span className={`font-mono text-2xl font-bold ${scoreColor(s.compositeScore)}`}>
                    {s.compositeScore.toFixed(0)}
                  </span>
                </div>
                <span className="font-mono text-[9px] uppercase tracking-wider text-muted">Score</span>
                {idx === 0 && <Trophy className="h-4 w-4 text-amber" />}
              </div>

              {/* Middle: details */}
              <div className="flex-1 space-y-3">
                <div className="flex items-center gap-3">
                  <h3 className="font-mono text-base font-semibold text-bright">{s.name}</h3>
                  {s.meets ? (
                    <span className="rounded border border-gain/30 bg-gain-dim px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-gain">
                      Meets Thresholds
                    </span>
                  ) : (
                    <span className="rounded border border-loss/30 bg-loss-dim px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-loss">
                      Below Thresholds
                    </span>
                  )}
                </div>
                <p className="text-sm text-dim">{s.description}</p>
                <div className="flex items-center gap-1.5 text-xs text-muted">
                  <Clock className="h-3 w-3" />
                  Hold period: {s.hold}
                </div>

                {/* Metrics grid */}
                <div className="grid grid-cols-6 gap-3 pt-2">
                  {[
                    { label: 'Sharpe', value: formatNumber(s.sharpe), ok: s.sharpe >= 1.0 },
                    { label: 'Sortino', value: formatNumber(s.sortino), ok: true },
                    { label: 'Max DD', value: formatPct(-s.maxDD), ok: s.maxDD <= 20 },
                    { label: 'Profit Factor', value: formatNumber(s.profitFactor), ok: s.profitFactor >= 1.5 },
                    { label: 'Win Rate', value: formatPct(s.winRate, 1), ok: true },
                    { label: 'Trades', value: s.totalTrades.toString(), ok: s.totalTrades >= 100 },
                  ].map((m) => (
                    <div key={m.label} className="rounded-lg bg-panel px-3 py-2">
                      <div className="font-mono text-[9px] uppercase tracking-wider text-muted">{m.label}</div>
                      <div className={`font-mono text-sm font-semibold ${m.ok ? 'text-text' : 'text-loss'}`}>
                        {m.value}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Right: mini equity curve */}
              <div className="w-56 shrink-0">
                <div className="font-mono text-[9px] uppercase tracking-wider text-muted mb-1">Equity Curve</div>
                <ResponsiveContainer width="100%" height={120}>
                  <AreaChart data={s.equity}>
                    <defs>
                      <linearGradient id={`grad-${s.name}`} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={s.meets ? '#00e676' : '#ffab00'} stopOpacity={0.2} />
                        <stop offset="100%" stopColor={s.meets ? '#00e676' : '#ffab00'} stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <Area
                      type="monotone"
                      dataKey="y"
                      stroke={s.meets ? '#00e676' : '#ffab00'}
                      strokeWidth={1.5}
                      fill={`url(#grad-${s.name})`}
                    />
                    <XAxis dataKey="x" hide />
                    <YAxis hide domain={['dataMin - 500', 'dataMax + 500']} />
                    <Tooltip
                      contentStyle={{
                        background: '#181c25',
                        border: '1px solid #232833',
                        borderRadius: 8,
                        fontFamily: 'JetBrains Mono',
                        fontSize: 11,
                      }}
                      formatter={(v: number) => [`$${v.toFixed(0)}`, 'Equity']}
                      labelFormatter={() => ''}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
