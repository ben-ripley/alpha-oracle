"""Sentiment feature calculator for ML signal pipeline."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd

from src.core.models import SentimentScore


def _as_utc(ts: datetime) -> datetime:
    """Normalize a datetime to UTC; treat naive datetimes as UTC."""
    if ts.tzinfo is None:
        return ts.replace(tzinfo=UTC)
    return ts.astimezone(UTC)


_SENTIMENT_COLS = [
    "sentiment_mean_7d",
    "sentiment_mean_30d",
    "sentiment_std_7d",
    "sentiment_trend",
    "sentiment_news_count_7d",
    "sentiment_filing_score",
]


class SentimentFeatureCalculator:
    """Compute sentiment features from SentimentScore records with point-in-time safety."""

    def compute(
        self,
        scores: list[SentimentScore] | None,
        as_of_dates: list[datetime],
    ) -> pd.DataFrame:
        """Compute sentiment features for each as_of_date.

        Returns DataFrame indexed by date. NaN columns when no data (graceful degradation).
        """
        if not as_of_dates:
            return pd.DataFrame(columns=_SENTIMENT_COLS)

        index = pd.DatetimeIndex(sorted(as_of_dates), name="date")
        features = pd.DataFrame(index=index)

        if not scores:
            for col in _SENTIMENT_COLS:
                features[col] = np.nan
            return features

        # Sort scores by timestamp for PIT correctness
        sorted_scores = sorted(scores, key=lambda s: s.timestamp)

        means_7d, means_30d, stds_7d, trends, counts_7d, filing_scores = (
            [], [], [], [], [], []
        )

        for dt in index:
            # PIT: normalize to UTC for comparison; treat naive timestamps as UTC
            as_of_utc = dt.to_pydatetime().replace(tzinfo=UTC)
            scores_30d = [
                s for s in sorted_scores
                if _as_utc(s.timestamp) <= as_of_utc
                and _as_utc(s.timestamp) >= as_of_utc - timedelta(days=30)
            ]
            scores_7d = [
                s for s in scores_30d
                if _as_utc(s.timestamp) >= as_of_utc - timedelta(days=7)
            ]

            # Filing-specific scores (source contains "filing" or "10-k" etc.)
            filing_s = [
                s for s in scores_30d
                if "filing" in s.source.lower() or "10-k" in s.source.lower() or "10-q" in s.source.lower()
            ]

            if not scores_7d:
                means_7d.append(np.nan)
                stds_7d.append(np.nan)
                trends.append(np.nan)
                counts_7d.append(0)
            else:
                sentiments_7d = [s.sentiment for s in scores_7d]
                means_7d.append(float(np.mean(sentiments_7d)))
                stds_7d.append(float(np.std(sentiments_7d, ddof=1)) if len(sentiments_7d) > 1 else 0.0)
                counts_7d.append(len(scores_7d))

                # Trend: slope of sentiment over 7d window (simple linear regression)
                if len(scores_7d) >= 3:
                    xs = np.arange(len(sentiments_7d), dtype=float)
                    ys = np.array(sentiments_7d, dtype=float)
                    slope = float(np.polyfit(xs, ys, 1)[0])
                    trends.append(slope)
                else:
                    trends.append(np.nan)

            if not scores_30d:
                means_30d.append(np.nan)
            else:
                means_30d.append(float(np.mean([s.sentiment for s in scores_30d])))

            if not filing_s:
                filing_scores.append(np.nan)
            else:
                filing_scores.append(float(np.mean([s.sentiment for s in filing_s])))

        features["sentiment_mean_7d"] = means_7d
        features["sentiment_mean_30d"] = means_30d
        features["sentiment_std_7d"] = stds_7d
        features["sentiment_trend"] = trends
        features["sentiment_news_count_7d"] = counts_7d
        features["sentiment_filing_score"] = filing_scores

        return features
