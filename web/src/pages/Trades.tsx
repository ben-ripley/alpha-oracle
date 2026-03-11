import { useState } from 'react';
import {
  ArrowUpRight, ArrowDownRight, Clock, CheckCircle2,
  XCircle, Filter, ThumbsUp, ThumbsDown,
} from 'lucide-react';
import { formatCurrency, formatPct, pnlColor, pnlBg } from '../lib/format';

const TRADE_HISTORY = [
  { id: 'T001', symbol: 'NVDA', side: 'BUY' as const, quantity: 10, entry_price: 875.50, exit_price: 912.30, entry_time: '2026-03-06T14:30:00Z', exit_time: '2026-03-10T15:45:00Z', pnl: 368.00, pnl_pct: 4.20, strategy_name: 'SwingMomentum', hold_duration_days: 4.05, is_day_trade: false },
  { id: 'T002', symbol: 'AAPL', side: 'BUY' as const, quantity: 15, entry_price: 178.50, exit_price: null, entry_time: '2026-03-07T10:15:00Z', exit_time: null, pnl: 70.50, pnl_pct: 2.63, strategy_name: 'SwingMomentum', hold_duration_days: 4.0, is_day_trade: false },
  { id: 'T003', symbol: 'META', side: 'BUY' as const, quantity: 6, entry_price: 502.80, exit_price: 495.20, entry_time: '2026-03-04T11:00:00Z', exit_time: '2026-03-07T14:30:00Z', pnl: -45.60, pnl_pct: -1.51, strategy_name: 'MeanReversion', hold_duration_days: 3.15, is_day_trade: false },
  { id: 'T004', symbol: 'MSFT', side: 'BUY' as const, quantity: 8, entry_price: 415.00, exit_price: null, entry_time: '2026-03-09T09:45:00Z', exit_time: null, pnl: 62.40, pnl_pct: 1.88, strategy_name: 'MeanReversion', hold_duration_days: 2.0, is_day_trade: false },
  { id: 'T005', symbol: 'GOOG', side: 'BUY' as const, quantity: 12, entry_price: 165.40, exit_price: 170.15, entry_time: '2026-03-03T13:20:00Z', exit_time: '2026-03-06T15:50:00Z', pnl: 57.00, pnl_pct: 2.87, strategy_name: 'SwingMomentum', hold_duration_days: 3.10, is_day_trade: false },
  { id: 'T006', symbol: 'JPM', side: 'BUY' as const, quantity: 12, entry_price: 195.20, exit_price: null, entry_time: '2026-03-08T10:30:00Z', exit_time: null, pnl: -37.20, pnl_pct: -1.59, strategy_name: 'ValueFactor', hold_duration_days: 3.0, is_day_trade: false },
];

const PENDING_APPROVALS = [
  { id: 'P001', symbol: 'AMZN', side: 'BUY' as const, quantity: 5, limit_price: 188.50, strategy_name: 'SwingMomentum', signal_strength: 0.78, created_at: '2026-03-11T09:32:00Z' },
  { id: 'P002', symbol: 'TSLA', side: 'SELL' as const, quantity: 8, limit_price: 245.00, strategy_name: 'MeanReversion', signal_strength: 0.65, created_at: '2026-03-11T09:35:00Z' },
];

const EXEC_QUALITY = {
  avg_slippage_bps: 3.2,
  fill_rate_pct: 96.8,
  avg_fill_time_sec: 1.4,
  total_orders: 42,
};

