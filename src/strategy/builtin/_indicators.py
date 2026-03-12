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


def ema(series: pd.Series, length: int) -> pd.Series:
    """Exponential Moving Average."""
    try:
        import pandas_ta as pta
        return pta.ema(series, length=length)
    except ImportError:
        return series.ewm(span=length, adjust=False).mean()


def macd(
    series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> pd.DataFrame | None:
    """MACD. Returns DataFrame with MACD, MACDh, MACDs columns."""
    try:
        import pandas_ta as pta
        return pta.macd(series, fast=fast, slow=slow, signal=signal)
    except ImportError:
        import ta.trend
        m = ta.trend.MACD(series, window_fast=fast, window_slow=slow, window_sign=signal)
        result = pd.DataFrame({
            f"MACD_{fast}_{slow}_{signal}": m.macd(),
            f"MACDh_{fast}_{slow}_{signal}": m.macd_diff(),
            f"MACDs_{fast}_{slow}_{signal}": m.macd_signal(),
        })
        return result if not result.empty else None


def atr(
    high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14
) -> pd.Series:
    """Average True Range."""
    try:
        import pandas_ta as pta
        return pta.atr(high=high, low=low, close=close, length=length)
    except ImportError:
        import ta.volatility
        return ta.volatility.AverageTrueRange(
            high=high, low=low, close=close, window=length
        ).average_true_range()


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """On-Balance Volume."""
    try:
        import pandas_ta as pta
        return pta.obv(close=close, volume=volume)
    except ImportError:
        import ta.volume
        return ta.volume.OnBalanceVolumeIndicator(
            close=close, volume=volume
        ).on_balance_volume()


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
