import time
import numpy as np
from typing import Dict, Any, Optional, List, Callable
from collections import deque
from core.event_logger import event_logger


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
        allow_runner: bool = False,
        allow_partial_tp: bool = False,
    ):
        self.position_id = position_id
        self.symbol      = symbol
        self.side        = side        # "BUY" or "SELL"
        self.entry_price = entry_price
        self.quantity    = quantity
        self.initial_tp  = tp_price
        self.tp_price    = tp_price
        self.initial_sl  = sl_price
        self.sl_price    = sl_price
        self.timestamp_ms = timestamp_ms
        self.status      = "OPEN"      # "OPEN" | "CLOSED_TP" | "CLOSED_SL" | "CLOSED_RUNNER_TRAIL" | "CLOSED_REVERSAL_EXIT"
        self.exit_price: Optional[float] = None
        self.exit_time_ms: Optional[float] = None
        self.pnl: float = 0.0
        self.total_fee: float = 0.0
        self.is_partial_closed: bool = False
        self.partial_pnl: float = 0.0
        self.partial_fee: float = 0.0
        self.initial_quantity: float = quantity

        # Dual-Decision Dynamic Runner Fields
        self.allow_runner: bool = allow_runner
        self.allow_partial_tp: bool = allow_partial_tp
        self.runner_mode: bool = False
        self.highest_price: float = entry_price
        self.lowest_price: float = entry_price
        self.runner_trail_pct: float = 0.012


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
        trade_cooldown_seconds: float = 300.0,  # 5 min cooldown entre operaciones para evitar sobreoperación
        enable_dynamic_runner: bool = False,
        runner_trail_pct: float = 0.012,        # 1.2% trailing stop para permitir expansión de tendencia real
        enable_partial_tp: bool = False,
    ):
        self.capital    = initial_capital
        self.maker_fee  = maker_fee
        self.slippage_pct = slippage_pct
        self.enable_partial_tp = enable_partial_tp

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

        self.enable_dynamic_runner: bool = enable_dynamic_runner
        self.runner_trail_pct: float = runner_trail_pct

        self.trailing_stop_pct: float = 0.04          # 4% trailing — only activates deep in-profit
        self.trailing_stop_activation_pct: float = 0.75  # Activates at 75% of TP distance

        self.on_trade_open:  Optional[Callable[[HFTPosition], bool]] = None
        self.on_trade_close: Optional[Callable[[HFTPosition], None]] = None
        self.on_partial_close: Optional[Callable[[HFTPosition, float, float], None]] = None

    # ------------------------------------------------------------------
    # Position management
    # ------------------------------------------------------------------

    def open_position(
        self,
        symbol: str,
        side: str,
        price: float = 0.0,
        quantity: float = 0.0,
        tp_price: float = 0.0,
        sl_price: float = 0.0,
        timestamp_ms: float = 0.0,
        allow_runner: Optional[bool] = None,
        entry_price: Optional[float] = None,
        allow_partial_tp: Optional[bool] = None,
    ) -> Optional[HFTPosition]:
        """Executes a simulated maker limit order with realistic slippage."""
        if entry_price is not None and (price == 0.0 or price is None):
            price = entry_price

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
        effective_allow_runner = self.enable_dynamic_runner if allow_runner is None else allow_runner
        effective_allow_partial = self.enable_partial_tp if allow_partial_tp is None else allow_partial_tp
        pos = HFTPosition(
            pos_id,
            symbol,
            side,
            execution_price,
            quantity,
            tp_price,
            sl_price,
            timestamp_ms,
            allow_runner=effective_allow_runner,
            allow_partial_tp=effective_allow_partial,
        )
        pos.runner_trail_pct = self.runner_trail_pct

        if self.on_trade_open:
            if not self.on_trade_open(pos):
                return None

        self.active_positions.append(pos)
        return pos

    def update_positions(self, current_tick_bid: float, current_tick_ask: float, timestamp_ms: float):
        """
        Dual-Decision Engine:
        Opción A (Runner Dinámico): Permite que la ganancia se expanda sin techo rígido mientras el precio suba.
        Opción B (Salida Defensiva Ultrarrápida): Si el precio retrocede o perfora el piso de protección, vende al instante.
        """
        for pos in list(self.active_positions):
            if pos.side == "BUY":
                if current_tick_bid > pos.highest_price:
                    pos.highest_price = current_tick_bid

                target_dist = pos.initial_tp - pos.entry_price if pos.initial_tp > pos.entry_price else (pos.entry_price * 0.02)
                curr_gain   = current_tick_bid - pos.entry_price

                # 1. Movimiento a Break-Even al alcanzar +1.4R (45% del objetivo TP)
                if curr_gain >= target_dist * 0.45:
                    be_sl = round(pos.entry_price * (1.0 + (self.maker_fee * 2.0)), 4)
                    if be_sl > pos.sl_price:
                        pos.sl_price = be_sl

                    # Asimetría institucional: Toma de ganancia parcial si está habilitado
                    if getattr(pos, "allow_partial_tp", False) and not pos.is_partial_closed:
                        self._take_partial_profit(pos, current_tick_bid, timestamp_ms)

                # 2. Transición a Modo Runner al alcanzar el TP inicial
                if pos.allow_runner and current_tick_bid >= pos.initial_tp:
                    if not pos.runner_mode:
                        pos.runner_mode = True
                        secured_floor = round(pos.entry_price + (target_dist * 0.85), 4)
                        if secured_floor > pos.sl_price:
                            pos.sl_price = secured_floor
                        pos.tp_price = 99999999.0

                # 3. Ratchet dinámico de Stop Loss persiguiendo el pico más alto
                if pos.runner_mode:
                    dynamic_floor = round(pos.highest_price * (1.0 - pos.runner_trail_pct), 4)
                    if dynamic_floor > pos.sl_price:
                        pos.sl_price = dynamic_floor

                # 4. Salidas
                if pos.runner_mode:
                    if current_tick_bid <= pos.sl_price or current_tick_ask <= pos.sl_price:
                        exit_price = min(current_tick_bid, pos.sl_price)
                        self._close_position(pos, exit_price, timestamp_ms, "CLOSED_RUNNER_TRAIL")
                    elif current_tick_bid >= pos.tp_price:
                        self._close_position(pos, pos.tp_price, timestamp_ms, "CLOSED_TP")
                else:
                    if current_tick_bid >= pos.tp_price:
                        self._close_position(pos, pos.tp_price, timestamp_ms, "CLOSED_TP")
                    elif current_tick_ask <= pos.sl_price or current_tick_bid <= pos.sl_price:
                        self._close_position(pos, pos.sl_price, timestamp_ms, "CLOSED_SL")

            else:  # SELL (SHORT)
                if current_tick_ask < pos.lowest_price:
                    pos.lowest_price = current_tick_ask

                target_dist = pos.entry_price - pos.initial_tp if pos.entry_price > pos.initial_tp else (pos.entry_price * 0.02)
                curr_gain   = pos.entry_price - current_tick_ask

                # 1. Movimiento a Break-Even al alcanzar +1.4R (45% del objetivo TP)
                if curr_gain >= target_dist * 0.45:
                    be_sl = round(pos.entry_price * (1.0 - (self.maker_fee * 2.0)), 4)
                    if be_sl < pos.sl_price:
                        pos.sl_price = be_sl

                    # Asimetría institucional: Toma de ganancia parcial si está habilitado
                    if getattr(pos, "allow_partial_tp", False) and not pos.is_partial_closed:
                        self._take_partial_profit(pos, current_tick_ask, timestamp_ms)

                # 2. Transición a Modo Runner al alcanzar el TP inicial
                if pos.allow_runner and current_tick_ask <= pos.initial_tp:
                    if not pos.runner_mode:
                        pos.runner_mode = True
                        secured_floor = round(pos.entry_price - (target_dist * 0.85), 4)
                        if secured_floor < pos.sl_price:
                            pos.sl_price = secured_floor
                        pos.tp_price = 0.0

                # 3. Ratchet dinámico de Stop Loss
                if pos.runner_mode:
                    dynamic_floor = round(pos.lowest_price * (1.0 + pos.runner_trail_pct), 4)
                    if dynamic_floor < pos.sl_price:
                        pos.sl_price = dynamic_floor

                # 4. Salidas
                if pos.runner_mode:
                    if current_tick_ask >= pos.sl_price or current_tick_bid >= pos.sl_price:
                        exit_price = max(current_tick_ask, pos.sl_price)
                        self._close_position(pos, exit_price, timestamp_ms, "CLOSED_RUNNER_TRAIL")
                    elif current_tick_ask <= pos.tp_price:
                        self._close_position(pos, pos.tp_price, timestamp_ms, "CLOSED_TP")
                else:
                    if current_tick_ask <= pos.tp_price:
                        self._close_position(pos, pos.tp_price, timestamp_ms, "CLOSED_TP")
                    elif current_tick_bid >= pos.sl_price or current_tick_ask >= pos.sl_price:
                        self._close_position(pos, pos.sl_price, timestamp_ms, "CLOSED_SL")

    def update_candle_extremes(
        self,
        symbol: str,
        candle_low: float,
        candle_high: float,
        candle_close: float,
        is_bullish: bool,
    ):
        """
        Trailing Vela a Vela (Bar-by-Bar Trailing):
        Al cerrar cada vela de 5m en beneficio, eleva el piso de protección al mínimo de la vela.
        """
        for pos in self.active_positions:
            if pos.symbol != symbol or not pos.runner_mode:
                continue

            if pos.side == "BUY" and is_bullish:
                structural_floor = round(candle_low * 0.999, 4)
                if structural_floor > pos.sl_price:
                    pos.sl_price = structural_floor
            elif pos.side == "SELL" and not is_bullish:
                structural_floor = round(candle_high * 1.001, 4)
                if structural_floor < pos.sl_price:
                    pos.sl_price = structural_floor

    def close_on_reversal(self, symbol: str, current_price: float, timestamp_ms: float, reason: str = "REVERSAL_SIGNAL"):
        """Cierre inmediato si se detecta un patrón de giro institucional en contra."""
        for pos in list(self.active_positions):
            if pos.symbol == symbol and pos.runner_mode:
                self._close_position(pos, current_price, timestamp_ms, "CLOSED_REVERSAL_EXIT")

    def _take_partial_profit(self, pos: HFTPosition, exit_price: float, timestamp_ms: float):
        """
        Locks in 50% of position profit at +1.5R, moves Stop Loss to Break-Even (Risk Zero),
        and allows the remaining 50% to ride with the Trailing Stop.
        """
        if pos.is_partial_closed or pos.quantity <= 0.0001:
            return

        partial_qty = round(pos.quantity * 0.5, 4)
        if partial_qty <= 0.0001:
            return

        if pos.side == "BUY":
            actual_exit = round(exit_price * (1 - self.slippage_pct), 4)
            raw_pnl = (actual_exit - pos.entry_price) * partial_qty
            breakeven_sl = round(pos.entry_price * (1.0 + (self.maker_fee * 2.0)), 4)
            if breakeven_sl > pos.sl_price:
                pos.sl_price = breakeven_sl
        else:
            actual_exit = round(exit_price * (1 + self.slippage_pct), 4)
            raw_pnl = (pos.entry_price - actual_exit) * partial_qty
            breakeven_sl = round(pos.entry_price * (1.0 - (self.maker_fee * 2.0)), 4)
            if breakeven_sl < pos.sl_price:
                pos.sl_price = breakeven_sl

        partial_fee = (pos.entry_price + actual_exit) * partial_qty * self.maker_fee
        partial_net_pnl = raw_pnl - partial_fee

        self.capital += partial_net_pnl
        self.cum_pnl += partial_net_pnl
        if self.capital > self.peak_equity:
            self.peak_equity = self.capital

        pos.quantity = round(pos.quantity - partial_qty, 4)
        pos.is_partial_closed = True
        pos.partial_pnl = partial_net_pnl
        pos.partial_fee = partial_fee

        event_logger.log(
            category="ORDER",
            message=(
                f"🎯 TOMA PARCIAL (+1.5R): 50% cerrado en {pos.symbol} ({pos.side}) @ ${actual_exit:,.2f} | "
                f"Ganancia Asegurada: +${partial_net_pnl:+.2f} USD | SL movido a Break-Even (${pos.sl_price:,.2f}) [RIESGO CERO]"
            ),
            symbol=pos.symbol,
            level="SUCCESS",
        )

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
        remaining_pnl = raw_pnl - total_fee

        self.capital  += remaining_pnl
        self.cum_pnl  += remaining_pnl
        self.total_trades += 1

        if self.capital > self.peak_equity:
            self.peak_equity = self.capital

        # Combined position result accounting for partial profits
        pos.total_fee = round(total_fee + pos.partial_fee, 4)
        pos.pnl       = round(remaining_pnl + pos.partial_pnl, 4)

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
