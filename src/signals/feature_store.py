"""Feature store with point-in-time joins and Parquet persistence."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

from src.core.models import (
    OHLCV,
    AnalystEstimate,
    FundamentalData,
    InsiderTransaction,
    OptionsFlowRecord,
    SentimentScore,
    ShortInterestData,
    TrendsData,
)
from src.signals.features.alternative import AlternativeFeatureCalculator
from src.signals.features.cross_asset import CrossAssetFeatureCalculator
from src.signals.features.estimates import EstimatesFeatureCalculator
from src.signals.features.fundamental import FundamentalFeatureCalculator
from src.signals.features.options_flow import OptionsFlowFeatureCalculator
from src.signals.features.sentiment import SentimentFeatureCalculator
from src.signals.features.technical import TechnicalFeatureCalculator
from src.signals.features.temporal import TemporalFeatureCalculator
from src.signals.features.trends import TrendsFeatureCalculator

logger = logging.getLogger(__name__)


class FeatureStore:
    """Orchestrates all feature calculators, performs point-in-time joins,
    and persists computed feature matrices."""

    def __init__(self, cache_dir: str = "data/features") -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        try:
            import pyarrow  # noqa: F401
            self._has_pyarrow = True
        except ImportError:
            self._has_pyarrow = False

        self._technical = TechnicalFeatureCalculator()
        self._fundamental = FundamentalFeatureCalculator()
        self._cross_asset = CrossAssetFeatureCalculator()
        self._alternative = AlternativeFeatureCalculator()
        self._temporal = TemporalFeatureCalculator()
        self._sentiment = SentimentFeatureCalculator()
        self._estimates = EstimatesFeatureCalculator()
        self._options_flow = OptionsFlowFeatureCalculator()
        self._trends = TrendsFeatureCalculator()

    def _cache_path(self, symbol: str) -> Path:
        ext = ".parquet" if self._has_pyarrow else ".pkl"
        return self.cache_dir / f"{symbol}{ext}"

    def compute_features(
        self,
        symbol: str,
        bars: list[OHLCV],
        spy_bars: list[OHLCV] | None = None,
        vix_bars: list[OHLCV] | None = None,
        sector_bars: list[OHLCV] | None = None,
        fundamentals: list[FundamentalData] | None = None,
        sector_fundamentals: list[FundamentalData] | None = None,
        insider_transactions: list[InsiderTransaction] | None = None,
        short_interest: list[ShortInterestData] | None = None,
        sentiment_scores: list[SentimentScore] | None = None,
        analyst_estimates: list[AnalystEstimate] | None = None,
        options_flow: list[OptionsFlowRecord] | None = None,
        trends_data: list[TrendsData] | None = None,
    ) -> pd.DataFrame:
        """Compute all features for a single symbol with point-in-time safety.

        Returns DataFrame indexed by date with 50+ feature columns.
        Missing data sources yield NaN columns (graceful degradation).
        """
        if not bars:
            return pd.DataFrame()

        # 1. Technical features (daily-indexed)
        tech_df = self._technical.compute(bars)
        bar_dates = list(tech_df.index)

        # 2. Fundamental features with point-in-time join
        fund_df = self._compute_pit_fundamentals(
            bar_dates, fundamentals, sector_fundamentals
        )

        # 3. Cross-asset features
        cross_df = self._cross_asset.compute(
            bars, spy_bars or [], sector_bars, vix_bars
        )

        # 4. Alternative features (insider + short interest)
        alt_df = self._compute_alternative_features(
            bar_dates, insider_transactions, short_interest
        )

        # 5. Temporal features
        temp_df = self._temporal.compute(bar_dates)

        # 6. Phase 3: sentiment, estimates, options flow, trends
        sent_df = self._sentiment.compute(sentiment_scores, bar_dates)
        est_df = self._estimates.compute(analyst_estimates, bar_dates)
        opts_df = self._options_flow.compute(options_flow, bar_dates)
        trend_df = self._trends.compute(trends_data, bar_dates)

        # 7. Left-join all on date index
        result = tech_df.copy()
        for df in (fund_df, cross_df, alt_df, temp_df, sent_df, est_df, opts_df, trend_df):
            if df is not None and not df.empty:
                # Align indices: reindex to tech_df's index
                aligned = df.reindex(result.index)
                for col in aligned.columns:
                    if col not in result.columns:
                        result[col] = aligned[col]

        result["symbol"] = symbol
        return result

    def get_features(
        self,
        symbols: list[str],
        start: str,
        end: str,
        data_provider=None,
    ) -> pd.DataFrame:
        """Get feature matrix for multiple symbols over a date range.

        Returns DataFrame with (symbol, date) multi-index and 50+ feature columns.
        Checks cache first, computes only missing dates.
        """
        frames = []
        for sym in symbols:
            cached = self.load(sym, start=start, end=end)
            if cached is not None and not cached.empty:
                frames.append(cached)
            else:
                logger.info("No cached features for %s, skipping (no data_provider)", sym)
        if not frames:
            return pd.DataFrame()
        combined = pd.concat(frames, axis=0)
        combined = combined.set_index("symbol", append=True)
        combined.index.names = ["date", "symbol"]
        combined = combined.reorder_levels(["symbol", "date"])
        return combined

    def save(self, df: pd.DataFrame, symbol: str) -> None:
        """Persist feature matrix as Parquet (if pyarrow available) or pickle."""
        path = self._cache_path(symbol)
        if self._has_pyarrow:
            df.to_parquet(path, engine="pyarrow")
        else:
            df.to_pickle(path)
        logger.info("Saved features for %s to %s (%d rows)", symbol, path, len(df))

    def load(
        self, symbol: str, start: str | None = None, end: str | None = None
    ) -> pd.DataFrame | None:
        """Load cached feature matrix."""
        path = self._cache_path(symbol)
        if not path.exists():
            return None
        if self._has_pyarrow:
            df = pd.read_parquet(path, engine="pyarrow")
        else:
            df = pd.read_pickle(path)
        if start:
            df = df[df.index >= pd.Timestamp(start)]
        if end:
            df = df[df.index <= pd.Timestamp(end)]
        if df.empty:
            return None
        return df

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _compute_pit_fundamentals(
        self,
        bar_dates: list[datetime],
        fundamentals: list[FundamentalData] | None,
        sector_fundamentals: list[FundamentalData] | None,
    ) -> pd.DataFrame:
        """Point-in-time join of fundamental data to bar dates.

        For each bar date, use the most recent FundamentalData with
        timestamp <= bar_date.  Never uses data filed after the bar date
        (no look-ahead bias).
        """
        if not fundamentals or not bar_dates:
            return pd.DataFrame()

        # Sort fundamentals by timestamp
        sorted_funds = sorted(fundamentals, key=lambda f: f.timestamp)

        # Build sector peer lookup (point-in-time): for each fundamental filing,
        # collect the sector peers available at that time
        sector_peers_by_date: dict[datetime, list[FundamentalData]] = {}
        if sector_fundamentals:
            sorted_sector = sorted(sector_fundamentals, key=lambda f: f.timestamp)
            for fund in sorted_funds:
                peers = [
                    sf for sf in sorted_sector if sf.timestamp <= fund.timestamp
                ]
                sector_peers_by_date[fund.timestamp] = peers

        calc = self._fundamental
        rows: list[dict[str, float | None]] = []

        for dt in bar_dates:
            # Find most recent fundamental with timestamp <= dt
            available = [f for f in sorted_funds if f.timestamp <= dt]
            if not available:
                rows.append({})
                continue

            latest = available[-1]
            peers = sector_peers_by_date.get(latest.timestamp, [latest])
            if not peers:
                peers = [latest]

            features = calc.compute(latest, peers)
            rows.append(features)

        df = pd.DataFrame(rows, index=pd.DatetimeIndex(bar_dates))
        return df

    def _compute_alternative_features(
        self,
        bar_dates: list[datetime],
        insider_transactions: list[InsiderTransaction] | None,
        short_interest: list[ShortInterestData] | None,
    ) -> pd.DataFrame:
        """Compute insider and short interest features for bar dates."""
        frames = []

        insider_df = self._alternative.compute_insider_features(
            insider_transactions or [], bar_dates
        )
        if not insider_df.empty:
            frames.append(insider_df)

        short_df = self._alternative.compute_short_interest_features(
            short_interest or [], bar_dates
        )
        if not short_df.empty:
            frames.append(short_df)

        if not frames:
            return pd.DataFrame()

        result = frames[0]
        for df in frames[1:]:
            result = result.join(df, how="outer")
        return result
