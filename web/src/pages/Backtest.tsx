import { useState } from 'react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import { BarChart2, Play, Info } from 'lucide-react';
import { formatPct, formatNumber } from '../lib/format';
import { useApi } from '../hooks/useApi';
import { api } from '../lib/api';

interface BacktestResult {
  strategy_name: string;
  start_date: string;
  end_date: string;
  initial_capital: number;
  final_capital: number;
  total_return_pct: number;
  annual_return_pct: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  max_drawdown_pct: number;
  profit_factor: number;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  avg_win_pct: number;
  avg_loss_pct: number;
  equity_curve: { date?: string; value?: number; [k: string]: any }[];
  trades: { [k: string]: any }[];
}

function returnColor(pct: number) {
  return pct >= 0 ? 'text-gain' : 'text-loss';
}

function StatCell({ label, value, ok = true }: { label: string; value: string; ok?: boolean }) {
  return (
    <div className="rounded-lg bg-panel px-3 py-2">
      <div className="font-mono text-[9px] uppercase tracking-wider text-muted">{label}</div>
      <div className={`font-mono text-sm font-semibold ${ok ? 'text-text' : 'text-loss'}`}>{value}</div>
    </div>
  );
}

export function Backtest() {
  const { data, loading } = useApi(() => api.strategies.results());
  const results: BacktestResult[] = data?.results ?? [];

  const [selected, setSelected] = useState<string>('');
  const [runStatus, setRunStatus] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  const strategyNames = Array.from(new Set(results.map((r) => r.strategy_name)));
  const activeResult: BacktestResult | undefined =
    results.find((r) => r.strategy_name === (selected || strategyNames[0]));

  // Normalise equity curve: accept {date,value} or {x,y} or {timestamp,equity}
  const equityCurve = (activeResult?.equity_curve ?? []).map((pt) => ({
    date: pt.date ?? pt.x ?? pt.timestamp ?? '',
    value: pt.value ?? pt.y ?? pt.equity ?? 0,
  }));

  const tradeRows = (activeResult?.trades ?? []).slice(0, 50);

  async function handleRunBacktest() {
    setRunning(true);
    setRunStatus(null);
    try {
      const res = await api.strategies.backtest({
        strategy_name: selected || strategyNames[0] || 'swing_momentum',
        symbols: ['SPY', 'AAPL', 'MSFT'],
        start_date: '2023-01-01',
      });
      setRunStatus(res.message ?? res.status ?? 'Request sent.');
    } catch {
      setRunStatus('Request failed — ensure the backend is running.');
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <BarChart2 className="h-4 w-4 text-cyan" />
          <h1 className="font-mono text-sm font-semibold uppercase tracking-wider text-bright">
            Backtest Results
          </h1>
        </div>

        {/* Strategy selector + run button */}
        <div className="flex items-center gap-3">
          {strategyNames.length > 0 && (
            <select
              value={selected || strategyNames[0]}
              onChange={(e) => setSelected(e.target.value)}
              className="rounded-lg border border-border bg-panel px-3 py-1.5 font-mono text-xs text-text focus:border-cyan/60 focus:outline-none"
            >
              {strategyNames.map((n) => (
                <option key={n} value={n}>{n}</option>
              ))}
            </select>
          )}
          <button
            onClick={handleRunBacktest}
            disabled={running}
            className="flex items-center gap-1.5 rounded-lg border border-cyan/30 bg-cyan-dim px-3 py-1.5 font-mono text-xs text-cyan hover:border-cyan/60 transition-colors disabled:opacity-50"
          >
            <Play className="h-3 w-3" />
            {running ? 'Running…' : 'Run Backtest'}
          </button>
        </div>
      </div>

      {/* Run status notice */}
      {runStatus && (
        <div className="flex items-start gap-2 rounded-lg border border-amber/30 bg-amber-dim px-4 py-3">
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber" />
          <p className="font-mono text-xs text-amber">{runStatus}</p>
        </div>
      )}

      {loading && (
        <div className="py-16 text-center font-mono text-xs text-muted">Loading results…</div>
      )}

      {!loading && results.length === 0 && (
        <div className="rounded-xl border border-border bg-surface p-10 text-center">
          <BarChart2 className="mx-auto mb-3 h-8 w-8 text-muted" />
          <p className="font-mono text-sm text-dim">No backtest results stored yet.</p>
          <p className="mt-1 font-mono text-xs text-muted">
            Run a backtest from the CLI or trigger one via the button above.
          </p>
        </div>
      )}

      {!loading && activeResult && (
        <>
          {/* Stats grid */}
          <div className="glow-border rounded-xl bg-surface p-5">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="font-mono text-xs uppercase tracking-wider text-muted">
                {activeResult.strategy_name}
              </h2>
              <span className="font-mono text-[10px] text-dim">
                {activeResult.start_date?.slice(0, 10)} → {activeResult.end_date?.slice(0, 10)}
              </span>
            </div>

            {/* Primary P&L */}
            <div className="mb-4 grid grid-cols-3 gap-4">
              <div className="rounded-lg bg-panel px-4 py-3">
                <div className="font-mono text-[9px] uppercase tracking-wider text-muted">Total Return</div>
                <div className={`font-mono text-2xl font-bold ${returnColor(activeResult.total_return_pct)}`}>
                  {formatPct(activeResult.total_return_pct)}
                </div>
              </div>
              <div className="rounded-lg bg-panel px-4 py-3">
                <div className="font-mono text-[9px] uppercase tracking-wider text-muted">Annual Return</div>
                <div className={`font-mono text-2xl font-bold ${returnColor(activeResult.annual_return_pct)}`}>
                  {formatPct(activeResult.annual_return_pct)}
                </div>
              </div>
              <div className="rounded-lg bg-panel px-4 py-3">
                <div className="font-mono text-[9px] uppercase tracking-wider text-muted">Final Capital</div>
                <div className="font-mono text-2xl font-bold text-bright">
                  ${activeResult.final_capital.toLocaleString('en-US', { maximumFractionDigits: 0 })}
                </div>
              </div>
            </div>

            {/* Secondary stats */}
            <div className="grid grid-cols-6 gap-3">
              <StatCell label="Sharpe" value={formatNumber(activeResult.sharpe_ratio)} ok={activeResult.sharpe_ratio >= 1.0} />
              <StatCell label="Sortino" value={formatNumber(activeResult.sortino_ratio)} />
              <StatCell label="Max DD" value={formatPct(-activeResult.max_drawdown_pct)} ok={activeResult.max_drawdown_pct <= 20} />
              <StatCell label="Profit Factor" value={formatNumber(activeResult.profit_factor)} ok={activeResult.profit_factor >= 1.5} />
              <StatCell label="Win Rate" value={formatPct(activeResult.win_rate, 1)} />
              <StatCell label="Total Trades" value={String(activeResult.total_trades)} />
            </div>

            <div className="mt-3 grid grid-cols-4 gap-3">
              <StatCell label="Winning Trades" value={String(activeResult.winning_trades)} />
              <StatCell label="Losing Trades" value={String(activeResult.losing_trades)} />
              <StatCell label="Avg Win" value={formatPct(activeResult.avg_win_pct)} />
              <StatCell label="Avg Loss" value={formatPct(-Math.abs(activeResult.avg_loss_pct))} ok={false} />
            </div>
          </div>

          {/* Equity curve */}
          {equityCurve.length > 1 && (
            <div className="glow-border rounded-xl bg-surface p-5">
              <div className="mb-3 font-mono text-[10px] uppercase tracking-wider text-muted">
                Equity Curve
              </div>
              <ResponsiveContainer width="100%" height={220}>
                <AreaChart data={equityCurve}>
                  <defs>
                    <linearGradient id="eq-gradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#00e676" stopOpacity={0.18} />
                      <stop offset="100%" stopColor="#00e676" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="date" tick={{ fontSize: 9, fill: '#5a6273' }} tickFormatter={(v) => String(v).slice(0, 10)} />
                  <YAxis tick={{ fontSize: 9, fill: '#5a6273' }} tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} />
                  <ReferenceLine
                    y={activeResult.initial_capital}
                    stroke="#5a6273"
                    strokeDasharray="3 3"
                  />
                  <Area
                    type="monotone"
                    dataKey="value"
                    stroke="#00e676"
                    strokeWidth={1.5}
                    fill="url(#eq-gradient)"
                    dot={false}
                  />
                  <Tooltip
                    contentStyle={{
                      background: '#181c25',
                      border: '1px solid #232833',
                      borderRadius: 8,
                      fontFamily: 'JetBrains Mono',
                      fontSize: 11,
                    }}
                    formatter={(v: number) => [`$${v.toLocaleString('en-US', { maximumFractionDigits: 0 })}`, 'Equity']}
                    labelFormatter={(l) => String(l).slice(0, 10)}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Trade list */}
          {tradeRows.length > 0 && (
            <div className="glow-border rounded-xl bg-surface p-5">
              <div className="mb-3 font-mono text-[10px] uppercase tracking-wider text-muted">
                Trade Log {activeResult.trades.length > 50 ? `(showing 50 of ${activeResult.trades.length})` : ''}
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-border">
                      {['Symbol', 'Side', 'Entry Date', 'Exit Date', 'Hold (d)', 'Entry $', 'Exit $', 'P&L %'].map((h) => (
                        <th key={h} className="px-3 py-2 text-left font-mono text-[9px] uppercase tracking-wider text-muted">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {tradeRows.map((t, i) => {
                      const pnl = t.pnl_pct ?? t.pnl ?? 0;
                      return (
                        <tr key={i} className="border-b border-border/40 hover:bg-panel/50">
                          <td className="px-3 py-1.5 font-mono font-semibold text-bright">{t.symbol ?? '—'}</td>
                          <td className="px-3 py-1.5 font-mono text-dim">{t.side ?? '—'}</td>
                          <td className="px-3 py-1.5 font-mono text-dim">{String(t.entry_time ?? t.entry_date ?? '—').slice(0, 10)}</td>
                          <td className="px-3 py-1.5 font-mono text-dim">{String(t.exit_time ?? t.exit_date ?? '—').slice(0, 10)}</td>
                          <td className="px-3 py-1.5 font-mono text-dim">{t.hold_duration_days != null ? Number(t.hold_duration_days).toFixed(0) : '—'}</td>
                          <td className="px-3 py-1.5 font-mono text-text">{t.entry_price != null ? `$${Number(t.entry_price).toFixed(2)}` : '—'}</td>
                          <td className="px-3 py-1.5 font-mono text-text">{t.exit_price != null ? `$${Number(t.exit_price).toFixed(2)}` : '—'}</td>
                          <td className={`px-3 py-1.5 font-mono font-semibold ${returnColor(pnl)}`}>
                            {formatPct(pnl, 2)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
