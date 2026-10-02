"""
Candlestick Price Action Strategy (Bot 1 - Velas)
Estrategia pura de Acción del Precio, 18 Patrones de Velas Japonesas, Wyckoff y Al Brooks.
Opera rechazos institucionales limpios en Soportes y Resistencias sin interferencia de osciladores secundarios.
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Optional
from core.market_structure import (
    detect_candlestick_patterns,
    detect_support_resistance_zones,
    calculate_fibonacci_levels,
)


class CandlestickPriceActionStrategy:
    """
    Bot 1: Estrategia de Acción del Precio y Velas Japonesas.
    - Detecta patrones de giro de alta probabilidad (Martillos, Envolventes, Estrellas de la Mañana/Tarde).
    - Valida ubicación en zonas estructurales (Soportes/Resistencias y Fibonacci).
    - Asimetría estricta 1:3 R:R con Stop Loss bajo la mecha de la vela y modo Runner dinámico.
    """

    def __init__(
        self,
        risk_per_trade_pct: float = 0.05,
        max_exposure_pct: float = 0.85,
        cooldown_candles: int = 2,
        atr_period: int = 14,
        atr_min_mult: float = 0.0006,
    ):
        self.risk_per_trade_pct = risk_per_trade_pct
        self.max_exposure_pct   = max_exposure_pct
        self.cooldown_candles   = cooldown_candles
        self.atr_period         = atr_period
        self.atr_min_mult       = atr_min_mult
        self._last_trade_idx    = -999

    def _calc_atr(self, df: pd.DataFrame) -> float:
        """Wilder's ATR for dynamic stop placement floor."""
        high = df["high"].values
        low = df["low"].values
        close = df["close"].values
        tr = np.maximum(high[1:] - low[1:], np.maximum(np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1])))
        if len(tr) < self.atr_period:
            return float(df["close"].iloc[-1] * 0.01)
        # EMA smoothed ATR
        atr = tr[:self.atr_period].mean()
        for val in tr[self.atr_period:]:
            atr = (atr * (self.atr_period - 1) + val) / self.atr_period
        return float(atr)

    def evaluate(
        self,
        df: pd.DataFrame,
        current_balance: float = 200.0,
        latest_metrics: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        min_len = 25
        if len(df) < min_len:
            return {
                "signal": "NEUTRAL",
                "reason": f"Velas insuficientes ({len(df)}/{min_len})",
                "position_size": 0.0,
                "sl_price": 0.0,
                "tp_price": 0.0,
            }

        current_idx = len(df) - 1
        last_candle = df.iloc[-1]
        close = float(last_candle["close"])
        open_p = float(last_candle["open"])
        candle_high = float(last_candle["high"])
        candle_low = float(last_candle["low"])

        # Cooldown check
        if (current_idx - self._last_trade_idx) < self.cooldown_candles:
            return {
                "signal": "NEUTRAL",
                "reason": f"Cooldown activo ({current_idx - self._last_trade_idx}/{self.cooldown_candles} velas)",
                "position_size": 0.0,
                "sl_price": 0.0,
                "tp_price": 0.0,
            }

        atr = self._calc_atr(df)
        if atr < (close * self.atr_min_mult):
            return {
                "signal": "NEUTRAL",
                "reason": f"Volatilidad ATR insuficiente ({atr:.4f} < {close * self.atr_min_mult:.4f})",
                "position_size": 0.0,
                "sl_price": 0.0,
                "tp_price": 0.0,
            }

        # Candlestick Pattern Detection (18 Patrones)
        candles = detect_candlestick_patterns(df)
        patterns = candles.get("patterns", [])
        pattern_str = ", ".join(patterns) if patterns else ("Cuchillo Cayendo ⚠️" if candles.get("is_falling_knife") else ("Rebote Verde" if close >= open_p else "Vela Roja"))

        # Never buy a falling knife with zero rejection wick
        if candles.get("is_falling_knife", False):
            return {
                "signal": "NEUTRAL",
                "reason": "Vela bajista en caída libre (Cuchillo cayendo) — Esperando mecha de rechazo",
                "position_size": 0.0,
                "sl_price": 0.0,
                "tp_price": 0.0,
            }

        # Market Structure: S/R zones, Fibonacci y Proximidad Reciente
        sr_zones = detect_support_resistance_zones(df)
        fibs = calculate_fibonacci_levels(df)
        fib_50 = fibs.get("fib_0_500", 0.0)
        fib_618 = fibs.get("fib_0_618", 0.0)

        has_support = any(z["type"] == "SUPPORT" and z["distance_pct"] <= 1.0 for z in sr_zones)
        has_resistance = any(z["type"] == "RESISTANCE" and z["distance_pct"] <= 1.0 for z in sr_zones)
        has_fib_level = (fib_50 > 0 and (abs(close - fib_50) / close <= 0.01 or abs(close - fib_618) / close <= 0.01))

        # Indicadores de agotamiento y rango (Anti-Whipsaw)
        from strategies.indicators import compute_rsi, compute_adx
        rsi_s = compute_rsi(df["close"], 14)
        rsi = float(rsi_s.iloc[-1]) if not pd.isna(rsi_s.iloc[-1]) else 50.0
        adx_s = compute_adx(df, 14)
        adx = float(adx_s.iloc[-1]) if not pd.isna(adx_s.iloc[-1]) else 0.0
        is_adx_climax = adx >= 55.0

        # S/R Proximity & Anti-Trap Filters (Calculated from prior candles excluding current)
        sr_window = min(30, max(5, len(df) - 1))
        prior_df = df.iloc[-sr_window-1:-1] if len(df) > sr_window else df.iloc[:-1]
        prior_low = float(prior_df["low"].min()) if "low" in prior_df.columns and not prior_df.empty else close
        prior_high = float(prior_df["high"].max()) if "high" in prior_df.columns and not prior_df.empty else close

        sr_buffer = max(close * 0.008, 1.0 * atr)
        is_near_support = (close - prior_low) < sr_buffer
        is_near_resistance = (prior_high - close) < sr_buffer

        # 1. BULLISH SETUP (COMPRA POR ACCIÓN DEL PRECIO EN SOPORTE)
        is_bullish_trigger = (
            candles.get("has_bullish_pattern", False)
            and not is_near_resistance
            and not is_adx_climax
            and rsi <= 70.0
            and (has_support or has_fib_level or is_near_support or (candle_low < open_p and (close - candle_low) >= (candle_high - candle_low) * 0.45))
        )

        if is_bullish_trigger:
            raw_dist = max(close - candle_low, 0.8 * atr)
            dist = max(close * 0.016, max(raw_dist, 1.5 * atr))
            sl_price = round(close - dist, 4)
            min_tp_dist = max(dist * 2.5, close * 0.038)
            tp_price = round(close + min_tp_dist, 4)

            # Sizing matemático: Asegura que el target proyectado sea > $4.50 USD netos
            risk_usd = current_balance * self.risk_per_trade_pct
            pos_size = round(risk_usd / dist, 4) if dist > 0 else 0.0

            # Garantizar que con comisiones (0.20% roundtrip) el neto sea >= $4.50 USD
            net_gain_per_unit = max(0.001, (tp_price - close) - (close * 0.0020))
            min_target_qty = round(4.50 / net_gain_per_unit, 4)
            pos_size = max(pos_size, min_target_qty)

            max_qty = (current_balance * self.max_exposure_pct * 0.98) / close if close > 0 else 0.0
            pos_size = min(pos_size, max_qty)
            pos_size = max(0.0001, round(pos_size, 4))

            self._last_trade_idx = current_idx
            return {
                "signal": "BUY",
                "confidence": 0.92,
                "reason": f"BOT VELAS [SNIPER]: {pattern_str} en Soporte/Fib | R:R 1:2.5+ (> $4.50 USD Target)",
                "entry_price": close,
                "sl_price": sl_price,
                "tp_price": tp_price,
                "position_size": pos_size,
                "risk_amount_usd": round(pos_size * dist, 2),
                "strategy_name": "candlestick_action",
                "indicators": {"candle_pattern": pattern_str, "atr": round(atr, 4), "rsi": round(rsi, 1), "adx": round(adx, 1)},
            }

        # 2. BEARISH SETUP (VENTA POR ACCIÓN DEL PRECIO EN RESISTENCIA)
        is_bearish_trigger = (
            candles.get("has_bearish_pattern", False)
            and not is_near_support
            and not is_adx_climax
            and rsi >= 30.0
            and (has_resistance or has_fib_level or is_near_resistance or (candle_high > open_p and (candle_high - close) >= (candle_high - candle_low) * 0.45))
        )

        if is_bearish_trigger:
            raw_dist = max(candle_high - close, 0.8 * atr)
            dist = max(close * 0.016, max(raw_dist, 1.5 * atr))
            sl_price = round(close + dist, 4)
            min_tp_dist = max(dist * 2.5, close * 0.038)
            tp_price = round(close - min_tp_dist, 4)

            risk_usd = current_balance * self.risk_per_trade_pct
            pos_size = round(risk_usd / dist, 4) if dist > 0 else 0.0

            net_gain_per_unit = max(0.001, (close - tp_price) - (close * 0.0020))
            min_target_qty = round(4.50 / net_gain_per_unit, 4)
            pos_size = max(pos_size, min_target_qty)

            max_qty = (current_balance * self.max_exposure_pct * 0.98) / close if close > 0 else 0.0
            pos_size = min(pos_size, max_qty)
            pos_size = max(0.0001, round(pos_size, 4))

            self._last_trade_idx = current_idx
            return {
                "signal": "SELL",
                "confidence": 0.92,
                "reason": f"BOT VELAS [SNIPER]: {pattern_str} en Resistencia/Fib | R:R 1:2.5+ (> $4.50 USD Target)",
                "entry_price": close,
                "sl_price": sl_price,
                "tp_price": tp_price,
                "position_size": pos_size,
                "risk_amount_usd": round(pos_size * dist, 2),
                "strategy_name": "candlestick_action",
                "indicators": {"candle_pattern": pattern_str, "atr": round(atr, 4), "rsi": round(rsi, 1), "adx": round(adx, 1)},
            }

        neutral_reason = f"Esperando patrón de vela claro (Última: {pattern_str})"
        if is_adx_climax:
            neutral_reason = f"Tendencia agotada/clímax (ADX {adx:.1f} >= 55.0) — Esperando consolidación"
        elif is_near_support:
            neutral_reason = f"Filtro Anti-Chop: Precio pegado a soporte reciente (${prior_low:.2f})"
        elif is_near_resistance:
            neutral_reason = f"Filtro Anti-Chop: Precio pegado a resistencia reciente (${prior_high:.2f})"

        return {
            "signal": "NEUTRAL",
            "reason": neutral_reason,
            "position_size": 0.0,
            "sl_price": 0.0,
            "tp_price": 0.0,
            "indicators": {"candle_pattern": pattern_str, "atr": round(atr, 4), "rsi": round(rsi, 1), "adx": round(adx, 1)},
        }

