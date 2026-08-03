import time
import numpy as np
from typing import Dict, Any, Optional, List, Callable
from collections import deque


class HFTPosition:
    """Active Sub-Second HFT Position."""
    def __init__(
        self,
        position_id: str,
        symbol: str,
        side: str,
        entry_price: float,
        quantity: float,
        tp_price: float,
        sl_price: float,
        timestamp_ms: float,
    ):
        self.position_id = position_id
        self.symbol      = symbol
        self.side        = side        # "BUY" or "SELL"
        self.entry_price = entry_price
        self.quantity    = quantity
        self.tp_price    = tp_price
        self.sl_price    = sl_price
        self.timestamp_ms = timestamp_ms
        self.status      = "OPEN"      # "OPEN" | "CLOSED_TP" | "CLOSED_SL"
        self.exit_price: Optional[float] = None
        self.exit_time_ms: Optional[float] = None
        self.pnl: float = 0.0
        self.total_fee: float = 0.0


class HFTExecutionEngine:
    """
    Manages post-only Maker limit orders with realistic fee execution and
    slippage simulation.

    Performance notes:
    - _gross_wins / _gross_losses are maintained incrementally so get_stats()
      does not need to iterate closed_positions on every call.
    - Sharpe ratio uses a running deque of the last 500 PnL values — no
      repeated numpy fromiter() over the full closed_positions deque.
    """

    def __init__(
        self,
        initial_capital: float = 50.0,
        maker_fee: float = 0.001,
        slippage_pct: float = 0.0005,
        trade_cooldown_seconds: float = 1.0,   # 1s for fast HFT scalping
    ):
        self.capital    = initial_capital
        self.maker_fee  = maker_fee
        self.slippage_pct = slippage_pct

        self.active_positions: List[HFTPosition] = []
        self.closed_positions: deque = deque(maxlen=500)

        self.total_trades = 0
        self.wins   = 0
        self.losses = 0
        self.cum_pnl = 0.0
        self.peak_equity: float = initial_capital

        # Incremental profit-factor accumulators (O(1) per trade vs O(n) scan)
        self._gross_wins:   float = 0.0
        self._gross_losses: float = 0.0

        # Rolling PnL values for Sharpe — last 500 trade results
        self._pnl_window: deque = deque(maxlen=500)

        self.last_trade_close_time: float = -999_999.0
        self.trade_cooldown_seconds: float = trade_cooldown_seconds

        self.trailing_stop_pct: float = 0.04          # 4% trailing — only activates deep in-profit
        self.trailing_stop_activation_pct: float = 0.75  # Activates at 75% of TP distance

        self.on_trade_open:  Optional[Callable[[HFTPosition], bool]] = None
        self.on_trade_close: Optional[Callable[[HFTPosition], None]] = None

    # ------------------------------------------------------------------
    # Position management
    # ------------------------------------------------------------------

    def open_position(
        self,
        symbol: str,
        side: str,
        price: float,
        quantity: float,
        tp_price: float,
        sl_price: float,
        timestamp_ms: float,
    ) -> Optional[HFTPosition]:
        """Executes a simulated maker limit order with realistic slippage."""
        if len(self.active_positions) >= 1:
            return None  # Only 1 position at a time for high-frequency scalp

        current_time = timestamp_ms / 1000.0
        if current_time - self.last_trade_close_time < self.trade_cooldown_seconds:
            return None

        # Apply slippage
        if side == "BUY":
            execution_price = round(price * (1 + self.slippage_pct), 4)
        else:
            execution_price = round(price * (1 - self.slippage_pct), 4)

        pos_id = f"HFT_{int(timestamp_ms)}_{self.total_trades + 1}"
        pos = HFTPosition(pos_id, symbol, side, execution_price, quantity, tp_price, sl_price, timestamp_ms)

        if self.on_trade_open:
            if not self.on_trade_open(pos):
                return None

        self.active_positions.append(pos)
        return pos

    def update_positions(self, current_tick_bid: float, current_tick_ask: float, timestamp_ms: float):
        """Checks if current tick triggers TP, SL, or trailing stop."""
        for pos in list(self.active_positions):
            if pos.side == "BUY":
                unrealized_pct  = (current_tick_bid - pos.entry_price) / pos.entry_price if pos.entry_price > 0 else 0
                tp_distance_pct = (pos.tp_price - pos.entry_price) / pos.entry_price if pos.entry_price > 0 else 0.01
            else:
                unrealized_pct  = (pos.entry_price - current_tick_ask) / pos.entry_price if pos.entry_price > 0 else 0
                tp_distance_pct = (pos.entry_price - pos.tp_price) / pos.entry_price if pos.entry_price > 0 else 0.01

            # Breakeven stop: only activates when >= 90% of TP distance is covered
            if unrealized_pct > 0 and tp_distance_pct > 0:
                if unrealized_pct >= tp_distance_pct * 0.90:
                    if pos.side == "BUY" and pos.sl_price < pos.entry_price:
                        pos.sl_price = pos.entry_price + (pos.entry_price * 0.001)
                    elif pos.side == "SELL" and pos.sl_price > pos.entry_price:
                        pos.sl_price = pos.entry_price - (pos.entry_price * 0.001)

            # Trailing stop
            if unrealized_pct >= self.trailing_stop_pct:
                trail_distance = pos.entry_price * self.trailing_stop_pct
                if pos.side == "BUY":
                    new_sl = current_tick_bid - trail_distance
                    if new_sl > pos.sl_price:
                        pos.sl_price = round(new_sl, 4)
                else:
                    new_sl = current_tick_ask + trail_distance
                    if new_sl < pos.sl_price:
                        pos.sl_price = round(new_sl, 4)

            # TP / SL triggers
            if pos.side == "BUY":
                if current_tick_bid >= pos.tp_price:
                    self._close_position(pos, pos.tp_price, timestamp_ms, "CLOSED_TP")
                elif current_tick_ask <= pos.sl_price:
                    self._close_position(pos, pos.sl_price, timestamp_ms, "CLOSED_SL")
            else:
                if current_tick_ask <= pos.tp_price:
                    self._close_position(pos, pos.tp_price, timestamp_ms, "CLOSED_TP")
                elif current_tick_bid >= pos.sl_price:
                    self._close_position(pos, pos.sl_price, timestamp_ms, "CLOSED_SL")

    def _close_position(self, pos: HFTPosition, exit_price: float, timestamp_ms: float, status: str):
        # Apply exit slippage
        if pos.side == "BUY":
            actual_exit = round(exit_price * (1 - self.slippage_pct), 4)
        else:
            actual_exit = round(exit_price * (1 + self.slippage_pct), 4)

        pos.exit_price    = actual_exit
        pos.exit_time_ms  = timestamp_ms
        pos.status        = status
        self.last_trade_close_time = timestamp_ms / 1000.0

        if pos.side == "BUY":
            raw_pnl = (actual_exit - pos.entry_price) * pos.quantity
        else:
            raw_pnl = (pos.entry_price - actual_exit) * pos.quantity

        entry_fee = pos.entry_price * pos.quantity * self.maker_fee
        exit_fee  = actual_exit     * pos.quantity * self.maker_fee
        total_fee = entry_fee + exit_fee
        pos.total_fee = total_fee
        pos.pnl       = raw_pnl - total_fee

        self.capital  += pos.pnl
        self.cum_pnl  += pos.pnl
        self.total_trades += 1

        if self.capital > self.peak_equity:
            self.peak_equity = self.capital

        # Incremental accumulators — O(1)
        if pos.pnl > 0:
            self.wins        += 1
            self._gross_wins += pos.pnl
        else:
            self.losses        += 1
            self._gross_losses += abs(pos.pnl)

        # Rolling PnL window for Sharpe
        self._pnl_window.append(pos.pnl)

        self.active_positions.remove(pos)
        self.closed_positions.append(pos)

        if self.on_trade_close:
            self.on_trade_close(pos)

    # ------------------------------------------------------------------
    # Stats — O(1) for profit factor, O(k) Sharpe only when k>=5
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        win_rate = (self.wins / self.total_trades * 100.0) if self.total_trades > 0 else 0.0

        # Profit Factor — incremental, no scan
        if self._gross_losses > 0:
            profit_factor = round(self._gross_wins / self._gross_losses, 2)
        elif self._gross_wins > 0:
            profit_factor = float(self._gross_wins)
        else:
            profit_factor = 0.0

        # Sharpe — only computed with enough data
        sharpe_ratio = 0.0
        n = len(self._pnl_window)
        if n >= 5:
            pnl_arr = np.fromiter(self._pnl_window, dtype=np.float64, count=n)
            prev    = pnl_arr[:-1]
            returns = np.diff(pnl_arr) / (np.abs(prev) + 1e-9)
            std     = returns.std()
            if std > 0:
                sharpe_ratio = round((returns.mean() / std) * np.sqrt(252), 2)

        return {
            "capital":          round(self.capital, 2),
            "cum_pnl":          round(self.cum_pnl, 4),
            "total_trades":     self.total_trades,
            "wins":             self.wins,
            "losses":           self.losses,
            "win_rate_percent": round(win_rate, 1),
            "profit_factor":    profit_factor,
            "sharpe_ratio":     sharpe_ratio,
            "open_positions":   len(self.active_positions),
        }
