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
    - Risk:Reward = 1:1.5 after fees (TP 3.0 ATR, SL 2.0 ATR)
    - Breakeven stop at 1.0 ATR profit, trailing stop at 0.5 ATR
    - Break-even win rate: ~40% (realistic target: 50-55%)

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
        ema_trend: int = 100,
        adx_period: int = 14,
        adx_min: float = 28.0,
        rsi_period: int = 14,
        atr_period: int = 14,
        atr_sl_mult: float = 1.5,
        atr_tp_mult: float = 4.5,
        risk_per_trade_pct: float = 0.05,
        pullback_tolerance: float = 0.008,
        bb_period: int = 20,
        bb_std: float = 2.0,
        cooldown_candles: int = 5,
        atr_min_mult: float = 0.0010,
        max_exposure_pct: float = 0.85,
        maker_fee_pct: float = 0.0004,
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
        self.max_exposure_pct   = max_exposure_pct
        self.maker_fee_pct      = maker_fee_pct
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

        # Candlestick Pattern Confirmation from '18 Patrones de Velas que Debes Conocer'
        from core.market_structure import detect_candlestick_patterns
        candles = detect_candlestick_patterns(df)
        open_curr = float(df["open"].iloc[-1])
        cand_pat_str = f" [{', '.join(candles['patterns'])}]" if candles.get("patterns") else ""
        candle_summary = ", ".join(candles.get("patterns", [])) if candles.get("patterns") else ("Cuchillo Cayendo ⚠️" if candles.get("is_falling_knife") else ("Rebote Verde" if close >= open_curr else "Vela Roja"))

        indicators = {
            "ema_fast":       round(ema_f, 2),
            "ema_slow":       round(ema_s, 2),
            "ema_trend":      round(ema_t, 2),
            "adx":            round(adx, 1),
            "rsi":            round(rsi, 1),
            "atr":            round(atr, 4),
            "pct_b":          round(pct_b, 2),
            "bb_middle":      round(bb_mid, 2),
            "close":          close,
            "candle_pattern": candle_summary,
        }

        vir = latest_metrics.get("vir", 1.0) if latest_metrics else 1.0

        # ATR-based TP/SL distances: Sniper Intraday Structure (1.6% - 2.2% SL, 3.8% - 5.5% TP)
        sl_dist = max(close * 0.016, atr * max(1.5, self.atr_sl_mult))
        tp_dist = max(sl_dist * 2.5, close * 0.038)

        # Position sizing: Dynamic conviction allocation targeting >= $4.50 USD net win up to max_exposure_pct (50%)
        conviction_mult = 1.0
        if adx >= 35.0:
            conviction_mult += 0.5   # Strong trend boost
        if vir >= 1.15 or vir <= 0.85:
            conviction_mult += 0.5   # Orderbook pressure boost

        target_exposure_pct = min(self.max_exposure_pct, 0.25 * conviction_mult)
        target_usd = current_balance * target_exposure_pct
        safe_target_usd = target_usd * 0.98

        position_size = round(safe_target_usd / close, 4) if close > 0 else 0.0
        net_gain_per_unit = max(0.001, tp_dist - (close * 0.0020))
        min_target_qty = round(4.50 / net_gain_per_unit, 4)
        position_size = max(position_size, min_target_qty)

        max_alloc = (current_balance * self.max_exposure_pct * 0.98) / close if close > 0 else 0.0
        position_size = min(position_size, max_alloc)
        position_size = max(0.0001, round(position_size, 4))

        # Orderbook L2 Imbalance confirmation (if available from live stream)
        vir = latest_metrics.get("vir", 1.0) if latest_metrics else 1.0
        orderbook_long_ok = vir >= 1.05 if latest_metrics else True
        orderbook_short_ok = vir <= 0.95 if latest_metrics else True

        # Anti-Falling Knife Protection: NEVER buy into a free-falling red candle
        if candles.get("is_falling_knife", False):
            return {
                "signal":        "NEUTRAL",
                "reason":        "Vela bajista en caída libre (Cuchillo cayendo) — Esperando rebote o patrón de giro (Al Brooks / 18 Patrones)",
                "position_size": 0.0, "sl_price": 0.0, "tp_price": 0.0,
                "indicators":    indicators,
            }

        # ── ENGINE 1: CANDLESTICK REVERSAL AT SUPPORT / RESISTANCE (MOTOR DE GIROS) ───
        from core.market_structure import detect_support_resistance_zones, calculate_fibonacci_levels
        sr_zones = detect_support_resistance_zones(df)
        fibs = calculate_fibonacci_levels(df)
        fib_50 = fibs.get("fib_0_500", 0.0)
        fib_618 = fibs.get("fib_0_618", 0.0)

        has_support = any(z["type"] == "SUPPORT" and z["distance_pct"] <= 0.8 for z in sr_zones)
        has_resistance = any(z["type"] == "RESISTANCE" and z["distance_pct"] <= 0.8 for z in sr_zones)
        has_fib = (close > 0 and fib_50 > 0 and (abs(close - fib_50) / close <= 0.008 or abs(close - fib_618) / close <= 0.008))

        candle_low = float(df["low"].iloc[-1])
        candle_high = float(df["high"].iloc[-1])

        # S/R Proximity & Climax Filters (Anti-Chop & Anti-Trap Filters)
        sr_window = min(30, max(5, len(df) - 1))
        prior_df = df.iloc[-sr_window-1:-1] if len(df) > sr_window else df.iloc[:-1]
        prior_low = float(prior_df["low"].min()) if "low" in prior_df.columns and not prior_df.empty else close
        prior_high = float(prior_df["high"].max()) if "high" in prior_df.columns and not prior_df.empty else close

        sr_buffer = max(close * 0.008, 1.0 * atr)
        is_near_support = (close - prior_low) < sr_buffer
        is_near_resistance = (prior_high - close) < sr_buffer
        is_adx_climax = adx >= 55.0

        # 1A. Reversal LONG: Bullish pattern at Support, Fibonacci, EMA or Swing Low
        is_reversal_long = (
            candles.get("has_bullish_pattern", False)
            and not candles.get("is_falling_knife", False)
            and not is_near_resistance
            and not is_adx_climax
            and rsi <= 70.0
            and (0.30 <= pct_b <= 0.65)
            and (has_support or has_fib or is_near_support or (candle_low < close and (close - candle_low) >= (candle_high - candle_low) * 0.45))
            and orderbook_long_ok
        )

        if is_reversal_long:
            raw_dist = max(close - candle_low, 0.8 * atr)
            dist = max(close * 0.016, max(raw_dist, 1.5 * atr))
            sl_price = round(close - dist, 4)
            min_tp_dist = max(dist * 2.5, close * 0.038)
            tp_price = round(close + min_tp_dist, 4)
            rr_ratio = round(min_tp_dist / dist, 1)

            rev_risk_usd = current_balance * 0.05
            rev_pos_size = round(rev_risk_usd / dist, 4) if dist > 0 else position_size
            net_gain_per_unit = max(0.001, (tp_price - close) - (close * 0.0020))
            min_target_qty = round(4.50 / net_gain_per_unit, 4)
            rev_pos_size = max(rev_pos_size, min_target_qty)

            max_alloc = (current_balance * self.max_exposure_pct * 0.98) / close if close > 0 else 0.0
            rev_pos_size = min(rev_pos_size, max_alloc)
            rev_pos_size = max(0.0001, round(rev_pos_size, 4))

            self._last_trade_idx = current_idx
            return {
                "signal":          "BUY",
                "confidence":      0.90,
                "reason":          f"AlphaEdge REVERSAL LONG [SNIPER]: {candle_summary} en Soporte | R:R 1:{rr_ratio} (> $4.50 USD Target)",
                "entry_price":     close,
                "sl_price":        sl_price,
                "tp_price":        tp_price,
                "position_size":   rev_pos_size,
                "risk_amount_usd": round(rev_pos_size * dist, 2),
                "indicators":      indicators,
            }

        # 1B. Reversal SHORT: Bearish pattern at Resistance, Fibonacci, EMA or Swing High
        is_reversal_short = (
            candles.get("has_bearish_pattern", False)
            and not is_near_support
            and not is_adx_climax
            and (30.0 <= rsi <= 70.0)
            and (0.35 <= pct_b <= 0.70)
            and (has_resistance or has_fib or is_near_resistance or (candle_high > close and (candle_high - close) >= (candle_high - candle_low) * 0.45))
            and orderbook_short_ok
        )

        if is_reversal_short:
            raw_dist = max(candle_high - close, 0.8 * atr)
            dist = max(close * 0.016, max(raw_dist, 1.5 * atr))
            sl_price = round(close + dist, 4)
            min_tp_dist = max(dist * 2.5, close * 0.038)
            tp_price = round(close - min_tp_dist, 4)
            rr_ratio = round(min_tp_dist / dist, 1)

            rev_risk_usd = current_balance * 0.05
            rev_pos_size = round(rev_risk_usd / dist, 4) if dist > 0 else position_size
            net_gain_per_unit = max(0.001, (close - tp_price) - (close * 0.0020))
            min_target_qty = round(4.50 / net_gain_per_unit, 4)
            rev_pos_size = max(rev_pos_size, min_target_qty)

            max_alloc = (current_balance * self.max_exposure_pct * 0.98) / close if close > 0 else 0.0
            rev_pos_size = min(rev_pos_size, max_alloc)
            rev_pos_size = max(0.0001, round(rev_pos_size, 4))

            self._last_trade_idx = current_idx
            return {
                "signal":          "SELL",
                "confidence":      0.90,
                "reason":          f"AlphaEdge REVERSAL SHORT [SNIPER]: {candle_summary} en Resistencia | R:R 1:{rr_ratio} (> $4.50 USD Target)",
                "entry_price":     close,
                "sl_price":        sl_price,
                "tp_price":        tp_price,
                "position_size":   rev_pos_size,
                "risk_amount_usd": round(rev_pos_size * dist, 2),
                "indicators":      indicators,
            }

        # ── ENGINE 2: TREND CONTINUATION (PULLBACK) ───────────────────
        # When no reversal pattern is present, standard trend rules apply
        if adx < self.adx_min:
            return {
                "signal":        "NEUTRAL",
                "reason":        f"ADX débil ({adx:.1f} < {self.adx_min}) — Mercado lateral (Cero comisiones)",
                "position_size": 0.0, "sl_price": 0.0, "tp_price": 0.0,
                "indicators":    indicators,
            }

        if is_adx_climax:
            return {
                "signal":        "NEUTRAL",
                "reason":        f"Tendencia agotada/clímax (ADX {adx:.1f} >= 55.0) — Esperando consolidación",
                "position_size": 0.0, "sl_price": 0.0, "tp_price": 0.0,
                "indicators":    indicators,
            }

        trade_allocation_usd = position_size * close

        # Minimum net profit floor: TP must be at least 3.0x SL distance AND exceed 4× the round-trip fee
        tp_dist = max(tp_dist, sl_dist * 3.0)
        fee_pct    = self.maker_fee_pct
        min_tp_usd = (trade_allocation_usd * (fee_pct * 2.0)) * 4.0
        if (position_size * tp_dist) < min_tp_usd and position_size > 0:
            tp_dist = min_tp_usd / position_size

        # ── LONG ──────────────────────────────────────────────────────
        is_uptrend        = ema_f > ema_s and ema_s > ema_t and close > ema_t
        pullback_long     = (
            ema_f * (1 - self.pullback_tolerance) <= close <= ema_f * (1 + self.pullback_tolerance)
            and close >= ema_s
        )
        is_rebound_candle = (close >= open_curr) or candles.get("has_bullish_pattern", False)

        if is_uptrend and pullback_long and orderbook_long_ok and is_rebound_candle and not is_near_resistance and (40.0 <= rsi <= 70.0) and (0.30 <= pct_b <= 0.65):
            sl_price = round(close - sl_dist, 4)
            tp_price = round(close + tp_dist, 4)
            self._last_trade_idx = current_idx

            return {
                "signal":          "BUY",
                "confidence":      round(min(1.0, adx / 40.0), 2),
                "reason":          f"AlphaEdge LONG: Pullback ({ema_s:.2f}≤{close:.2f}≤{ema_f:.2f}){cand_pat_str} | ADX {adx:.1f} | VIR {vir:.2f}",
                "entry_price":     close,
                "sl_price":        sl_price,
                "tp_price":        tp_price,
                "position_size":   position_size,
                "risk_amount_usd": round(position_size * sl_dist, 2),
                "indicators":      indicators,
            }

        # ── SHORT ─────────────────────────────────────────────────────
        is_downtrend      = ema_f < ema_s and ema_s < ema_t and close < ema_t
        pullback_short    = (
            ema_f * (1 - self.pullback_tolerance) <= close <= ema_f * (1 + self.pullback_tolerance)
            and close <= ema_s
        )
        is_bearish_candle = (close <= open_curr) or candles.get("has_bearish_pattern", False)

        if is_downtrend and pullback_short and orderbook_short_ok and is_bearish_candle and not is_near_support and (30.0 <= rsi <= 60.0) and (0.35 <= pct_b <= 0.70):
            sl_price = round(close + sl_dist, 4)
            tp_price = round(close - tp_dist, 4)
            self._last_trade_idx = current_idx

            return {
                "signal":          "SELL",
                "confidence":      round(min(1.0, adx / 40.0), 2),
                "reason":          f"AlphaEdge SHORT: Rally ({ema_f:.2f}≥{close:.2f}≥{ema_s:.2f}){cand_pat_str} | ADX {adx:.1f} | VIR {vir:.2f}",
                "entry_price":     close,
                "sl_price":        sl_price,
                "tp_price":        tp_price,
                "position_size":   position_size,
                "risk_amount_usd": round(position_size * sl_dist, 2),
                "indicators":      indicators,
            }

        # ── NEUTRAL ───────────────────────────────────────────────────
        if not is_uptrend and not is_downtrend:
            reason = f"Sin tendencia (EMA20:{ema_f:.1f} vs EMA50:{ema_s:.1f})"
        elif is_near_support and is_downtrend:
            reason = f"Filtro Anti-Chop: Precio pegado a soporte reciente (${prior_low:.2f})"
        elif is_near_resistance and is_uptrend:
            reason = f"Filtro Anti-Chop: Precio pegado a resistencia reciente (${prior_high:.2f})"
        elif pct_b < 0.35 and is_downtrend:
            reason = f"Filtro Anti-Suelo Bollinger: %b en {pct_b:.2f} < 0.35 (Sobreventa en soporte) — Esperando retroceso"
        elif pct_b > 0.65 and is_uptrend:
            reason = f"Filtro Anti-Techo Bollinger: %b en {pct_b:.2f} > 0.65 (Sobrecompra en techo) — Esperando retroceso"
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
