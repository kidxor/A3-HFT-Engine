import pandas as pd
import numpy as np
from typing import Dict, Any, Optional


class OrderbookScalperStrategy:
    def __init__(
        self,
        vir_threshold: float = 2.0,
        target_ticks: int = 12,
        stop_ticks: int = 6,
        tick_size: float = 0.01,
        risk_per_trade_pct: float = 0.005,
        cooldown_ticks: int = 5,
    ):
        self.vir_threshold = vir_threshold
        self.target_ticks = target_ticks
        self.stop_ticks = stop_ticks
        self.tick_size = tick_size
        self.risk_per_trade_pct = risk_per_trade_pct
        self.cooldown_ticks = cooldown_ticks
        self._last_trade_tick = -999

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        return df

    def evaluate(
        self,
        df: pd.DataFrame,
        current_balance: float = 1000.0,
        latest_metrics: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if latest_metrics is None:
            return {
                "signal": "NEUTRAL",
                "reason": "Sin datos de orderbook",
                "position_size": 0.0,
                "sl_price": 0.0,
                "tp_price": 0.0,
            }

        vir = latest_metrics.get("volume_imbalance", 1.0)
        ofi = latest_metrics.get("ofi_delta", 0.0)
        mid = latest_metrics.get("mid_price", 0.0)
        spread = latest_metrics.get("spread", 0.0)
        best_bid = latest_metrics.get("best_bid", 0.0)
        best_ask = latest_metrics.get("best_ask", 0.0)

        if mid <= 0:
            return {"signal": "NEUTRAL", "reason": "Precio inválido", "position_size": 0.0, "sl_price": 0.0, "tp_price": 0.0}

        tick = max(self.tick_size, spread / 2.0)

        indicators = {
            "vir": round(vir, 2),
            "ofi": round(ofi, 2),
            "spread": spread,
            "mid": mid,
        }

        # BUY: strong bid pressure
        if vir >= self.vir_threshold and ofi > 0:
            sl_price = round(best_bid - (self.stop_ticks * tick), 4)
            tp_price = round(best_bid + (self.target_ticks * tick), 4)
            risk_per_unit = best_bid - sl_price
            risk_amount = current_balance * self.risk_per_trade_pct
            position_size = round(risk_amount / max(risk_per_unit, tick), 4) if risk_per_unit > 0 else 0.0
            return {
                "signal": "BUY",
                "confidence": round(min(1.0, (vir - 1.0) / 3.0), 2),
                "reason": f"Orderbook LONG: VIR {vir:.1f}x | OFI {ofi:+.1f} | Spread ${spread:.2f}",
                "entry_price": best_bid,
                "sl_price": sl_price,
                "tp_price": tp_price,
                "position_size": position_size,
                "risk_amount_usd": round(risk_amount, 2),
                "indicators": indicators,
            }

        # SELL: strong ask pressure
        if vir <= (1.0 / self.vir_threshold) and ofi < 0:
            sl_price = round(best_ask + (self.stop_ticks * tick), 4)
            tp_price = round(best_ask - (self.target_ticks * tick), 4)
            risk_per_unit = sl_price - best_ask
            risk_amount = current_balance * self.risk_per_trade_pct
            position_size = round(risk_amount / max(risk_per_unit, tick), 4) if risk_per_unit > 0 else 0.0
            return {
                "signal": "SELL",
                "confidence": round(min(1.0, (1.0 / max(vir, 0.01) - 1.0) / 3.0), 2),
                "reason": f"Orderbook SHORT: VIR {vir:.1f}x | OFI {ofi:+.1f} | Spread ${spread:.2f}",
                "entry_price": best_ask,
                "sl_price": sl_price,
                "tp_price": tp_price,
                "position_size": position_size,
                "risk_amount_usd": round(risk_amount, 2),
                "indicators": indicators,
            }

        reasons = []
        if 1.0 / self.vir_threshold < vir < self.vir_threshold:
            reasons.append(f"VIR neutral ({vir:.1f}x)")
        if abs(ofi) < 0.5:
            reasons.append(f"OFI bajo ({ofi:+.1f})")
        return {
            "signal": "NEUTRAL",
            "reason": " | ".join(reasons) or "Sin condiciones L2",
            "position_size": 0.0,
            "sl_price": 0.0,
            "tp_price": 0.0,
            "indicators": indicators,
        }
