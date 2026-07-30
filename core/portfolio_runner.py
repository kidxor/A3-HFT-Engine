import asyncio
import json
import logging
import os
import time
from typing import Dict, Any, List, Optional
import numpy as np

from engine.tick_simulator import SubSecondTickSimulator
from core.risk_guard import RiskGuard
from core.database import DatabaseManager
from core.event_logger import event_logger

logger = logging.getLogger("PortfolioRunner")


class MultiAssetPortfolioRunner:
    """
    Multi-Asset Portfolio Runner — runs AlphaEdge on multiple symbols simultaneously.
    """
    def __init__(
        self,
        symbols: List[str] = None,
        initial_capital: float = 1000.0,
        strategy_name: str = "alpha_edge",
        profile_id: str = "default",
    ):
        if symbols is None:
            symbols = ["SOL-USDT", "BTC-USDT", "ETH-USDT"]

        self.symbols = symbols
        self.initial_capital = initial_capital
        self.strategy_name = strategy_name
        self.profile_id = profile_id
        self.preset_key = "alpha_edge_1000"
        self.preset_info: Dict[str, Any] = {}

        self.risk_guard = RiskGuard(
            initial_capital=initial_capital,
            max_daily_drawdown_pct=0.05,
            max_consecutive_losses=5,
            max_exposure_pct=0.25,
        )
        self.db_manager = DatabaseManager()
        # DB query cache — avoid hitting SQLite on every SSE tick (5/sec)
        self._db_cache_ttl: float = 30.0   # seconds between DB reads
        self._db_cache_ts: float = 0.0
        self._db_cache: Dict[str, Any] = {"total_trades":0,"win_trades":0,"win_rate_pct":0.0,"total_pnl":0.0,"avg_pnl":0.0}
        self._recent_trades_cache: list = []
        self._recent_trades_ts: float = 0.0

        self.simulators: Dict[str, SubSecondTickSimulator] = {}
        alloc_per_symbol = initial_capital / len(symbols)

        for sym in self.symbols:
            sim = SubSecondTickSimulator(
                symbol=sym,
                initial_capital=alloc_per_symbol,
                strategy_name=strategy_name,
            )
            self._attach_hooks(sim)
            self.simulators[sym] = sim

        logger.info(f"🚀 Portfolio Runner [{profile_id}] initialized: {symbols}")

    def _attach_hooks(self, sim: SubSecondTickSimulator):
        runner = self

        def on_trade_open(pos):
            trade_cost = pos.entry_price * pos.quantity
            allowed, reason = runner.risk_guard.check_trade_allowed(
                sim.execution_engine.capital, trade_cost
            )
            if not allowed:
                logger.warning(
                    f"🛡️ Risk Guard [{runner.profile_id}] rejected {pos.symbol} {pos.side}: {reason}"
                )
                event_logger.log(
                    category="RISK",
                    message=f"Risk Guard RECHAZÓ {pos.side} en {pos.symbol}: {reason}",
                    symbol=pos.symbol,
                    profile_id=runner.profile_id,
                    level="WARNING",
                )
                return False
            event_logger.log(
                category="RISK",
                message=f"Risk Guard APROBÓ {pos.side} en {pos.symbol} (${sim.execution_engine.capital:.2f})",
                symbol=pos.symbol,
                profile_id=runner.profile_id,
                level="INFO",
            )
            return True

        def on_trade_close(pos):
            runner.risk_guard.record_trade_result(
                pos.pnl, current_balance=sim.execution_engine.capital
            )
            runner.db_manager.save_trade(
                symbol=pos.symbol,
                strategy=sim.strategy_name,
                side=pos.side,
                entry_price=pos.entry_price,
                exit_price=pos.exit_price or 0.0,
                quantity=pos.quantity,
                pnl=pos.pnl,
                exit_reason=getattr(pos, "status", "CLOSED"),
                timestamp_ms=pos.timestamp_ms,
                profile_id=runner.profile_id,
                fee=getattr(pos, "total_fee", 0.0),
            )
            is_win = pos.pnl > 0
            event_logger.log(
                category="ORDER",
                message=f"{pos.side} CERRADA en {pos.symbol} -> PnL: ${pos.pnl:+.4f} ({getattr(pos, 'status', '')})",
                symbol=pos.symbol,
                profile_id=runner.profile_id,
                level="SUCCESS" if is_win else "ERROR",
            )

        sim.execution_engine.on_trade_open = on_trade_open
        sim.execution_engine.on_trade_close = on_trade_close

    def set_strategy(self, strategy_name: str):
        self.strategy_name = strategy_name
        for sim in self.simulators.values():
            sim.set_strategy(strategy_name)

    def load_preset(self, preset_key: str, custom_capital: Optional[float] = None, custom_symbols: Optional[List[str]] = None):
        presets_file = os.path.join(os.path.dirname(__file__), "..", "config", "strategy_presets.json")
        if not os.path.exists(presets_file):
            return

        with open(presets_file, "r") as f:
            data = json.load(f)

        presets = data.get("presets", {})
        if preset_key not in presets:
            return

        preset = presets[preset_key]
        symbols = custom_symbols or preset.get("symbols", ["SOL-USDT"])
        capital = custom_capital if (custom_capital and custom_capital > 0) else preset.get("initial_capital", 1000.0)
        max_dd = preset.get("max_daily_drawdown_pct", 0.05)

        self.preset_key = preset_key
        self.preset_info = {
            "key": preset_key,
            "name": preset.get("name", preset_key),
            "description": preset.get("description", ""),
            "badge": preset.get("badge", "ALPHAEDGE"),
            "initial_capital": capital,
            "symbols": symbols,
        }
        self.initial_capital = capital
        self.symbols = symbols

        existing_syms = set(self.simulators.keys())
        new_syms = set(symbols)
        alloc_per_symbol = capital / len(symbols)

        for sym in existing_syms - new_syms:
            self.simulators[sym].ws_client.stop()
            del self.simulators[sym]

        for sym in new_syms:
            if sym not in self.simulators:
                sim = SubSecondTickSimulator(symbol=sym, initial_capital=alloc_per_symbol, strategy_name=self.strategy_name)
                self._attach_hooks(sim)
                self.simulators[sym] = sim
            else:
                self.simulators[sym].execution_engine.capital = alloc_per_symbol

        self.risk_guard.max_daily_drawdown_pct = max_dd
        self.risk_guard.peak_equity = capital
        self.risk_guard.starting_daily_capital = capital
        self.risk_guard.initial_capital = capital

        logger.info(f"📊 Preset [{self.profile_id}] -> '{preset_key}' (${capital:,.2f}, {symbols})")

    def set_mode(self, use_live: bool):
        for sim in self.simulators.values():
            sim.ws_client.use_live_market_data = use_live

    def set_engine_state(self, running: bool):
        for sim in self.simulators.values():
            sim.ws_client.is_running = running

    def reset_portfolio(self):
        alloc = self.initial_capital / len(self.symbols)
        for sim in self.simulators.values():
            sim.execution_engine.capital = alloc
            sim.execution_engine.cum_pnl = 0.0
            sim.execution_engine.total_trades = 0
            sim.execution_engine.wins = 0
            sim.execution_engine.losses = 0
            sim.execution_engine.peak_equity = alloc
            sim.execution_engine.active_positions.clear()
            sim.execution_engine.closed_positions.clear()
            sim.tick_count = 0
        self.risk_guard.reset_circuit_breaker(self.initial_capital)

    def get_portfolio_summary(self) -> Dict[str, Any]:
        sims = list(self.simulators.values())
        total_capital = sum(s.execution_engine.capital for s in sims)
        total_pnl     = sum(s.execution_engine.cum_pnl for s in sims)
        total_trades  = sum(s.execution_engine.total_trades for s in sims)
        total_wins    = sum(s.execution_engine.wins for s in sims)
        win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0.0

        # Aggregate closed PnLs using numpy for fast vectorized stats
        closed_pnls = np.concatenate([
            np.fromiter((p.pnl for p in s.execution_engine.closed_positions), dtype=np.float64)
            for s in sims
        ]) if sims else np.array([], dtype=np.float64)

        if closed_pnls.size > 0:
            wins_arr   = closed_pnls[closed_pnls > 0]
            losses_arr = closed_pnls[closed_pnls < 0]
            gross_wins   = wins_arr.sum()
            gross_losses = abs(losses_arr.sum())
            profit_factor = round(gross_wins / gross_losses, 2) if gross_losses > 0 else (float(gross_wins) if gross_wins > 0 else 0.0)
        else:
            profit_factor = 0.0

        sharpe_ratio = 0.0
        if closed_pnls.size >= 5:
            prev = closed_pnls[:-1]
            returns = np.diff(closed_pnls) / (np.abs(prev) + 1e-9)
            std = returns.std()
            if std > 0:
                sharpe_ratio = round((returns.mean() / std) * np.sqrt(252), 2)

        per_symbol_metrics = {}
        for sym, sim in self.simulators.items():
            metrics  = sim.latest_metrics or {}
            sim_stats = sim.execution_engine.get_stats()
            per_symbol_metrics[sym] = {
                "mid_price":     metrics.get("mid_price", 0.0),
                "capital":       round(sim.execution_engine.capital, 2),
                "pnl":           round(sim.execution_engine.cum_pnl, 4),
                "trades":        sim.execution_engine.total_trades,
                "profit_factor": sim_stats.get("profit_factor", 0.0),
                "sharpe_ratio":  sim_stats.get("sharpe_ratio", 0.0),
                "latest_signal": sim.latest_signal,
            }

        # TTL-cached DB queries — avoid 5 SQLite reads/sec during streaming
        now = time.time()
        if now - self._db_cache_ts >= self._db_cache_ttl:
            self._db_cache         = self.db_manager.get_total_summary()
            self._recent_trades_cache = self.db_manager.get_recent_trades(limit=10)
            self._db_cache_ts      = now

        return {
            "profile_id":       self.profile_id,
            "preset_key":       self.preset_key,
            "preset_info":      self.preset_info,
            "symbols":          self.symbols,
            "total_capital":    round(total_capital, 2),
            "total_pnl":        round(total_pnl, 4),
            "total_trades":     total_trades,
            "win_rate_percent": round(win_rate, 1),
            "profit_factor":    profit_factor,
            "sharpe_ratio":     sharpe_ratio,
            "active_strategy":  self.strategy_name,
            "risk_guard":       self.risk_guard.get_status(),
            "per_symbol":       per_symbol_metrics,
            "all_time_db":      self._db_cache,
            "recent_db_trades": self._recent_trades_cache,
        }


