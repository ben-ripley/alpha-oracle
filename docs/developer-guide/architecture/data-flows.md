# Data Flows

This page documents the three main data flows through the **alpha-oracle** system: signal generation, order execution, and risk management.

## 1. Signal Generation Flow

Strategies generate trading signals from market data, which are ranked and passed to the execution engine.

<!-- DIAGRAM: Signal Generation Flow
Market data sources (IBKR, Alpha Vantage, EDGAR) → Data adapters → TimescaleDB → Feature store (50+ PIT features) → Strategy engine (builtin strategies + ML strategy) → XGBoost model (optional) → Ranked signals → Execution engine
-->

### Step-by-Step

1. **Data Ingestion** (Daily Bars Job)
   - `daily_bars_job()` runs at 5pm ET weekdays (after market close)
   - Fetches [OHLCV](../glossary.md#ohlcv) bars from IBKR or Alpha Vantage for all [universe](../glossary.md#universe) symbols (S&P 500)
   - Stores in [TimescaleDB](../glossary.md#timescaledb) hypertables via `TimeSeriesStorage`
   - Redis idempotency key: `jobs:daily_bars:{date}:done`

2. **Feature Calculation**
   - Feature store (`src/signals/feature_store.py`) orchestrates 50+ feature calculators
   - Features include technical (RSI, MACD, Bollinger), fundamental (PE, ROE), cross-asset (VIX, SPY correlation), and alternative (Form 4 insider buys, short interest)
   - Point-in-time (PIT) joins ensure no lookahead bias
   - Cached in Parquet format for fast access

3. **ML Prediction** (Optional)
   - `MLSignalStrategy` loads latest XGBoost model from registry
   - Predicts 5-day forward returns (UP/DOWN/NEUTRAL)
   - Calibrated confidence scores (0.0-1.0)
   - Filters by confidence threshold (default 0.55)
   - Min hold: 3 days for PDT compliance

4. **Builtin Strategy Signals**
   - `MomentumStrategy`, `MeanReversionStrategy`, `BreakoutStrategy` run in parallel
   - Each returns list of `Signal` objects (symbol, direction, strength, timestamp)
   - Min hold: 2 days (all strategies enforce swing trading)

5. **Signal Ranking**
   - `StrategyRanker` uses walk-forward backtest results to rank strategies
   - Composite score weights: Sharpe (30%), Sortino (20%), max drawdown inverse (20%), profit factor (15%), consistency (15%)
   - Only strategies meeting thresholds (Sharpe > 1.0, profit factor > 1.5, max drawdown < 20%) are used

6. **Redis Pub/Sub Event**
   - Signal published to `signals` channel:
     ```json
     {
       "event": "signal:generated",
       "symbol": "AAPL",
       "direction": "LONG",
       "strength": 0.82,
       "strategy": "MLSignalStrategy",
       "timestamp": "2026-03-12T10:30:00Z"
     }
     ```

7. **Execution Engine Receives Signals**
   - `ExecutionEngine` subscribes to `signals` channel
   - Converts signals to order requests
   - Passes to risk checks (next flow)

## 2. Order Execution Flow

Orders go through risk checks, smart routing, broker submission, and quality tracking.

<!-- DIAGRAM: Order Execution Flow
Signal → Order generator (Kelly sizing) → Pre-trade risk checks (PDT guard, position limits, portfolio limits) → Smart router (market/limit/TWAP selection) → Broker adapter (IBKR) → Order submitted → Fill confirmation → Execution quality tracker → Redis pub/sub event
-->

### Step-by-Step

1. **Order Generation**
   - `OrderGenerator` converts signal to order request
   - **Position sizing** using half-Kelly criterion:
     ```
     f = (win_rate - (1 - win_rate) / avg_win_loss_ratio) / 2
     position_size = equity * f
     ```
   - Max position size: 5% of equity (risk limit)
   - Calculates notional value: `price * quantity`

2. **Pre-Trade Risk Checks**
   - `PreTradeRiskManager.check_pre_trade()` runs:
     - **PDT Guard** (`src/risk/pdt_guard.py`) — Critical check
       - Accounts under $25K: max 3 day trades per 5 business days
       - Rejects same-day round trips
       - Allows swing trades (hold >= 2 days)
       - Logs all decisions for audit
     - **Position Limits** (`src/risk/pre_trade.py`)
       - Max 5% per position
       - Max 25% per sector
       - Min stock price: $5 (no penny stocks)
       - No leverage (100% cash)
     - **Portfolio Limits** (`src/risk/portfolio_monitor.py`)
       - Max 10% drawdown from peak
       - Max 3% daily loss
       - Max 20 positions
       - Max 50 trades/day
       - Min 10% cash reserve
   - Returns `RiskCheckResult` with action: APPROVE, REJECT, REQUIRE_HUMAN_APPROVAL, REDUCE_SIZE

3. **Autonomy Mode Gate**
   - Config: `risk.autonomy_mode` (PAPER_ONLY, MANUAL_APPROVAL, BOUNDED_AUTONOMOUS, FULL_AUTONOMOUS)
   - **PAPER_ONLY**: Order marked as simulation, not submitted to broker
   - **MANUAL_APPROVAL**: Order saved to DB, requires manual approval via API
   - **BOUNDED_AUTONOMOUS**: Order auto-approved if within risk limits
   - **FULL_AUTONOMOUS**: Order auto-approved (for live accounts > $25K)

4. **Smart Order Router**
   - `SmartOrderRouter` selects order type based on:
     - **Order size**: Small (< 0.1% ADV), medium, large (> 1% ADV)
     - **Spread**: Tight (< 20 bps) vs wide (> 20 bps)
     - **Urgency**: Normal vs high
   - **Routing logic**:
     - Small + tight spread + normal urgency → MARKET order
     - Medium + tight spread → LIMIT order (at ask for buys, bid for sells)
     - Large or wide spread → TWAP (5 slices, 60s intervals)
   - Reads `bid_price` and `ask_price` from Redis feed cache

5. **Broker Submission**
   - `BrokerAdapter.submit_order()` sends order to IBKR
   - IBKR client ID scheme:
     - Broker adapter: `client_id` (default 1)
     - Data adapter: `client_id + 1` (default 2)
     - Market feed: `client_id + 2` (default 3)
   - Order receives `broker_order_id` from IBKR
   - Status: PENDING → SUBMITTED

6. **Fill Confirmation**
   - Broker adapter polls or receives WebSocket update
   - Status: SUBMITTED → PARTIALLY_FILLED → FILLED
   - Fill price and timestamp recorded

7. **Execution Quality Tracking**
   - `ExecutionQualityTracker` calculates:
     - **Slippage**: `(fill_price - reference_price) / reference_price`
     - **Effective spread**: `fill_price - midpoint`
     - **Implementation shortfall**: `(fill_price - decision_price) * quantity`
   - Metrics aggregated in Prometheus (percentiles by symbol, order type)

8. **Redis Pub/Sub Events**
   - `order:submitted`:
     ```json
     {"event": "order:submitted", "order_id": "123", "symbol": "AAPL", ...}
     ```
   - `order:filled`:
     ```json
     {"event": "order:filled", "order_id": "123", "fill_price": 150.25, ...}
     ```
   - `order:rejected`:
     ```json
     {"event": "order:rejected", "order_id": "123", "reason": "PDT violation", ...}
     ```

## 3. Risk Cascade

Every order and portfolio state goes through a multi-layer risk cascade before execution.

<!-- DIAGRAM: Risk Cascade
Order request → Kill switch check → Circuit breaker checks (VIX, stale data, reconciliation, dead man switch) → PDT guard → Position limits → Portfolio limits → Autonomy mode gate → Order approved/rejected
-->

### Step-by-Step

1. **Kill Switch Check** (Top Priority)
   - `KillSwitch.is_active()` checks Redis key `kill_switch:active`
   - If active, **all trading halted immediately**
   - Activated manually via API (`POST /api/risk/kill-switch/activate`) or Telegram bot
   - Requires typed confirmation: `"KILL"` or `"RESUME"`
   - Cooldown: 60 minutes after reactivation
   - Event: `kill_switch:activated` → Redis `kill_switch` channel

2. **Circuit Breaker Checks** (`src/risk/circuit_breakers.py`)
   - **VIX Threshold**: If VIX > 35, halt trading (market panic)
   - **Stale Data**: If latest bar > 5 minutes old, reject orders (feed outage)
   - **Reconciliation Drift**: If broker positions differ from DB by > 1%, halt trading
   - **Dead Man Switch**: If no API activity for 48 hours, halt trading (system failure)
   - Any triggered breaker → Redis `risk:circuit_breaker` event → Slack/Telegram alert

3. **PDT Guard** (Most Critical for <$25K Accounts)
   - See [Order Execution Flow](#2-order-execution-flow) Step 2
   - Conservative: rejects if uncertain (e.g., missing data)
   - All decisions logged to database `pdt_audit_log` table

4. **Position Limits**
   - Max 5% per position, 25% per sector
   - Min stock price $5, no leverage

5. **Portfolio Limits**
   - Max 10% drawdown, 3% daily loss
   - Max 20 positions, 50 trades/day
   - Min 10% cash reserve

6. **Autonomy Mode Gate**
   - PAPER_ONLY: Simulate only
   - MANUAL_APPROVAL: Require human approval
   - BOUNDED_AUTONOMOUS: Auto-approve within limits
   - FULL_AUTONOMOUS: Full automation (live accounts)

7. **Final Approval/Rejection**
   - If all checks pass → Order approved → Submit to broker
   - If any check fails → Order rejected → Log reason → Redis `order:rejected` event

### Risk Alert Flow

When risk limits are breached:

1. `PortfolioMonitor.check_portfolio()` detects breach (e.g., drawdown > 10%)
2. Redis `risk:alert` event published:
   ```json
   {
     "event": "risk:alert",
     "type": "portfolio_drawdown",
     "severity": "high",
     "value": 12.5,
     "threshold": 10.0,
     "timestamp": "2026-03-12T10:30:00Z"
   }
   ```
3. `AlertManager` receives event, sends Slack/Telegram notification
4. If severity is `critical`, auto-activate kill switch

## Next Steps

- [Module Map](module-map.md) — Detailed file structure for each subsystem
- [Module Reference](../modules/index.md) — In-depth docs for data, strategy, execution, risk modules
