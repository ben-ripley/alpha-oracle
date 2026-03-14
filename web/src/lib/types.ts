export interface Position {
  symbol: string;
  quantity: number;
  avg_entry_price: number;
  current_price: number;
  market_value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  side: 'BUY' | 'SELL';
  sector: string;
  entry_date: string | null;
  strategy_name: string;
}

export interface PortfolioSnapshot {
  timestamp: string;
  total_equity: number;
  cash: number;
  positions_value: number;
  daily_pnl: number;
  daily_pnl_pct: number;
  total_pnl: number;
  total_pnl_pct: number;
  max_drawdown_pct: number;
  positions: Position[];
  sector_exposure: Record<string, number>;
}

export interface Strategy {
  name: string;
  description: string;
  min_hold_days: number;
  parameters: Record<string, unknown>;
  required_data: string[];
}

export interface StrategyRanking {
  strategy_name: string;
  composite_score: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  max_drawdown_pct: number;
  profit_factor: number;
  consistency_score: number;
  total_trades: number;
  win_rate: number;
  meets_thresholds: boolean;
  ranked_at: string;
}

export interface BacktestResult {
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
  equity_curve: Array<{ date: string; equity: number }>;
  trades: Array<Record<string, unknown>>;
}

export interface Order {
  id: string;
  symbol: string;
  side: 'BUY' | 'SELL';
  order_type: string;
  quantity: number;
  limit_price: number | null;
  stop_price: number | null;
  status: string;
  strategy_name: string;
  signal_strength: number;
  created_at: string;
  filled_at: string | null;
  filled_price: number | null;
  filled_quantity: number | null;
  broker_order_id: string;
}

export interface TradeRecord {
  id: string;
  symbol: string;
  side: 'BUY' | 'SELL';
  quantity: number;
  entry_price: number;
  exit_price: number | null;
  entry_time: string;
  exit_time: string | null;
  pnl: number;
  pnl_pct: number;
  strategy_name: string;
  hold_duration_days: number;
  is_day_trade: boolean;
}

export interface RiskLimits {
  position_limits: {
    max_position_pct: number;
    max_sector_pct: number;
    stop_loss_pct: number;
    min_price: number;
  };
  portfolio_limits: {
    max_drawdown_pct: number;
    current_drawdown_pct: number;
    max_daily_loss_pct: number;
    current_daily_pnl_pct: number;
    max_positions: number;
    current_positions: number;
    min_cash_reserve_pct: number;
    current_cash_pct: number;
  };
  pdt: {
    day_trades_used: number;
    max_day_trades: number;
    rolling_window_days: number;
    enabled: boolean;
  };
}

export interface CircuitBreaker {
  name: string;
  tripped: boolean;
  reason: string;
}

export interface WSMessage {
  channel: string;
  data: Record<string, unknown>;
}

// Phase 3: LLM Agent types

export type AgentAnalysisType = 'FILING_10K' | 'FILING_10Q' | 'FILING_8K' | 'EARNINGS_SUMMARY';

export interface AgentAnalysis {
  id?: string;
  symbol: string;
  analysis_type: AgentAnalysisType;
  summary: string;
  key_points: string[];
  sentiment_score: number;
  risk_flags: string[];
  financial_highlights: Record<string, unknown>;
  tokens_used: number;
  cost_usd: number;
  model_name: string;
  schema_version: number;
  created_at?: string;
}

export type RecommendationAction = 'BUY' | 'SELL' | 'HOLD';

export interface TradeRecommendation {
  id?: string;
  symbol: string;
  action: RecommendationAction;
  confidence: number;
  rationale: string;
  supporting_signals: string[];
  risk_factors: string[];
  suggested_entry: number | null;
  suggested_stop: number | null;
  suggested_target: number | null;
  human_approved: boolean | null;
  schema_version: number;
  created_at?: string;
}

export interface DailyBriefing {
  date: string;
  portfolio_summary: string;
  daily_pnl: number;
  risk_utilization: number;
  upcoming_catalysts: string[];
  suggested_exits: string[];
  market_regime: string;
  key_observations: string[];
  schema_version: number;
}

export interface LLMCostSummary {
  daily_cost_usd: number;
  daily_budget_usd: number;
  monthly_cost_usd: number;
  monthly_budget_usd: number;
}

export interface MonteCarloResult {
  num_simulations: number;
  time_horizon_days: number;
  percentiles: {
    p5: number[];
    p25: number[];
    p50: number[];
    p75: number[];
    p95: number[];
  };
  probability_of_loss: number;
  value_at_risk_95: number;
  simulation_paths: number[][];
}

export type MarketRegime = 'BULL' | 'BEAR' | 'SIDEWAYS' | 'HIGH_VOLATILITY';

export interface RegimeAnalysis {
  current_regime: MarketRegime;
  regime_probability: number;
  strategy_performance_by_regime: Record<string, unknown>;
  regime_history: Array<{ day_index: number; regime: MarketRegime }>;
}

export interface StrategyAllocation {
  strategy_name: string;
  weight: number;
  expected_return: number;
  contribution_to_risk: number;
}

export interface OptimizationResult {
  allocations: StrategyAllocation[];
  portfolio_sharpe: number;
  portfolio_expected_return: number;
  portfolio_volatility: number;
}

export interface AutonomyReadiness {
  current_mode: string;
  readiness: Record<string, { approved: boolean; blocking_reasons: string[] }>;
}

export interface GuardrailStatus {
  verified: boolean;
  last_verified: string | null;
  age_hours: number;
  stale: boolean;
}
