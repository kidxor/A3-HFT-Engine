import asyncio
import logging
import random
from collections import deque
import pandas as pd
import time as _time
from typing import Dict, Any, Optional

from core.websocket_client import HFTWebSocketClient, OrderbookTick
from core.orderbook_engine import OrderbookEngine
from strategies import STRATEGY_REGISTRY, DEFAULT_STRATEGY
from core.hft_execution import HFTExecutionEngine
from core.risk_guard import RiskGuard
from core.event_logger import event_logger

logger = logging.getLogger("HFT_Simulator")

CANDLE_INTERVAL_MS = 60_000
WARMUP_CANDLES = 215


class SubSecondTickSimulator:
    """Sub-second Tick Simulator with AlphaEdge trend-pullback strategy."""
    def __init__(
        self,
        symbol: str = "SOL-USDT",
        initial_capital: float = 50.0,
        use_live_market_data: bool = True,
        strategy_name: str = "alpha_edge",
    ):
        self.symbol = symbol
        self.strategy_name = strategy_name
        self.orderbook_engine = OrderbookEngine(depth_levels=10)

        strategy_class = STRATEGY_REGISTRY.get(strategy_name, STRATEGY_REGISTRY[DEFAULT_STRATEGY])
        if strategy_name == "alpha_edge":
            self.strategy = strategy_class(
                ema_fast=20, ema_slow=50, ema_trend=200,
                adx_min=20.0, atr_sl_mult=1.5, atr_tp_mult=2.5,
                risk_per_trade_pct=0.01, pullback_tolerance=0.003,
                cooldown_candles=3, atr_min_mult=0.002,
            )
        else:
            self.strategy = strategy_class()

        self.execution_engine = HFTExecutionEngine(initial_capital=initial_capital)
        self.risk_guard = RiskGuard(
            initial_capital=initial_capital,
            max_daily_drawdown_pct=0.05,
            max_consecutive_losses=3,
            max_exposure_pct=0.25,
        )
        self.ws_client = HFTWebSocketClient(symbol=symbol, on_tick_callback=self._handle_tick)
        self.ws_client.use_live_market_data = use_live_market_data

        self._attach_risk_hooks()

        self.tick_count = 0
        self.candle_history: deque = deque(maxlen=500)
        self._current_candle: Optional[Dict[str, Any]] = None
        self._current_candle_start_ms: float = 0.0
        self._warmup_done = False
        self.latest_metrics: Dict[str, Any] = {}
        self.latest_signal: Dict[str, Any] = {
            "signal": "NEUTRAL",
            "reason": "Esperando datos...",
            "strategy_name": self.strategy_name,
            "indicators": {},
        }

    def set_strategy(self, strategy_name: str):
        self.strategy_name = strategy_name

    def _attach_risk_hooks(self):
        sim = self

        def on_trade_open(pos):
            trade_cost = pos.entry_price * pos.quantity
            allowed, reason = sim.risk_guard.check_trade_allowed(sim.execution_engine.capital, trade_cost)
            if not allowed:
                return False
            return True

        def on_trade_close(pos):
            sim.risk_guard.record_trade_result(pos.pnl, current_balance=sim.execution_engine.capital)

        self.execution_engine.on_trade_open = on_trade_open
        self.execution_engine.on_trade_close = on_trade_close

    def _generate_warmup_candles(self, first_price: float):
        now_ms = self._current_candle_start_ms
        start_ms = now_ms - (WARMUP_CANDLES * CANDLE_INTERVAL_MS)
        curr_p = first_price
        for j in range(WARMUP_CANDLES):
            t_ms = start_ms + (j * CANDLE_INTERVAL_MS)
            change = random.gauss(0.0, curr_p * 0.0008)
            c_close = max(1.0, round(curr_p + change, 4))
            c_open = curr_p
            curr_p = c_close
            self.candle_history.append({
                'timestamp': t_ms,
                'datetime': pd.to_datetime(t_ms, unit='ms'),
                'open': c_open,
                'high': max(c_open, c_close) + abs(change) * 0.5,
                'low': min(c_open, c_close) - abs(change) * 0.5,
                'close': c_close,
                'volume': round(random.uniform(50, 500), 2),
            })
        self._warmup_done = True

    def _get_candle_start_ms(self, timestamp_ms: float) -> float:
        return (timestamp_ms // CANDLE_INTERVAL_MS) * CANDLE_INTERVAL_MS

    def _update_candle(self, tick: OrderbookTick):
        ts_ms = tick.timestamp_ms
        mid = tick.mid_price
        candle_start = self._get_candle_start_ms(ts_ms)

        if not self._warmup_done:
            self._current_candle_start_ms = candle_start
            self._generate_warmup_candles(mid)
            self._current_candle = {
                'timestamp': candle_start,
                'datetime': pd.to_datetime(candle_start, unit='ms'),
                'open': mid, 'high': mid, 'low': mid, 'close': mid,
                'volume': 0.0,
            }
            return False

        if candle_start != self._current_candle_start_ms:
            if self._current_candle is not None:
                self.candle_history.append(self._current_candle)
            self._current_candle_start_ms = candle_start
            self._current_candle = {
                'timestamp': candle_start,
                'datetime': pd.to_datetime(candle_start, unit='ms'),
                'open': mid, 'high': mid, 'low': mid, 'close': mid,
                'volume': 0.0,
            }
            return True

        c = self._current_candle
        c['high'] = max(c['high'], mid)
        c['low'] = min(c['low'], mid)
        c['close'] = mid
        c['volume'] += round(random.uniform(5.0, 50.0), 2)
        return False

    async def _handle_tick(self, tick: OrderbookTick):
        if not self.ws_client.is_running:
            return

        self.tick_count += 1

        self.execution_engine.update_positions(tick.best_bid, tick.best_ask, tick.timestamp_ms)

        metrics = self.orderbook_engine.process_tick(tick)
        metrics["vir"] = metrics.get("volume_imbalance", 1.0)
        metrics["bids"] = tick.bids
        metrics["asks"] = tick.asks
        self.latest_metrics = metrics

        candle_closed = self._update_candle(tick)

        # AlphaEdge evaluates on candle close only
        if not candle_closed:
            return

        df_candles = pd.DataFrame(self.candle_history)
        if self._current_candle is not None:
            df_candles = pd.concat([df_candles, pd.DataFrame([self._current_candle])], ignore_index=True)

        signal_info = self.strategy.evaluate(
            df_candles,
            current_balance=self.execution_engine.capital,
            latest_metrics=self.latest_metrics,
        )

        # Map BUY/SELL to execution format
        if signal_info["signal"] == "BUY":
            signal_info["signal"] = "BUY_MAKER"
            signal_info["suggested_entry"] = tick.best_bid
        elif signal_info["signal"] == "SELL":
            signal_info["signal"] = "SELL_MAKER"
            signal_info["suggested_entry"] = tick.best_ask
        else:
            signal_info["suggested_entry"] = tick.mid_price

        signal_info["strategy_name"] = self.strategy_name

        # Block OrderbookScalper in demo mode (no real orderbook data)
        if self.strategy_name == "orderbook_scalper" and not self.ws_client.use_live_market_data:
            signal_info = {
                "signal": "NEUTRAL",
                "reason": "Orderbook L2 solo disponible en modo LIVE (KuCoin)",
                "position_size": 0.0,
                "sl_price": 0.0,
                "tp_price": 0.0,
                "indicators": signal_info.get("indicators", {}),
                "strategy_name": self.strategy_name,
            }

        self.latest_signal = signal_info

        sig = signal_info["signal"]
        if sig in ["BUY_MAKER", "SELL_MAKER"]:
            side = "BUY" if sig == "BUY_MAKER" else "SELL"
            price = signal_info.get("suggested_entry", tick.mid_price)
            tp_price = signal_info.get("tp_price", price * 1.01)
            sl_price = signal_info.get("sl_price", price * 0.99)

            event_logger.log(
                category="SIGNAL",
                message=f"Señal {side} [{self.strategy_name}] en {self.symbol}: {signal_info.get('reason', '')}",
                symbol=self.symbol,
                level="SUCCESS" if side == "BUY" else "WARNING",
            )

            strategy_pos_size = signal_info.get("position_size", 0)
            if strategy_pos_size and strategy_pos_size > 0:
                quantity = strategy_pos_size
            else:
                target_risk_usd = self.execution_engine.capital * 0.01
                stop_distance = abs(price - sl_price) if sl_price > 0 else (price * 0.005)
                stop_distance = max(stop_distance, price * 0.001)
                quantity = target_risk_usd / stop_distance

            max_allowed_qty = (self.execution_engine.capital * 0.20) / max(1.0, price)
            quantity = min(quantity, max_allowed_qty)
            quantity = max(0.0001, round(quantity, 4))

            pos = self.execution_engine.open_position(
                symbol=self.symbol,
                side=side,
                price=price,
                quantity=quantity,
                tp_price=tp_price,
                sl_price=sl_price,
                timestamp_ms=tick.timestamp_ms,
            )

            if pos:
                p_fmt = f"${price:.2f}" if price > 10 else f"${price:.4f}"
                tp_fmt = f"${tp_price:.2f}" if tp_price > 10 else f"${tp_price:.4f}"
                sl_fmt = f"${sl_price:.2f}" if sl_price > 10 else f"${sl_price:.4f}"
                event_logger.log(
                    category="ORDER",
                    message=f"Orden {side} EJECUTADA en {self.symbol} -> Precio: {p_fmt} | Qty: {quantity} | TP: {tp_fmt} | SL: {sl_fmt}",
                    symbol=self.symbol,
                    level="SUCCESS",
                )

    def get_summary(self) -> Dict[str, Any]:
        stats = self.execution_engine.get_stats()
        stats["processed_ticks"] = self.tick_count
        stats["active_strategy"] = self.strategy_name
        if self.execution_engine.closed_positions:
            last_pos = self.execution_engine.closed_positions[-1]
            stats["last_trade"] = {
                "side": last_pos.side,
                "entry_price": last_pos.entry_price,
                "pnl": last_pos.pnl,
            }
        return stats
