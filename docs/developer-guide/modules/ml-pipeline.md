# ML Pipeline Module

The `src/signals/` module implements a complete machine learning pipeline for stock signal generation: feature engineering (50+ point-in-time features), [XGBoost](../glossary.md#xgboost) training with walk-forward validation, confidence calibration, model monitoring (PSI drift, rolling accuracy), and model registry (register/promote/rollback).

## Purpose

The ML pipeline provides:

- **Feature store** orchestrating 5 calculators (technical, fundamental, cross-asset, alternative, temporal) with point-in-time joins
- **XGBoost pipeline** for 3-class classification (UP/DOWN/FLAT)
- **Walk-forward validation** with Optuna hyperparameter tuning
- **Confidence calibration** via Platt scaling
- **Model registry** for versioning, promotion, and rollback
- **Model monitoring** for distribution drift (PSI) and rolling accuracy
- **MLSignalStrategy** wrapping predictions as tradeable signals

## Key Components

### Feature Store

#### `FeatureStore` (src/signals/feature_store.py)

Orchestrates all feature calculators, performs point-in-time (PIT) joins, and persists feature matrices to Parquet.

**Methods:**

| Method | Purpose | Returns |
|--------|---------|---------|
| `compute_features(symbol, bars, spy_bars, vix_bars, sector_bars, fundamentals, sector_fundamentals, insider_transactions, short_interest)` | Compute all features for a single symbol | DataFrame with 50+ columns indexed by date |
| `get_features(symbols, start, end, data_provider)` | Get feature matrix for multiple symbols | DataFrame with (symbol, date) multi-index |
| `load(symbol, start, end)` | Load cached features from Parquet | DataFrame (or None if cache miss) |
| `save(symbol, features)` | Save features to Parquet | None |

**Feature Categories:**

1. **Technical Features** (30+ indicators via `TechnicalFeatureCalculator`):
   - Momentum: RSI(14), MACD, ROC(10), Stochastic
   - Trend: SMA(20/50/200), EMA(12/26), ADX
   - Volatility: ATR(14), Bollinger Bands, Historical Volatility
   - Volume: OBV, VWAP, Volume SMA ratio
   - Price patterns: Distance from highs/lows, range metrics

2. **Fundamental Features** (via `FundamentalFeatureCalculator`):
   - Valuation: P/E, P/B, P/S, EV/EBITDA, relative to sector median
   - Profitability: ROE, current ratio, debt-to-equity
   - Growth: Revenue growth, earnings growth, dividend yield
   - Sector exposure: Sector dummy variables

3. **Cross-Asset Features** (via `CrossAssetFeatureCalculator`):
   - SPY correlation (60-day rolling)
   - SPY relative strength (symbol return / SPY return)
   - Sector relative strength (symbol return / sector ETF return)
   - VIX level (market fear gauge)

4. **Alternative Features** (via `AlternativeFeatureCalculator`):
   - Insider activity: Net insider buys (last 90 days), total shares purchased, total value
   - Short interest: Short interest ratio, days to cover, change in short interest

5. **Temporal Features** (via `TemporalFeatureCalculator`):
   - Day of week (Monday=1, Friday=5)
   - Month of year (January=1, December=12)
   - Quarter (1-4)
   - Days since year start
   - Is month-end (binary)

**Point-in-Time Join Logic:**

Fundamental and alternative data are sparse (weekly, biweekly). The feature store uses **forward-fill** to align these to daily OHLCV bars, ensuring no lookahead bias:

```python
# Fundamentals filed on 2024-01-15 apply to all bars from 2024-01-15 onward until next filing
fundamentals_df = self._compute_pit_fundamentals(bar_dates, fundamentals, sector_fundamentals)

# Insider transactions filed on 2024-02-01 count toward net buys from 2024-02-01 onward
alt_df = self._compute_alternative_features(bar_dates, insider_transactions, short_interest)

# Left-join all feature categories on date index
result = tech_df.join(fundamentals_df).join(cross_df).join(alt_df).join(temp_df)
```

**Parquet Cache:**
- Features cached in `data/features/{symbol}.parquet` (or `.pkl` if pyarrow not available).
- Cache hit: `load(symbol, start, end)` reads Parquet and filters by date range.
- Cache miss: `compute_features()` recalculates and saves.

### ML Pipeline

#### `MLPipeline` (src/signals/ml/pipeline.py)

XGBoost training pipeline for 3-class classification.

**Target Encoding:**

Forward returns define the target:
```python
horizon = 5  # config.ml.prediction_horizon
forward_return = (close[t+5] - close[t]) / close[t]

if forward_return > 0.01:  # config.ml.up_threshold
    target = 2  # UP
elif forward_return < -0.01:  # config.ml.down_threshold
    target = 0  # DOWN
else:
    target = 1  # FLAT
```

Last `horizon` rows (where forward return is NaN) are dropped from training.

**Training:**

```python
from src.signals.ml.pipeline import MLPipeline

pipeline = MLPipeline()
target = pipeline.prepare_target(df, close_col="close")
metrics = pipeline.train(features, target)

# metrics = {"accuracy": 0.58, "log_loss": 0.95, "class_distribution": [0.30, 0.40, 0.30]}
```

**Class Imbalance Handling:**
- Sample weights: `w[i] = total_samples / (n_classes * class_count[y[i]])`
- Gives minority classes (UP/DOWN) higher weight to balance the dataset

**Model Configuration** (config/settings.yaml):
```yaml
ml:
  prediction_horizon: 5
  up_threshold: 0.01
  down_threshold: -0.01
  min_training_samples: 500
  retrain_interval_days: 7
  model_staleness_days: 14
  confidence_threshold: 0.55
  xgb_params:
    n_estimators: 300
    max_depth: 6
    learning_rate: 0.05
    subsample: 0.8
    colsample_bytree: 0.8
    min_child_weight: 5
    objective: multi:softprob
    num_class: 3
    eval_metric: mlogloss
```

**Prediction:**
```python
predictions = pipeline.predict(features)
# predictions shape: (n_samples, 3) — probabilities for [DOWN, FLAT, UP]

pred_classes = predictions.argmax(axis=1)  # 0/1/2
pred_confidence = predictions.max(axis=1)  # max probability
```

### Walk-Forward Validation

#### `WalkForwardValidator` (src/signals/ml/validation.py)

Implements time-series cross-validation with hyperparameter tuning.

**Logic:**
1. Split data into train/test windows (default: 24 months train, 6 months test, 3-month step).
2. For each window:
   - Tune hyperparameters on training period via Optuna (100 trials).
   - Train XGBoost with best hyperparameters.
   - Predict on test period.
   - Compute metrics (accuracy, log loss, Sharpe ratio of signal-based returns).
3. Return list of validation results (one per window).

**Hyperparameter Search Space:**
- `n_estimators`: [100, 500]
- `max_depth`: [3, 10]
- `learning_rate`: [0.01, 0.2]
- `subsample`: [0.6, 1.0]
- `colsample_bytree`: [0.6, 1.0]
- `min_child_weight`: [1, 10]

**Usage:**
```python
from src.signals.ml.validation import WalkForwardValidator

validator = WalkForwardValidator()
results = validator.run(features, target, train_months=24, test_months=6, step_months=3)

for result in results:
    print(f"Test period {result['start']} to {result['end']}: accuracy={result['accuracy']:.3f}")
```

### Confidence Calibration

#### `ConfidenceCalibrator` (src/signals/ml/calibration.py)

Uses Platt scaling (logistic regression on predicted probabilities) to calibrate XGBoost output probabilities to true likelihoods.

**Why Calibration?**
- XGBoost probabilities are often overconfident (e.g., 0.95 confidence but only 70% actual accuracy).
- Calibration ensures `P(correct | confidence=0.8) ≈ 0.8`.

**Training:**
```python
from sklearn.calibration import CalibratedClassifierCV

calibrator = CalibratedClassifierCV(xgb_model, method="sigmoid", cv=5)
calibrator.fit(X_train, y_train)
```

**Prediction:**
```python
calibrated_probs = calibrator.predict_proba(X_test)
# Now probabilities are better aligned with actual outcomes
```

### Model Registry

#### `ModelRegistry` (src/signals/ml/registry.py)

Tracks model versions, metrics, and active/inactive status.

**Methods:**

| Method | Purpose | Returns |
|--------|---------|---------|
| `register(version_id, model_path, metrics)` | Register a new model version | ModelVersion |
| `get_active()` | Get currently active (deployed) model | ModelVersion or None |
| `promote(version_id)` | Promote a version to active (deactivates others) | bool |
| `rollback(version_id)` | Roll back to a previous version | bool |
| `list_versions()` | List all registered versions | list[ModelVersion] |

**Version Metadata:**
- `version_id`: Timestamp-based ID (e.g., "20240315_120000")
- `path`: File path to saved model (e.g., "models/xgb_20240315_120000.pkl")
- `metrics`: dict with accuracy, log_loss, sharpe_ratio, etc.
- `created_at`: datetime
- `is_active`: bool

**Storage:**
- Models saved as pickle files in `models/` directory.
- Metadata stored in Redis (key: `ml:models:{version_id}`).

**Usage:**
```python
from src.signals.ml.registry import ModelRegistry

registry = ModelRegistry(models_dir="models")

# After training
version = registry.register(
    version_id="20240315_120000",
    model_path="models/xgb_20240315_120000.pkl",
    metrics={"accuracy": 0.58, "sharpe_ratio": 1.2}
)

# Promote to active
registry.promote("20240315_120000")

# Later: rollback if new model underperforms
registry.rollback("20240310_090000")
```

### Model Monitoring

#### `ModelMonitor` (src/signals/ml/monitoring.py)

Tracks distribution drift (PSI) and rolling accuracy for deployed models.

**Population Stability Index (PSI):**

Measures distribution shift between training and production feature distributions:

```
PSI = sum((actual_pct - expected_pct) * log(actual_pct / expected_pct))

PSI < 0.1: No significant drift
PSI 0.1-0.2: Minor drift (monitor)
PSI > 0.2: Major drift (retrain required)
```

**Rolling Accuracy:**
- Tracks accuracy over last N predictions (default: 100).
- Alerts if accuracy drops below threshold (e.g., 0.50).

**Monitoring Workflow:**
1. On each prediction batch:
   - Compute feature distribution → compare to training distribution → calculate PSI.
   - Append predictions + actual outcomes to rolling window.
   - Compute rolling accuracy.
2. If PSI > 0.2 or accuracy < 0.50:
   - Trigger alert (Slack/Telegram via `AlertManager`).
   - Log event to `ml:drift:events` Redis stream.
   - Optionally trigger retraining job.

### MLSignalStrategy

#### `MLSignalStrategy` (src/signals/ml_strategy.py)

Wraps XGBoost predictions as a trading strategy implementing `BaseStrategy`.

**Properties:**
- `name`: "MLSignalStrategy"
- `description`: "XGBoost-based signal generation with 3-class prediction (UP/DOWN/FLAT)"
- `min_hold_days`: 3 (longer than minimum 2 for PDT compliance, reflecting ML prediction horizon)

**Signal Generation:**
```python
def generate_signals(self, data: dict[str, list[OHLCV]]) -> list[Signal]:
    signals = []
    for symbol, bars in data.items():
        # 1. Compute features via FeatureStore
        features = self.feature_store.compute_features(symbol, bars, ...)

        # 2. Predict with active model
        probs = self.pipeline.predict(features)
        pred_class = probs.argmax(axis=1)[-1]  # Most recent prediction
        confidence = probs.max(axis=1)[-1]

        # 3. Convert to signal if confidence > threshold (0.55)
        if confidence > self.config.confidence_threshold:
            if pred_class == 2:  # UP
                direction = SignalDirection.LONG
            elif pred_class == 0:  # DOWN
                direction = SignalDirection.SHORT
            else:  # FLAT
                continue  # No signal

            signals.append(Signal(
                symbol=symbol,
                timestamp=bars[-1].timestamp,
                direction=direction,
                strength=confidence,  # Use calibrated probability as strength
                strategy_name=self.name,
                metadata={"prediction_class": int(pred_class), "confidence": float(confidence)}
            ))
    return signals
```

**Integration:**
- Registered with `StrategyEngine` like any other strategy.
- Backtested via `run_backtest()` and `run_walk_forward()`.
- Deployed in production: signals → orders → execution.

## Data Flow

<!-- DIAGRAM: ML pipeline flow — raw data → feature store → XGBoost training → model registry → MLSignalStrategy → signals → execution -->

1. **Feature Engineering:**
   - Scheduled jobs (daily_bars, weekly_fundamentals, biweekly_altdata) populate TimescaleDB.
   - `FeatureStore.compute_features()` reads OHLCV, fundamentals, insider trades, short interest.
   - Features cached to Parquet in `data/features/`.

2. **Training (weekly_retrain_job):**
   - Load features for universe symbols (last 2 years).
   - Prepare target from forward returns.
   - Run walk-forward validation to tune hyperparameters.
   - Train final model on all available data.
   - Register model with `ModelRegistry`.
   - Promote to active if metrics exceed threshold.

3. **Prediction (live trading):**
   - `MLSignalStrategy.generate_signals()` called by execution engine.
   - Computes features for current bar.
   - Predicts with active model from registry.
   - Converts high-confidence predictions to signals.
   - Model monitor tracks PSI drift and rolling accuracy.

4. **Monitoring & Retraining:**
   - If PSI > 0.2 or accuracy drops:
     - Alert sent to Slack/Telegram.
     - Retraining job triggered (can be manual or automated).
   - New model registered and promoted.
   - Old model remains available for rollback.

## Configuration

**Settings (config/settings.yaml):**
```yaml
ml:
  prediction_horizon: 5          # Days ahead to predict
  up_threshold: 0.01             # +1% return → UP class
  down_threshold: -0.01          # -1% return → DOWN class
  min_training_samples: 500      # Minimum rows for training
  retrain_interval_days: 7       # Weekly retraining
  model_staleness_days: 14       # Alert if model older than 14 days
  confidence_threshold: 0.55     # Min probability to generate signal
  xgb_params:
    n_estimators: 300
    max_depth: 6
    learning_rate: 0.05
    subsample: 0.8
    colsample_bytree: 0.8
    min_child_weight: 5
    objective: multi:softprob
    num_class: 3
    eval_metric: mlogloss
```

**Environment Variable Overrides:**
```bash
export SA_ML__PREDICTION_HORIZON=3
export SA_ML__UP_THRESHOLD=0.015
export SA_ML__CONFIDENCE_THRESHOLD=0.60
export SA_ML__XGB_PARAMS__N_ESTIMATORS=500
```

## Integration with Other Modules

- **Data Ingestion** (`src/data/`): Provides OHLCV, fundamentals, insider trades, short interest → feature store.
- **Strategy Engine** (`src/strategy/`): `MLSignalStrategy` registered as a strategy, backtested, ranked.
- **Execution Engine** (`src/execution/`): Converts ML signals → orders with Kelly sizing.
- **Scheduler** (`src/scheduling/jobs.py`): `weekly_retrain_job` trains and registers models every Sunday at 2am.
- **API** (`src/api/routes/strategies.py`): Endpoints for model metrics, feature importance, drift alerts.
- **Dashboard** (`web/src/pages/`): SignalFeed, FeatureImportance, ModelPerformance, DriftHeatmap components.

## Critical Patterns

1. **Point-in-time joins:** All features use forward-fill to avoid lookahead bias. Fundamental data filed on date D applies to all bars >= D.
2. **Walk-forward validation:** Time-series split (no shuffle) ensures no future data leaks into training.
3. **Class imbalance:** Sample weights balance UP/DOWN/FLAT classes during training.
4. **Confidence threshold:** Only high-confidence predictions (> 0.55) generate signals.
5. **Model staleness:** Alert if active model older than 14 days → triggers retraining.
6. **PSI monitoring:** Drift detection catches distribution shift (e.g., market regime change).
7. **Lazy imports:** XGBoost, scikit-learn imported inside functions to avoid load-time errors.

## Glossary Links

- [XGBoost](../glossary.md#xgboost) — Gradient boosting ML library
- [OHLCV](../glossary.md#ohlcv) — Open/High/Low/Close/Volume bar data
- [PDT](../glossary.md#pdt) — Pattern Day Trader rule
- [Sharpe Ratio](../glossary.md#sharpe-ratio) — Risk-adjusted return metric
- [TimescaleDB](../glossary.md#timescaledb) — Time-series PostgreSQL extension
- [Redis](../glossary.md#redis) — In-memory data store

<!-- DIAGRAM: Feature store architecture — 5 calculators → point-in-time join → Parquet cache -->
