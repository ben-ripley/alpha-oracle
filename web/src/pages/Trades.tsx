import { useState } from 'react';
import {
  ArrowUpRight, ArrowDownRight, Clock, CheckCircle2,
  ThumbsUp, ThumbsDown,
} from 'lucide-react';
import { formatCurrency, formatPct, pnlColor, pnlBg } from '../lib/format';
import { useApi } from '../hooks/useApi';
import { api } from '../lib/api';

export function Trades() {
  const [filter, setFilter] = useState<'all' | 'open' | 'closed'>('all');

  const { data: historyData } = useApi(() => api.trades.history(30, 100));
  const { data: pendingData, refetch: refetchPending } = useApi(() => api.trades.pendingApprovals());
  const { data: qualityData } = useApi(() => api.trades.executionQuality(30));
  const { data: summaryData } = useApi(() => api.trades.dailySummary());

  const trades: any[] = historyData?.trades ?? [];
  const pending: any[] = pendingData?.pending ?? [];
  const quality = qualityData ?? { total_trades: 0, fill_rate: 0 };
  const summary = summaryData ?? { total_trades: 0, total_pnl: 0, winning_trades: 0, losing_trades: 0 };

  const filtered = trades.filter((t: any) => {
    if (filter === 'open') return !t.exit_time;
    if (filter === 'closed') return !!t.exit_time;
    return true;
  });

  async function handleApproval(orderId: string, action: 'approve' | 'reject') {
    await api.trades.approve(orderId, action);
    refetchPending();
  }

  return (
    <div className="space-y-6">
      {/* Pending Approvals */}
      {pending.length > 0 && (
        <div className="rounded-xl border border-amber/20 bg-amber-dim/30 animate-in">
          <div className="border-b border-amber/10 px-4 py-3 flex items-center gap-2">
            <Clock className="h-4 w-4 text-amber" />
            <h3 className="font-mono text-xs font-medium uppercase tracking-wider text-amber">
              Pending Approvals ({pending.length})
            </h3>
          </div>
          <div className="divide-y divide-amber/10">
            {pending.map((p: any) => (
              <div key={p.id} className="flex items-center justify-between px-4 py-3">
                <div className="flex items-center gap-4">
                  <div className={`flex items-center gap-1 rounded px-2 py-0.5 font-mono text-xs font-medium ${p.side === 'BUY' ? 'bg-gain-dim text-gain' : 'bg-loss-dim text-loss'}`}>
                    {p.side === 'BUY' ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}
                    {p.side}
                  </div>
                  <span className="font-mono text-sm font-semibold text-bright">{p.symbol}</span>
                  <span className="font-mono text-sm text-dim">{p.quantity} shares @ {p.limit_price ? formatCurrency(p.limit_price) : 'MKT'}</span>
                  <span className="rounded border border-border bg-panel px-1.5 py-0.5 font-mono text-[10px] text-dim">{p.strategy_name}</span>
                  <span className="font-mono text-xs text-muted">Signal: {((p.signal_strength ?? 0) * 100).toFixed(0)}%</span>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleApproval(p.id, 'approve')}
                    className="flex items-center gap-1 rounded-lg border border-gain/30 bg-gain-dim px-3 py-1.5 font-mono text-xs font-medium text-gain transition-colors hover:bg-gain/20"
                  >
                    <ThumbsUp className="h-3 w-3" /> Approve
                  </button>
                  <button
                    onClick={() => handleApproval(p.id, 'reject')}
                    className="flex items-center gap-1 rounded-lg border border-loss/30 bg-loss-dim px-3 py-1.5 font-mono text-xs font-medium text-loss transition-colors hover:bg-loss/20"
                  >
                    <ThumbsDown className="h-3 w-3" /> Reject
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4 animate-in animate-in-delay-1">
        <div className="glow-border rounded-xl bg-surface p-4">
          <span className="font-mono text-[10px] uppercase tracking-wider text-muted">Today's Trades</span>
          <p className="mt-1 font-mono text-xl font-bold text-text">{summary.total_trades}</p>
        </div>
        <div className="glow-border rounded-xl bg-surface p-4">
          <span className="font-mono text-[10px] uppercase tracking-wider text-muted">Today's P&L</span>
          <p className={`mt-1 font-mono text-xl font-bold ${summary.total_pnl >= 0 ? 'text-gain' : 'text-loss'}`}>
            {formatCurrency(summary.total_pnl)}
          </p>
        </div>
        <div className="glow-border rounded-xl bg-surface p-4">
          <span className="font-mono text-[10px] uppercase tracking-wider text-muted">Fill Rate</span>
          <p className="mt-1 font-mono text-xl font-bold text-gain">{((quality.fill_rate ?? 0) * 100).toFixed(1)}%</p>
        </div>
        <div className="glow-border rounded-xl bg-surface p-4">
          <span className="font-mono text-[10px] uppercase tracking-wider text-muted">Total Orders</span>
          <p className="mt-1 font-mono text-xl font-bold text-text">{quality.total_trades ?? 0}</p>
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
                  filter === f ? 'bg-surface text-bright shadow-sm border border-border-bright' : 'text-muted hover:text-dim border border-transparent'
                }`}
              >
                {f}
              </button>
            ))}
          </div>
        </div>
        {filtered.length === 0 ? (
          <div className="px-4 py-8 text-center font-mono text-sm text-muted">No trades found</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border text-left">
                  {['Side', 'Symbol', 'Qty', 'Entry', 'Exit', 'P&L', 'P&L %', 'Hold', 'Strategy', 'Status'].map((h) => (
                    <th key={h} className="px-4 py-2.5 font-mono text-[10px] font-medium uppercase tracking-wider text-muted">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((t: any) => (
                  <tr key={t.id} className="border-b border-border/50 transition-colors hover:bg-panel/50">
                    <td className="px-4 py-2.5">
                      <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 font-mono text-[10px] font-medium ${t.side === 'BUY' ? 'bg-gain-dim text-gain' : 'bg-loss-dim text-loss'}`}>
                        {t.side === 'BUY' ? <ArrowUpRight className="h-2.5 w-2.5" /> : <ArrowDownRight className="h-2.5 w-2.5" />}
                        {t.side}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 font-mono text-sm font-semibold text-bright">{t.symbol}</td>
                    <td className="px-4 py-2.5 font-mono text-sm text-text">{t.quantity}</td>
                    <td className="px-4 py-2.5 font-mono text-sm text-dim">{formatCurrency(t.entry_price)}</td>
                    <td className="px-4 py-2.5 font-mono text-sm text-dim">{t.exit_price ? formatCurrency(t.exit_price) : '—'}</td>
                    <td className={`px-4 py-2.5 font-mono text-sm font-medium ${pnlColor(t.pnl)}`}>{formatCurrency(t.pnl)}</td>
                    <td className="px-4 py-2.5">
                      <span className={`inline-block rounded px-1.5 py-0.5 font-mono text-xs font-medium ${pnlColor(t.pnl_pct)} ${pnlBg(t.pnl_pct)}`}>
                        {formatPct(t.pnl_pct)}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 font-mono text-xs text-dim">{(t.hold_duration_days ?? 0).toFixed(1)}d</td>
                    <td className="px-4 py-2.5">
                      <span className="rounded border border-border bg-panel px-1.5 py-0.5 font-mono text-[10px] text-dim">{t.strategy_name}</span>
                    </td>
                    <td className="px-4 py-2.5">
                      {t.exit_time ? (
                        <span className="inline-flex items-center gap-1 font-mono text-[10px] text-dim"><CheckCircle2 className="h-3 w-3" /> Closed</span>
                      ) : (
                        <span className="inline-flex items-center gap-1 font-mono text-[10px] text-cyan live-pulse"><Clock className="h-3 w-3" /> Open</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
