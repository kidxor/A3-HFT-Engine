import asyncio
import json
import logging
import os
import random
import urllib.request
from collections import deque
from typing import Dict, Any, Optional

import numpy as np
import pandas as pd
import time as _time

from core.websocket_client import HFTWebSocketClient, OrderbookTick
from core.orderbook_engine import OrderbookEngine
from strategies import STRATEGY_REGISTRY, DEFAULT_STRATEGY
from core.hft_execution import HFTExecutionEngine
from core.risk_guard import RiskGuard
from core.event_logger import event_logger

logger = logging.getLogger("HFT_Simulator")

CANDLE_INTERVAL_MS = 900_000    # 15-minute candles: Sniper Intraday Structure — Zero sub-second micro-churn
WARMUP_CANDLES     = 230

# Pre-defined column order — keeps DataFrame construction consistent
_CANDLE_COLS = ["timestamp", "open", "high", "low", "close", "volume"]

# Path to strategy presets configuration
_PRESETS_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "strategy_presets.json")


def _load_preset_params(preset_name: str = None) -> Dict[str, Any]:
    """Load strategy parameters from strategy_presets.json."""
    try:
        with open(_PRESETS_PATH, "r") as f:
            presets = json.load(f)
        if preset_name is None:
            preset_name = presets.get("default_preset", "institutional_trend_pro")
        preset = presets["presets"].get(preset_name, {})
        logger.info(f"📋 Loaded strategy preset '{preset_name}': adx_min={preset.get('adx_min')}, atr_sl_mult={preset.get('atr_sl_mult')}, atr_tp_mult={preset.get('atr_tp_mult')}")
        return preset
    except Exception as e:
        logger.warning(f"⚠️ Could not load preset '{preset_name}': {e}. Using defaults.")
        return {}