class MultiProfileEngineManager:
    """Single-profile engine manager (simplified)."""
    def __init__(self):
        self.active_mode = "single"
        self.active_preset_key = "alpha_edge_1000"
        self.use_live_market_data = True
        self.is_running = True

        self.portfolio_peak_equity = 0.0
        self.portfolio_max_drawdown_pct = 0.08
        self.portfolio_circuit_breaker = False
        self.portfolio_circuit_breaker_reason = ""

        self.single_runner = MultiAssetPortfolioRunner(profile_id="default")
        self.single_runner.load_preset(self.active_preset_key)

    def select_preset_or_mode(self, preset_key: str, custom_capital: Optional[float] = None, custom_symbols: Optional[List[str]] = None):
        self.active_preset_key = preset_key
        self.single_runner.load_preset(preset_key, custom_capital=custom_capital, custom_symbols=custom_symbols)
        self.single_runner.set_engine_state(self.is_running)
        self.single_runner.set_mode(self.use_live_market_data)

    def set_engine_state(self, running: bool):
        self.is_running = running
        self.single_runner.set_engine_state(running)
        if running:
            total_cap = self.get_total_portfolio_capital()
            if total_cap > self.portfolio_peak_equity:
                self.portfolio_peak_equity = total_cap

    def set_mode(self, use_live: bool):
        self.use_live_market_data = use_live
        self.single_runner.set_mode(use_live)

    def reset_engine(self):
        self.single_runner.reset_portfolio()
        self.portfolio_peak_equity = self.single_runner.initial_capital
        self.portfolio_circuit_breaker = False
        self.portfolio_circuit_breaker_reason = ""

    def get_total_portfolio_capital(self) -> float:
        return sum(sim.execution_engine.capital for sim in self.single_runner.simulators.values())

    def get_combined_summary(self) -> Dict[str, Any]:
        summary = self.single_runner.get_portfolio_summary()
        summary["active_mode"] = "single"
        summary["is_live"] = self.use_live_market_data

        total_cap = summary["total_capital"]
        if total_cap > self.portfolio_peak_equity:
            self.portfolio_peak_equity = total_cap
        dd_pct = ((self.portfolio_peak_equity - total_cap) / self.portfolio_peak_equity * 100) if self.portfolio_peak_equity > 0 else 0.0

        if dd_pct >= self.portfolio_max_drawdown_pct * 100:
            self.portfolio_circuit_breaker = True
            self.portfolio_circuit_breaker_reason = f"Portfolio drawdown {dd_pct:.1f}%"
            self.set_engine_state(False)

        summary["risk_guard"]["portfolio_peak_equity"] = round(self.portfolio_peak_equity, 2)
        summary["risk_guard"]["portfolio_drawdown_pct"] = round(dd_pct, 2)
        return summary

    def configure_custom_bots(self, bot_configs: List[Dict[str, Any]]):
        if not bot_configs:
            return
        total_capital = sum(b.get("capital", 1000) for b in bot_configs)
        self.single_runner.reset_portfolio()
        self.single_runner.initial_capital = total_capital
        self.single_runner.symbols = [b.get("symbol", "SOL-USDT") for b in bot_configs]
        self.single_runner.strategy_name = bot_configs[0].get("strategy", "alpha_edge")

        new_simulators = {}
        alloc_per_bot = total_capital / len(bot_configs)
        for i, cfg in enumerate(bot_configs):
            sym = cfg.get("symbol", "SOL-USDT")
            strat = cfg.get("strategy", "alpha_edge")
            capital = cfg.get("capital", alloc_per_bot)
            if sym in self.single_runner.simulators:
                sim = self.single_runner.simulators[sym]
                sim.execution_engine.capital = capital
                sim.set_strategy(strat)
            else:
                sim = SubSecondTickSimulator(
                    symbol=sym,
                    initial_capital=capital,
                    strategy_name=strat,
                )
                self.single_runner._attach_hooks(sim)
            new_simulators[sym] = sim
        self.single_runner.simulators = new_simulators
        self.single_runner.set_mode(self.use_live_market_data)
        self.single_runner.set_engine_state(self.is_running)
        logger.info(f"🔧 Configured {len(bot_configs)} custom bot(s): {[(b.get('symbol'), b.get('strategy')) for b in bot_configs]}")
