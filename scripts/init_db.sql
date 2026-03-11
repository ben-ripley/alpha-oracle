-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- OHLCV price data
CREATE TABLE IF NOT EXISTS ohlcv (
    symbol TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    open DOUBLE PRECISION NOT NULL,
    high DOUBLE PRECISION NOT NULL,
    low DOUBLE PRECISION NOT NULL,
    close DOUBLE PRECISION NOT NULL,
    volume BIGINT NOT NULL,
    adjusted_close DOUBLE PRECISION,
    source TEXT DEFAULT '',
    PRIMARY KEY (symbol, timestamp)
);

SELECT create_hypertable('ohlcv', 'timestamp', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_ohlcv_symbol ON ohlcv (symbol, timestamp DESC);

-- Fundamental data
CREATE TABLE IF NOT EXISTS fundamentals (
    symbol TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    pe_ratio DOUBLE PRECISION,
    pb_ratio DOUBLE PRECISION,
    ps_ratio DOUBLE PRECISION,
    ev_ebitda DOUBLE PRECISION,
    debt_to_equity DOUBLE PRECISION,
    current_ratio DOUBLE PRECISION,
    roe DOUBLE PRECISION,
    revenue_growth DOUBLE PRECISION,
    earnings_growth DOUBLE PRECISION,
    dividend_yield DOUBLE PRECISION,
    market_cap DOUBLE PRECISION,
    sector TEXT DEFAULT '',
    industry TEXT DEFAULT '',
    PRIMARY KEY (symbol, timestamp)
);

SELECT create_hypertable('fundamentals', 'timestamp', if_not_exists => TRUE);

-- SEC filings
CREATE TABLE IF NOT EXISTS filings (
    id SERIAL,
    symbol TEXT NOT NULL,
    filing_type TEXT NOT NULL,
    filed_date TIMESTAMPTZ NOT NULL,
    url TEXT NOT NULL,
    content TEXT DEFAULT '',
    metadata JSONB DEFAULT '{}',
    PRIMARY KEY (id, filed_date)
);

SELECT create_hypertable('filings', 'filed_date', if_not_exists => TRUE);

-- Trade records (audit trail)
CREATE TABLE IF NOT EXISTS trades (
    id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity DOUBLE PRECISION NOT NULL,
    entry_price DOUBLE PRECISION NOT NULL,
    exit_price DOUBLE PRECISION,
    entry_time TIMESTAMPTZ NOT NULL,
    exit_time TIMESTAMPTZ,
    pnl DOUBLE PRECISION DEFAULT 0,
    pnl_pct DOUBLE PRECISION DEFAULT 0,
    strategy_name TEXT DEFAULT '',
    hold_duration_days DOUBLE PRECISION DEFAULT 0,
    is_day_trade BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (id, entry_time)
);

SELECT create_hypertable('trades', 'entry_time', if_not_exists => TRUE);

-- Orders (audit trail)
CREATE TABLE IF NOT EXISTS orders (
    id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    order_type TEXT NOT NULL,
    quantity DOUBLE PRECISION NOT NULL,
    limit_price DOUBLE PRECISION,
    stop_price DOUBLE PRECISION,
    status TEXT NOT NULL,
    strategy_name TEXT DEFAULT '',
    signal_strength DOUBLE PRECISION DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL,
    filled_at TIMESTAMPTZ,
    filled_price DOUBLE PRECISION,
    filled_quantity DOUBLE PRECISION,
    broker_order_id TEXT DEFAULT '',
    metadata JSONB DEFAULT '{}',
    PRIMARY KEY (id, created_at)
);

SELECT create_hypertable('orders', 'created_at', if_not_exists => TRUE);

-- Portfolio snapshots
CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    timestamp TIMESTAMPTZ NOT NULL,
    total_equity DOUBLE PRECISION NOT NULL,
    cash DOUBLE PRECISION NOT NULL,
    positions_value DOUBLE PRECISION NOT NULL,
    daily_pnl DOUBLE PRECISION DEFAULT 0,
    daily_pnl_pct DOUBLE PRECISION DEFAULT 0,
    total_pnl DOUBLE PRECISION DEFAULT 0,
    total_pnl_pct DOUBLE PRECISION DEFAULT 0,
    max_drawdown_pct DOUBLE PRECISION DEFAULT 0,
    positions JSONB DEFAULT '[]',
    sector_exposure JSONB DEFAULT '{}',
    PRIMARY KEY (timestamp)
);

SELECT create_hypertable('portfolio_snapshots', 'timestamp', if_not_exists => TRUE);

-- Signals log
CREATE TABLE IF NOT EXISTS signals (
    symbol TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    direction TEXT NOT NULL,
    strength DOUBLE PRECISION NOT NULL,
    strategy_name TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    PRIMARY KEY (symbol, timestamp, strategy_name)
);

SELECT create_hypertable('signals', 'timestamp', if_not_exists => TRUE);

-- Risk events
CREATE TABLE IF NOT EXISTS risk_events (
    id SERIAL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event_type TEXT NOT NULL,
    action TEXT NOT NULL,
    reasons TEXT[] DEFAULT '{}',
    metadata JSONB DEFAULT '{}',
    PRIMARY KEY (id, timestamp)
);

SELECT create_hypertable('risk_events', 'timestamp', if_not_exists => TRUE);

-- Kill switch state
CREATE TABLE IF NOT EXISTS kill_switch (
    id SERIAL PRIMARY KEY,
    active BOOLEAN NOT NULL DEFAULT FALSE,
    activated_at TIMESTAMPTZ,
    reason TEXT DEFAULT '',
    deactivated_at TIMESTAMPTZ
);

INSERT INTO kill_switch (active) VALUES (FALSE) ON CONFLICT DO NOTHING;

-- Backtest results
CREATE TABLE IF NOT EXISTS backtest_results (
    id SERIAL,
    strategy_name TEXT NOT NULL,
    run_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    start_date TIMESTAMPTZ NOT NULL,
    end_date TIMESTAMPTZ NOT NULL,
    initial_capital DOUBLE PRECISION NOT NULL,
    final_capital DOUBLE PRECISION NOT NULL,
    total_return_pct DOUBLE PRECISION,
    annual_return_pct DOUBLE PRECISION,
    sharpe_ratio DOUBLE PRECISION,
    sortino_ratio DOUBLE PRECISION,
    max_drawdown_pct DOUBLE PRECISION,
    profit_factor DOUBLE PRECISION,
    total_trades INTEGER,
    winning_trades INTEGER,
    losing_trades INTEGER,
    win_rate DOUBLE PRECISION,
    equity_curve JSONB DEFAULT '[]',
    metadata JSONB DEFAULT '{}',
    PRIMARY KEY (id, run_at)
);

SELECT create_hypertable('backtest_results', 'run_at', if_not_exists => TRUE);

-- Operator heartbeat (dead man's switch)
CREATE TABLE IF NOT EXISTS operator_heartbeat (
    id SERIAL PRIMARY KEY,
    last_heartbeat TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO operator_heartbeat (last_heartbeat) VALUES (NOW()) ON CONFLICT DO NOTHING;
