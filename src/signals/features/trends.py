"""Google Trends feature calculator for ML signal pipeline."""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from src.core.models import TrendsData

_TRENDS_COLS = [
    "search_trend_momentum_7d",
    "search_trend_zscore",
    "search_trend_acceleration",
]


class TrendsFeatureCalculator:
    """Compute search trend features with point-in-time safety."""

    def compute(
        self,
        trends: list[TrendsData] | None,
        as_of_dates: list[datetime],
        lookback_days: int = 30,
    ) -> pd.DataFrame:
        """Compute search trend features for each as_of_date.

        Returns DataFrame indexed by date. NaN columns when no data (graceful degradation).
        """
        if not as_of_dates:
            return pd.DataFrame(columns=_TRENDS_COLS)

        index = pd.DatetimeIndex(sorted(as_of_dates), name="date")
        features = pd.DataFrame(index=index)

        if not trends:
            for col in _TRENDS_COLS:
                features[col] = np.nan
            return features

        sorted_trends = sorted(trends, key=lambda t: t.timestamp)

        momentums, zscores, accelerations = [], [], []

        for dt in index:
            dt_naive = dt.to_pydatetime().replace(tzinfo=None)

            # All trend data up to as_of_date within lookback window
            window_30d = [
                t for t in sorted_trends
                if t.timestamp.replace(tzinfo=None) <= dt_naive
                and t.timestamp.replace(tzinfo=None) > (dt_naive - timedelta(days=lookback_days))
            ]
            window_7d = [
                t for t in window_30d
                if t.timestamp.replace(tzinfo=None) > (dt_naive - timedelta(days=7))
            ]

            # Average interest across all keywords per window
            interests_30d = [t.interest_over_time for t in window_30d]
            interests_7d = [t.interest_over_time for t in window_7d]

            if not interests_7d:
                momentums.append(np.nan)
                accelerations.append(np.nan)
            else:
                # Momentum: mean of last 7d vs prior 7d (8-14d ago)
                window_prev7 = [
                    t for t in window_30d
                    if t.timestamp.replace(tzinfo=None) <= (dt_naive - timedelta(days=7))
                    and t.timestamp.replace(tzinfo=None) > (dt_naive - timedelta(days=14))
                ]
                interests_prev7 = [t.interest_over_time for t in window_prev7]

                mean_7d = float(np.mean(interests_7d))
                if interests_prev7:
                    mean_prev7 = float(np.mean(interests_prev7))
                    momentums.append(mean_7d - mean_prev7)
                else:
                    momentums.append(np.nan)

                # Acceleration: second derivative (change in momentum)
                if len(interests_7d) >= 3:
                    xs = np.arange(len(interests_7d), dtype=float)
                    ys = np.array(interests_7d, dtype=float)
                    # Use 2nd derivative of linear fit (constant for linear, so use slope change)
                    poly = np.polyfit(xs, ys, 2)
                    accelerations.append(float(poly[0]) * 2)  # 2nd derivative of quadratic
                else:
                    accelerations.append(np.nan)

            if len(interests_30d) >= 2:
                mean_30 = float(np.mean(interests_30d))
                std_30 = float(np.std(interests_30d, ddof=1))
                if std_30 > 0 and interests_7d:
                    latest_interest = float(np.mean(interests_7d))
                    zscores.append((latest_interest - mean_30) / std_30)
                else:
                    zscores.append(0.0)
            else:
                zscores.append(np.nan)

        features["search_trend_momentum_7d"] = momentums
        features["search_trend_zscore"] = zscores
        features["search_trend_acceleration"] = accelerations

        return features
