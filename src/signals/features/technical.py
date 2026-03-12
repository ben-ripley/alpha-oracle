"""Technical feature calculator for ML signal pipeline."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.core.models import OHLCV
from src.strategy.builtin._indicators import atr, bbands, ema, macd, obv, rsi, sma


class TechnicalFeatureCalculator:
    """Compute 25+ technical features from OHLCV data."""

    def compute(self, bars: list[OHLCV]) -> pd.DataFrame:
        """Compute all technical features. Returns DataFrame indexed by timestamp.

        Features include:
        - Returns: ret_1d, ret_5d, ret_10d, ret_20d
        - SMA ratios: sma_5_20_ratio, sma_10_50_ratio, sma_20_200_ratio
        - EMA ratios: ema_12_26_ratio
        - RSI: rsi_14
        - MACD: macd_line, macd_signal, macd_histogram
        - Bollinger Bands: bb_width, bb_position
        - ATR: atr_14, atr_pct
        - OBV: obv, obv_sma_ratio
        - Volume: volume_ratio_20d
        - Volatility: volatility_20d
        - Gap: gap_pct
        - High/Low: high_low_range_pct
        - Momentum: momentum_10d
        """
        df = pd.DataFrame([b.model_dump() for b in bars])
        df = df.sort_values("timestamp").reset_index(drop=True)
        df = df.set_index("timestamp")

        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"].astype(float)
        open_ = df["open"]

        features = pd.DataFrame(index=df.index)

        # Returns
        features["ret_1d"] = close.pct_change(1)
        features["ret_5d"] = close.pct_change(5)
        features["ret_10d"] = close.pct_change(10)
        features["ret_20d"] = close.pct_change(20)

        # SMA ratios
        sma_5 = sma(close, 5)
        sma_10 = sma(close, 10)
        sma_20 = sma(close, 20)
        sma_50 = sma(close, 50)
        sma_200 = sma(close, 200)

        features["sma_5_20_ratio"] = sma_5 / sma_20
        features["sma_10_50_ratio"] = sma_10 / sma_50
        features["sma_20_200_ratio"] = sma_20 / sma_200

        # EMA ratio
        ema_12 = ema(close, 12)
        ema_26 = ema(close, 26)
        features["ema_12_26_ratio"] = ema_12 / ema_26

        # RSI
        features["rsi_14"] = rsi(close, 14)

        # MACD
        macd_df = macd(close, fast=12, slow=26, signal=9)
        if macd_df is not None and not macd_df.empty:
            cols = macd_df.columns
            features["macd_line"] = macd_df[cols[0]].values
            features["macd_histogram"] = macd_df[cols[1]].values
            features["macd_signal"] = macd_df[cols[2]].values
        else:
            features["macd_line"] = np.nan
            features["macd_histogram"] = np.nan
            features["macd_signal"] = np.nan

        # Bollinger Bands
        bb_df = bbands(close, length=20, std=2.0)
        if bb_df is not None and not bb_df.empty:
            bb_cols = bb_df.columns
            bb_lower = bb_df[bb_cols[0]].values
            bb_mid = bb_df[bb_cols[1]].values
            bb_upper = bb_df[bb_cols[2]].values
            features["bb_width"] = (bb_upper - bb_lower) / bb_mid
            band_range = bb_upper - bb_lower
            features["bb_position"] = np.where(
                band_range != 0,
                (close.values - bb_lower) / band_range,
                np.nan,
            )
        else:
            features["bb_width"] = np.nan
            features["bb_position"] = np.nan

        # ATR
        atr_14 = atr(high, low, close, length=14)
        features["atr_14"] = atr_14
        features["atr_pct"] = atr_14 / close

        # OBV
        obv_series = obv(close, volume)
        features["obv"] = obv_series
        obv_sma_20 = sma(obv_series, 20)
        features["obv_sma_ratio"] = obv_series / obv_sma_20

        # Volume ratio
        vol_sma_20 = sma(volume, 20)
        features["volume_ratio_20d"] = volume / vol_sma_20

        # Volatility (annualized)
        daily_ret = close.pct_change(1)
        features["volatility_20d"] = daily_ret.rolling(20).std() * np.sqrt(252)

        # Gap
        features["gap_pct"] = (open_ - close.shift(1)) / close.shift(1)

        # High-low range
        features["high_low_range_pct"] = (high - low) / close

        # Momentum
        features["momentum_10d"] = close / close.shift(10) - 1

        # Close-to-SMA distance (price relative to 20-day SMA)
        features["close_sma20_pct"] = (close - sma_20) / sma_20

        # Return standard deviation ratio (5d vs 20d volatility regime)
        features["vol_regime_5_20"] = (
            daily_ret.rolling(5).std() / daily_ret.rolling(20).std()
        )

        return features