def _fetch_real_candles(symbol: str, limit: int = 230) -> list:
    """
    Fetch real historical 15-minute OHLCV candles from Bybit REST API.
    Returns list of candle dicts (chronological order) or empty list on failure.
    Bybit kline format: [startTime, open, high, low, close, volume, turnover]
    """
    bybit_symbol = symbol.replace("-", "")  # SOL-USDT → SOLUSDT
    url = (
        f"https://api.bybit.com/v5/market/kline"
        f"?category=spot&symbol={bybit_symbol}&interval=15&limit={min(limit, 200)}"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "A3-Motor-Trade/2.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        if data.get("retCode") != 0 or not data.get("result", {}).get("list"):
            raise ValueError(f"Bad response: retCode={data.get('retCode')} retMsg={data.get('retMsg')}")
        candles = []
        # Bybit returns newest first — reverse to chronological order
        for c in reversed(data["result"]["list"]):
            # [startTime(ms), open, high, low, close, volume, turnover]
            ts_ms          = float(c[0])
            o, h, l, cl, vol = float(c[1]), float(c[2]), float(c[3]), float(c[4]), float(c[5])
            candles.append({
                "timestamp": ts_ms,
                "open":   o,
                "high":   h,
                "low":    l,
                "close":  cl,
                "volume": vol,
            })
        logger.info(f"✅ Fetched {len(candles)} real historical candles for {symbol} from Bybit")
        return candles
    except Exception as e:
        logger.warning(f"⚠️ Could not fetch real candles for {symbol} from Bybit: {e}. Falling back to synthetic warmup.")
        return []


class SubSecondTickSimulator:
    """Sub-second Tick Simulator with pluggable strategy evaluation."""

    def __init__(
        self,
        symbol: str = "SOL-USDT",
        initial_capital: float = 50.0,
        use_live_market_data: bool = True,
        strategy_name: str = DEFAULT_STRATEGY,
    ):
        self.symbol        = symbol
        self.strategy_name = strategy_name

        self.orderbook_engine = OrderbookEngine(depth_levels=10)

        strategy_class = STRATEGY_REGISTRY.get(
            strategy_name, STRATEGY_REGISTRY[DEFAULT_STRATEGY]
        )
        if strategy_name == "alpha_edge":
            # Load params from strategy_presets.json — do NOT hardcode them here
            preset = _load_preset_params()
            self.strategy = strategy_class(
                ema_fast=preset.get("ema_fast", 20),
                ema_slow=preset.get("ema_slow", 50),
                ema_trend=preset.get("ema_trend", 200),
                adx_min=preset.get("adx_min", 30.0),
                atr_sl_mult=preset.get("atr_sl_mult", 2.0),
                atr_tp_mult=preset.get("atr_tp_mult", 4.0),
                risk_per_trade_pct=preset.get("risk_per_trade_pct", 0.01),
                pullback_tolerance=preset.get("pullback_tolerance", 0.003),
                cooldown_candles=preset.get("cooldown_candles", 6),
                atr_min_mult=preset.get("atr_min_mult", 0.004),
                max_exposure_pct=preset.get("max_exposure_pct", 0.25),
            )
        else:
            self.strategy = strategy_class()

        self.execution_engine = HFTExecutionEngine(
            initial_capital=initial_capital,
            trade_cooldown_seconds=10.0,
            enable_dynamic_runner=True,
            enable_partial_tp=True,
        )
        preset = _load_preset_params()
        self.risk_guard = RiskGuard(
            initial_capital=initial_capital,
            max_daily_drawdown_pct=preset.get("max_daily_drawdown_pct", 0.05),
            max_consecutive_losses=2,   # ← tightened: pause after 2 consecutive losses
            cooldown_seconds=1800.0,    # ← 30 min cooldown tras pérdidas consecutivas
            max_exposure_pct=preset.get("max_exposure_pct", 0.25),
            session_filter_enabled=True,
            weekend_filter_enabled=True,
        )
        self.ws_client = HFTWebSocketClient(
            symbol=symbol, on_tick_callback=self._handle_tick
        )
        self.ws_client.use_live_market_data = use_live_market_data

        self._attach_risk_hooks()

        self.tick_count: int = 0
        self.candle_history: deque = deque(maxlen=500)
        self._current_candle: Optional[Dict[str, Any]] = None
        self._current_candle_start_ms: float = 0.0
        self._warmup_done: bool = False
        self.latest_metrics: Dict[str, Any] = {}
        self.latest_signal: Dict[str, Any] = {
            "signal":        "NEUTRAL",
            "reason":        "Esperando datos...",
            "strategy_name": self.strategy_name,
            "indicators":    {},
        }

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def set_strategy(self, strategy_name: str, **kwargs):
        self.strategy_name = strategy_name
        strategy_class = STRATEGY_REGISTRY.get(
            strategy_name, STRATEGY_REGISTRY[DEFAULT_STRATEGY]
        )
        if strategy_name == "alpha_edge":
            # Base params from preset — caller kwargs override
            preset = _load_preset_params()
            params = {
                "ema_fast":           preset.get("ema_fast", 20),
                "ema_slow":           preset.get("ema_slow", 50),
                "ema_trend":          preset.get("ema_trend", 100),
                "adx_min":            preset.get("adx_min", 20.0),
                "atr_sl_mult":        preset.get("atr_sl_mult", 2.0),
                "atr_tp_mult":        preset.get("atr_tp_mult", 4.0),
                "risk_per_trade_pct": preset.get("risk_per_trade_pct", 0.05),
                "pullback_tolerance": preset.get("pullback_tolerance", 0.008),
                "cooldown_candles":   preset.get("cooldown_candles", 3),
                "atr_min_mult":       preset.get("atr_min_mult", 0.0006),
                "max_exposure_pct":   preset.get("max_exposure_pct", 0.50),
            }
            params.update(kwargs)
            self.strategy = strategy_class(**params)
        else:
            self.strategy = strategy_class(**kwargs)
        logger.info(f"🔄 Strategy updated to '{strategy_name}' ({self.strategy.__class__.__name__}) for {self.symbol}")

    def _attach_risk_hooks(self):
        sim = self

        def on_trade_open(pos):
            trade_cost = pos.entry_price * pos.quantity
            sig_info = getattr(sim, "latest_signal", None)
            allowed, _ = sim.risk_guard.check_trade_allowed(
                sim.execution_engine.capital, trade_cost, signal_info=sig_info
            )
            if allowed:
                sim.risk_guard.daily_trades_count += 1
                is_session, _ = sim.risk_guard.is_institutional_session()
                if not is_session:
                    sim.risk_guard.night_trades_count += 1
            return allowed

        def on_trade_close(pos):
            sim.risk_guard.record_trade_result(
                pos.pnl, current_balance=sim.execution_engine.capital
            )

        self.execution_engine.on_trade_open  = on_trade_open
        self.execution_engine.on_trade_close = on_trade_close

    # ------------------------------------------------------------------
    # Candle management
    # ------------------------------------------------------------------

    def _generate_warmup_candles(self, first_price: float):
        """
        Populate candle history with REAL historical data from Bybit REST API.
        Falls back to synthetic gaussian candles only if the REST call fails.
        """
        real_candles = _fetch_real_candles(self.symbol, limit=WARMUP_CANDLES)

        if real_candles:
            # Use real market data — indicators will be meaningful from the start
            for candle in real_candles:
                self.candle_history.append(candle)
            logger.info(
                f"📊 Warmup complete for {self.symbol}: {len(real_candles)} real candles loaded "
                f"(price range ${real_candles[0]['close']:.2f}–${real_candles[-1]['close']:.2f})"
            )
        else:
            # Fallback: synthetic walk anchored to real first_price
            logger.warning(
                f"⚠️ Using synthetic warmup for {self.symbol} — indicators may be unreliable for first ~{WARMUP_CANDLES} candles"
            )
            now_ms   = self._current_candle_start_ms
            start_ms = now_ms - (WARMUP_CANDLES * CANDLE_INTERVAL_MS)
            curr_p   = first_price
            for j in range(WARMUP_CANDLES):
                t_ms    = start_ms + (j * CANDLE_INTERVAL_MS)
                change  = random.gauss(0.0, curr_p * 0.0008)
                c_close = max(1.0, round(curr_p + change, 4))
                c_open  = curr_p
                curr_p  = c_close
                self.candle_history.append({
                    "timestamp": t_ms,
                    "open":  c_open,
                    "high":  max(c_open, c_close) + abs(change) * 0.5,
                    "low":   min(c_open, c_close) - abs(change) * 0.5,
                    "close": c_close,
                    "volume": round(random.uniform(50, 500), 2),
                })

        self._warmup_done = True

        # Initial strategy evaluation from warmup candles to populate indicators immediately
        if len(self.candle_history) >= 20:
            try:
                arr = np.empty((len(self.candle_history), len(_CANDLE_COLS)), dtype=np.float64)
                for i, row in enumerate(self.candle_history):
                    for j, col in enumerate(_CANDLE_COLS):
                        arr[i, j] = row[col]
                df_warmup = pd.DataFrame(arr, columns=_CANDLE_COLS)
                init_sig = self.strategy.evaluate(
                    df_warmup,
                    current_balance=self.execution_engine.capital,
                    latest_metrics=self.latest_metrics or {},
                )
                if isinstance(init_sig, dict):
                    init_sig["strategy_name"] = self.strategy_name
                    init_sig["signal"] = "NEUTRAL"
                    base_reason = init_sig.get("reason", "Warmup completado")
                    init_sig["reason"] = f"{base_reason} (Próxima evaluación al cierre de vela de 15m)"
                    self.latest_signal = init_sig
            except Exception as _e:
                logger.warning(f"Could not compute initial warmup signal: {_e}")

    def _get_candle_start_ms(self, timestamp_ms: float) -> float:
        return (timestamp_ms // CANDLE_INTERVAL_MS) * CANDLE_INTERVAL_MS

    def _update_candle(self, tick: OrderbookTick) -> bool:
        """Returns True if a new candle started (signals strategy evaluation)."""
        ts_ms       = tick.timestamp_ms
        mid         = tick.mid_price
        candle_start = self._get_candle_start_ms(ts_ms)

        if not self._warmup_done:
            self._current_candle_start_ms = candle_start
            self._generate_warmup_candles(mid)
            self._current_candle = {
                "timestamp": candle_start,
                "open": mid, "high": mid, "low": mid, "close": mid,
                "volume": 0.0,
            }
            return False

        if candle_start != self._current_candle_start_ms:
            if self._current_candle is not None:
                self.candle_history.append(self._current_candle)
            self._current_candle_start_ms = candle_start
            self._current_candle = {
                "timestamp": candle_start,
                "open": mid, "high": mid, "low": mid, "close": mid,
                "volume": 0.0,
            }
            return True

        c = self._current_candle
        c["high"]   = max(c["high"], mid)
        c["low"]    = min(c["low"],  mid)
        c["close"]  = mid
        c["volume"] += round(random.uniform(5.0, 50.0), 2)
        return False

    # ------------------------------------------------------------------
    # Tick handler
    # ------------------------------------------------------------------

    async def _handle_tick(self, tick: OrderbookTick):
        if not self.ws_client.is_running:
            return

        self.tick_count += 1
        self.execution_engine.update_positions(
            tick.best_bid, tick.best_ask, tick.timestamp_ms
        )

        metrics          = self.orderbook_engine.process_tick(tick)
        metrics["vir"]   = metrics.get("volume_imbalance", 1.0)
        metrics["bids"]  = tick.bids
        metrics["asks"]  = tick.asks
        self.latest_metrics = metrics

        candle_closed = self._update_candle(tick)
        if candle_closed and len(self.candle_history) > 0:
            last_c = self.candle_history[-1]
            self.execution_engine.update_candle_extremes(
                symbol=self.symbol,
                candle_low=last_c["low"],
                candle_high=last_c["high"],
                candle_close=last_c["close"],
                is_bullish=(last_c["close"] >= last_c["open"]),
            )

        # SNIPER DISCIPLINE: Evaluamos entradas EXCLUSIVAMENTE al cierre de vela de 15m.
        # Cero ruido intra-vela, cero micro-scalping de milisegundos.
        if not candle_closed:
            return

        # Build DataFrame efficiently using pre-allocated numpy array
        # (avoids Python-loop copy overhead from list of dicts → pd.concat)
        # Evaluamos la serie histórica que incluye la vela que acaba de cerrar (candle_history[-1])
        history_list = list(self.candle_history)
        if not history_list and self._current_candle is not None:
            history_list.append(self._current_candle)

        n = len(history_list)
        arr = np.empty((n, len(_CANDLE_COLS)), dtype=np.float64)
        for i, row in enumerate(history_list):
            for j, col in enumerate(_CANDLE_COLS):
                arr[i, j] = row[col]
        df_candles = pd.DataFrame(arr, columns=_CANDLE_COLS)

        # Shared portfolio dynamic balance support
        effective_balance = self.execution_engine.capital
        if hasattr(self, "portfolio_runner") and self.portfolio_runner:
            effective_balance = getattr(self.portfolio_runner, "total_portfolio_equity", self.execution_engine.capital)

        # Autonomous / Hybrid / Algorithmic mode routing
        from core.autonomous_trader import autonomous_trader
        agent_mode = getattr(autonomous_trader, "mode", "HYBRID_CONSENSUS")

        if agent_mode == "AUTONOMOUS":
            adx_v = float(self.latest_signal.get("indicators", {}).get("adx", 30.0)) if isinstance(self.latest_signal, dict) else 30.0
            atr_v = float(self.latest_signal.get("indicators", {}).get("atr", 1.5)) if isinstance(self.latest_signal, dict) else 1.5
            agent_dec = autonomous_trader.evaluate_opportunity(
                symbol=self.symbol,
                df_candles=df_candles,
                orderbook=self.latest_metrics,
                current_balance=effective_balance,
                adx_val=adx_v,
                atr_val=atr_v,
            )
            act = agent_dec.get("action", "HOLD")
            sig_mapped = "BUY_MAKER" if act == "BUY" else ("SELL_MAKER" if act == "SELL" else "NEUTRAL")
            signal_info = {
                "signal": sig_mapped,
                "reason": agent_dec.get("chain_of_thought", "Evaluación de Agente Autónomo"),
                "suggested_entry": agent_dec.get("entry_price", tick.mid_price),
                "tp_price": agent_dec.get("tp_price", tick.mid_price * 1.02),
                "sl_price": agent_dec.get("sl_price", tick.mid_price * 0.98),
                "risk_pct": agent_dec.get("risk_pct", 0.05),
                "grade": agent_dec.get("grade", "STANDARD_CONVICTION"),
                "strategy_name": "autonomous_agent",
            }
        else:
            signal_info = self.strategy.evaluate(
                df_candles,
                current_balance=effective_balance,
                latest_metrics=self.latest_metrics,
            )
            # Map generic BUY/SELL → maker execution signals
            if signal_info["signal"] == "BUY":
                signal_info["signal"]          = "BUY_MAKER"
                signal_info["suggested_entry"] = tick.best_bid
            elif signal_info["signal"] == "SELL":
                signal_info["signal"]          = "SELL_MAKER"
                signal_info["suggested_entry"] = tick.best_ask
            else:
                signal_info["suggested_entry"] = tick.mid_price

            signal_info["strategy_name"] = self.strategy_name

            # In Smart Combination (Hybrid Consensus), enrich BUY/SELL with Agent conviction & sizing
            if agent_mode == "HYBRID_CONSENSUS" and signal_info["signal"] in ("BUY_MAKER", "SELL_MAKER"):
                adx_v = float(signal_info.get("indicators", {}).get("adx", 30.0))
                atr_v = float(signal_info.get("indicators", {}).get("atr", 1.5))
                agent_dec = autonomous_trader.evaluate_opportunity(
                    symbol=self.symbol,
                    df_candles=df_candles,
                    orderbook=self.latest_metrics,
                    current_balance=effective_balance,
                    adx_val=adx_v,
                    atr_val=atr_v,
                    async_llm=True,
                )
                sig_side = "BUY" if signal_info["signal"] == "BUY_MAKER" else "SELL"
                agent_act = agent_dec.get("action")

                if agent_act in ("BUY", "SELL") and agent_act != sig_side:
                    signal_info["signal"] = "NEUTRAL"
                    signal_info["reason"] = f"🛑 VETO AGENTE: Conflicto Cuantitativo ({sig_side}) vs Agente ({agent_act})"
                    event_logger.log("AGENT", f"Veto en {self.symbol}: Señal {sig_side} descartada por conflicto con análisis del Agente ({agent_act})", symbol=self.symbol, level="WARNING")
                elif agent_act == sig_side:
                    signal_info["risk_pct"] = agent_dec.get("risk_pct", 0.05)
                    signal_info["grade"] = agent_dec.get("grade", "STANDARD_CONVICTION")
                    signal_info["reason"] = f"[{agent_dec.get('grade')}] {agent_dec.get('chain_of_thought', signal_info['reason'])}"
                    if agent_dec.get("grade") == "A_PLUS_MAX_CONVICTION":
                        # Deploy full 50% max exposure allocation for high-conviction big-win setups
                        max_exp = getattr(self.risk_guard, 'max_exposure_pct', 0.50)
                        suggested_p = signal_info.get("suggested_entry", tick.mid_price)
                        if suggested_p > 0:
                            signal_info["position_size"] = round((effective_balance * max_exp * 0.98) / suggested_p, 4)
                elif agent_dec.get("grade") == "NEUTRAL_WAIT":
                    if self.strategy_name == "crypto_futures_hunter":
                        signal_info["grade"] = "STANDARD_CONVICTION"
                        signal_info["risk_pct"] = getattr(self.strategy, "risk_per_trade_pct", 0.05)
                    else:
                        signal_info["signal"] = "NEUTRAL"
                        signal_info["reason"] = f"🛡️ FILTRO AGENTE: Mercado sin confluencias ({agent_dec.get('chain_of_thought', 'NEUTRAL_WAIT')})"
                        event_logger.log("AGENT", f"Filtro en {self.symbol}: Señal {sig_side} descartada por falta de confluencias de mercado", symbol=self.symbol, level="INFO")
                else:
                    signal_info["grade"] = "STANDARD_CONVICTION"
                    signal_info["risk_pct"] = 0.05
                    signal_info["reason"] = f"[STANDARD_CONVICTION] {signal_info['reason']}"

        # OrderbookScalper requires real L2 data — block in demo mode
        if (
            self.strategy_name == "orderbook_scalper"
            and not self.ws_client.use_live_market_data
        ):
            signal_info = {
                "signal":        "NEUTRAL",
                "reason":        "Orderbook L2 solo disponible en modo LIVE (Bybit)",
                "position_size": 0.0,
                "sl_price":      0.0,
                "tp_price":      0.0,
                "indicators":    signal_info.get("indicators", {}),
                "strategy_name": self.strategy_name,
            }

        self.latest_signal = signal_info

        sig = signal_info["signal"]
        if sig in ("BUY_MAKER", "SELL_MAKER"):
            side  = "BUY" if sig == "BUY_MAKER" else "SELL"
            price = signal_info.get("suggested_entry", tick.mid_price)
            tp    = signal_info.get("tp_price", price * 1.01)
            sl    = signal_info.get("sl_price", price * 0.99)

            event_logger.log(
                category="SIGNAL",
                message=(
                    f"Señal {side} [{self.strategy_name}] en {self.symbol}: "
                    f"{signal_info.get('reason', '')}"
                ),
                symbol=self.symbol,
                level="SUCCESS" if side == "BUY" else "WARNING",
            )

            strategy_qty = signal_info.get("position_size", 0)
            if strategy_qty and strategy_qty > 0:
                quantity = strategy_qty
            else:
                # Dynamic Risk Scaling: 5% (Standard) to 8% (A+ Max Conviction) on Live Balance
                assigned_risk_pct = signal_info.get("risk_pct", getattr(self.strategy, "risk_per_trade_pct", 0.05))
                target_risk_usd   = effective_balance * assigned_risk_pct
                stop_distance     = abs(price - sl) if sl > 0 else (price * 0.005)
                stop_distance     = max(stop_distance, price * 0.001)
                quantity          = target_risk_usd / stop_distance

            max_exp = getattr(self.risk_guard, 'max_exposure_pct', 0.50)
            max_qty  = (effective_balance * max_exp) / max(1.0, price)
            quantity = min(quantity, max_qty)
            quantity = max(0.0001, round(quantity, 4))

            pos = self.execution_engine.open_position(
                symbol=self.symbol,
                side=side,
                price=price,
                quantity=quantity,
                tp_price=tp,
                sl_price=sl,
                timestamp_ms=tick.timestamp_ms,
            )

            if pos:
                fmt = lambda v: f"${v:.2f}" if v > 10 else f"${v:.4f}"
                event_logger.log(
                    category="ORDER",
                    message=(
                        f"Orden {side} EJECUTADA en {self.symbol} → "
                        f"Precio: {fmt(price)} | Qty: {quantity} | "
                        f"TP: {fmt(tp)} | SL: {fmt(sl)}"
                    ),
                    symbol=self.symbol,
                    level="SUCCESS",
                )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def get_summary(self) -> Dict[str, Any]:
        stats = self.execution_engine.get_stats()
        stats["processed_ticks"]  = self.tick_count
        stats["active_strategy"]  = self.strategy_name
        if self.execution_engine.closed_positions:
            last_pos = self.execution_engine.closed_positions[-1]
            stats["last_trade"] = {
                "side":        last_pos.side,
                "entry_price": last_pos.entry_price,
                "pnl":         last_pos.pnl,
            }
        return stats
