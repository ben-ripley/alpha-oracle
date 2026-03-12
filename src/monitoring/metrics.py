from __future__ import annotations

from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    Info,
    start_http_server,
)

from src.core.config import get_settings


class TradingMetrics:
    """Prometheus metrics for the trading system."""

    # System metrics
    system_info = Info("trading_system", "Trading system information")

    # Trading metrics
    orders_total = Counter(
        "trading_orders_total",
        "Total orders submitted",
        ["side", "order_type", "strategy", "status"],
    )
    trades_total = Counter(
        "trading_trades_total",
        "Total trades executed",
        ["side", "strategy"],
    )
    trade_pnl = Histogram(
        "trading_trade_pnl_dollars",
        "Trade P&L in dollars",
        ["strategy"],
        buckets=[-1000, -500, -200, -100, -50, -20, 0, 20, 50, 100, 200, 500, 1000],
    )

    # Portfolio metrics
    portfolio_equity = Gauge(
        "trading_portfolio_equity_dollars",
        "Total portfolio equity",
    )
    portfolio_cash = Gauge(
        "trading_portfolio_cash_dollars",
        "Available cash",
    )
    portfolio_positions_count = Gauge(
        "trading_portfolio_positions_count",
        "Number of open positions",
    )
    portfolio_daily_pnl = Gauge(
        "trading_portfolio_daily_pnl_dollars",
        "Daily P&L in dollars",
    )
    portfolio_daily_pnl_pct = Gauge(
        "trading_portfolio_daily_pnl_pct",
        "Daily P&L percentage",
    )
    portfolio_drawdown_pct = Gauge(
        "trading_portfolio_drawdown_pct",
        "Current drawdown percentage",
    )

    # Risk metrics
    risk_checks_total = Counter(
        "trading_risk_checks_total",
        "Total risk checks performed",
        ["result"],  # approve, reject, require_approval, reduce_size
    )
    pdt_trades_used = Gauge(
        "trading_pdt_trades_used",
        "Day trades used in rolling 5-day window (max 3)",
    )
    circuit_breakers_tripped = Gauge(
        "trading_circuit_breakers_tripped",
        "Number of circuit breakers currently tripped",
    )
    kill_switch_active = Gauge(
        "trading_kill_switch_active",
        "Kill switch status (1=active, 0=inactive)",
    )

    # Execution metrics
    order_latency = Histogram(
        "trading_order_latency_seconds",
        "Time from signal to order submission",
        buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    )
    slippage_bps = Histogram(
        "trading_slippage_bps",
        "Execution slippage in basis points",
        buckets=[-50, -20, -10, -5, 0, 5, 10, 20, 50, 100],
    )
    fill_rate = Gauge(
        "trading_fill_rate_pct",
        "Order fill rate percentage",
    )

    # Signal metrics
    signals_generated = Counter(
        "trading_signals_total",
        "Total signals generated",
        ["strategy", "direction"],
    )
    signal_strength = Histogram(
        "trading_signal_strength",
        "Signal strength distribution",
        ["strategy"],
        buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
    )

    # Data pipeline metrics
    data_fetch_total = Counter(
        "trading_data_fetch_total",
        "Total data fetch operations",
        ["source", "status"],  # source: alpaca/alpha_vantage/edgar, status: success/error
    )
    data_fetch_latency = Histogram(
        "trading_data_fetch_latency_seconds",
        "Data fetch latency",
        ["source"],
        buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
    )
    data_staleness_seconds = Gauge(
        "trading_data_staleness_seconds",
        "Age of most recent data in seconds",
        ["source"],
    )

    # Strategy metrics
    strategy_sharpe = Gauge(
        "trading_strategy_sharpe_ratio",
        "Live Sharpe ratio",
        ["strategy"],
    )
    strategy_win_rate = Gauge(
        "trading_strategy_win_rate_pct",
        "Strategy win rate",
        ["strategy"],
    )

    # ML Model metrics
    model_accuracy = Gauge(
        "trading_model_accuracy",
        "ML model rolling directional accuracy",
    )
    feature_drift_psi = Gauge(
        "trading_feature_drift_psi",
        "Maximum PSI across all features (feature drift indicator)",
    )
    model_staleness_hours = Gauge(
        "trading_model_staleness_hours",
        "Hours since last model retrain",
    )
    ml_fallback_active = Gauge(
        "trading_ml_fallback_active",
        "ML fallback to rule-based active (1=active, 0=inactive)",
    )


def setup_metrics() -> None:
    """Start Prometheus metrics HTTP server."""
    settings = get_settings()
    port = settings.monitoring.prometheus_port

    TradingMetrics.system_info.info({
        "environment": settings.environment,
        "broker": settings.broker.provider,
        "paper_trading": str(settings.broker.paper_trading),
        "autonomy_mode": settings.risk.autonomy_mode,
    })

    start_http_server(port)