export function Trades() {
  const [filter, setFilter] = useState<'all' | 'open' | 'closed'>('all');

  const filtered = TRADE_HISTORY.filter((t) => {
    if (filter === 'open') return !t.exit_time;
    if (filter === 'closed') return !!t.exit_time;
    return true;
  });

  return (
    <div className="space-y-6">
      {/* Pending Approvals */}
      {PENDING_APPROVALS.length > 0 && (
        <div className="rounded-xl border border-amber/20 bg-amber-dim/30 animate-in">
          <div className="border-b border-amber/10 px-4 py-3 flex items-center gap-2">
            <Clock className="h-4 w-4 text-amber" />
            <h3 className="font-mono text-xs font-medium uppercase tracking-wider text-amber">
              Pending Approvals ({PENDING_APPROVALS.length})
            </h3>
          </div>
          <div className="divide-y divide-amber/10">
            {PENDING_APPROVALS.map((p) => (
              <div key={p.id} className="flex items-center justify-between px-4 py-3">
                <div className="flex items-center gap-4">
                  <div className={`flex items-center gap-1 rounded px-2 py-0.5 font-mono text-xs font-medium ${
                    p.side === 'BUY' ? 'bg-gain-dim text-gain' : 'bg-loss-dim text-loss'
                  }`}>
                    {p.side === 'BUY' ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}
                    {p.side}
                  </div>
                  <span className="font-mono text-sm font-semibold text-bright">{p.symbol}</span>
                  <span className="font-mono text-sm text-dim">{p.quantity} shares @ {formatCurrency(p.limit_price!)}</span>
                  <span className="rounded border border-border bg-panel px-1.5 py-0.5 font-mono text-[10px] text-dim">
                    {p.strategy_name}
                  </span>
                  <span className="font-mono text-xs text-muted">
                    Signal: {(p.signal_strength * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <button className="flex items-center gap-1 rounded-lg border border-gain/30 bg-gain-dim px-3 py-1.5 font-mono text-xs font-medium text-gain transition-colors hover:bg-gain/20">
                    <ThumbsUp className="h-3 w-3" />
                    Approve
                  </button>
                  <button className="flex items-center gap-1 rounded-lg border border-loss/30 bg-loss-dim px-3 py-1.5 font-mono text-xs font-medium text-loss transition-colors hover:bg-loss/20">
                    <ThumbsDown className="h-3 w-3" />
                    Reject
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Execution quality stats */}
      <div className="grid grid-cols-4 gap-4 animate-in animate-in-delay-1">
        <div className="glow-border rounded-xl bg-surface p-4">
          <span className="font-mono text-[10px] uppercase tracking-wider text-muted">Avg Slippage</span>
          <p className="mt-1 font-mono text-xl font-bold text-text">{EXEC_QUALITY.avg_slippage_bps} <span className="text-sm text-dim">bps</span></p>
        </div>
        <div className="glow-border rounded-xl bg-surface p-4">
          <span className="font-mono text-[10px] uppercase tracking-wider text-muted">Fill Rate</span>
          <p className="mt-1 font-mono text-xl font-bold text-gain">{EXEC_QUALITY.fill_rate_pct}%</p>
        </div>
        <div className="glow-border rounded-xl bg-surface p-4">
          <span className="font-mono text-[10px] uppercase tracking-wider text-muted">Avg Fill Time</span>
          <p className="mt-1 font-mono text-xl font-bold text-text">{EXEC_QUALITY.avg_fill_time_sec}s</p>
        </div>
        <div className="glow-border rounded-xl bg-surface p-4">
          <span className="font-mono text-[10px] uppercase tracking-wider text-muted">Total Orders</span>
          <p className="mt-1 font-mono text-xl font-bold text-text">{EXEC_QUALITY.total_orders}</p>
        </div>
      </div>

      {/* Trade history table */}
      <div className="glow-border rounded-xl bg-surface animate-in animate-in-delay-2">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h3 className="font-mono text-[10px] uppercase tracking-wider text-muted">Trade History</h3>
          <div className="flex items-center gap-1 rounded-lg bg-panel p-0.5">
            {(['all', 'open', 'closed'] as const).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`rounded-md px-3 py-1 font-mono text-[10px] uppercase tracking-wider transition-all ${
                  filter === f
                    ? 'bg-surface text-bright shadow-sm border border-border-bright'
                    : 'text-muted hover:text-dim border border-transparent'
                }`}
              >
                {f}
              </button>
            ))}
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border text-left">
                {['Side', 'Symbol', 'Qty', 'Entry', 'Exit', 'P&L', 'P&L %', 'Hold', 'Strategy', 'Status'].map((h) => (
                  <th key={h} className="px-4 py-2.5 font-mono text-[10px] font-medium uppercase tracking-wider text-muted">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((t) => (
                <tr key={t.id} className="border-b border-border/50 transition-colors hover:bg-panel/50">
                  <td className="px-4 py-2.5">
                    <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 font-mono text-[10px] font-medium ${
                      t.side === 'BUY' ? 'bg-gain-dim text-gain' : 'bg-loss-dim text-loss'
                    }`}>
                      {t.side === 'BUY' ? <ArrowUpRight className="h-2.5 w-2.5" /> : <ArrowDownRight className="h-2.5 w-2.5" />}
                      {t.side}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 font-mono text-sm font-semibold text-bright">{t.symbol}</td>
                  <td className="px-4 py-2.5 font-mono text-sm text-text">{t.quantity}</td>
                  <td className="px-4 py-2.5 font-mono text-sm text-dim">{formatCurrency(t.entry_price)}</td>
                  <td className="px-4 py-2.5 font-mono text-sm text-dim">
                    {t.exit_price ? formatCurrency(t.exit_price) : '—'}
                  </td>
                  <td className={`px-4 py-2.5 font-mono text-sm font-medium ${pnlColor(t.pnl)}`}>
                    {formatCurrency(t.pnl)}
                  </td>
                  <td className="px-4 py-2.5">
                    <span className={`inline-block rounded px-1.5 py-0.5 font-mono text-xs font-medium ${pnlColor(t.pnl_pct)} ${pnlBg(t.pnl_pct)}`}>
                      {formatPct(t.pnl_pct)}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 font-mono text-xs text-dim">{t.hold_duration_days.toFixed(1)}d</td>
                  <td className="px-4 py-2.5">
                    <span className="rounded border border-border bg-panel px-1.5 py-0.5 font-mono text-[10px] text-dim">
                      {t.strategy_name}
                    </span>
                  </td>
                  <td className="px-4 py-2.5">
                    {t.exit_time ? (
                      <span className="inline-flex items-center gap-1 font-mono text-[10px] text-dim">
                        <CheckCircle2 className="h-3 w-3" /> Closed
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 font-mono text-[10px] text-cyan live-pulse">
                        <Clock className="h-3 w-3" /> Open
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
