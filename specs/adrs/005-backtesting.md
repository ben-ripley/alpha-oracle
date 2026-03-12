# ADR-005: Backtesting - Backtrader + VectorBT

**Status:** Accepted

**Decision:** Backtrader for event-driven backtesting, VectorBT for rapid parameter optimization.

| Framework | Strength | Use Case |
|---|---|---|
| Backtrader (20.7K stars) | Realistic execution model, broker simulation, 122 indicators | Primary backtesting, strategy validation |
| VectorBT (~4K stars) | 20,000 parameter configs in <30s | Parameter sweeps, optimization |
| QuantConnect Lean (38.6K stars) | Professional-grade, multi-asset | Future upgrade if needed |

**Non-negotiable validation protocol:**
1. Walk-forward analysis (train on [t-N, t], test on [t, t+M], slide forward)
2. Out-of-sample holdout (reserve most recent 20%, touch once)
3. Monte Carlo simulation (randomize trade order/timing)
4. Transaction cost modeling (slippage + spread even at $0 commission)
5. Survivorship bias check (include delisted stocks)
6. Paper trading minimum 30 days before live capital
7. Minimum thresholds: Sharpe > 1.0, max drawdown < 20%, profit factor > 1.5, 100+ trades

**Strategy ranking formula:** Sharpe (30%) + Sortino (20%) + max drawdown inverse (20%) + profit factor (15%) + consistency across time periods (15%)
