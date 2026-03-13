# Glossary

Financial and trading terms used throughout the Stock Analysis system.

---

### ADV (Average Daily Volume) {#adv}
The average number of shares traded per day over a specified period (typically 20-30 days). Used to assess liquidity and determine appropriate order sizing. The system's smart order router uses ADV to decide between market, limit, and TWAP orders.

### Alpha {#alpha}
Excess return of a strategy relative to a benchmark index (like the S&P 500). Positive alpha indicates outperformance. The system tracks alpha for each strategy to measure value added beyond market returns.

### ATR (Average True Range) {#atr}
A volatility indicator measuring the average range between high and low prices over a period. Used for position sizing and stop-loss placement. Higher ATR suggests more volatile price action.

### Backtest {#backtest}
Simulating a trading strategy on historical data to evaluate performance before risking real capital. The system uses Backtrader and VectorBT for backtesting with point-in-time data to avoid look-ahead bias.

### Beta {#beta}
Measure of a stock's volatility relative to the overall market. Beta > 1 means more volatile than market, beta < 1 means less volatile. Used in portfolio construction to manage systematic risk.

### Bollinger Bands {#bollinger-bands}
Technical indicator consisting of a moving average with upper and lower bands set at standard deviations above and below. Used to identify overbought/oversold conditions and volatility expansion/contraction.

### Bracket Order {#bracket-order}
An order that includes both a profit target (limit order) and a stop-loss, creating a "bracket" around the entry price. Manages both upside and downside risk automatically.

### Circuit Breaker {#circuit-breaker}
Automatic trading halt triggered by specific risk conditions. The system implements circuit breakers for high VIX (>35), excessive drawdown, stale data, and failed reconciliation checks.

### Day Trade {#day-trade}
Opening and closing a position in the same security on the same trading day. Retail accounts under $25K are limited to 3 day trades per rolling 5 business days under the PDT rule.

### Drawdown {#drawdown}
Peak-to-trough decline in portfolio value. Current drawdown measures the percentage drop from the highest point. The system's circuit breakers trigger at 10% max drawdown.

### EMA (Exponential Moving Average) {#ema}
A moving average that gives more weight to recent prices, making it more responsive to new information than a simple moving average. Widely used in momentum and trend-following strategies.

### Equity Curve {#equity-curve}
A chart showing portfolio value over time. Used to visualize performance, identify drawdown periods, and assess consistency. A smooth upward curve indicates stable returns.

### Fill {#fill}
Execution of an order at a specific price. The fill price may differ from the order price for market orders. The system's execution quality tracker monitors fill prices versus prevailing bid/ask.

### Float {#float}
The number of shares available for public trading (excluding insider holdings and restricted shares). Low float stocks tend to be more volatile and may have wider bid-ask spreads.

### Form 4 {#form-4}
SEC filing reporting insider transactions (buys/sells by officers, directors, and 10%+ owners). The system ingests Form 4 data as an alternative signal since insider buying can indicate confidence.

### Fundamental Analysis {#fundamental-analysis}
Evaluation of a company's financial health using metrics like P/E ratio, revenue growth, profit margins, and debt levels. The system combines fundamental features with technical indicators.

### Half-Kelly {#half-kelly}
Position sizing method using half the Kelly Criterion optimal fraction. Provides most of Kelly's growth rate with significantly less volatility. The system uses Half-Kelly for conservative position sizing.

### Insider Trading (Legal) {#insider-trading}
Legal purchases or sales of company stock by corporate insiders (officers, directors) reported via Form 4. Distinct from illegal insider trading based on material non-public information.

### Kelly Criterion {#kelly-criterion}
Mathematical formula for optimal position sizing based on win rate and average win/loss ratio. Maximizes long-term growth rate but can be aggressive. The system uses Half-Kelly for better risk management.

### Limit Order {#limit-order}
Order to buy or sell at a specified price or better. Provides price certainty but not execution certainty. The system uses limit orders for less liquid stocks or when execution urgency is low.

### MACD (Moving Average Convergence Divergence) {#macd}
Trend-following momentum indicator showing the relationship between two moving averages (typically 12-day and 26-day EMA). Crossovers and divergences generate buy/sell signals.

### Market Cap {#market-cap}
Total value of a company's outstanding shares (price × shares). Used to classify stocks (large-cap >$10B, mid-cap $2-10B, small-cap <$2B). The system filters for minimum market cap to ensure liquidity.

### Market Order {#market-order}
Order to buy or sell immediately at the best available price. Guarantees execution but not price. The system uses market orders for highly liquid stocks when urgency is high.

### Max Drawdown {#max-drawdown}
Largest peak-to-trough decline in portfolio value over a specified period. Key risk metric; the system halts trading at 10% max drawdown via circuit breakers.

### OHLCV {#ohlcv}
Open, High, Low, Close, Volume - the five standard data points for each trading period. Forms the foundation for technical analysis and backtesting.

