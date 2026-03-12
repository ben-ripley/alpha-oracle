"""Cross-asset feature calculator for ML signal pipeline."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.core.models import OHLCV


class CrossAssetFeatureCalculator:
    """Compute cross-asset features: SPY beta, sector RS, VIX regime."""

    def compute(
        self,
        symbol_bars: list[OHLCV],
        spy_bars: list[OHLCV],
        sector_bars: list[OHLCV] | None = None,
        vix_bars: list[OHLCV] | None = None,
    ) -> pd.DataFrame:
        """Compute cross-asset features indexed by timestamp."""
        if not symbol_bars or not spy_bars:
            return self._empty_features(symbol_bars)

        sym_df = self._to_df(symbol_bars)
        spy_df = self._to_df(spy_bars)

        # Align on timestamp
        merged = sym_df[["close"]].rename(columns={"close": "sym_close"}).join(
            spy_df[["close"]].rename(columns={"close": "spy_close"}),
            how="inner",
        )
        if merged.empty:
            return self._empty_features(symbol_bars)

        sym_ret = merged["sym_close"].pct_change()
        spy_ret = merged["spy_close"].pct_change()

        features = pd.DataFrame(index=merged.index)

        # Rolling 60-day beta vs SPY
        cov = sym_ret.rolling(60).cov(spy_ret)
        var = spy_ret.rolling(60).var()
        features["spy_beta_60d"] = cov / var

        # Rolling 60-day correlation with SPY
        features["spy_correlation_60d"] = sym_ret.rolling(60).corr(spy_ret)

        # SPY 20-day return (market momentum)
        features["spy_return_20d"] = merged["spy_close"].pct_change(20)

        # Relative strength: stock 20d return minus SPY 20d return
        sym_ret_20d = merged["sym_close"].pct_change(20)
        features["relative_strength_20d"] = sym_ret_20d - features["spy_return_20d"]

        # Sector relative strength
        if sector_bars:
            sec_df = self._to_df(sector_bars)
            merged_sec = merged.join(
                sec_df[["close"]].rename(columns={"close": "sec_close"}),
                how="left",
            )
            sec_ret_20d = merged_sec["sec_close"].pct_change(20)
            features["sector_relative_strength_20d"] = sym_ret_20d - sec_ret_20d
        else:
            features["sector_relative_strength_20d"] = np.nan

        # VIX features
        if vix_bars:
            vix_df = self._to_df(vix_bars)
            vix_close = vix_df[["close"]].rename(columns={"close": "vix_close"})
            merged_vix = features.join(vix_close, how="left")
            features["vix_level"] = merged_vix["vix_close"]
            features["vix_regime"] = pd.cut(
                merged_vix["vix_close"],
                bins=[-np.inf, 15, 25, 35, np.inf],
                labels=[0, 1, 2, 3],
            ).astype(float)
            features["vix_change_5d"] = merged_vix["vix_close"].pct_change(5)
        else:
            features["vix_level"] = np.nan
            features["vix_regime"] = np.nan
            features["vix_change_5d"] = np.nan

        return features

    @staticmethod
    def _to_df(bars: list[OHLCV]) -> pd.DataFrame:
        df = pd.DataFrame([b.model_dump() for b in bars])
        df = df.sort_values("timestamp").reset_index(drop=True)
        df = df.set_index("timestamp")
        return df

    def _empty_features(self, bars: list[OHLCV]) -> pd.DataFrame:
        cols = [
            "spy_beta_60d",
            "spy_correlation_60d",
            "spy_return_20d",
            "relative_strength_20d",
            "sector_relative_strength_20d",
            "vix_level",
            "vix_regime",
            "vix_change_5d",
        ]
        if bars:
            df = self._to_df(bars)
            return pd.DataFrame(np.nan, index=df.index, columns=cols)
        return pd.DataFrame(columns=cols)
