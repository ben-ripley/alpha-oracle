# ADR-003: ML/AI Model Architecture - Layered Approach

**Status:** Accepted

**Decision:** Start simple, add complexity only when it beats the baseline.

- **Phase 1:** Rule-based factor models (momentum crossover, mean reversion, value factors). No ML. Establishes baseline and validates infrastructure.
- **Phase 2:** XGBoost ensemble as primary signal generator. scikit-learn for feature engineering. Features: technical indicators, fundamentals, cross-asset signals, insider activity.
- **Phase 3:** Add FinBERT sentiment signals as XGBoost features. Optionally LSTM (PyTorch) for specific time-series tasks where XGBoost underperforms.

**Why XGBoost over deep learning:** XGBoost consistently wins financial ML competitions on tabular data, handles missing values natively, provides feature importance, and is fast to train. Deep learning (LSTM/Transformer) requires much more data, is prone to overfitting, and harder to interpret.

**Why not reinforcement learning:** Extremely sample-inefficient, brittle, hard to debug. Deferred indefinitely.

**Key pitfalls to guard against:** Overfitting (walk-forward validation), look-ahead bias (point-in-time features only), survivorship bias (include delisted stocks), regime changes (strategy decay detection).
