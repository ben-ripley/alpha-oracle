# ML Signal Intelligence

The system uses machine learning (specifically XGBoost, a gradient boosting algorithm) to predict stock price movements and generate buy/sell signals. This is more sophisticated than rule-based strategies because it learns patterns from data.

## What Are ML Signals?

**ML signals** are predictions about whether a stock will go up, down, or stay flat over the next 5 trading days. The system:

1. **Collects 50+ features** about each stock (technical indicators, fundamentals, market data)
2. **Trains an XGBoost model** to predict 5-day forward returns
3. **Classifies movements:** UP (>1%), DOWN (<-1%), or FLAT (-1% to +1%)
4. **Generates signals:** Only acts on predictions with high confidence (≥55%)

The model learns from historical data and continuously retrains to adapt to changing market conditions.

## The 50+ Features

Features are organized into five categories:

### Technical Features (20+ features)
Price and volume-based indicators:
- Moving averages (10-day, 50-day, 200-day)
- RSI (Relative Strength Index)
- MACD (Moving Average Convergence Divergence)
- Bollinger Bands
- Volume ratios (volume relative to 20-day average)
- Price momentum (5-day, 10-day, 20-day returns)

### Fundamental Features (10+ features)
Financial statement data:
- P/E ratio (price-to-earnings)
- P/B ratio (price-to-book)
- P/S ratio (price-to-sales)
- EV/EBITDA (enterprise value to earnings)
- Debt-to-equity ratio
- ROE (return on equity)
- Revenue growth
- Earnings growth
- Sector and industry classification

### Cross-Asset Features (8 features)
Market context:
- SPY correlation (correlation with S&P 500)
- Sector correlation (correlation with sector ETF)
- SPY beta (sensitivity to market movements)
- VIX level (market volatility index)
- Relative strength vs. SPY
- Relative strength vs. sector

### Alternative Features (6 features)
Non-traditional data:
- Insider buying/selling (Form 4 filings)
- Net insider transaction value
- Short interest ratio
- Days to cover short positions
- Short interest change rate

### Temporal Features (4 features)
Time-based patterns:
- Day of week
- Week of month
- Month of year
- Quarter

All features are engineered with **point-in-time correctness**, meaning they only use data that would have been available at prediction time. No future leaking.

<!-- DIAGRAM: Feature categories with examples and counts -->

## How Predictions Work

### Training Phase

1. **Historical data:** Collect 2+ years of daily bars and fundamentals
2. **Feature computation:** Calculate all 50+ features for each stock-date
3. **Label creation:** Tag each date with 5-day forward return (UP/DOWN/FLAT)
4. **Model training:** XGBoost learns patterns that predict forward returns
5. **Validation:** Test on out-of-sample data to measure accuracy

Minimum 500 training samples required before model is considered valid.

### Prediction Phase

1. **Latest data:** Fetch today's price, volume, fundamentals
2. **Compute features:** Calculate all 50+ features using latest data
3. **Model inference:** XGBoost predicts probability of UP/DOWN/FLAT
4. **Confidence check:** Only act if max probability ≥ 55%
5. **Signal generation:** Create BUY signal for UP, SELL signal for DOWN

**Example:**
```
Stock: AAPL
Features: [RSI=45.2, MA_10/50_cross=True, PE=28.4, ...]
Prediction: [DOWN: 15%, FLAT: 25%, UP: 60%]
Confidence: 60% (≥ 55% threshold)
→ Signal: BUY (LONG) with strength 0.60
```

## Confidence Calibration

Raw probabilities from XGBoost can be overconfident. The system uses **confidence calibration** to adjust probabilities to match empirical accuracy.

If the model says "60% confident," calibration ensures that historically, it was correct ~60% of the time at that confidence level.

This prevents overtrading on false confidence.

## Model Retraining

The market changes constantly, so the model must adapt:

- **Retraining schedule:** Every Sunday at 2am (weekly)
- **Incremental learning:** Uses latest data from the past week
- **Staleness detection:** Model is considered stale after 14 days without retraining
- **Automatic fallback:** If model is stale or missing, system uses rule-based strategies instead

Retraining job runs automatically via APScheduler cron. No manual intervention needed.

## Drift Monitoring

**Data drift** occurs when the statistical properties of features change over time. The system monitors drift using PSI (Population Stability Index):

- **PSI score:** Measures how much feature distributions have shifted
- **Thresholds:** PSI > 0.1 = minor drift, PSI > 0.2 = major drift
- **Alerts:** Dashboard shows drift warnings when detected
- **Response:** Major drift triggers model retraining

Drift monitoring runs daily and is displayed on the Model Health dashboard.

## MLSignalStrategy Details

The ML strategy operates like other strategies but with ML-generated signals:

- **Name:** `ml_xgboost_signal`
- **Min hold days:** 3 (PDT compliant)
- **Signal generation:** Only high-confidence predictions (≥55%)
- **Feature importance:** Tracks which features drive predictions
- **Model path:** `models/xgboost_signal.joblib`

If the model is missing or stale, the strategy returns FLAT signals (no trades) until a valid model is available.

## Model Performance Tracking

The dashboard displays:

- **Rolling accuracy:** 30-day and 90-day accuracy rates
- **Precision/recall:** For UP and DOWN predictions
- **Feature importance:** Top 10 features driving predictions
- **Drift heatmap:** PSI scores for all features
- **Model version history:** Track deployed models over time

<!-- DIAGRAM: Model performance dashboard with accuracy chart and feature importance bar chart -->

## Configuration

ML settings in `config/settings.yaml`:

```yaml
ml:
  prediction_horizon: 5              # Predict 5-day forward returns
  up_threshold: 0.01                 # >1% = UP
  down_threshold: -0.01              # <-1% = DOWN
  min_training_samples: 500          # Min data points for training
  retrain_interval_days: 7           # Weekly retraining
  model_staleness_days: 14           # Model expires after 14 days
  confidence_threshold: 0.55         # Min 55% confidence to act

  xgb_params:                        # XGBoost hyperparameters
    n_estimators: 300
    max_depth: 6
    learning_rate: 0.05
    subsample: 0.8
    colsample_bytree: 0.8
```

## When to Use ML Signals

**Advantages:**
- Learns complex, non-linear patterns
- Adapts to changing market conditions
- Integrates diverse data sources (technical, fundamental, alternative)
- Feature importance shows what drives predictions

**Disadvantages:**
- Requires more data (500+ samples)
- Computationally expensive (retraining takes time)
- Less interpretable than rule-based strategies
- Risk of overfitting to historical patterns

**Recommended for:**
- Users comfortable with machine learning concepts
- Portfolios with access to rich fundamental and alternative data
- Long-term trading (5+ day horizons)

## Related Topics

- [Trading Strategies](./strategies-explained.md) — Rule-based strategies (Swing Momentum, Mean Reversion, Value Factor)
- [Risk Management](./risk-management.md) — How ML signals are constrained by risk limits
- [PDT Rule](./pdt-rule.md) — Why MLSignalStrategy uses min_hold_days = 3
- [Monitoring & Alerts](../operations/monitoring-alerts.md) — Model health notifications
