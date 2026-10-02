"""
A3 Crypto Futures Hunter Strategy (strategies/crypto_futures_hunter.py)
Motor Cuantitativo de Futuros con Esperanza Matemática Positiva (E > 0).
Diseñado para la campaña de crecimiento acelerado de $200 USD a $1,200 USD.

Principios Clave:
1. Alineación 100% con la Marea Mayor (4H Macro Trend Gatekeeper):
   - En Macro Bull: Solo se permiten compras (LONGS). Prohibido vender en corto contra la tendencia.
   - En Macro Bear: Solo se permiten ventas (SHORTS). Prohibido comprar en cuchillos que caen.
2. Gatillo de Entrada de Doble Confluencia:
   - Barrido de Liquidez (Liquidity Sweep / Fakeout): Rechazo tras barrer un mínimo/máximo local.
   - Retroceso Táctico a Zona de Valor (EMA 20 / EMA 50) con confirmación de vela.
3. Asimetría R:R 1:2.5 a 1:3.0 con Stop Loss Estricto:
   - Riesgo controlado del 5% del capital por operación.
   - Pérdida máxima acotada vs. ganancias superiores a +$20 USD por trade ganador.
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
from core.macro_regime import macro_regime_detector

logger = logging.getLogger("CryptoFuturesHunter")


class CryptoFuturesHunterStrategy:
    """
    Estrategia de Cripto Futuros de Alta Asimetría basada en Psicología de Mercado,
    Barridos de Liquidez y Gestión de Capital de $200 a $1,200.
    """

    def __init__(
        self,
        symbol: str = "SOL-USDT",
        ema_fast: int = 20,
        ema_slow: int = 50,
        ema_trend: int = 200,
        adx_min: float = 18.0,
        risk_per_trade_pct: float = 0.05,
        target_account_goal: float = 1200.0,
        cooldown_candles: int = 3,
        **kwargs,
    ):
        self.symbol = symbol
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.ema_trend = ema_trend
        self.adx_min = adx_min
        self.risk_per_trade_pct = risk_per_trade_pct
        self.target_account_goal = target_account_goal
        self.cooldown_candles = cooldown_candles
        self.bb_period = 20
        self._last_trade_idx = -999
        self.macro_detector = macro_regime_detector
        self.extra_kwargs = kwargs

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
        if latest_metrics is None:
            latest_metrics = {}

        if len(df) < 30:
            return {
                "signal": "NEUTRAL",
                "reason": "Calentando velas históricas (< 30 velas)",
                "position_size": 0.0,
                "sl_price": 0.0,
                "tp_price": 0.0,
                "strategy_name": "crypto_futures_hunter",
                "indicators": {},
            }

        data = self.compute_indicators(df.copy())
        curr = data.iloc[-1]

        close = float(curr["close"])
        open_p = float(curr["open"])
        high = float(curr["high"])
        low = float(curr["low"])

        ema_20 = float(curr["ema_fast"]) if not pd.isna(curr["ema_fast"]) else close
        ema_50 = float(curr["ema_slow"]) if not pd.isna(curr["ema_slow"]) else close
        ema_200 = float(curr["ema_trend"]) if not pd.isna(curr["ema_trend"]) else close
        atr = float(curr["atr"]) if not pd.isna(curr["atr"]) else max(0.1, close * 0.01)
        rsi = float(curr["rsi"]) if not pd.isna(curr["rsi"]) else 50.0
        adx = float(curr["adx"]) if not pd.isna(curr["adx"]) else 20.0
        pct_b = float(curr["pct_b"]) if not pd.isna(curr["pct_b"]) else 0.5

        # ── 1. FILTRO DE DIRECCIÓN MACRO (4H GATEKEEPER) ──────────────────────
        macro_info = self.macro_detector.get_regime(self.symbol, fallback_15m_df=df)
        allowed_side = macro_info.get("allowed_side", "NONE")
        macro_bias = macro_info.get("regime", "CHOP_STANDBY")

        indicators = {
            "ema_20": round(ema_20, 2),
            "ema_50": round(ema_50, 2),
            "ema_200": round(ema_200, 2),
            "atr": round(atr, 4),
            "rsi": round(rsi, 1),
            "adx": round(adx, 1),
            "pct_b": round(pct_b, 2),
            "macro_bias": macro_bias,
            "target_goal": f"${self.target_account_goal:.2f}",
        }

        # Standby si el mercado macro está sin tendencia clara (preservar los $200)
        if allowed_side == "NONE" or macro_bias == "CHOP_STANDBY":
            return {
                "signal": "NEUTRAL",
                "reason": f"🛡️ Standby de Preservación: Mercado en {macro_bias}. Esperando marea clara.",
                "position_size": 0.0,
                "sl_price": 0.0,
                "tp_price": 0.0,
                "strategy_name": "crypto_futures_hunter",
                "indicators": indicators,
            }

        # Control disciplinario post-trade
        current_idx = len(df) - 1
        if (current_idx - self._last_trade_idx) < self.cooldown_candles:
            rem = self.cooldown_candles - (current_idx - self._last_trade_idx)
            return {
                "signal": "NEUTRAL",
                "reason": f"🧘 Control Emocional: Enfriamiento post-trade ({rem} velas restantes)",
                "position_size": 0.0,
                "sl_price": 0.0,
                "tp_price": 0.0,
                "strategy_name": "crypto_futures_hunter",
                "indicators": indicators,
            }

        # Lookback de swing local
        lookback = min(15, len(df) - 2)
        prior_slice = df.iloc[-lookback - 1 : -1]
        swing_high = float(prior_slice["high"].max())
        swing_low = float(prior_slice["low"].min())

        # Riesgo y dimensionamiento dinámico
        risk_pct = self.risk_per_trade_pct
        if current_balance > 400.0:
            risk_pct = min(0.08, self.risk_per_trade_pct * 1.3)
        risk_usd = current_balance * risk_pct

        # ── 2. SEÑAL COMPRADORA (LONG) ────────────────────────────────────────
        if allowed_side == "BUY":
            is_sweep_reversal = (low < swing_low and close > swing_low)
            is_pullback = (close <= ema_20 * 1.015) and (close >= ema_50 * 0.985) and (close > open_p)

            if is_sweep_reversal or is_pullback:
                sl_dist = max(close * 0.012, max(close - low, atr * 1.3))
                sl_price = round(close - sl_dist, 4)
                tp_dist = sl_dist * 2.6
                tp_price = round(close + tp_dist, 4)

                pos_size = round(risk_usd / sl_dist, 4) if sl_dist > 0 else 0.01
                max_pos = (current_balance * 0.50 * 0.98) / close if close > 0 else 0.01
                pos_size = min(pos_size, max_pos)
                pos_size = max(0.001, round(pos_size, 4))

                pattern_name = "BARRIDO DE LIQUIDEZ (BEAR TRAP)" if is_sweep_reversal else "RETROCESO EN TENDENCIA EMA20"
                self._last_trade_idx = current_idx
                return {
                    "signal": "BUY",
                    "confidence": 0.93 if is_sweep_reversal else 0.88,
                    "reason": (
                        f"🚀 FUTURES LONG [{pattern_name}]: Confluencia 4H Alcista en ${close:.2f}. "
                        f"R:R 1:2.6 | Target: ${tp_price:.2f} (Ganancia estimada: +${round(pos_size * tp_dist, 2):.2f})"
                    ),
                    "entry_price": close,
                    "sl_price": sl_price,
                    "tp_price": tp_price,
                    "position_size": pos_size,
                    "risk_amount_usd": round(risk_usd, 2),
                    "strategy_name": "crypto_futures_hunter",
                    "indicators": indicators,
                }

        # ── 3. SEÑAL VENDEDORA (SHORT) ────────────────────────────────────────
        if allowed_side == "SELL":
            is_sweep_reversal = (high > swing_high and close < swing_high)
            is_rally = (close >= ema_20 * 0.985) and (close <= ema_50 * 1.015) and (close < open_p)

            if is_sweep_reversal or is_rally:
                sl_dist = max(close * 0.012, max(high - close, atr * 1.3))
                sl_price = round(close + sl_dist, 4)
                tp_dist = sl_dist * 2.6
                tp_price = round(close - tp_dist, 4)

                pos_size = round(risk_usd / sl_dist, 4) if sl_dist > 0 else 0.01
                max_pos = (current_balance * 0.50 * 0.98) / close if close > 0 else 0.01
                pos_size = min(pos_size, max_pos)
                pos_size = max(0.001, round(pos_size, 4))

                pattern_name = "TRAMPA DE COMPRADORES (BULL TRAP)" if is_sweep_reversal else "RALLY A RESISTENCIA EMA20"
                self._last_trade_idx = current_idx
                return {
                    "signal": "SELL",
                    "confidence": 0.93 if is_sweep_reversal else 0.88,
                    "reason": (
                        f"🔻 FUTURES SHORT [{pattern_name}]: Confluencia 4H Bajista en ${close:.2f}. "
                        f"R:R 1:2.6 | Target: ${tp_price:.2f} (Ganancia estimada: +${round(pos_size * tp_dist, 2):.2f})"
                    ),
                    "entry_price": close,
                    "sl_price": sl_price,
                    "tp_price": tp_price,
                    "position_size": pos_size,
                    "risk_amount_usd": round(risk_usd, 2),
                    "strategy_name": "crypto_futures_hunter",
                    "indicators": indicators,
                }

        return {
            "signal": "NEUTRAL",
            "reason": f"Esperando confluencia en dirección {allowed_side}: Mercado en zona de balance",
            "position_size": 0.0,
            "sl_price": 0.0,
            "tp_price": 0.0,
            "strategy_name": "crypto_futures_hunter",
            "indicators": indicators,
        }
