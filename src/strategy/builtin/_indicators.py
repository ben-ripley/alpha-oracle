"""Technical indicator wrappers with fallback from pandas_ta to ta library."""
from __future__ import annotations

import pandas as pd


def sma(series: pd.Series, length: int) -> pd.Series:
    """Simple Moving Average."""
    try:
        import pandas_ta as pta
        return pta.sma(series, length=length)
    except ImportError:
        return series.rolling(window=length).mean()


def rsi(series: pd.Series, length: int = 14) -> pd.Series:
    """Relative Strength Index."""
    try:
        import pandas_ta as pta
        return pta.rsi(series, length=length)
    except ImportError:
        import ta.momentum
        return ta.momentum.RSIIndicator(series, window=length).rsi()


def bbands(series: pd.Series, length: int = 20, std: float = 2.0) -> pd.DataFrame | None:
    """Bollinger Bands. Returns DataFrame with BBL, BBM, BBU columns."""
    try:
        import pandas_ta as pta
        return pta.bbands(series, length=length, std=std)
    except ImportError:
        import ta.volatility
        bb = ta.volatility.BollingerBands(series, window=length, window_dev=std)
        result = pd.DataFrame({
            f"BBL_{length}_{std}": bb.bollinger_lband(),
            f"BBM_{length}_{std}": bb.bollinger_mavg(),
            f"BBU_{length}_{std}": bb.bollinger_hband(),
        })
        return result if not result.empty else None
