import { useEffect } from 'react';
import { TrendingUp } from 'lucide-react';
import { useApi } from '../hooks/useApi';
import { useWebSocket } from '../hooks/useWebSocket';
import { api } from '../lib/api';
import type { RegimeAnalysis, AutonomyReadiness, GuardrailStatus } from '../lib/types';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';

const REGIME_COLORS: Record<string, string> = {
  BULL: 'text-gain',
  BEAR: 'text-loss',
  SIDEWAYS: 'text-amber',
  HIGH_VOLATILITY: 'text-loss',
};

const REGIME_BG: Record<string, string> = {
  BULL: 'border-gain/30 bg-gain-dim',
  BEAR: 'border-loss/30 bg-loss-dim',
  SIDEWAYS: 'border-amber/30 bg-amber-dim',
  HIGH_VOLATILITY: 'border-loss/30 bg-loss-dim',
};

// Stub data for Monte Carlo demo — replace with real API call in production
const STUB_MC_DATA = Array.from({ length: 252 }, (_, i) => ({
  day: i,
  p5: 10000 * Math.pow(1 + 0.0002, i) * (1 - 0.15 * (1 - i / 252)),
  p25: 10000 * Math.pow(1 + 0.0004, i) * (1 - 0.06 * (1 - i / 252)),
  p50: 10000 * Math.pow(1 + 0.0006, i),
  p75: 10000 * Math.pow(1 + 0.0008, i) * (1 + 0.04 * (i / 252)),
  p95: 10000 * Math.pow(1 + 0.001, i) * (1 + 0.12 * (i / 252)),
}));

function MonteCarloChart() {
  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <div className="font-mono text-[10px] uppercase tracking-wider text-muted">
          Monte Carlo (1Y, 10K runs)
        </div>
        <span className="rounded border border-amber/40 bg-amber-dim px-2 py-0.5 font-mono text-[9px] uppercase text-amber tracking-wider">
          Demo Data
        </span>
      </div>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={STUB_MC_DATA} margin={{ top: 4, right: 4, bottom: 4, left: 0 }}>
          <XAxis
            dataKey="day"
            tick={{ fontSize: 9, fontFamily: 'JetBrains Mono, monospace', fill: 'var(--color-muted)' }}
            axisLine={false}
            tickLine={false}
            interval={50}
            tickFormatter={(v) => `D${v}`}
          />
          <YAxis
            tick={{ fontSize: 9, fontFamily: 'JetBrains Mono, monospace', fill: 'var(--color-muted)' }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
            width={36}
          />
          <Tooltip
            contentStyle={{ background: 'var(--color-panel)', border: '1px solid var(--color-border)', borderRadius: 8 }}
            labelStyle={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 10, color: 'var(--color-muted)' }}
            itemStyle={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 10 }}
            formatter={(v) => [`$${Number(v).toFixed(0)}`, '']}
          />
          <ReferenceLine y={10000} stroke="var(--color-border)" strokeDasharray="3 3" />
          <Line type="monotone" dataKey="p95" stroke="var(--color-gain)" strokeWidth={1} dot={false} name="p95" />
          <Line type="monotone" dataKey="p75" stroke="var(--color-cyan)" strokeWidth={1} dot={false} name="p75" />
          <Line type="monotone" dataKey="p50" stroke="var(--color-bright)" strokeWidth={2} dot={false} name="p50 (median)" />
          <Line type="monotone" dataKey="p25" stroke="var(--color-amber)" strokeWidth={1} dot={false} name="p25" />
          <Line type="monotone" dataKey="p5" stroke="var(--color-loss)" strokeWidth={1} dot={false} name="p5" />
        </LineChart>
      </ResponsiveContainer>
      <div className="flex gap-4 mt-2 justify-center">
        {[
          { label: 'p95', color: 'text-gain' },
          { label: 'p75', color: 'text-cyan' },
          { label: 'p50', color: 'text-bright' },
          { label: 'p25', color: 'text-amber' },
          { label: 'p5', color: 'text-loss' },
        ].map(({ label, color }) => (
          <span key={label} className={`font-mono text-[9px] uppercase ${color}`}>{label}</span>
        ))}
      </div>
    </div>
  );
}

