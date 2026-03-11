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
