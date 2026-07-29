import time
import numpy as np
from typing import Dict, Any, Optional, List, Callable
from collections import deque

class HFTPosition:
    """Active Sub-Second HFT Position."""
    def __init__(self, position_id: str, symbol: str, side: str, entry_price: float, quantity: float, tp_price: float, sl_price: float, timestamp_ms: float):
        self.position_id = position_id
        self.symbol = symbol
        self.side = side  # "BUY" or "SELL"
        self.entry_price = entry_price
        self.quantity = quantity
        self.tp_price = tp_price
        self.sl_price = sl_price
        self.timestamp_ms = timestamp_ms
        self.status = "OPEN"  # "OPEN", "CLOSED_TP", "CLOSED_SL"
        self.exit_price: Optional[float] = None
        self.exit_time_ms: Optional[float] = None
        self.pnl: float = 0.0
        self.total_fee: float = 0.0

class HFTExecutionEngine:
    """Manages post-only Maker limit orders with realistic fee execution and slippage simulation."""
    def __init__(self, initial_capital: float = 50.0, maker_fee: float = 0.001, slippage_pct: float = 0.0005):
        self.capital = initial_capital
        self.maker_fee = maker_fee  # 0.10% KuCoin standard maker fee
        self.slippage_pct = slippage_pct  # 0.05% simulated slippage per fill
        self.active_positions: List[HFTPosition] = []
        self.closed_positions: deque = deque(maxlen=500)
        self.total_trades = 0
        self.wins = 0
        self.losses = 0
        self.cum_pnl = 0.0
        self.peak_equity: float = initial_capital
        self.last_trade_close_time: float = -999999.0
        self.trade_cooldown_seconds: float = 10.0
        self.trailing_stop_pct: float = 0.003  # 0.3% unrealized profit to activate trailing stop
        self.trailing_stop_activation_pct: float = 0.5  # activate at 50% of TP distance
        self.on_trade_open: Optional[Callable[[HFTPosition], bool]] = None
        self.on_trade_close: Optional[Callable[[HFTPosition], None]] = None

    def open_position(self, symbol: str, side: str, price: float, quantity: float, tp_price: float, sl_price: float, timestamp_ms: float) -> Optional[HFTPosition]:
        """Executes a simulated maker limit order with realistic slippage."""
        if len(self.active_positions) >= 1:
            return None  # Only 1 position at a time for high frequency scalp

        # Enforce cooldown between trades
        current_time = timestamp_ms / 1000.0
        if current_time - self.last_trade_close_time < self.trade_cooldown_seconds:
            return None

        # Apply slippage: BUY pays slightly more, SELL receives slightly less
        if side == "BUY":
            execution_price = round(price * (1 + self.slippage_pct), 4)
        else:
            execution_price = round(price * (1 - self.slippage_pct), 4)

        pos_id = f"HFT_{int(timestamp_ms)}_{self.total_trades + 1}"
        pos = HFTPosition(pos_id, symbol, side, execution_price, quantity, tp_price, sl_price, timestamp_ms)

        if self.on_trade_open:
            allowed = self.on_trade_open(pos)
            if not allowed:
                return None

        self.active_positions.append(pos)
        return pos

    def update_positions(self, current_tick_bid: float, current_tick_ask: float, timestamp_ms: float):
        """Checks if current tick price triggers TP, SL, or trailing stop for open positions."""
        for pos in list(self.active_positions):
            # Calculate unrealized PnL for trailing/breakeven logic
            if pos.side == "BUY":
                unrealized_pct = (current_tick_bid - pos.entry_price) / pos.entry_price if pos.entry_price > 0 else 0
                tp_distance_pct = (pos.tp_price - pos.entry_price) / pos.entry_price if pos.entry_price > 0 else 0.01
            else:
                unrealized_pct = (pos.entry_price - current_tick_ask) / pos.entry_price if pos.entry_price > 0 else 0
                tp_distance_pct = (pos.entry_price - pos.tp_price) / pos.entry_price if pos.entry_price > 0 else 0.01

            # Breakeven stop: if unrealized profit reaches 50% of TP distance, move SL to entry price
            if unrealized_pct > 0 and tp_distance_pct > 0:
                if unrealized_pct >= tp_distance_pct * self.trailing_stop_activation_pct:
                    if pos.side == "BUY" and pos.sl_price < pos.entry_price:
                        pos.sl_price = pos.entry_price + (pos.entry_price * 0.0002)  # tiny buffer above entry
                    elif pos.side == "SELL" and pos.sl_price > pos.entry_price:
                        pos.sl_price = pos.entry_price - (pos.entry_price * 0.0002)

            # Trailing stop: if unrealized profit exceeds threshold, trail SL behind price
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

            if pos.side == "BUY":
                # Take Profit hit if best bid reaches or exceeds TP
                if current_tick_bid >= pos.tp_price:
                    self._close_position(pos, pos.tp_price, timestamp_ms, "CLOSED_TP")
                # Stop Loss hit if best ask falls to or below SL
                elif current_tick_ask <= pos.sl_price:
                    self._close_position(pos, pos.sl_price, timestamp_ms, "CLOSED_SL")

            elif pos.side == "SELL":
                # Take Profit hit for short
                if current_tick_ask <= pos.tp_price:
                    self._close_position(pos, pos.tp_price, timestamp_ms, "CLOSED_TP")
                elif current_tick_bid >= pos.sl_price:
                    self._close_position(pos, pos.sl_price, timestamp_ms, "CLOSED_SL")

    def _close_position(self, pos: HFTPosition, exit_price: float, timestamp_ms: float, status: str):
        # Apply slippage on exit: BUY exits sell lower, SELL exits buy higher
        if pos.side == "BUY":
            actual_exit_price = round(exit_price * (1 - self.slippage_pct), 4)
        else:
            actual_exit_price = round(exit_price * (1 + self.slippage_pct), 4)

        pos.exit_price = actual_exit_price
        pos.exit_time_ms = timestamp_ms
        pos.status = status
        self.last_trade_close_time = timestamp_ms / 1000.0

        if pos.side == "BUY":
            raw_pnl = (actual_exit_price - pos.entry_price) * pos.quantity
        else:
            raw_pnl = (pos.entry_price - actual_exit_price) * pos.quantity

        # Deduct fees on both entry and exit
        entry_fee = pos.entry_price * pos.quantity * self.maker_fee
        exit_fee = actual_exit_price * pos.quantity * self.maker_fee
        total_fee = entry_fee + exit_fee
        pos.total_fee = total_fee
        pos.pnl = raw_pnl - total_fee

        self.capital += pos.pnl
        self.cum_pnl += pos.pnl
        self.total_trades += 1

        if self.capital > self.peak_equity:
            self.peak_equity = self.capital

        if pos.pnl > 0:
            self.wins += 1
        else:
            self.losses += 1

        self.active_positions.remove(pos)
        self.closed_positions.append(pos)

        if self.on_trade_close:
            self.on_trade_close(pos)

    def get_stats(self) -> Dict[str, Any]:
        win_rate = (self.wins / self.total_trades * 100.0) if self.total_trades > 0 else 0.0

        # Profit Factor
        closed_pnls = [p.pnl for p in self.closed_positions]
        gross_wins = sum(p for p in closed_pnls if p > 0)
        gross_losses = abs(sum(p for p in closed_pnls if p < 0))
        profit_factor = round(gross_wins / gross_losses, 2) if gross_losses > 0 else (gross_wins if gross_wins > 0 else 0.0)

        # Sharpe Ratio (using trade returns, risk-free = 0)
        sharpe_ratio = 0.0
        if len(closed_pnls) >= 5:
            returns = np.diff(closed_pnls) / (np.abs(closed_pnls[:-1]) + 1e-9)
            if returns.std() > 0:
                sharpe_ratio = round((returns.mean() / returns.std()) * np.sqrt(252), 2)

        return {
            "capital": round(self.capital, 2),
            "cum_pnl": round(self.cum_pnl, 4),
            "total_trades": self.total_trades,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate_percent": round(win_rate, 1),
            "profit_factor": profit_factor,
            "sharpe_ratio": sharpe_ratio,
            "open_positions": len(self.active_positions)
        }
