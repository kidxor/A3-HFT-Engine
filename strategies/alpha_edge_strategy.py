import pandas as pd
import numpy as np
from typing import Dict, Any, Optional
from strategies.indicators import (
    compute_atr, compute_adx, compute_ema,
    compute_rsi, compute_bollinger_bands, _compute_true_range,
)


class AlphaEdgeStrategy:
    """
    AlphaEdge — Trend-Pullback Strategy (v1.1)

    Edges:
    - Enters pullbacks in confirmed trends (better entry → tighter SL → higher R:R)
    - Multi-factor confirmation: EMA stack + ADX + RSI + ATR volatility gate
    - Risk:Reward = 1:1.67 after fees (TP 2.5 ATR, SL 1.5 ATR)
    - Breakeven stop at 1.0 ATR profit, trailing stop at 0.5 ATR
    - Break-even win rate: ~38% (realistic target: 50-55%)

    Performance notes (v1.1):
    - compute_indicators no longer calls df.copy(); instead it works on a
      view and adds computed columns directly.  The caller passes a sliced
      DataFrame so the original history deque is never mutated.
    - True Range is computed once and shared by ATR and ADX (was computed
      twice in v1.0).
    """

    def __init__(
        self,
        ema_fast: int = 20,
        ema_slow: int = 50,
        ema_trend: int = 200,
        adx_period: int = 14,
        adx_min: float = 20.0,
        rsi_period: int = 14,
        atr_period: int = 14,
        atr_sl_mult: float = 1.5,
        atr_tp_mult: float = 2.5,
        risk_per_trade_pct: float = 0.01,
        pullback_tolerance: float = 0.003,
        bb_period: int = 20,
        bb_std: float = 2.0,
        cooldown_candles: int = 3,
        atr_min_mult: float = 0.002,
    ):
        self.ema_fast           = ema_fast
        self.ema_slow           = ema_slow
        self.ema_trend          = ema_trend
        self.adx_period         = adx_period
        self.adx_min            = adx_min
        self.rsi_period         = rsi_period
        self.atr_period         = atr_period
        self.atr_sl_mult        = atr_sl_mult
        self.atr_tp_mult        = atr_tp_mult
        self.risk_per_trade_pct = risk_per_trade_pct
        self.pullback_tolerance  = pullback_tolerance
        self.bb_period          = bb_period
        self.bb_std             = bb_std
        self.cooldown_candles   = cooldown_candles
        self.atr_min_mult       = atr_min_mult
        self._last_trade_idx    = -999

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Computes all technical indicators in-place on df.
        Caller must pass a fresh DataFrame (slice from history); this method
        does NOT copy — avoids 500-row allocation on every candle close.
        True Range is computed once and reused by both ATR and ADX.
        """
        close = df["close"]
        # Compute TR once, share with ATR and ADX
        tr = _compute_true_range(df)
        df["ema_fast"]  = compute_ema(close, self.ema_fast)
        df["ema_slow"]  = compute_ema(close, self.ema_slow)
        df["ema_trend"] = compute_ema(close, self.ema_trend)
        df["atr"]       = tr.ewm(
            alpha=1.0 / self.atr_period, min_periods=self.atr_period, adjust=False
        ).mean()
        df["adx"]       = compute_adx(df, self.adx_period, use_ewm=True, _tr=tr)
        df["rsi"]       = compute_rsi(close, self.rsi_period)
        df["bb_upper"], df["bb_middle"], df["bb_lower"], df["pct_b"] = (
            compute_bollinger_bands(close, self.bb_period, self.bb_std)
        )
        return df

    def evaluate(
        self,
        df: pd.DataFrame,
        current_balance: float = 1000.0,
        latest_metrics: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        min_len = max(self.ema_trend, self.bb_period) + 20
        if len(df) < min_len:
            return {
                "signal":        "NEUTRAL",
                "reason":        f"Calentando ({len(df)}/{min_len})",
                "position_size": 0.0,
                "sl_price":      0.0,
                "tp_price":      0.0,
            }

        # compute_indicators works in-place — no copy needed
        data = self.compute_indicators(df)
        curr = data.iloc[-1]

        close  = curr["close"]
        ema_f  = curr["ema_fast"]
        ema_s  = curr["ema_slow"]
        ema_t  = curr["ema_trend"]
        adx    = curr["adx"]   if not pd.isna(curr["adx"])   else 0.0
        rsi    = curr["rsi"]   if not pd.isna(curr["rsi"])   else 50.0
        atr    = curr["atr"]   if not pd.isna(curr["atr"])   else close * 0.01
        bb_mid = curr["bb_middle"] if not pd.isna(curr["bb_middle"]) else close
        pct_b  = curr["pct_b"] if not pd.isna(curr["pct_b"]) else 0.5

        if pd.isna(atr) or atr <= 0:
            return {
                "signal": "NEUTRAL", "reason": "ATR invalid",
                "position_size": 0.0, "sl_price": 0.0, "tp_price": 0.0,
            }

        # Cooldown: skip if too soon after last trade
        current_idx = len(data) - 1
        if (current_idx - self._last_trade_idx) < self.cooldown_candles:
            return {
                "signal": "NEUTRAL", "reason": "Cooldown activo",
                "position_size": 0.0, "sl_price": 0.0, "tp_price": 0.0,
            }

        # Volatility gate
        atr_min = close * self.atr_min_mult
        if atr < atr_min:
            return {
                "signal":        "NEUTRAL",
                "reason":        f"ATR bajo ({atr:.4f} < {atr_min:.4f}) — vol insuficiente",
                "position_size": 0.0, "sl_price": 0.0, "tp_price": 0.0,
            }

        # ADX filter
        if adx < self.adx_min:
            return {
                "signal":        "NEUTRAL",
                "reason":        f"ADX débil ({adx:.1f} < {self.adx_min}) — mercado lateral",
                "position_size": 0.0, "sl_price": 0.0, "tp_price": 0.0,
            }

        indicators = {
            "ema_fast":  round(ema_f, 2),
            "ema_slow":  round(ema_s, 2),
            "ema_trend": round(ema_t, 2),
            "adx":       round(adx, 1),
            "rsi":       round(rsi, 1),
            "atr":       round(atr, 4),
            "pct_b":     round(pct_b, 2),
            "bb_middle": round(bb_mid, 2),
            "close":     close,
        }

        risk_amount = current_balance * self.risk_per_trade_pct

        # ── LONG ──────────────────────────────────────────────────────
        is_uptrend     = ema_f > ema_s and close > ema_t
        pullback_long  = (
            ema_f * (1 - self.pullback_tolerance) <= close <= ema_f * (1 + self.pullback_tolerance)
            and close >= ema_s
        )
        rsi_long = 35 <= rsi <= 60

        if is_uptrend and pullback_long and rsi_long:
            sl_price      = round(close - atr * self.atr_sl_mult, 4)
            tp_price      = round(close + atr * self.atr_tp_mult, 4)
            risk_per_unit = close - sl_price
            position_size = round(risk_amount / risk_per_unit, 4) if risk_per_unit > 0 else 0.0
            self._last_trade_idx = current_idx

            return {
                "signal":          "BUY",
                "confidence":      round(min(1.0, adx / 40.0), 2),
                "reason":          f"AlphaEdge LONG: Pullback ({ema_s:.2f}≤{close:.2f}≤{ema_f:.2f}) | ADX {adx:.1f} | RSI {rsi:.1f}",
                "entry_price":     close,
                "sl_price":        sl_price,
                "tp_price":        tp_price,
                "position_size":   position_size,
                "risk_amount_usd": round(risk_amount, 2),
                "indicators":      indicators,
            }

        # ── SHORT ─────────────────────────────────────────────────────
        is_downtrend    = ema_f < ema_s and close < ema_t
        pullback_short  = (
            ema_f * (1 - self.pullback_tolerance) <= close <= ema_f * (1 + self.pullback_tolerance)
            and close <= ema_s
        )
        rsi_short = 40 <= rsi <= 65

        if is_downtrend and pullback_short and rsi_short:
            sl_price      = round(close + atr * self.atr_sl_mult, 4)
            tp_price      = round(close - atr * self.atr_tp_mult, 4)
            risk_per_unit = sl_price - close
            position_size = round(risk_amount / risk_per_unit, 4) if risk_per_unit > 0 else 0.0
            self._last_trade_idx = current_idx

            return {
                "signal":          "SELL",
                "confidence":      round(min(1.0, adx / 40.0), 2),
                "reason":          f"AlphaEdge SHORT: Rally ({close:.2f}≥{ema_f:.2f}) | ADX {adx:.1f} | RSI {rsi:.1f}",
                "entry_price":     close,
                "sl_price":        sl_price,
                "tp_price":        tp_price,
                "position_size":   position_size,
                "risk_amount_usd": round(risk_amount, 2),
                "indicators":      indicators,
            }

        # ── NEUTRAL ───────────────────────────────────────────────────
        if not is_uptrend and not is_downtrend:
            reason = f"Sin tendencia (EMA20:{ema_f:.1f} vs EMA50:{ema_s:.1f})"
        elif is_uptrend:
            reason = f"Uptrend sin pullback (pct_b={pct_b:.2f})"
        else:
            reason = f"Downtrend sin rally (pct_b={pct_b:.2f})"

        return {
            "signal":        "NEUTRAL",
            "reason":        reason,
            "position_size": 0.0,
            "sl_price":      0.0,
            "tp_price":      0.0,
            "indicators":    indicators,
        }