### P&L (Profit and Loss) {#pnl}
The net gain or loss on your portfolio or individual positions. Daily P&L measures today's change; total P&L measures cumulative performance. Unrealized P&L is on open positions; realized P&L is on closed trades.

### PSI (Population Stability Index) {#psi}
A statistical measure used to detect when the data distribution feeding the ML model has shifted significantly from what it was trained on. PSI < 0.1 indicates stable data, 0.1-0.25 indicates moderate drift, and > 0.25 indicates significant drift that may require model retraining.

### P/E Ratio (Price-to-Earnings) {#pe-ratio}
Stock price divided by earnings per share. Measures valuation relative to profitability. Low P/E may indicate undervaluation, high P/E may signal growth expectations or overvaluation.

### PDT (Pattern Day Trader) {#pdt}
FINRA regulation requiring $25K minimum balance for accounts making 4+ day trades within 5 business days. The system's PDT guard enforces the 3 day trade limit for sub-$25K accounts.

### Point-in-Time (PIT) {#point-in-time}
Data as it existed at a specific historical date, preventing look-ahead bias. The system's feature store ensures all features use point-in-time data for accurate backtesting.

### Position Sizing {#position-sizing}
Determining how many shares to buy based on account size, risk tolerance, and signal strength. The system uses Half-Kelly sizing with maximum 5% per position and sector limits.

### Profit Factor {#profit-factor}
Ratio of gross profits to gross losses. A profit factor of 2.0 means winning trades generated twice as much profit as losing trades lost. Values above 1.5 are generally considered good.

### RSI (Relative Strength Index) {#rsi}
Momentum oscillator ranging from 0-100, measuring speed and magnitude of price changes. Values above 70 suggest overbought conditions, below 30 suggest oversold. Used to identify reversal opportunities.

### Sector Exposure {#sector-exposure}
Percentage of portfolio allocated to each market sector (Technology, Healthcare, Financials, etc.). The system limits sector concentration to 25% to reduce sector-specific risk.

### Sharpe Ratio {#sharpe-ratio}
Risk-adjusted return metric: (portfolio return - risk-free rate) / portfolio volatility. Higher Sharpe indicates better risk-adjusted performance. Values above 1.0 are considered good, above 2.0 excellent.

### Short Interest {#short-interest}
Percentage of float sold short by investors. High short interest can lead to short squeeze volatility. The system ingests FINRA short interest data as an alternative signal.

### Signal {#signal}
Algorithmic recommendation to buy, sell, or hold a security. Generated by technical indicators, fundamental analysis, or ML models. Signals include confidence scores and rationale.

### Slippage {#slippage}
Difference between expected execution price and actual fill price. Results from market impact, volatility, and liquidity constraints. The system's execution quality tracker monitors slippage.

### Sortino Ratio {#sortino-ratio}
Risk-adjusted return metric similar to Sharpe but only penalizes downside volatility. Preferred by many traders since upside volatility is desirable. Higher values indicate better downside-adjusted returns.

### Stop-Loss {#stop-loss}
Order that automatically sells a position when price falls to a specified level, limiting losses. The system uses ATR-based stop-losses to adapt to volatility.

### Swing Trading {#swing-trading}
Holding positions for multiple days to weeks to capture medium-term price moves. Contrasts with day trading (intraday) and position trading (months/years). Primary strategy for this system.

### Technical Analysis {#technical-analysis}
Studying price charts, patterns, and indicators to forecast future price movements. Based on the premise that historical price action contains predictive information.

### TWAP (Time-Weighted Average Price) {#twap}
Execution algorithm that splits a large order into smaller chunks executed at regular intervals. Reduces market impact for illiquid stocks or large positions relative to ADV.

### Unrealized P&L {#unrealized-pnl}
Profit or loss on open positions based on current market prices. Becomes realized P&L when the position is closed. The dashboard displays both realized and unrealized P&L.

### VIX {#vix}
CBOE Volatility Index measuring expected 30-day S&P 500 volatility based on option prices. VIX > 20 indicates elevated fear, VIX > 35 triggers circuit breakers in the system.

### Volume {#volume}
Number of shares traded during a period. High volume confirms price moves, low volume suggests weak conviction. Volume analysis helps validate breakouts and identify accumulation/distribution.

### Walk-Forward Validation {#walk-forward-validation}
Backtesting method that trains a model on historical data, tests on subsequent unseen data, then rolls forward. Prevents overfitting by simulating real-world model deployment. The system uses walk-forward validation for ML model training.

### Win Rate {#win-rate}
Percentage of trades that are profitable. A 60% win rate means 6 out of 10 trades were winners. Must be considered alongside profit factor and risk/reward ratio for full picture.

### XGBoost {#xgboost}
Gradient boosting machine learning algorithm optimized for speed and performance. The system uses XGBoost to generate ML signals based on 50+ technical, fundamental, and alternative features.
