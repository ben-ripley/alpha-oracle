"""ML signal quality metrics for walk-forward validation."""
from __future__ import annotations

import numpy as np
from sklearn.metrics import log_loss as _sklearn_log_loss


def directional_accuracy(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Fraction of predictions that got the direction right.

    Labels: 0=DOWN, 1=FLAT, 2=UP.
    A prediction is correct if it matches the true label exactly.
    """
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    if len(y_true) == 0:
        return 0.0
    return float(np.mean(y_true == y_pred))


def profit_weighted_accuracy(
    y_true: np.ndarray, y_pred: np.ndarray, returns: np.ndarray
) -> float:
    """Accuracy weighted by the magnitude of actual returns.

    Correct directional predictions are weighted by abs(return).
    Returns the ratio of weighted-correct to total weight.
    """
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    returns = np.asarray(returns, dtype=float)
    if len(y_true) == 0:
        return 0.0

    abs_ret = np.abs(returns)
    total_weight = abs_ret.sum()
    if total_weight == 0:
        return 0.0

    correct = y_true == y_pred
    return float((correct * abs_ret).sum() / total_weight)


def signal_max_drawdown(cumulative_returns: np.ndarray) -> float:
    """Maximum drawdown of signal-generated cumulative returns.

    Args:
        cumulative_returns: Cumulative return series (e.g. from cumprod or cumsum).

    Returns:
        Maximum drawdown as a positive float (0.10 = 10% drawdown).
    """
    cumulative_returns = np.asarray(cumulative_returns, dtype=float)
    if len(cumulative_returns) < 2:
        return 0.0

    running_max = np.maximum.accumulate(cumulative_returns)
    drawdowns = (running_max - cumulative_returns) / np.where(
        running_max != 0, running_max, 1.0
    )
    return float(np.max(drawdowns))


def log_loss_score(y_true: np.ndarray, y_proba: np.ndarray) -> float:
    """Multi-class log loss.

    Args:
        y_true: True class labels (0, 1, 2).
        y_proba: Predicted probabilities, shape (n_samples, 3).

    Returns:
        Log loss score (lower is better).
    """
    y_true = np.asarray(y_true)
    y_proba = np.asarray(y_proba)
    return float(_sklearn_log_loss(y_true, y_proba, labels=[0, 1, 2]))
