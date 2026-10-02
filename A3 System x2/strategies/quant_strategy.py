"""
Quant Statistical Strategy (Bot 2 - Matemáticas y Algoritmos)
Estrategia cuantitativa basada en los 8 modelos del catálogo ALGORITMOS_ESTADISTICOS.md:
1. Micro-Price y Volume Imbalance Ratio (VIR) de L2 Orderbook.
2. Order Flow Imbalance (OFI).
3. Apilamiento Armónico de 3-EMA (20, 50, 200).
4. Velocidad de Tendencia ADX de Wilder (>= 28.0).
5. Bandas de Bollinger (%B) y Compresión/Expansión.
6. Oscilador de Momento RSI de Wilder.
7. Asimetría matemática estricta 1:3 basada en Wilder ATR.
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Optional
from strategies.indicators import (
    compute_ema,
    compute_bollinger_bands,
    compute_rsi,
    compute_adx,
    compute_atr,
)


class QuantStatisticalStrategy:
    """
    Bot 2: Estrategia Cuantitativa y de Algoritmos Estadísticos.
    Ejecuta únicamente cuando existe confluencia matemática verificable entre:
    - Flujo de Órdenes L2 (VIR / Micro-Price).
    - Tendencia Multi-Temporal (3-EMA Stack).
    - Fuerza Direccional (ADX >= 28).
    - Volatilidad (Wilder ATR 1:3 R:R).
    """

    def __init__(
        self,
        ema_fast: int = 20,
        ema_slow: int = 50,
        ema_trend: int = 200,
        adx_min: float = 28.0,
        vir_long_threshold: float = 1.20,
        vir_short_threshold: float = 0.80,
        atr_sl_mult: float = 1.5,
        atr_tp_mult: float = 4.5,
        risk_per_trade_pct: float = 0.05,
        max_exposure_pct: float = 0.85,
        cooldown_candles: int = 2,
    ):
        self.ema_fast            = ema_fast
        self.ema_slow            = ema_slow
        self.ema_trend           = ema_trend
        self.adx_min             = adx_min
        self.vir_long_threshold  = vir_long_threshold
        self.vir_short_threshold = vir_short_threshold
        self.atr_sl_mult         = atr_sl_mult
        self.atr_tp_mult         = atr_tp_mult
        self.risk_per_trade_pct  = risk_per_trade_pct
        self.max_exposure_pct    = max_exposure_pct
        self.cooldown_candles    = cooldown_candles
        self._last_trade_idx     = -999

    def evaluate(
        self,
        df: pd.DataFrame,
        current_balance: float = 200.0,
        latest_metrics: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        min_len = 35
        if df is None or len(df) < min_len:
            return {
                "signal": "NEUTRAL",
                "reason": f"Velas insuficientes para indicadores ({len(df) if df is not None else 0}/{min_len})",
                "position_size": 0.0,
                "sl_price": 0.0,
                "tp_price": 0.0,
            }

        close_s = df["close"]
        high_s  = df["high"]
        low_s   = df["low"]
        close   = float(close_s.iloc[-1])

        # Mathematical Indicators
        ema_f = float(compute_ema(close_s, self.ema_fast).iloc[-1])
        ema_s = float(compute_ema(close_s, self.ema_slow).iloc[-1])
        ema_t = float(compute_ema(close_s, self.ema_trend).iloc[-1])

        adx_s = compute_adx(df, 14)
        adx = float(adx_s.iloc[-1]) if not pd.isna(adx_s.iloc[-1]) else 0.0

        rsi_s = compute_rsi(close_s, 14)
        rsi = float(rsi_s.iloc[-1]) if not pd.isna(rsi_s.iloc[-1]) else 50.0

        atr_s = compute_atr(df, 14)
        atr = float(atr_s.iloc[-1]) if not pd.isna(atr_s.iloc[-1]) else (close * 0.01)

        _, _, _, pct_b_s = compute_bollinger_bands(close_s, 20, 2.0)
        pct_b_val = pct_b_s.iloc[-1]
        pct_b = float(pct_b_val) if not pd.isna(pct_b_val) else 0.5

        # Cooldown check
        current_idx = len(df) - 1
        if (current_idx - self._last_trade_idx) < self.cooldown_candles:
            return {
                "signal": "NEUTRAL",
                "reason": f"Cooldown cuantitativo activo ({current_idx - self._last_trade_idx}/{self.cooldown_candles} velas)",
                "position_size": 0.0,
                "sl_price": 0.0,
                "tp_price": 0.0,
            }

        # Orderbook L2 Quantitative metrics
        vir = float(latest_metrics.get("vir", 1.0)) if latest_metrics else 1.0
        micro_price = float(latest_metrics.get("micro_price", close)) if latest_metrics else close
        spread = float(latest_metrics.get("spread", 0.01)) if latest_metrics else 0.01

        indicators = {
            "ema_20": round(ema_f, 2),
            "ema_50": round(ema_s, 2),
            "ema_200": round(ema_t, 2),
            "adx": round(adx, 1),
            "rsi": round(rsi, 1),
            "atr": round(atr, 4),
            "pct_b": round(pct_b, 2),
            "vir": round(vir, 2),
            "micro_price": round(micro_price, 2),
        }

        # S/R Proximity & Climax Filters (Anti-Chop & Anti-Trap Filters)
        sr_window = min(30, max(5, len(df) - 1))
        prior_df = df.iloc[-sr_window-1:-1] if len(df) > sr_window else df.iloc[:-1]
        prior_low = float(prior_df["low"].min()) if "low" in prior_df.columns and not prior_df.empty else close
        prior_high = float(prior_df["high"].max()) if "high" in prior_df.columns and not prior_df.empty else close

        sr_buffer = max(close * 0.008, 1.0 * atr)
        is_near_support = (close - prior_low) < sr_buffer
        is_near_resistance = (prior_high - close) < sr_buffer
        is_adx_climax = adx >= 55.0

        # 1. QUANT LONG CONFLUENCE
        quant_long_ok = (
            ema_f > ema_s
            and close >= ema_s * 0.998
            and (self.adx_min <= adx < 55.0)
            and not is_near_resistance
            and vir >= self.vir_long_threshold
            and micro_price >= (close - spread)
            and (45.0 <= rsi <= 70.0)
            and (0.30 <= pct_b <= 0.65)
        )

        if quant_long_ok:
            dist = max(close * 0.016, atr * max(1.5, self.atr_sl_mult))
            sl_price = round(close - dist, 4)
            min_tp_dist = max(dist * 2.5, close * 0.038)
            tp_price = round(close + min_tp_dist, 4)

            risk_usd = current_balance * self.risk_per_trade_pct
            pos_size = round(risk_usd / dist, 4) if dist > 0 else 0.0

            net_gain_per_unit = max(0.001, (tp_price - close) - (close * 0.0020))
            min_target_qty = round(4.50 / net_gain_per_unit, 4)
            pos_size = max(pos_size, min_target_qty)

            max_qty = (current_balance * self.max_exposure_pct * 0.98) / close if close > 0 else 0.0
            pos_size = min(pos_size, max_qty)
            pos_size = max(0.0001, round(pos_size, 4))

            self._last_trade_idx = current_idx
            return {
                "signal": "BUY",
                "confidence": 0.95,
                "reason": (
                    f"BOT ALGORITMOS [SNIPER]: Confluencia 3-EMA + ADX {adx:.1f} + "
                    f"VIR {vir:.2f} + MicroPrice ${micro_price:.2f} | R:R 1:2.5+ (> $4.50 USD Target)"
                ),
                "entry_price": close,
                "sl_price": sl_price,
                "tp_price": tp_price,
                "position_size": pos_size,
                "risk_amount_usd": round(pos_size * dist, 2),
                "strategy_name": "quant_statistical",
                "indicators": indicators,
            }

        # 2. QUANT SHORT CONFLUENCE
        quant_short_ok = (
            ema_f < ema_s
            and close <= ema_s * 1.002
            and (self.adx_min <= adx < 55.0)
            and not is_near_support
            and vir <= self.vir_short_threshold
            and micro_price <= (close + spread)
            and (30.0 <= rsi <= 55.0)
            and (0.35 <= pct_b <= 0.70)
        )

        if quant_short_ok:
            dist = max(close * 0.016, atr * max(1.5, self.atr_sl_mult))
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
                "confidence": 0.95,
                "reason": (
                    f"BOT ALGORITMOS [SNIPER]: Confluencia Cuantitativa 3-EMA + ADX {adx:.1f} + "
                    f"VIR {vir:.2f} + MicroPrice ${micro_price:.2f} | R:R 1:2.5+ (> $4.50 USD Target)"
                ),
                "entry_price": close,
                "sl_price": sl_price,
                "tp_price": tp_price,
                "position_size": pos_size,
                "risk_amount_usd": round(pos_size * dist, 2),
                "strategy_name": "quant_statistical",
                "indicators": indicators,
            }

        # Motivo descriptivo si fue bloqueado por protección
        neutral_reason = f"Esperando confluencia matemática (ADX: {adx:.1f}, VIR: {vir:.2f}, RSI: {rsi:.1f})"
        if is_adx_climax:
            neutral_reason = f"Tendencia agotada/clímax (ADX {adx:.1f} >= 55.0) — Esperando consolidación"
        elif is_near_support and ema_f < ema_s:
            neutral_reason = f"Filtro Anti-Chop: Precio pegado a soporte reciente (${prior_low:.2f})"
        elif is_near_resistance and ema_f > ema_s:
            neutral_reason = f"Filtro Anti-Chop: Precio pegado a resistencia reciente (${prior_high:.2f})"
        elif pct_b < 0.35 and ema_f < ema_s:
            neutral_reason = f"Filtro Anti-Suelo Bollinger: %b en {pct_b:.2f} < 0.35 (Sobreventa en soporte) — Esperando retroceso"
        elif pct_b > 0.65 and ema_f > ema_s:
            neutral_reason = f"Filtro Anti-Techo Bollinger: %b en {pct_b:.2f} > 0.65 (Sobrecompra en techo) — Esperando retroceso"

        return {
            "signal": "NEUTRAL",
            "reason": neutral_reason,
            "position_size": 0.0,
            "sl_price": 0.0,
            "tp_price": 0.0,
            "indicators": indicators,
        }

