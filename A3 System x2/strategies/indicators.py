import pandas as pd
import numpy as np


def _compute_true_range(data: pd.DataFrame) -> pd.Series:
    """Compute True Range using fast numpy operations — shared by ATR and ADX."""
    high = data['high'].values
    low = data['low'].values
    prev_close = data['close'].shift(1).values
    # Vectorized max without pd.concat — ~3x faster
    hl = high - low
    hc = np.abs(high - prev_close)
    lc = np.abs(low - prev_close)
    tr = np.maximum(hl, np.maximum(hc, lc))
    return pd.Series(tr, index=data.index)


def compute_atr(data: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range (ATR) using Wilder's EWM smoothing."""
    alpha = 1.0 / period
    tr = _compute_true_range(data)
    return tr.ewm(alpha=alpha, min_periods=period, adjust=False).mean()


def compute_adx(data: pd.DataFrame, period: int = 14, use_ewm: bool = False,
                _tr: pd.Series = None) -> pd.Series:
    """Average Directional Index (ADX). Set use_ewm=True for Wilder's smoothing (EWM).
    Accepts pre-computed True Range series to avoid duplicate computation when
    called alongside compute_atr in compute_indicators."""
    high = data['high'].values
    low  = data['low'].values

    up_move   = high - np.roll(high, 1)
    down_move = np.roll(low, 1) - low
    up_move[0]   = 0.0
    down_move[0] = 0.0

    plus_dm  = np.where((up_move > down_move)   & (up_move > 0),   up_move,   0.0)
    minus_dm = np.where((down_move > up_move)    & (down_move > 0), down_move, 0.0)

    tr = _tr if _tr is not None else _compute_true_range(data)
    alpha = 1.0 / period

    if use_ewm:
        atr_smooth = tr.ewm(alpha=alpha, adjust=False).mean()
        plus_di    = 100 * (pd.Series(plus_dm,  index=data.index).ewm(alpha=alpha, adjust=False).mean() / (atr_smooth + 1e-9))
        minus_di   = 100 * (pd.Series(minus_dm, index=data.index).ewm(alpha=alpha, adjust=False).mean() / (atr_smooth + 1e-9))
    else:
        tr_smooth = tr.rolling(window=period).sum()
        plus_di   = 100 * (pd.Series(plus_dm,  index=data.index).rolling(period).sum() / (tr_smooth + 1e-9))
        minus_di  = 100 * (pd.Series(minus_dm, index=data.index).rolling(period).sum() / (tr_smooth + 1e-9))

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9)
    return dx.rolling(window=period).mean()


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI using EWM smoothing."""
    alpha = 1.0 / period
    delta = series.diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=alpha, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=alpha, min_periods=period, adjust=False).mean()
    rs = avg_gain / (avg_loss + 1e-9)
    return 100.0 - (100.0 / (1.0 + rs))


def compute_bollinger_bands(series: pd.Series, period: int = 20, std_dev: float = 2.0):
    """Returns (upper_band, middle_band, lower_band, pct_b) tuple."""
    roll  = series.rolling(window=period)
    middle = roll.mean()
    std    = roll.std()
    band   = std_dev * std
    upper  = middle + band
    lower  = middle - band
    pct_b  = (series - lower) / (upper - lower + 1e-9)
    return upper, middle, lower, pct_b


def compute_ema(series: pd.Series, span: int) -> pd.Series:
    """Exponential Moving Average."""
    return series.ewm(span=span, adjust=False).mean()
