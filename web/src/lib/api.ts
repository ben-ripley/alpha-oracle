const BASE = '/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
  return res.json();
}

export const api = {
  portfolio: {
    snapshot: () => request<any>('/portfolio/snapshot'),
    positions: () => request<any>('/portfolio/positions'),
    history: (days = 30) => request<any>(`/portfolio/history?days=${days}`),
    allocation: () => request<any>('/portfolio/allocation'),
  },
  strategies: {
    list: () => request<any>('/strategies/list'),
    rankings: () => request<any>('/strategies/rankings'),
    backtest: (params: { strategy_name: string; symbols: string[]; start_date: string; end_date?: string; initial_capital?: number }) =>
      request<any>('/strategies/backtest', { method: 'POST', body: JSON.stringify(params) }),
    results: (strategyName?: string, limit = 20) =>
      request<any>(`/strategies/backtest/results?${strategyName ? `strategy_name=${strategyName}&` : ''}limit=${limit}`),
    backtestJob: (jobId: string) =>
      request<any>(`/strategies/backtest/jobs/${jobId}`),
    mlSignals: () => request<any>('/strategies/ml/signals'),
    mlFeatureImportance: () => request<any>('/strategies/ml/feature-importance'),
    mlMonitoring: () => request<any>('/strategies/ml/monitoring'),
  },
  risk: {
    dashboard: () => request<any>('/risk/dashboard'),
    limits: () => request<any>('/risk/limits'),
    circuitBreakers: () => request<any>('/risk/circuit-breakers'),
    autonomyMode: () => request<any>('/risk/autonomy-mode'),
    killSwitch: {
      status: () => request<any>('/risk/kill-switch/status'),
      activate: (reason: string) => request<any>(`/risk/kill-switch/activate?reason=${encodeURIComponent(reason)}`, { method: 'POST' }),
      deactivate: () => request<any>('/risk/kill-switch/deactivate', { method: 'POST' }),
    },
  },
  trades: {
    history: (days = 30, limit = 100, symbol?: string) =>
      request<any>(`/trades/history?days=${days}&limit=${limit}${symbol ? `&symbol=${symbol}` : ''}`),
    openOrders: () => request<any>('/trades/open-orders'),
    pendingApprovals: () => request<any>('/trades/pending-approvals'),
    approve: (orderId: string, action: 'approve' | 'reject', reason = '') =>
      request<any>('/trades/approve', { method: 'POST', body: JSON.stringify({ order_id: orderId, action, reason }) }),
    dailySummary: () => request<any>('/trades/daily-summary'),
    executionQuality: (days = 30) => request<any>(`/trades/execution-quality?days=${days}`),
  },
  system: {
    health: () => request<any>('/system/health'),
    config: () => request<any>('/system/config'),
    heartbeat: () => request<any>('/system/heartbeat', { method: 'POST' }),
  },
  agent: {
    analyzeFiling: (params: { symbol: string; filing_text: string; filing_type?: string }) =>
      request<any>('/agent/analyze-filing', { method: 'POST', body: JSON.stringify(params) }),
    listAnalyses: (symbol: string, limit = 20) =>
      request<any>(`/agent/analyses?symbol=${encodeURIComponent(symbol)}&limit=${limit}`),
    getAnalysis: (id: string) =>
      request<any>(`/agent/analyses/${encodeURIComponent(id)}`),
    recommend: (symbol: string, contextData: Record<string, unknown> = {}) =>
      request<any>(`/agent/recommend/${encodeURIComponent(symbol)}`, {
        method: 'POST',
        body: JSON.stringify({ context_data: contextData }),
      }),
    listRecommendations: (symbol?: string, limit = 20) =>
      request<any>(`/agent/recommendations?${symbol ? `symbol=${encodeURIComponent(symbol)}&` : ''}limit=${limit}`),
    approveRecommendation: (id: string) =>
      request<any>(`/agent/recommendations/${encodeURIComponent(id)}/approve`, { method: 'POST' }),
    rejectRecommendation: (id: string) =>
      request<any>(`/agent/recommendations/${encodeURIComponent(id)}/reject`, { method: 'POST' }),
    latestBriefing: () => request<any>('/agent/briefing/latest'),
    briefingHistory: (limit = 7) => request<any>(`/agent/briefing/history?limit=${limit}`),
    costSummary: () => request<any>('/agent/cost-summary'),
  },
  analysis: {
    monteCarlo: (params: {
      historical_returns: number[];
      time_horizon_days?: number;
      initial_value?: number;
      num_simulations?: number;
      num_paths_for_chart?: number;
    }) => request<any>('/analysis/monte-carlo', { method: 'POST', body: JSON.stringify(params) }),
    regime: (spyPrices: number[], vixValues: number[]) =>
      request<any>('/analysis/regime', {
        method: 'POST',
        body: JSON.stringify({ spy_prices: spyPrices, vix_values: vixValues }),
      }),
    optimize: (strategyReturns: Record<string, number[]>, regime?: string) =>
      request<any>('/analysis/optimize', {
        method: 'POST',
        body: JSON.stringify({ strategy_returns: strategyReturns, regime }),
      }),
    autonomyReadiness: () => request<any>('/risk/autonomy-mode/readiness'),
    transitionAutonomy: (params: {
      target_mode: string;
      days_in_mode?: number;
      sharpe?: number;
      max_drawdown_pct?: number;
      circuit_breakers_tested?: boolean;
      confirmation?: string;
    }) => request<any>('/risk/autonomy-mode/transition', { method: 'POST', body: JSON.stringify(params) }),
    guardrailsStatus: () => request<any>('/risk/guardrails/status'),
  },
};
