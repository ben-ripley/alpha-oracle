"""Tests for the SentimentFeatureCalculator."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from src.core.models import SentimentScore
from src.signals.features.sentiment import SentimentFeatureCalculator


def _score(symbol: str = "AAPL", days_ago: int = 0, sentiment: float = 0.5, source: str = "news") -> SentimentScore:
    return SentimentScore(
        symbol=symbol,
        timestamp=datetime.now(timezone.utc) - timedelta(days=days_ago),
        source=source,
        text_snippet="test",
        sentiment=sentiment,
        confidence=abs(sentiment),
    )


class TestEmptyAndNoneInputs:
    """Test graceful degradation with missing data."""

    def test_none_scores_returns_nan_columns(self):
        calc = SentimentFeatureCalculator()
        dates = [datetime(2026, 1, 1), datetime(2026, 1, 2)]
        df = calc.compute(None, dates)
        assert not df.empty
        assert "sentiment_mean_7d" in df.columns
        assert df["sentiment_mean_7d"].isna().all()

    def test_empty_scores_returns_nan_columns(self):
        calc = SentimentFeatureCalculator()
        dates = [datetime(2026, 1, 1)]
        df = calc.compute([], dates)
        assert df["sentiment_mean_30d"].isna().all()

    def test_empty_dates_returns_empty_df(self):
        calc = SentimentFeatureCalculator()
        df = calc.compute([_score()], [])
        assert df.empty

    def test_nan_has_all_expected_columns(self):
        calc = SentimentFeatureCalculator()
        df = calc.compute(None, [datetime(2026, 1, 1)])
        expected = [
            "sentiment_mean_7d", "sentiment_mean_30d", "sentiment_std_7d",
            "sentiment_trend", "sentiment_news_count_7d", "sentiment_filing_score",
        ]
        for col in expected:
            assert col in df.columns


class TestFeatureValues:
    """Test correct feature computation."""

    def test_mean_7d_computed(self):
        calc = SentimentFeatureCalculator()
        scores = [_score(days_ago=i, sentiment=0.5) for i in range(5)]
        dates = [datetime.now().replace(tzinfo=None)]
        df = calc.compute(scores, dates)
        assert df["sentiment_mean_7d"].iloc[0] == pytest.approx(0.5)

    def test_mean_30d_includes_older_scores(self):
        calc = SentimentFeatureCalculator()
        # 3 recent scores + 1 older (20 days ago)
        scores = [
            _score(days_ago=1, sentiment=0.8),
            _score(days_ago=2, sentiment=0.6),
            _score(days_ago=20, sentiment=0.2),
        ]
        dates = [datetime.now().replace(tzinfo=None)]
        df = calc.compute(scores, dates)
        # 30d mean includes all 3; 7d mean only includes first 2
        assert df["sentiment_mean_30d"].iloc[0] < df["sentiment_mean_7d"].iloc[0]

    def test_news_count_7d_correct(self):
        calc = SentimentFeatureCalculator()
        scores = [_score(days_ago=i, sentiment=0.5) for i in range(10)]
        dates = [datetime.now().replace(tzinfo=None)]
        df = calc.compute(scores, dates)
        assert df["sentiment_news_count_7d"].iloc[0] == 7

    def test_filing_score_uses_filing_source(self):
        calc = SentimentFeatureCalculator()
        scores = [
            _score(days_ago=1, sentiment=0.9, source="filing"),
            _score(days_ago=2, sentiment=0.1, source="news"),
        ]
        dates = [datetime.now().replace(tzinfo=None)]
        df = calc.compute(scores, dates)
        # Filing score should be ~0.9, not average of all
        assert df["sentiment_filing_score"].iloc[0] == pytest.approx(0.9)

    def test_pit_correctness_no_future_data(self):
        calc = SentimentFeatureCalculator()
        # Score from the future should not be included
        scores = [
            _score(days_ago=-5, sentiment=0.9),  # future
            _score(days_ago=2, sentiment=0.3),   # past
        ]
        as_of = datetime.now().replace(tzinfo=None) - timedelta(days=1)
        df = calc.compute(scores, [as_of])
        # Mean should only include the past score
        assert df["sentiment_mean_7d"].iloc[0] == pytest.approx(0.3)

    def test_std_7d_with_multiple_scores(self):
        calc = SentimentFeatureCalculator()
        scores = [
            _score(days_ago=1, sentiment=0.8),
            _score(days_ago=2, sentiment=0.2),
            _score(days_ago=3, sentiment=0.5),
        ]
        dates = [datetime.now().replace(tzinfo=None)]
        df = calc.compute(scores, dates)
        assert not np.isnan(df["sentiment_std_7d"].iloc[0])
        assert df["sentiment_std_7d"].iloc[0] > 0

    def test_trend_computed_with_3plus_scores(self):
        calc = SentimentFeatureCalculator()
        # Increasing sentiment over 6 days -> positive slope
        scores = [_score(days_ago=6 - i, sentiment=float(i) * 0.1) for i in range(7)]
        dates = [datetime.now().replace(tzinfo=None)]
        df = calc.compute(scores, dates)
        assert not np.isnan(df["sentiment_trend"].iloc[0])

    def test_trend_nan_with_fewer_than_3_scores(self):
        calc = SentimentFeatureCalculator()
        scores = [_score(days_ago=1, sentiment=0.5)]
        dates = [datetime.now().replace(tzinfo=None)]
        df = calc.compute(scores, dates)
        assert np.isnan(df["sentiment_trend"].iloc[0])

    def test_multiple_dates_indexed_correctly(self):
        calc = SentimentFeatureCalculator()
        scores = [_score(days_ago=i, sentiment=0.5) for i in range(10)]
        dates = [
            datetime.now().replace(tzinfo=None) - timedelta(days=2),
            datetime.now().replace(tzinfo=None),
        ]
        df = calc.compute(scores, dates)
        assert len(df) == 2

    def test_no_scores_in_window_returns_nan(self):
        calc = SentimentFeatureCalculator()
        # Score from 60 days ago — outside 30d window
        scores = [_score(days_ago=60, sentiment=0.5)]
        dates = [datetime.now().replace(tzinfo=None)]
        df = calc.compute(scores, dates)
        assert np.isnan(df["sentiment_mean_7d"].iloc[0])
        assert np.isnan(df["sentiment_mean_30d"].iloc[0])

    def test_count_is_zero_when_no_7d_scores(self):
        calc = SentimentFeatureCalculator()
        scores = [_score(days_ago=60, sentiment=0.5)]
        dates = [datetime.now().replace(tzinfo=None)]
        df = calc.compute(scores, dates)
        assert df["sentiment_news_count_7d"].iloc[0] == 0

    def test_negative_sentiment_handled(self):
        calc = SentimentFeatureCalculator()
        scores = [_score(days_ago=1, sentiment=-0.7)]
        dates = [datetime.now().replace(tzinfo=None)]
        df = calc.compute(scores, dates)
        assert df["sentiment_mean_7d"].iloc[0] == pytest.approx(-0.7)

    def test_filing_score_nan_when_no_filing_sources(self):
        calc = SentimentFeatureCalculator()
        scores = [_score(days_ago=1, sentiment=0.5, source="news")]
        dates = [datetime.now().replace(tzinfo=None)]
        df = calc.compute(scores, dates)
        assert np.isnan(df["sentiment_filing_score"].iloc[0])

    def test_10k_source_included_in_filing_score(self):
        calc = SentimentFeatureCalculator()
        scores = [_score(days_ago=1, sentiment=0.6, source="10-k")]
        dates = [datetime.now().replace(tzinfo=None)]
        df = calc.compute(scores, dates)
        assert not np.isnan(df["sentiment_filing_score"].iloc[0])
        assert df["sentiment_filing_score"].iloc[0] == pytest.approx(0.6)

    def test_result_indexed_by_date(self):
        calc = SentimentFeatureCalculator()
        dt = datetime(2026, 1, 15)
        df = calc.compute(None, [dt])
        assert df.index.name == "date"
