import math
from typing import Dict, Any, Optional
from core.websocket_client import OrderbookTick

class OrderbookEngine:
    """Computes real-time Order Flow Imbalance (OFI), Micro-Price, and Depth Imbalance metrics."""
    def __init__(self, depth_levels: int = 10, ofi_ema_alpha: float = 0.1):
        self.depth_levels = depth_levels
        self.prev_tick: Optional[OrderbookTick] = None
        self.cumulative_ofi: float = 0.0
        self.ofi_ema_alpha = ofi_ema_alpha

    def process_tick(self, tick: OrderbookTick) -> Dict[str, Any]:
        """Processes an incoming tick and returns micro-structural analytics."""
        best_bid = tick.best_bid
        best_ask = tick.best_ask
        mid_price = tick.mid_price
        spread = tick.spread

        # Calculate top-k volume sums
        bid_vol_sum = sum(vol for _, vol in tick.bids[:self.depth_levels])
        ask_vol_sum = sum(vol for _, vol in tick.asks[:self.depth_levels])

        top_bid_vol = tick.bids[0][1] if tick.bids else 1.0
        top_ask_vol = tick.asks[0][1] if tick.asks else 1.0

        # 1. Calculate Micro-Price (Volume-Weighted Mid Price)
        total_top_vol = top_bid_vol + top_ask_vol
        if total_top_vol > 0:
            micro_price = (top_ask_vol * best_bid + top_bid_vol * best_ask) / total_top_vol
        else:
            micro_price = mid_price

        # 2. Volume Imbalance Ratio (VIR)
        volume_imbalance = (bid_vol_sum / ask_vol_sum) if ask_vol_sum > 0 else 1.0

        # 3. Compute Order Flow Imbalance (OFI) delta relative to prev tick
        ofi_delta = 0.0
        if self.prev_tick:
            prev_bid = self.prev_tick.best_bid
            prev_bid_vol = self.prev_tick.bids[0][1] if self.prev_tick.bids else 0.0
            prev_ask = self.prev_tick.best_ask
            prev_ask_vol = self.prev_tick.asks[0][1] if self.prev_tick.asks else 0.0

            # Bid side OFI
            if best_bid > prev_bid:
                delta_bid = top_bid_vol
            elif best_bid == prev_bid:
                delta_bid = top_bid_vol - prev_bid_vol
            else:
                delta_bid = -prev_bid_vol

            # Ask side OFI
            if best_ask < prev_ask:
                delta_ask = top_ask_vol
            elif best_ask == prev_ask:
                delta_ask = top_ask_vol - prev_ask_vol
            else:
                delta_ask = -prev_ask_vol

            ofi_delta = delta_bid - delta_ask

        # EMA-decayed OFI: prevents unbounded accumulation over hours of tick data
        self.cumulative_ofi = self.ofi_ema_alpha * ofi_delta + (1.0 - self.ofi_ema_alpha) * self.cumulative_ofi
        self.prev_tick = tick

        return {
            "symbol": tick.symbol,
            "timestamp_ms": tick.timestamp_ms,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "mid_price": mid_price,
            "micro_price": micro_price,
            "spread": spread,
            "bid_vol_sum": bid_vol_sum,
            "ask_vol_sum": ask_vol_sum,
            "volume_imbalance": volume_imbalance,
            "ofi_delta": ofi_delta,
            "cumulative_ofi": self.cumulative_ofi
        }
