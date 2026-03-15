import { useState, useEffect } from 'react';
import { Bot } from 'lucide-react';
import { useApi } from '../hooks/useApi';
import { useWebSocket } from '../hooks/useWebSocket';
import { api } from '../lib/api';
import type { LLMCostSummary, DailyBriefing, TradeRecommendation, AgentAnalysis } from '../lib/types';

function CostBar({ label, value, budget }: { label: string; value: number; budget: number }) {
  const pct = budget > 0 ? Math.min(100, (value / budget) * 100) : 0;
  const color = pct > 90 ? 'bg-loss' : pct > 70 ? 'bg-amber' : 'bg-cyan';
  return (
    <div>
      <div className="flex justify-between font-mono text-[10px] text-muted mb-1">
        <span>{label}</span>
        <span className="text-dim">${value.toFixed(4)} / ${budget.toFixed(2)}</span>
      </div>
      <div className="h-1.5 w-full rounded-full bg-panel">
        <div className={`h-1.5 rounded-full ${color} transition-all`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function RecommendationCard({ rec }: { rec: TradeRecommendation }) {
  const [isLoading, setIsLoading] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const actionColor =
    rec.action === 'BUY' ? 'text-gain' :
    rec.action === 'SELL' ? 'text-loss' : 'text-amber';

  const approvalBadge =
    rec.human_approved === true ? (
      <span className="rounded border border-gain/30 bg-gain-dim px-2 py-0.5 font-mono text-[9px] uppercase text-gain">Approved</span>
    ) : rec.human_approved === false ? (
      <span className="rounded border border-loss/30 bg-loss-dim px-2 py-0.5 font-mono text-[9px] uppercase text-loss">Rejected</span>
    ) : (
      <span className="rounded border border-amber/30 bg-amber-dim px-2 py-0.5 font-mono text-[9px] uppercase text-amber">Pending</span>
    );

  const handleApprove = async () => {
    if (!rec.id || isLoading) return;
    setIsLoading(true);
    setActionError(null);
    try {
      await api.agent.approveRecommendation(rec.id);
    } catch {
      setActionError('Failed to approve — please retry');
    } finally {
      setIsLoading(false);
    }
  };
  const handleReject = async () => {
    if (!rec.id || isLoading) return;
    setIsLoading(true);
    setActionError(null);
    try {
      await api.agent.rejectRecommendation(rec.id);
    } catch {
      setActionError('Failed to reject — please retry');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="rounded-lg bg-panel p-4 space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="font-mono text-sm font-bold text-bright">{rec.symbol}</span>
          <span className={`font-mono text-xs font-semibold ${actionColor}`}>{rec.action}</span>
          <span className="font-mono text-[10px] text-muted">
            conf {(rec.confidence * 100).toFixed(0)}%
          </span>
        </div>
        {approvalBadge}
      </div>
      <p className="font-mono text-[11px] text-dim leading-relaxed">{rec.rationale}</p>
      {rec.risk_factors.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {rec.risk_factors.map((rf, i) => (
            <span key={i} className="rounded border border-loss/20 bg-loss-dim px-1.5 py-0.5 font-mono text-[9px] text-loss/80">
              {rf}
            </span>
          ))}
        </div>
      )}
      {rec.human_approved === null && (
        <div className="space-y-1 pt-1">
          <div className="flex gap-2">
            <button
              onClick={handleApprove}
              disabled={isLoading}
              className="rounded border border-gain/40 bg-gain-dim px-3 py-1 font-mono text-[10px] uppercase text-gain hover:bg-gain/20 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {isLoading ? '...' : 'Approve'}
            </button>
            <button
              onClick={handleReject}
              disabled={isLoading}
              className="rounded border border-loss/40 bg-loss-dim px-3 py-1 font-mono text-[10px] uppercase text-loss hover:bg-loss/20 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {isLoading ? '...' : 'Reject'}
            </button>
          </div>
          {actionError && (
            <p className="font-mono text-[9px] text-loss">{actionError}</p>
          )}
        </div>
      )}
    </div>
  );
}

function AnalysisCard({ analysis }: { analysis: AgentAnalysis }) {
  const sentColor = analysis.sentiment_score > 0.1 ? 'text-gain' : analysis.sentiment_score < -0.1 ? 'text-loss' : 'text-amber';
  return (
    <div className="rounded-lg bg-panel p-4 space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="font-mono text-sm font-bold text-bright">{analysis.symbol}</span>
          <span className="font-mono text-[10px] text-muted uppercase">{analysis.analysis_type}</span>
        </div>
        <span className={`font-mono text-xs font-semibold ${sentColor}`}>
          {analysis.sentiment_score > 0 ? '+' : ''}{analysis.sentiment_score.toFixed(2)}
        </span>
      </div>
      <p className="font-mono text-[11px] text-dim leading-relaxed">{analysis.summary}</p>
      {analysis.risk_flags.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {analysis.risk_flags.map((flag, i) => (
            <span key={i} className="rounded border border-loss/20 bg-loss-dim px-1.5 py-0.5 font-mono text-[9px] text-loss/80">
              {flag}
            </span>
          ))}
        </div>
      )}
      <div className="font-mono text-[9px] text-muted">
        {analysis.tokens_used.toLocaleString()} tokens · ${analysis.cost_usd.toFixed(4)} · {analysis.model_name}
      </div>
    </div>
  );
}

export function Agent() {
  const { lastMessage } = useWebSocket();
  const { data: costRaw, error: costError } = useApi(() => api.agent.costSummary());
  const { data: briefingRaw, loading: briefingLoading, error: briefingError } = useApi(() => api.agent.latestBriefing());
  const { data: recsRaw, refetch: refetchRecs } = useApi(() => api.agent.listRecommendations(undefined, 10));
  const { data: analysesRaw, loading: analysesLoading, error: analysesError, refetch: refetchAnalyses } = useApi(() => api.agent.listAnalyses(undefined, 5));

  useEffect(() => {
    if (!lastMessage) return;
    if (lastMessage.channel === 'agent:recommendation') {
      refetchRecs();
    } else if (lastMessage.channel === 'agent:analysis') {
      refetchAnalyses();
    }
  }, [lastMessage]);

  const agentDisabled = costError?.includes('503');

  const cost = costRaw as LLMCostSummary | null;
  const briefing = briefingRaw as DailyBriefing | null;
  const recs = (recsRaw?.recommendations ?? []) as TradeRecommendation[];
  const analyses = (analysesRaw?.analyses ?? []) as AgentAnalysis[];

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Bot className="h-4 w-4 text-cyan" />
        <h1 className="font-mono text-sm font-semibold uppercase tracking-wider text-bright">
          Agent Dashboard
        </h1>
      </div>

      {/* Disabled banner */}
      {agentDisabled && (
        <div className="rounded-xl border border-amber/30 bg-amber-dim p-4">
          <p className="font-mono text-xs text-amber uppercase tracking-wider">
            Agent module is disabled — set <code>SA_AGENT__ENABLED=true</code> to enable LLM features
          </p>
        </div>
      )}

      {/* Cost summary */}
      {cost && (
        <div className="glow-border rounded-xl bg-surface p-5">
          <div className="font-mono text-[10px] uppercase tracking-wider text-muted mb-4">LLM Cost</div>
          <div className="space-y-3">
            <CostBar label="Daily" value={cost.daily_cost_usd} budget={cost.daily_budget_usd} />
            <CostBar label="Monthly" value={cost.monthly_cost_usd} budget={cost.monthly_budget_usd} />
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 gap-6">
        {/* Daily briefing */}
        <div className="glow-border rounded-xl bg-surface p-5 space-y-3">
          <div className="font-mono text-[10px] uppercase tracking-wider text-muted">Daily Briefing</div>
          {briefingLoading ? (
            <p className="font-mono text-[11px] text-muted">Loading briefing...</p>
          ) : briefingError ? (
            <p className="font-mono text-[11px] text-loss">Failed to load briefing</p>
          ) : briefing && briefing.date ? (
            <>
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs text-dim">{briefing.date}</span>
                <span className="font-mono text-[10px] uppercase text-muted border border-border rounded px-1.5 py-0.5">
                  {briefing.market_regime}
                </span>
              </div>
              <p className="font-mono text-[11px] text-dim leading-relaxed">{briefing.portfolio_summary}</p>
              {briefing.key_observations.length > 0 && (
                <ul className="space-y-1">
                  {briefing.key_observations.map((obs, i) => (
                    <li key={i} className="font-mono text-[10px] text-muted flex gap-2">
                      <span className="text-cyan/60">·</span>{obs}
                    </li>
                  ))}
                </ul>
              )}
              {briefing.suggested_exits.length > 0 && (
                <div>
                  <div className="font-mono text-[9px] uppercase text-muted mb-1">Suggested Exits</div>
                  {briefing.suggested_exits.map((exit, i) => (
                    <div key={i} className="font-mono text-[10px] text-amber">· {exit}</div>
                  ))}
                </div>
              )}
            </>
          ) : (
            <p className="font-mono text-[11px] text-muted">No briefing available yet</p>
          )}
        </div>

        {/* Trade recommendations */}
        <div className="glow-border rounded-xl bg-surface p-5 space-y-3">
          <div className="font-mono text-[10px] uppercase tracking-wider text-muted">
            Trade Recommendations
          </div>
          {recs.length > 0 ? (
            <div className="space-y-2 max-h-80 overflow-y-auto">
              {recs.map((rec) => (
                <RecommendationCard key={rec.id} rec={rec} />
              ))}
            </div>
          ) : (
            <p className="font-mono text-[11px] text-muted">No recommendations yet</p>
          )}
        </div>
      </div>

      {/* Recent analyses */}
      <div className="glow-border rounded-xl bg-surface p-5 space-y-3">
        <div className="font-mono text-[10px] uppercase tracking-wider text-muted">
          Recent Filing Analyses
        </div>
        {analysesLoading ? (
          <p className="font-mono text-[11px] text-muted">Loading analyses...</p>
        ) : analysesError ? (
          <p className="font-mono text-[11px] text-loss">Failed to load analyses</p>
        ) : analyses.length > 0 ? (
          <div className="grid grid-cols-2 gap-3">
            {analyses.map((a) => (
              <AnalysisCard key={a.id} analysis={a} />
            ))}
          </div>
        ) : (
          <p className="font-mono text-[11px] text-muted">No filing analyses available. Analyses are generated automatically when SEC filings are processed.</p>
        )}
      </div>
    </div>
  );
}
