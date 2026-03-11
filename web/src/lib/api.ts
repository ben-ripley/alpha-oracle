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
};
