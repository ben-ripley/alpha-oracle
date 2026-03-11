import { TrendingUp, TrendingDown, DollarSign, PieChart, BarChart3 } from 'lucide-react';
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart as RPieChart, Pie, Cell,
} from 'recharts';
import { StatCard } from '../components/StatCard';
import { formatCurrency, formatPct, pnlColor, pnlBg } from '../lib/format';

// Demo data for rendering — replaced by API calls in production
const EQUITY_HISTORY = Array.from({ length: 30 }, (_, i) => ({
  date: new Date(Date.now() - (29 - i) * 86400000).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
  equity: 20000 + Math.sin(i / 4) * 800 + i * 50 + Math.random() * 200,
}));

const POSITIONS = [
  { symbol: 'AAPL', quantity: 15, avg_entry_price: 178.50, current_price: 183.20, market_value: 2748.00, unrealized_pnl: 70.50, unrealized_pnl_pct: 2.63, sector: 'Technology', strategy_name: 'SwingMomentum' },
  { symbol: 'MSFT', quantity: 8, avg_entry_price: 415.00, current_price: 422.80, market_value: 3382.40, unrealized_pnl: 62.40, unrealized_pnl_pct: 1.88, sector: 'Technology', strategy_name: 'MeanReversion' },
  { symbol: 'JPM', quantity: 12, avg_entry_price: 195.20, current_price: 192.10, market_value: 2305.20, unrealized_pnl: -37.20, unrealized_pnl_pct: -1.59, sector: 'Financials', strategy_name: 'ValueFactor' },
  { symbol: 'UNH', quantity: 4, avg_entry_price: 528.00, current_price: 541.50, market_value: 2166.00, unrealized_pnl: 54.00, unrealized_pnl_pct: 2.56, sector: 'Healthcare', strategy_name: 'SwingMomentum' },
  { symbol: 'XOM', quantity: 20, avg_entry_price: 105.40, current_price: 103.20, market_value: 2064.00, unrealized_pnl: -44.00, unrealized_pnl_pct: -2.09, sector: 'Energy', strategy_name: 'ValueFactor' },
];

const ALLOCATION = [
  { name: 'Technology', value: 6130.40, color: '#00e5ff' },
  { name: 'Financials', value: 2305.20, color: '#7c4dff' },
  { name: 'Healthcare', value: 2166.00, color: '#00e676' },
  { name: 'Energy', value: 2064.00, color: '#ffab00' },
  { name: 'Cash', value: 8819.72, color: '#2e3442' },
];

export function Portfolio() {
  const totalEquity = 21485.32;
  const totalPnl = 105.70;
  const totalPnlPct = 0.53;

  return (
    <div className="space-y-6">
      {/* Top stat cards */}
      <div className="grid grid-cols-4 gap-4 animate-in">
        <StatCard
          label="Total Equity"
          value={formatCurrency(totalEquity)}
          sub="5 positions"
          icon={<DollarSign className="h-4 w-4" />}
          color="cyan"
        />
        <StatCard
          label="Unrealized P&L"
          value={formatCurrency(totalPnl)}
          sub={formatPct(totalPnlPct)}
          icon={totalPnl >= 0 ? <TrendingUp className="h-4 w-4 text-gain" /> : <TrendingDown className="h-4 w-4 text-loss" />}
          color={totalPnl >= 0 ? 'gain' : 'loss'}
        />
        <StatCard
          label="Cash"
          value={formatCurrency(8819.72)}
          sub="41.1% of equity"
          icon={<BarChart3 className="h-4 w-4" />}
        />
        <StatCard
          label="Positions Value"
          value={formatCurrency(12665.60)}
          sub="58.9% invested"
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
            <AreaChart data={EQUITY_HISTORY}>
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
                tickFormatter={(v: number) => `$${(v / 1000).toFixed(1)}K`}
              />
              <Tooltip
                contentStyle={{
                  background: '#181c25',
                  border: '1px solid #232833',
                  borderRadius: 8,
                  fontFamily: 'JetBrains Mono',
                  fontSize: 12,
                }}
                formatter={(v: number) => [formatCurrency(v), 'Equity']}
              />
              <Area
                type="monotone"
                dataKey="equity"
                stroke="#00e5ff"
                strokeWidth={2}
                fill="url(#equityGrad)"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Allocation donut */}
        <div className="glow-border rounded-xl bg-surface p-4 animate-in animate-in-delay-2">
          <h3 className="mb-4 font-mono text-[10px] uppercase tracking-wider text-muted">
            Allocation
          </h3>
          <ResponsiveContainer width="100%" height={180}>
            <RPieChart>
              <Pie
                data={ALLOCATION}
                cx="50%"
                cy="50%"
                innerRadius={55}
                outerRadius={80}
                paddingAngle={2}
                dataKey="value"
                stroke="none"
              >
                {ALLOCATION.map((entry) => (
                  <Cell key={entry.name} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{
                  background: '#181c25',
                  border: '1px solid #232833',
                  borderRadius: 8,
                  fontFamily: 'JetBrains Mono',
                  fontSize: 11,
                }}
                formatter={(v: number) => [formatCurrency(v)]}
              />
            </RPieChart>
          </ResponsiveContainer>
          <div className="mt-2 space-y-1.5">
            {ALLOCATION.map((a) => (
              <div key={a.name} className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-2">
                  <div className="h-2 w-2 rounded-full" style={{ backgroundColor: a.color }} />
                  <span className="text-dim">{a.name}</span>
                </div>
                <span className="font-mono text-text">{((a.value / totalEquity) * 100).toFixed(1)}%</span>
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
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border text-left">
                {['Symbol', 'Qty', 'Avg Entry', 'Current', 'Mkt Value', 'P&L', 'P&L %', 'Sector', 'Strategy'].map((h) => (
                  <th key={h} className="px-4 py-2.5 font-mono text-[10px] font-medium uppercase tracking-wider text-muted">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {POSITIONS.map((p) => (
                <tr key={p.symbol} className="border-b border-border/50 transition-colors hover:bg-panel/50">
                  <td className="px-4 py-2.5 font-mono text-sm font-semibold text-bright">{p.symbol}</td>
                  <td className="px-4 py-2.5 font-mono text-sm text-text">{p.quantity}</td>
                  <td className="px-4 py-2.5 font-mono text-sm text-dim">{formatCurrency(p.avg_entry_price)}</td>
                  <td className="px-4 py-2.5 font-mono text-sm text-text">{formatCurrency(p.current_price)}</td>
                  <td className="px-4 py-2.5 font-mono text-sm text-text">{formatCurrency(p.market_value)}</td>
                  <td className={`px-4 py-2.5 font-mono text-sm font-medium ${pnlColor(p.unrealized_pnl)}`}>
                    {formatCurrency(p.unrealized_pnl)}
                  </td>
                  <td className="px-4 py-2.5">
                    <span className={`inline-block rounded px-1.5 py-0.5 font-mono text-xs font-medium ${pnlColor(p.unrealized_pnl_pct)} ${pnlBg(p.unrealized_pnl_pct)}`}>
                      {formatPct(p.unrealized_pnl_pct)}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-xs text-dim">{p.sector}</td>
                  <td className="px-4 py-2.5">
                    <span className="rounded border border-border bg-panel px-1.5 py-0.5 font-mono text-[10px] text-dim">
                      {p.strategy_name}
                    </span>
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