function AutonomyTransition({ readiness }: { readiness: AutonomyReadiness }) {
  return (
    <div className="space-y-3">
      <div className="font-mono text-[10px] uppercase tracking-wider text-muted mb-2">
        Current: <span className="text-cyan">{readiness.current_mode}</span>
      </div>
      {Object.entries(readiness.readiness).map(([mode, status]) => (
        <div key={mode} className="rounded-lg bg-panel px-3 py-2">
          <div className="flex items-center justify-between mb-1">
            <span className="font-mono text-xs text-dim">{mode}</span>
            <span className={`font-mono text-[9px] uppercase ${status.approved ? 'text-gain' : 'text-muted'}`}>
              {status.approved ? 'Ready' : 'Not Ready'}
            </span>
          </div>
          {status.blocking_reasons.length > 0 && (
            <ul className="space-y-0.5">
              {status.blocking_reasons.map((reason, i) => (
                <li key={i} className="font-mono text-[9px] text-loss/80 flex gap-1.5">
                  <span>·</span>{reason}
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </div>
  );
}

export function Analysis() {
  const { lastMessage } = useWebSocket();
  const { data: regimeRaw, loading: regimeLoading, refetch: refetchRegime } = useApi(() => api.analysis.regime([], []).catch(() => null));
  const { data: readinessRaw, loading: readinessLoading, error: readinessError } = useApi(() => api.risk.autonomyReadiness());
  const { data: guardrailsRaw, loading: guardrailsLoading } = useApi(() => api.risk.guardrailsStatus());

  useEffect(() => {
    if (lastMessage?.channel === 'agent:analysis') {
      refetchRegime();
    }
  }, [lastMessage]);

  const regime = regimeRaw as RegimeAnalysis | null;
  const readiness = readinessRaw as AutonomyReadiness | null;
  const guardrails = guardrailsRaw as GuardrailStatus | null;

  const regimeName = regime?.current_regime ?? 'SIDEWAYS';
  const regimeProb = ((regime?.regime_probability ?? 0.5) * 100).toFixed(0);

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <TrendingUp className="h-4 w-4 text-cyan" />
        <h1 className="font-mono text-sm font-semibold uppercase tracking-wider text-bright">
          Analysis
        </h1>
      </div>

      {/* Status bar */}
      <div className="glow-border rounded-xl bg-surface p-5">
        <div className="grid grid-cols-3 gap-4">
          <div className="rounded-lg bg-panel px-4 py-3">
            <div className="font-mono text-[9px] uppercase tracking-wider text-muted mb-1">
              Market Regime
            </div>
            {regimeLoading ? (
              <div className="font-mono text-sm text-muted">Loading...</div>
            ) : (
              <div className={`font-mono text-sm font-bold uppercase rounded border px-2 py-0.5 inline-block ${REGIME_BG[regimeName] ?? ''} ${REGIME_COLORS[regimeName] ?? 'text-dim'}`}>
                {regimeName}
              </div>
            )}
          </div>
          <div className="rounded-lg bg-panel px-4 py-3">
            <div className="font-mono text-[9px] uppercase tracking-wider text-muted mb-1">
              Regime Confidence
            </div>
            <div className="font-mono text-sm font-semibold text-bright">
              {regimeLoading ? '—' : `${regimeProb}%`}
            </div>
          </div>
          <div className="rounded-lg bg-panel px-4 py-3">
            <div className="font-mono text-[9px] uppercase tracking-wider text-muted mb-1">
              Guardrails
            </div>
            <div className={`font-mono text-sm font-semibold ${guardrails?.verified ? 'text-gain' : 'text-amber'}`}>
              {guardrailsLoading ? 'Loading...' : guardrails?.verified ? 'Verified' : guardrails?.last_verified ? `Stale (${guardrails.age_hours?.toFixed(1)}h)` : 'Unverified'}
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-6">
        {/* Monte Carlo fan chart */}
        <div className="glow-border rounded-xl bg-surface p-5">
          <MonteCarloChart />
        </div>

        {/* Regime history */}
        <div className="glow-border rounded-xl bg-surface p-5">
          <div className="font-mono text-[10px] uppercase tracking-wider text-muted mb-3">
            Regime History
          </div>
          {(regime?.regime_history?.length ?? 0) > 0 ? (
            <div className="space-y-1 max-h-48 overflow-y-auto">
              {regime?.regime_history?.slice(-20).reverse().map((entry, i) => (
                <div key={i} className="flex items-center justify-between rounded bg-panel px-3 py-1.5">
                  <span className="font-mono text-[9px] text-muted">Day {entry.day_index}</span>
                  <span className={`font-mono text-[9px] uppercase font-semibold ${REGIME_COLORS[entry.regime] ?? 'text-dim'}`}>
                    {entry.regime}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="font-mono text-[11px] text-muted">
              Provide spy_prices and vix_values to detect regime history
            </p>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-6">
        {/* Strategy allocation */}
        <div className="glow-border rounded-xl bg-surface p-5">
          <div className="font-mono text-[10px] uppercase tracking-wider text-muted mb-3">
            Optimal Strategy Allocation
          </div>
          <p className="font-mono text-[11px] text-muted">
            Run POST /api/analysis/optimize with strategy returns to view allocations.
          </p>
        </div>

        {/* Autonomy transition readiness */}
        <div className="glow-border rounded-xl bg-surface p-5">
          <div className="font-mono text-[10px] uppercase tracking-wider text-muted mb-3">
            Autonomy Mode Readiness
          </div>
          {readinessLoading ? (
            <p className="font-mono text-[11px] text-muted">Loading readiness data...</p>
          ) : readinessError ? (
            <p className="font-mono text-[11px] text-loss">Failed to load readiness data</p>
          ) : readiness ? (
            <AutonomyTransition readiness={readiness} />
          ) : (
            <p className="font-mono text-[11px] text-muted">No readiness data available</p>
          )}
        </div>
      </div>
    </div>
  );
}
