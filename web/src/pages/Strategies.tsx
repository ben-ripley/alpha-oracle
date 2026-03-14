import { useState, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { Trophy, ShieldCheck, HelpCircle, X, ExternalLink, Sparkles, Play, Loader2 } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { formatPct, formatNumber } from '../lib/format';
import { useApi } from '../hooks/useApi';
import { api } from '../lib/api';
import { STRATEGY_DESCRIPTIONS, type StrategyDescription } from '../lib/strategyDescriptions';
import { SignalFeed } from '../components/SignalFeed';
import { FeatureImportance } from '../components/FeatureImportance';
import { ModelPerformance } from '../components/ModelPerformance';

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

// ---------------------------------------------------------------------------
// Strategy Help Popover
// ---------------------------------------------------------------------------

function StrategyHelp({
  desc,
  anchor,
  onClose,
}: {
  desc: StrategyDescription;
  anchor: HTMLElement;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const rect = anchor.getBoundingClientRect();
  const left = Math.max(8, rect.right - 480);
  const top = rect.bottom + 8;

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (
        ref.current &&
        !ref.current.contains(e.target as Node) &&
        !anchor.contains(e.target as Node)
      ) {
        onClose();
      }
    }
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    document.addEventListener('mousedown', handleClick);
    document.addEventListener('keydown', handleKey);
    return () => {
      document.removeEventListener('mousedown', handleClick);
      document.removeEventListener('keydown', handleKey);
    };
  }, [anchor, onClose]);

  return createPortal(
    <div
      ref={ref}
      className="fixed z-[9999] w-[480px] rounded-xl border border-border bg-surface shadow-2xl"
      style={{ top, left, boxShadow: '0 0 40px rgba(0,0,0,0.6)' }}
    >
      {/* Header */}
      <div className="flex items-start justify-between border-b border-border px-5 py-4">
        <div>
          <h4 className="font-mono text-sm font-semibold text-bright">{desc.displayName}</h4>
          <p className="mt-0.5 text-xs text-cyan">{desc.tagline}</p>
        </div>
        <button onClick={onClose} className="ml-4 mt-0.5 shrink-0 text-muted hover:text-text transition-colors">
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Scrollable body */}
      <div className="max-h-[60vh] overflow-y-auto px-5 py-4 space-y-4">
        {/* Sections */}
        {desc.sections.map((s) => (
          <div key={s.title}>
            <div className="mb-1 font-mono text-[10px] uppercase tracking-wider text-cyan">{s.title}</div>
            <p className="text-xs leading-relaxed text-dim">{s.body}</p>
          </div>
        ))}

        {/* Parameters table */}
        <div>
          <div className="mb-2 font-mono text-[10px] uppercase tracking-wider text-cyan">Parameters</div>
          <div className="rounded-lg border border-border overflow-hidden">
            <table className="w-full text-xs">
              <tbody>
                {desc.parameters.map((p, i) => (
                  <tr key={p.label} className={i % 2 === 0 ? 'bg-panel' : 'bg-surface'}>
                    <td className="px-3 py-1.5 font-mono text-muted whitespace-nowrap">{p.label}</td>
                    <td className="px-3 py-1.5 font-mono font-semibold text-bright whitespace-nowrap">{p.value}</td>
                    <td className="px-3 py-1.5 text-dim">{p.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Best for / Risks */}
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-lg border border-gain/20 bg-gain-dim px-3 py-2.5">
            <div className="mb-1 font-mono text-[9px] uppercase tracking-wider text-gain">Best For</div>
            <p className="text-xs leading-relaxed text-dim">{desc.bestFor}</p>
          </div>
          <div className="rounded-lg border border-loss/20 bg-loss-dim px-3 py-2.5">
            <div className="mb-1 font-mono text-[9px] uppercase tracking-wider text-loss">Key Risks</div>
            <p className="text-xs leading-relaxed text-dim">{desc.risks}</p>
          </div>
        </div>

        {/* References */}
        {desc.references.length > 0 && (
          <div>
            <div className="mb-2 font-mono text-[10px] uppercase tracking-wider text-cyan">Academic References</div>
            <div className="space-y-1.5">
              {desc.references.map((ref) => (
                <a
                  key={ref.url}
                  href={ref.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-2 rounded-lg border border-border bg-panel px-3 py-2 text-xs text-dim hover:border-cyan/40 hover:text-cyan transition-colors"
                >
                  <ExternalLink className="h-3 w-3 shrink-0 text-muted" />
                  {ref.label}
                </a>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>,
    document.body,
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function Strategies() {
  const { data: rankingsData } = useApi(() => api.strategies.rankings());
  const { data: resultsData } = useApi(() => api.strategies.results());
  const { data: listData } = useApi(() => api.strategies.list());

  const [openHelp, setOpenHelp] = useState<{ name: string; anchor: HTMLElement } | null>(null);

  const rankings: any[] = Array.isArray(rankingsData) ? rankingsData : [];
  const results: any[] = resultsData?.results ?? [];
  const strategyList: any[] = listData?.strategies ?? [];

  // Merge rankings + backtest results + strategy list metadata
  const strategies = rankings.map((r: any, idx: number) => {
    const result = results.find((res: any) => res.strategy_name === r.strategy_name);
    const meta = strategyList.find((s: any) => s.name === r.strategy_name);
    const holdDays = meta?.min_hold_days ?? 2;
    return {
      ...r,
      description: meta?.description ?? r.strategy_name,
      hold: `${holdDays}+ days`,
      equity: result?.equity_curve?.map((p: any) => ({ x: p.date, y: p.equity })) ?? [],
      total_trades: result?.total_trades ?? r.total_trades,
      idx,
    };
  });

  type BacktestState =
    | { phase: 'idle' }
    | { phase: 'running'; jobId: string; estimatedSeconds: number; startedAt: number }
    | { phase: 'complete'; result: any }
    | { phase: 'failed'; error: string };

  const [backtestState, setBacktestState] = useState<BacktestState>({ phase: 'idle' });
  const [progress, setProgress] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [btForm, setBtForm] = useState({
    strategy_name: '',
    symbols: '',
    start_date: '2024-01-01',
    end_date: '',
    initial_capital: '20000',
  });

  // Progress bar ticker -- advances every 100ms while running
  useEffect(() => {
    if (backtestState.phase !== 'running') return;
    const { startedAt, estimatedSeconds } = backtestState;
    const interval = setInterval(() => {
      const elapsedMs = Date.now() - startedAt;
      setProgress(Math.min(elapsedMs / (estimatedSeconds * 1000), 0.95));
      setElapsed(Math.round(elapsedMs / 1000));
    }, 100);
    return () => clearInterval(interval);
  }, [backtestState]);

  // Job polling -- checks status every 2s while running
  useEffect(() => {
    if (backtestState.phase !== 'running') return;
    const { jobId } = backtestState;
    const interval = setInterval(async () => {
      try {
        const job = await api.strategies.backtestJob(jobId);
        if (job.status === 'complete') {
          setProgress(1);
          setTimeout(() => {
            setBacktestState({ phase: 'complete', result: job.result });
          }, 300);
          clearInterval(interval);
        } else if (job.status === 'failed') {
          setBacktestState({ phase: 'failed', error: job.error ?? 'Unknown error' });
          clearInterval(interval);
        }
      } catch {
        // transient error -- keep polling
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [backtestState]);

  const handleRunBacktest = async () => {
    if (backtestState.phase === 'running') return;
    setBacktestState({ phase: 'idle' });
    setProgress(0);
    setElapsed(0);
    try {
      const symbols = btForm.symbols.split(',').map(s => s.trim()).filter(Boolean);
      const payload: any = {
        strategy_name: btForm.strategy_name,
        symbols,
        start_date: btForm.start_date,
        initial_capital: parseFloat(btForm.initial_capital) || 20000,
      };
      if (btForm.end_date) payload.end_date = btForm.end_date;
      const res = await api.strategies.backtest(payload);
      setBacktestState({
        phase: 'running',
        jobId: res.job_id,
        estimatedSeconds: res.estimated_seconds ?? 5,
        startedAt: Date.now(),
      });
    } catch (err: any) {
      setBacktestState({ phase: 'failed', error: err.message ?? 'Failed to submit backtest' });
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between animate-in">
        <h2 className="font-mono text-xs uppercase tracking-wider text-muted">Strategy Rankings</h2>
        <div className="flex items-center gap-2 text-xs text-dim">
          <ShieldCheck className="h-3.5 w-3.5" />
          Thresholds: Sharpe &gt; 1.0 &middot; DD &lt; 20% &middot; PF &gt; 1.5 &middot; 100+ trades
        </div>
      </div>

      {strategies.length === 0 ? (
        <div className="glow-border rounded-xl bg-surface p-8 text-center font-mono text-sm text-muted">
          No rankings available. Run the seed script to load demo data.
        </div>
      ) : (
        <div className="space-y-4">
          {strategies.map((s) => (
            <div key={s.strategy_name} className={`glow-border rounded-xl bg-surface animate-in animate-in-delay-${s.idx + 1}`}>
              <div className="flex gap-6 p-5">
                {/* Score */}
                <div className="flex flex-col items-center gap-2 pr-6 border-r border-border">
                  <div className={`flex h-16 w-16 items-center justify-center rounded-xl border ${scoreBg(s.composite_score)}`}>
                    <span className={`font-mono text-2xl font-bold ${scoreColor(s.composite_score)}`}>
                      {s.composite_score.toFixed(0)}
                    </span>
                  </div>
                  <span className="font-mono text-[9px] uppercase tracking-wider text-muted">Score</span>
                  {s.idx === 0 && <Trophy className="h-4 w-4 text-amber" />}
                </div>

                {/* Details */}
                <div className="flex-1 space-y-3">
                  <div className="flex items-center gap-3">
                    <h3 className="font-mono text-base font-semibold text-bright">{s.strategy_name}</h3>
                    {s.meets_thresholds ? (
                      <span className="rounded border border-gain/30 bg-gain-dim px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-gain">Meets Thresholds</span>
                    ) : (
                      <span className="rounded border border-loss/30 bg-loss-dim px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-loss">Below Thresholds</span>
                    )}

                    {/* Help button */}
                    {STRATEGY_DESCRIPTIONS[s.strategy_name] && (
                      <div className="ml-auto">
                        <button
                          onClick={(e) => {
                            const btn = e.currentTarget;
                            setOpenHelp(
                              openHelp?.name === s.strategy_name
                                ? null
                                : { name: s.strategy_name, anchor: btn },
                            );
                          }}
                          className="flex items-center gap-1 rounded border border-border px-2 py-0.5 font-mono text-[9px] uppercase tracking-wider text-muted hover:border-cyan/40 hover:text-cyan transition-colors"
                          title="How this strategy works"
                        >
                          <HelpCircle className="h-3 w-3" />
                          How it works
                        </button>
                      </div>
                    )}
                  </div>
                  <p className="text-sm text-dim">{s.description}</p>
                  <div className="grid grid-cols-6 gap-3 pt-2">
                    {[
                      { label: 'Sharpe', value: formatNumber(s.sharpe_ratio), ok: s.sharpe_ratio >= 1.0 },
                      { label: 'Sortino', value: formatNumber(s.sortino_ratio), ok: true },
                      { label: 'Max DD', value: formatPct(-s.max_drawdown_pct), ok: s.max_drawdown_pct <= 20 },
                      { label: 'Profit Factor', value: formatNumber(s.profit_factor), ok: s.profit_factor >= 1.5 },
                      { label: 'Win Rate', value: formatPct(s.win_rate, 1), ok: true },
                      { label: 'Trades', value: String(s.total_trades), ok: s.total_trades >= 100 },
                    ].map((m) => (
                      <div key={m.label} className="rounded-lg bg-panel px-3 py-2">
                        <div className="font-mono text-[9px] uppercase tracking-wider text-muted">{m.label}</div>
                        <div className={`font-mono text-sm font-semibold ${m.ok ? 'text-text' : 'text-loss'}`}>{m.value}</div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Mini equity curve */}
                {s.equity.length > 0 && (
                  <div className="w-56 shrink-0">
                    <div className="font-mono text-[9px] uppercase tracking-wider text-muted mb-1">Equity Curve</div>
                    <ResponsiveContainer width="100%" height={120}>
                      <AreaChart data={s.equity}>
                        <defs>
                          <linearGradient id={`grad-${s.strategy_name}`} x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor={s.meets_thresholds ? '#00e676' : '#ffab00'} stopOpacity={0.2} />
                            <stop offset="100%" stopColor={s.meets_thresholds ? '#00e676' : '#ffab00'} stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <Area type="monotone" dataKey="y" stroke={s.meets_thresholds ? '#00e676' : '#ffab00'} strokeWidth={1.5} fill={`url(#grad-${s.strategy_name})`} />
                        <XAxis dataKey="x" hide />
                        <YAxis hide domain={['dataMin - 500', 'dataMax + 500']} />
                        <Tooltip
                          contentStyle={{ background: '#181c25', border: '1px solid #232833', borderRadius: 8, fontFamily: 'JetBrains Mono', fontSize: 11 }}
                          formatter={(v) => [`$${Number(v).toFixed(0)}`, 'Equity']}
                          labelFormatter={() => ''}
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Run Backtest */}
      <div className="animate-in">
        <div className="flex items-center gap-2 mb-4">
          <Play className="h-3.5 w-3.5 text-cyan" />
          <h2 className="font-mono text-xs uppercase tracking-wider text-muted">Run Backtest</h2>
        </div>
        <div className="glow-border rounded-xl bg-surface p-5 space-y-4">
          {/* Form */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="font-mono text-[9px] uppercase tracking-wider text-muted block mb-1">Strategy</label>
              <select
                className="w-full rounded-lg border border-border bg-panel px-3 py-2 font-mono text-xs text-text focus:border-cyan/50 focus:outline-none"
                value={btForm.strategy_name}
                onChange={e => setBtForm(f => ({ ...f, strategy_name: e.target.value }))}
              >
                <option value="">Select strategy...</option>
                {strategyList.map((s: any) => (
                  <option key={s.name} value={s.name}>{s.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="font-mono text-[9px] uppercase tracking-wider text-muted block mb-1">Symbols (comma-separated)</label>
              <input
                className="w-full rounded-lg border border-border bg-panel px-3 py-2 font-mono text-xs text-text placeholder:text-muted focus:border-cyan/50 focus:outline-none"
                placeholder="AAPL, MSFT, GOOG"
                value={btForm.symbols}
                onChange={e => setBtForm(f => ({ ...f, symbols: e.target.value }))}
              />
            </div>
            <div>
              <label className="font-mono text-[9px] uppercase tracking-wider text-muted block mb-1">Start Date</label>
              <input
                type="date"
                className="w-full rounded-lg border border-border bg-panel px-3 py-2 font-mono text-xs text-text focus:border-cyan/50 focus:outline-none"
                value={btForm.start_date}
                onChange={e => setBtForm(f => ({ ...f, start_date: e.target.value }))}
              />
            </div>
            <div>
              <label className="font-mono text-[9px] uppercase tracking-wider text-muted block mb-1">End Date (optional)</label>
              <input
                type="date"
                className="w-full rounded-lg border border-border bg-panel px-3 py-2 font-mono text-xs text-text focus:border-cyan/50 focus:outline-none"
                value={btForm.end_date}
                onChange={e => setBtForm(f => ({ ...f, end_date: e.target.value }))}
              />
            </div>
            <div>
              <label className="font-mono text-[9px] uppercase tracking-wider text-muted block mb-1">Initial Capital ($)</label>
              <input
                type="number"
                className="w-full rounded-lg border border-border bg-panel px-3 py-2 font-mono text-xs text-text focus:border-cyan/50 focus:outline-none"
                value={btForm.initial_capital}
                onChange={e => setBtForm(f => ({ ...f, initial_capital: e.target.value }))}
              />
            </div>
            <div className="flex items-end">
              <button
                onClick={handleRunBacktest}
                disabled={backtestState.phase === 'running' || !btForm.strategy_name || !btForm.symbols}
                className="w-full rounded-lg border border-cyan/40 bg-cyan/10 px-4 py-2 font-mono text-xs font-semibold text-cyan hover:bg-cyan/20 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {backtestState.phase === 'running' ? 'Running...' : 'Run Backtest'}
              </button>
            </div>
          </div>

          {/* Progress bar */}
          {backtestState.phase === 'running' && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 font-mono text-xs text-dim">
                  <Loader2 className="h-3 w-3 animate-spin text-cyan" />
                  Running... {elapsed}s
                </div>
                <span className="font-mono text-xs text-muted">{Math.round(progress * 100)}%</span>
              </div>
              <div className="h-1.5 w-full rounded-full bg-panel overflow-hidden">
                <div
                  className="h-full rounded-full bg-cyan transition-all duration-100"
                  style={{ width: `${progress * 100}%` }}
                />
              </div>
            </div>
          )}

          {/* Error state */}
          {backtestState.phase === 'failed' && (
            <div className="rounded-lg border border-loss/30 bg-loss-dim px-4 py-3 font-mono text-xs text-loss">
              {backtestState.error}
            </div>
          )}

          {/* Results card */}
          {backtestState.phase === 'complete' && backtestState.result && (
            <div className="space-y-3">
              <div className="font-mono text-[9px] uppercase tracking-wider text-cyan">Backtest Results</div>
              <div className="grid grid-cols-4 gap-3">
                {[
                  { label: 'Total Return', value: `${backtestState.result.total_return_pct?.toFixed(1)}%` },
                  { label: 'Annual Return', value: `${backtestState.result.annual_return_pct?.toFixed(1)}%` },
                  { label: 'Sharpe', value: backtestState.result.sharpe_ratio?.toFixed(2) },
                  { label: 'Sortino', value: backtestState.result.sortino_ratio?.toFixed(2) },
                  { label: 'Max DD', value: `${backtestState.result.max_drawdown_pct?.toFixed(1)}%` },
                  { label: 'Profit Factor', value: backtestState.result.profit_factor?.toFixed(2) },
                  { label: 'Win Rate', value: `${((backtestState.result.win_rate ?? 0) * 100).toFixed(1)}%` },
                  { label: 'Trades', value: String(backtestState.result.total_trades ?? 0) },
                ].map(m => (
                  <div key={m.label} className="rounded-lg bg-panel px-3 py-2">
                    <div className="font-mono text-[9px] uppercase tracking-wider text-muted">{m.label}</div>
                    <div className="font-mono text-sm font-semibold text-text">{m.value}</div>
                  </div>
                ))}
              </div>
              <button
                onClick={() => { setBacktestState({ phase: 'idle' }); setProgress(0); setElapsed(0); }}
                className="font-mono text-[9px] uppercase tracking-wider text-muted hover:text-text transition-colors"
              >
                Run another
              </button>
            </div>
          )}
        </div>
      </div>

      {openHelp && STRATEGY_DESCRIPTIONS[openHelp.name] && (
        <StrategyHelp
          desc={STRATEGY_DESCRIPTIONS[openHelp.name]}
          anchor={openHelp.anchor}
          onClose={() => setOpenHelp(null)}
        />
      )}

      {/* ML Signal Intelligence */}
      <div className="animate-in">
        <div className="flex items-center gap-2 mb-4">
          <Sparkles className="h-3.5 w-3.5 text-cyan" />
          <h2 className="font-mono text-xs uppercase tracking-wider text-muted">ML Signal Intelligence</h2>
        </div>
        <div className="glow-border rounded-xl bg-surface p-5">
          <div className="grid grid-cols-3 gap-6">
            <div className="col-span-2">
              <SignalFeed />
            </div>
            <div className="space-y-6">
              <FeatureImportance />
              <ModelPerformance />
            </div>
          </div>
        </div>
      </div>

    </div>
  );
}
