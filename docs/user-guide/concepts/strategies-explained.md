---
title: Trading Strategies
nav_order: 4
parent: Concepts
---

# Trading Strategies

The system includes three built-in trading strategies, each designed for swing trading (holding positions for days to weeks, not intraday). All strategies comply with the [PDT rule](./pdt-rule.md) by using minimum holding periods of 2+ days.

## The Three Built-In Strategies

### 1. Swing Momentum
**Follows trends using moving average crossovers.**

**What it looks for:**
- Fast moving average (10-day) crosses above slow moving average (50-day) = uptrend starting
- RSI confirmation: not overbought (RSI < 70)
- Rides the momentum until trend reverses

**Buy signal:**
- Fast MA crosses above slow MA
- RSI < 70 (not overbought)

**Sell signal:**
- Fast MA crosses below slow MA (trend reversal), OR
- RSI > 80 (severely overbought), OR
- 5% stop-loss triggered

**Time horizon:** 2-14 days (swing trades)

**Best for:** Trending markets, stocks with clear momentum

### 2. Mean Reversion
**Buys oversold stocks, sells when they return to normal.**

**What it looks for:**
- Price drops to lower Bollinger Band (2 standard deviations below 20-day average)
- RSI shows oversold conditions (RSI < 30)
- Bets on the stock bouncing back to its average price

**Buy signal:**
- Price touches or breaks below lower Bollinger Band
- RSI < 30 (oversold)

**Sell signal:**
- Price reaches middle Bollinger Band (mean), OR
- RSI > 60 (momentum returning to neutral), OR
- 5% stop-loss triggered

**Time horizon:** 2-10 days (short swing trades)

**Best for:** Range-bound markets, stocks with established support levels

### 3. Value Factor
**Ranks stocks by fundamental value metrics.**

**What it looks for:**
- Low P/E ratio (price relative to earnings)
- Low P/B ratio (price relative to book value)
- Low EV/EBITDA ratio (enterprise value relative to cash flow)
- Composite score ranks all stocks; buys top 20%

**Buy signal:**
- Stock ranks in top 20% by composite value score
- Rebalance occurs every 5+ days

**Sell signal:**
- Stock drops out of top 20%
- Rebalance period reached

**Time horizon:** 5-30 days (position trading)

**Best for:** Long-term value investing, fundamental-driven portfolios

## How Strategies Are Ranked

The system uses **walk-forward validation** to test strategies on historical data, then ranks them by a composite score.

### Walk-Forward Process

1. **Train period:** 24 months of historical data
2. **Test period:** 6 months of out-of-sample data
3. **Step forward:** Advance 3 months, retrain, test again
4. **Repeat:** Continue stepping through history

This simulates real-world conditions where the future is unknown.

<!-- DIAGRAM: Timeline showing train/test/step windows sliding through historical data -->

### Ranking Metrics

Each strategy is scored on five metrics:

| Metric | Weight | What It Measures |
|--------|--------|------------------|
| [Sharpe Ratio](../glossary.md#sharpe-ratio) | 30% | Risk-adjusted return (return per unit of volatility) |
| [Sortino Ratio](../glossary.md#sortino-ratio) | 20% | Downside risk-adjusted return (only penalizes downside volatility) |
| Max Drawdown (Inverse) | 20% | Worst peak-to-trough loss (lower is better, inverted for scoring) |
| [Profit Factor](../glossary.md#profit-factor) | 15% | Gross profit ÷ gross loss |
| Consistency | 15% | Percentage of positive months |

**Composite score formula:**
```
score = (0.30 × Sharpe) + (0.20 × Sortino) + (0.20 × MaxDD_inv) +
        (0.15 × ProfitFactor) + (0.15 × Consistency)
```

### Minimum Thresholds

To be eligible for live trading, a strategy must meet these thresholds in backtesting:

- **Sharpe ratio:** ≥ 1.0 (strong risk-adjusted returns)
- **Profit factor:** ≥ 1.5 (win $1.50 for every $1.00 lost)
- **Max drawdown:** ≤ 20% (largest loss no worse than 20%)
- **Min trades:** ≥ 100 trades (statistically significant sample)

Strategies that fail these thresholds are not deployed, even if their composite score is high.

## Strategy Selection

The system displays ranked strategies on the Strategies page:

1. **Top-ranked strategy:** Highest composite score, meets all thresholds
2. **Performance details:** Sharpe, Sortino, drawdown, profit factor, win rate
3. **Trade history:** Recent signals and execution quality

You can:
- Enable/disable strategies
- View detailed backtest results
- Compare strategies side-by-side

## ML Signal Strategy (Advanced)

In addition to the three rule-based strategies, the system includes an [ML Signal Strategy](./ml-signals.md) that uses machine learning to predict stock movements. This strategy uses 50+ features and XGBoost to generate buy/sell signals.

See [ML Signal Intelligence](./ml-signals.md) for details.

## Configuration

Strategy thresholds and ranking weights are in `config/settings.yaml`:

```yaml
strategy:
  min_sharpe_ratio: 1.0
  min_profit_factor: 1.5
  max_drawdown_pct: 20.0
  min_trades: 100

  walk_forward:
    train_months: 24
    test_months: 6
    step_months: 3

  ranking_weights:
    sharpe: 0.30
    sortino: 0.20
    max_drawdown_inverse: 0.20
    profit_factor: 0.15
    consistency: 0.15
```

## Related Topics

- [ML Signal Intelligence](./ml-signals.md) — Machine learning strategy
- [PDT Rule](./pdt-rule.md) — Why all strategies use min_hold_days ≥ 2
- [Risk Management](./risk-management.md) — Position sizing and stop-losses
- [Glossary](../glossary.md) — Definitions of Sharpe ratio, Sortino ratio, etc.
