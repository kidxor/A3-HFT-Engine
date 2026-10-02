"""
A3 Institutional Trend & Macro Engine (strategies/institutional_trend.py)
Estrategia Cuantitativa de Grado Institucional con Esperanza Matemática Positiva (E > 0).

3 Filtros Innegociables:
1. Macro-Régimen 4H (core/macro_regime.py): Solo opera a favor de la marea mayor. 100% Cash en consolidación.
2. Retroceso Táctico a Zona de Valor (15m/1h): Compra con descuento en EMA 20/50, nunca en techos. Vende en rally a resistencia, nunca en suelos.
3. Asimetría R:R 1:2.8+ (> $5.00 USD Objetivo Neto): Stop loss amplio detrás de pivote (1.6% - 2.2%), Take Profit amplio (4% - 6%).
"""

import logging
from typing import Dict, Any, Optional
import pandas as pd
import numpy as np

from strategies.indicators import (
    compute_ema,
    compute_rsi,
    compute_adx,
    compute_atr,
    compute_bollinger_bands,
)
from core.market_structure import (
    detect_candlestick_patterns,
    detect_support_resistance_zones,
    calculate_fibonacci_levels,
)
from core.macro_regime import macro_regime_detector

logger = logging.getLogger("InstitutionalTrend")


class InstitutionalTrendStrategy:
    """
    Institutional Trend-Following & Value Pullback Strategy.
    Designed for zero micro-churn, asymmetric reward, and positive expectancy.
    """

    def __init__(
        self,
        symbol: str = "SOL-USDT",
        ema_fast: int = 20,
        ema_slow: int = 50,
        ema_trend: int = 200,
        adx_min: float = 22.0,
        atr_sl_mult: float = 1.6,
        atr_tp_mult: float = 4.5,
        risk_per_trade_pct: float = 0.03,  # 3% controlled risk
        max_exposure_pct: float = 0.50,    # Max 50% equity in one asset
        cooldown_candles: int = 4,         # 1-hour patience between trades
        **kwargs,
    ):
        self.symbol = symbol
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.ema_trend = ema_trend
        self.adx_min = adx_min
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult
        self.risk_per_trade_pct = risk_per_trade_pct
        self.max_exposure_pct = max_exposure_pct
        self.cooldown_candles = cooldown_candles
        self.bb_period = 20
        self._last_trade_idx = -999
        self.extra_kwargs = kwargs
        self.macro_detector = macro_regime_detector

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        close = df["close"]
        df["ema_fast"] = compute_ema(close, self.ema_fast)
        df["ema_slow"] = compute_ema(close, self.ema_slow)
        df["ema_trend"] = compute_ema(close, self.ema_trend)
        df["atr"] = compute_atr(df, 14)
        df["adx"] = compute_adx(df, 14)
        df["rsi"] = compute_rsi(close, 14)
        df["bb_upper"], df["bb_middle"], df["bb_lower"], df["pct_b"] = (
            compute_bollinger_bands(close, 20, 2.0)
        )
        return df

    def evaluate(
        self,
        df: pd.DataFrame,
        current_balance: float = 200.0,
        latest_metrics: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Evaluates the 3-Filter Institutional Execution Model on 15m candle close.
        """
        if latest_metrics is None:
            latest_metrics = {}
        for k, v in kwargs.items():
            if k not in latest_metrics:
                latest_metrics[k] = v
        if len(df) < 35:
            return {
                "signal": "NEUTRAL",
                "reason": "Historial insuficiente (< 35 velas)",
                "position_size": 0.0, "sl_price": 0.0, "tp_price": 0.0,
                "strategy_name": "institutional_trend",
                "indicators": {},
            }

        close_s = df["close"]
        close   = float(close_s.iloc[-1])
        open_p  = float(df["open"].iloc[-1])
        candle_low  = float(df["low"].iloc[-1])
        candle_high = float(df["high"].iloc[-1])

        # Technical Indicators (15m execution timeframe)
        ema_20_s = compute_ema(close_s, 20)
        ema_50_s = compute_ema(close_s, 50)
        ema_200_s = compute_ema(close_s, 200)

        ema_20  = float(ema_20_s.iloc[-1]) if not pd.isna(ema_20_s.iloc[-1]) else close
        ema_50  = float(ema_50_s.iloc[-1]) if not pd.isna(ema_50_s.iloc[-1]) else close
        ema_200 = float(ema_200_s.iloc[-1]) if not pd.isna(ema_200_s.iloc[-1]) else close

        atr_s = compute_atr(df, 14)
        atr   = float(atr_s.iloc[-1]) if not pd.isna(atr_s.iloc[-1]) else (close * 0.01)

        rsi_s = compute_rsi(close_s, 14)
        rsi   = float(rsi_s.iloc[-1]) if not pd.isna(rsi_s.iloc[-1]) else 50.0

        adx_s = compute_adx(df, 14)
        adx   = float(adx_s.iloc[-1]) if not pd.isna(adx_s.iloc[-1]) else 15.0

        _, _, _, pct_b_s = compute_bollinger_bands(close_s, 20, 2.0)
        pct_b = float(pct_b_s.iloc[-1]) if not pd.isna(pct_b_s.iloc[-1]) else 0.5

        # Candlestick Pattern & Rejection Wicks
        candles = detect_candlestick_patterns(df)
        patterns = candles.get("patterns", [])
        pattern_str = ", ".join(patterns) if patterns else ("Rebote Verde" if close >= open_p else "Vela Roja")

        # Orderbook Metrics
        vir = float(latest_metrics.get("vir", 1.0)) if latest_metrics else 1.0
        micro_price = float(latest_metrics.get("micro_price", close)) if latest_metrics else close

        indicators = {
            "ema_20": round(ema_20, 2),
            "ema_50": round(ema_50, 2),
            "ema_200": round(ema_200, 2),
            "adx": round(adx, 1),
            "rsi": round(rsi, 1),
            "atr": round(atr, 4),
            "pct_b": round(pct_b, 2),
            "vir": round(vir, 2),
            "candle_pattern": pattern_str,
            "micro_price": round(micro_price, 2),
        }

        # ── FILTRO 1: SEMÁFORO MACRO DE 4 HORAS (GATEKEEPER) ───────────
        macro_info = self.macro_detector.get_regime(self.symbol, fallback_15m_df=df)
        macro_regime = macro_info.get("regime", "CHOP_STANDBY")
        allowed_side = macro_info.get("allowed_side", "NONE")
        indicators["macro_regime"] = macro_regime
        indicators["macro_adx"] = macro_info.get("adx_4h", 0.0)

        # Si el macro es de rango o sin tendencia, QUEDARSE EN CASH (Preservar 100% Capital)
        if macro_regime == "CHOP_STANDBY" or allowed_side == "NONE":
            return {
                "signal": "NEUTRAL",
                "reason": f"🛡️ STANDBY INSTITUCIONAL [{macro_regime}]: {macro_info.get('reason')}",
                "position_size": 0.0, "sl_price": 0.0, "tp_price": 0.0,
                "strategy_name": "institutional_trend",
                "indicators": indicators,
            }

        # Cooldown Check
        current_idx = len(df) - 1
        if (current_idx - self._last_trade_idx) < self.cooldown_candles:
            return {
                "signal": "NEUTRAL",
                "reason": f"Pausa reflexiva post-trade ({current_idx - self._last_trade_idx}/{self.cooldown_candles} velas)",
                "position_size": 0.0, "sl_price": 0.0, "tp_price": 0.0,
                "strategy_name": "institutional_trend",
                "indicators": indicators,
            }

        # ── FILTRO 2: RETROCESO TÁCTICO A ZONA DE VALOR & ANTI-CHOP ────
        # S/R Buffer dinámico basado en ATR
        sr_window = min(30, max(5, len(df) - 1))
        prior_df = df.iloc[-sr_window-1:-1] if len(df) > sr_window else df.iloc[:-1]
        prior_low = float(prior_df["low"].min()) if "low" in prior_df.columns and not prior_df.empty else close
        prior_high = float(prior_df["high"].max()) if "high" in prior_df.columns and not prior_df.empty else close

        sr_buffer = max(close * 0.008, 1.0 * atr)
        is_near_support = (close - prior_low) < sr_buffer
        is_near_resistance = (prior_high - close) < sr_buffer

        # Rejection wick validation
        candle_range = max(0.001, candle_high - candle_low)
        has_bullish_rejection = (close - candle_low) >= (candle_range * 0.45) or candles.get("has_bullish_pattern", False)
        has_bearish_rejection = (candle_high - close) >= (candle_range * 0.45) or candles.get("has_bearish_pattern", False)

        # ── COMPRA INSTITUCIONAL (LONG) ────────────────────────────────
        if allowed_side == "BUY":
            is_pullback_to_value = (close <= ema_20 * 1.015) and (close >= ema_50 * 0.985)
            is_valid_bollinger = (0.30 <= pct_b <= 0.65)  # No comprar en techo
            is_not_extended_rsi = (40.0 <= rsi <= 68.0)

            if (
                is_pullback_to_value
                and is_valid_bollinger
                and is_not_extended_rsi
                and not is_near_resistance
                and not candles.get("is_falling_knife", False)
                and has_bullish_rejection
                and vir >= 1.02
            ):
                # Parámetros Asimétricos R:R >= 1:2.8
                sl_dist = max(close * 0.016, atr * max(1.5, self.atr_sl_mult))
                sl_price = round(close - sl_dist, 4)
                tp_dist = max(sl_dist * 2.8, close * 0.040)
                tp_price = round(close + tp_dist, 4)

                # Dimensionamiento para objetivo > $5.00 USD netos
                net_gain_per_unit = max(0.001, tp_dist - (close * 0.0020))
                min_target_qty = round(5.00 / net_gain_per_unit, 4)

                risk_usd = current_balance * self.risk_per_trade_pct
                pos_size = round(risk_usd / sl_dist, 4) if sl_dist > 0 else min_target_qty
                pos_size = max(pos_size, min_target_qty)

                max_alloc = (current_balance * self.max_exposure_pct * 0.98) / close if close > 0 else 0.0
                pos_size = min(pos_size, max_alloc)
                pos_size = max(0.0001, round(pos_size, 4))

                self._last_trade_idx = current_idx
                return {
                    "signal": "BUY",
                    "confidence": 0.95,
                    "reason": (
                        f"INSTITUTIONAL BUY [R:R 1:2.8+]: Confluencia 4H Macro Bull + "
                        f"Pullback EMA20/50 (${close:.2f}) + {pattern_str} | Target > $5.00 USD"
                    ),
                    "entry_price": close,
                    "sl_price": sl_price,
                    "tp_price": tp_price,
                    "position_size": pos_size,
                    "risk_amount_usd": round(pos_size * sl_dist, 2),
                    "strategy_name": "institutional_trend",
                    "indicators": indicators,
                }

        # ── VENTA INSTITUCIONAL (SHORT) ────────────────────────────────
        if allowed_side == "SELL":
            is_rally_to_value = (close >= ema_20 * 0.985) and (close <= ema_50 * 1.015)
            is_valid_bollinger = (0.35 <= pct_b <= 0.70)  # No vender en suelo
            is_not_extended_rsi = (32.0 <= rsi <= 60.0)

            if (
                is_rally_to_value
                and is_valid_bollinger
                and is_not_extended_rsi
                and not is_near_support
                and has_bearish_rejection
                and vir <= 0.98
            ):
                # Parámetros Asimétricos R:R >= 1:2.8
                sl_dist = max(close * 0.016, atr * max(1.5, self.atr_sl_mult))
                sl_price = round(close + sl_dist, 4)
                tp_dist = max(sl_dist * 2.8, close * 0.040)
                tp_price = round(close - tp_dist, 4)

                # Dimensionamiento para objetivo > $5.00 USD netos
                net_gain_per_unit = max(0.001, tp_dist - (close * 0.0020))
                min_target_qty = round(5.00 / net_gain_per_unit, 4)

                risk_usd = current_balance * self.risk_per_trade_pct
                pos_size = round(risk_usd / sl_dist, 4) if sl_dist > 0 else min_target_qty
                pos_size = max(pos_size, min_target_qty)

                max_alloc = (current_balance * self.max_exposure_pct * 0.98) / close if close > 0 else 0.0
                pos_size = min(pos_size, max_alloc)
                pos_size = max(0.0001, round(pos_size, 4))

                self._last_trade_idx = current_idx
                return {
                    "signal": "SELL",
                    "confidence": 0.95,
                    "reason": (
                        f"INSTITUTIONAL SELL [R:R 1:2.8+]: Confluencia 4H Macro Bear + "
                        f"Rally EMA20/50 (${close:.2f}) + {pattern_str} | Target > $5.00 USD"
                    ),
                    "entry_price": close,
                    "sl_price": sl_price,
                    "tp_price": tp_price,
                    "position_size": pos_size,
                    "risk_amount_usd": round(pos_size * sl_dist, 2),
                    "strategy_name": "institutional_trend",
                    "indicators": indicators,
                }

        # Motivos descriptivos para el usuario
        if allowed_side == "BUY" and is_near_resistance:
            neutral_reason = f"Esperando retroceso: Precio en techo/resistencia reciente (${prior_high:.2f})"
        elif allowed_side == "SELL" and is_near_support:
            neutral_reason = f"Esperando rally: Precio en suelo/soporte reciente (${prior_low:.2f})"
        elif allowed_side == "BUY" and pct_b > 0.65:
            neutral_reason = f"Esperando retroceso a la media: Precio sobreextendido (%b {pct_b:.2f} > 0.65)"
        elif allowed_side == "SELL" and pct_b < 0.35:
            neutral_reason = f"Esperando rally a la media: Precio sobreextendido (%b {pct_b:.2f} < 0.35)"
        elif allowed_side == "BUY":
            neutral_reason = f"Esperando retroceso a zona de valor EMA20 (${ema_20:.2f}) en 15m"
        else:
            neutral_reason = f"Esperando rally a zona de valor EMA20 (${ema_20:.2f}) en 15m"

        return {
            "signal": "NEUTRAL",
            "reason": neutral_reason,
            "position_size": 0.0, "sl_price": 0.0, "tp_price": 0.0,
            "strategy_name": "institutional_trend",
            "indicators": indicators,
        }
