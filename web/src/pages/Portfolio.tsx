import { TrendingUp, TrendingDown, DollarSign, PieChart, BarChart3 } from 'lucide-react';
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart as RPieChart, Pie, Cell,
} from 'recharts';
import { StatCard } from '../components/StatCard';
import { formatCurrency, formatPct, pnlColor, pnlBg } from '../lib/format';
import { useApi } from '../hooks/useApi';
import { api } from '../lib/api';

const SECTOR_COLORS: Record<string, string> = {
  Technology: '#00e5ff', Financials: '#7c4dff', Healthcare: '#00e676',
  Energy: '#ffab00', Industrials: '#ff6d00', 'Consumer Discretionary': '#f50057',
  Materials: '#69f0ae', Utilities: '#b2ff59', Cash: '#2e3442',
};

export function Portfolio() {
  const { data: snapshot } = useApi(() => api.portfolio.snapshot());
  const { data: historyData } = useApi(() => api.portfolio.history(30));
  const { data: allocationData } = useApi(() => api.portfolio.allocation());

  const totalEquity = snapshot?.total_equity ?? 0;
  const totalPnl = snapshot?.daily_pnl ?? 0;
  const totalPnlPct = snapshot?.daily_pnl_pct ?? 0;
  const cash = snapshot?.cash ?? 0;
  const positionsValue = snapshot?.positions_value ?? 0;
  const positions = snapshot?.positions ?? [];

  const equityHistory = (historyData?.snapshots ?? []).map((s: any) => ({
    date: new Date(s.timestamp).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
    equity: s.total_equity,
  }));

  const sectors = allocationData?.sectors ?? {};
  const cashPct = allocationData?.cash_pct ?? 0;
  const allocation = [
    ...Object.entries(sectors).map(([name, value]) => ({
      name, value: value as number,
      color: SECTOR_COLORS[name] ?? '#8888aa',
    })),
    { name: 'Cash', value: cash, color: SECTOR_COLORS.Cash },
  ].filter(a => (a.value as number) > 0);

  return (
    <div className="space-y-6">
      {/* Top stat cards */}
      <div className="grid grid-cols-4 gap-4 animate-in">
        <StatCard
          label="Total Equity"
          value={formatCurrency(totalEquity)}
          sub={`${positions.length} position${positions.length !== 1 ? 's' : ''}`}
          icon={<DollarSign className="h-4 w-4" />}
          color="cyan"
        />
        <StatCard
          label="Daily P&L"
          value={formatCurrency(totalPnl)}
          sub={formatPct(totalPnlPct)}
          icon={totalPnl >= 0 ? <TrendingUp className="h-4 w-4 text-gain" /> : <TrendingDown className="h-4 w-4 text-loss" />}
          color={totalPnl >= 0 ? 'gain' : 'loss'}
        />
        <StatCard
          label="Cash"
          value={formatCurrency(cash)}
          sub={`${cashPct.toFixed(1)}% of equity`}
          icon={<BarChart3 className="h-4 w-4" />}
        />
        <StatCard
          label="Positions Value"
          value={formatCurrency(positionsValue)}
          sub={totalEquity > 0 ? `${(positionsValue / totalEquity * 100).toFixed(1)}% invested` : '—'}
          icon={<PieChart className="h-4 w-4" />}
        />
      </div>

      <div className="grid grid-cols-3 gap-4">
        {/* Equity curve */}
        <div className="col-span-2 glow-border rounded-xl bg-surface p-4 animate-in animate-in-delay-1">
          <h3 className="mb-4 font-mono text-[10px] uppercase tracking-wider text-muted">
            Account Value — 30 Days
          </h3>
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={equityHistory}>
              <defs>
                <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#00e5ff" stopOpacity={0.25} />
                  <stop offset="100%" stopColor="#00e5ff" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="date" tickLine={false} axisLine={false} tick={{ fontSize: 10 }} />
              <YAxis
                tickLine={false}
                axisLine={false}
                tick={{ fontSize: 10 }}
                domain={['dataMin - 200', 'dataMax + 200']}
                tickFormatter={(v) => `$${(Number(v) / 1000).toFixed(1)}K`}
              />
              <Tooltip
                contentStyle={{ background: '#181c25', border: '1px solid #232833', borderRadius: 8, fontFamily: 'JetBrains Mono', fontSize: 12 }}
                formatter={(v) => [formatCurrency(Number(v)), 'Equity']}
              />
              <Area type="monotone" dataKey="equity" stroke="#00e5ff" strokeWidth={2} fill="url(#equityGrad)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Allocation donut */}
        <div className="glow-border rounded-xl bg-surface p-4 animate-in animate-in-delay-2">
          <h3 className="mb-4 font-mono text-[10px] uppercase tracking-wider text-muted">Allocation</h3>
          <ResponsiveContainer width="100%" height={180}>
            <RPieChart>
              <Pie data={allocation} cx="50%" cy="50%" innerRadius={55} outerRadius={80} paddingAngle={2} dataKey="value" stroke="none">
                {allocation.map((entry) => (
                  <Cell key={entry.name} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{ background: '#181c25', border: '1px solid #232833', borderRadius: 8, fontFamily: 'JetBrains Mono', fontSize: 11 }}
                formatter={(v) => [formatCurrency(Number(v))]}
              />
            </RPieChart>
          </ResponsiveContainer>
          <div className="mt-2 space-y-1.5">
            {allocation.map((a) => (
              <div key={a.name} className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-2">
                  <div className="h-2 w-2 rounded-full" style={{ backgroundColor: a.color }} />
                  <span className="text-dim">{a.name}</span>
                </div>
                <span className="font-mono text-text">
                  {totalEquity > 0 ? ((a.value / totalEquity) * 100).toFixed(1) : '0.0'}%
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Positions table */}
      <div className="glow-border rounded-xl bg-surface animate-in animate-in-delay-3">
        <div className="border-b border-border px-4 py-3">
          <h3 className="font-mono text-[10px] uppercase tracking-wider text-muted">Open Positions</h3>
        </div>
        {positions.length === 0 ? (
          <div className="px-4 py-8 text-center font-mono text-sm text-muted">No open positions</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border text-left">
                  {['Symbol', 'Qty', 'Avg Entry', 'Current', 'Mkt Value', 'P&L', 'P&L %', 'Sector', 'Strategy'].map((h) => (
                    <th key={h} className="px-4 py-2.5 font-mono text-[10px] font-medium uppercase tracking-wider text-muted">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {positions.map((p: any) => (
                  <tr key={p.symbol} className="border-b border-border/50 transition-colors hover:bg-panel/50">
                    <td className="px-4 py-2.5 font-mono text-sm font-semibold text-bright">{p.symbol}</td>
                    <td className="px-4 py-2.5 font-mono text-sm text-text">{p.quantity}</td>
                    <td className="px-4 py-2.5 font-mono text-sm text-dim">{formatCurrency(p.avg_entry_price)}</td>
                    <td className="px-4 py-2.5 font-mono text-sm text-text">{formatCurrency(p.current_price)}</td>
                    <td className="px-4 py-2.5 font-mono text-sm text-text">{formatCurrency(p.market_value)}</td>
                    <td className={`px-4 py-2.5 font-mono text-sm font-medium ${pnlColor(p.unrealized_pnl)}`}>{formatCurrency(p.unrealized_pnl)}</td>
                    <td className="px-4 py-2.5">
                      <span className={`inline-block rounded px-1.5 py-0.5 font-mono text-xs font-medium ${pnlColor(p.unrealized_pnl_pct)} ${pnlBg(p.unrealized_pnl_pct)}`}>
                        {formatPct(p.unrealized_pnl_pct)}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-xs text-dim">{p.sector || '—'}</td>
                    <td className="px-4 py-2.5">
                      <span className="rounded border border-border bg-panel px-1.5 py-0.5 font-mono text-[10px] text-dim">
                        {p.strategy_name || '—'}
                      </span>
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
