import pandas as pd
import numpy as np


def compute_atr(data: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range (ATR) using Wilder's EWM smoothing."""
    high_low = data['high'] - data['low']
    high_close = (data['high'] - data['close'].shift(1)).abs()
    low_close = (data['low'] - data['close'].shift(1)).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, min_periods=period, adjust=False).mean()


def compute_adx(data: pd.DataFrame, period: int = 14, use_ewm: bool = False) -> pd.Series:
    """Average Directional Index (ADX). Set use_ewm=True for Wilder's smoothing (EWM)."""
    up_move = data['high'] - data['high'].shift(1)
    down_move = data['low'].shift(1) - data['low']

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    high_low = data['high'] - data['low']
    high_close = (data['high'] - data['close'].shift(1)).abs()
    low_close = (data['low'] - data['close'].shift(1)).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)

    if use_ewm:
        atr_smooth = tr.ewm(alpha=1/period, adjust=False).mean()
        plus_di = 100 * (pd.Series(plus_dm, index=data.index).ewm(alpha=1/period, adjust=False).mean() / (atr_smooth + 1e-9))
        minus_di = 100 * (pd.Series(minus_dm, index=data.index).ewm(alpha=1/period, adjust=False).mean() / (atr_smooth + 1e-9))
    else:
        tr_smooth = tr.rolling(window=period).sum()
        plus_di = 100 * (pd.Series(plus_dm, index=data.index).rolling(period).sum() / (tr_smooth + 1e-9))
        minus_di = 100 * (pd.Series(minus_dm, index=data.index).rolling(period).sum() / (tr_smooth + 1e-9))

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9)
    return dx.rolling(window=period).mean()


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI using EWM smoothing."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rs = avg_gain / (avg_loss + 1e-9)
    return 100 - (100 / (1 + rs))


def compute_bollinger_bands(series: pd.Series, period: int = 20, std_dev: float = 2.0):
    """Returns (upper_band, middle_band, lower_band, pct_b) tuple."""
    middle = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper = middle + (std_dev * std)
    lower = middle - (std_dev * std)
    pct_b = (series - lower) / (upper - lower + 1e-9)
    return upper, middle, lower, pct_b


def compute_ema(series: pd.Series, span: int) -> pd.Series:
    """Exponential Moving Average."""
    return series.ewm(span=span, adjust=False).mean()
