"""
Dual Bot Tournament Runner (A3 System x2)
Orquestador de Duelo A/B entre:
- Bot 1: Acción de Precio & Velas Japonesas (profile_id='bot_velas')
- Bot 2: Matemáticas & Algoritmos Estadísticos (profile_id='bot_algoritmos')
Ambos reciben el mismo feed de mercado de Bybit en tiempo real, operando con capitales y bases de datos independientes.
"""

import os
import time
import asyncio
import logging
import threading
from typing import Dict, Any, Optional, List
from core.database import DatabaseManager
from core.event_logger import event_logger
from engine.tick_simulator import SubSecondTickSimulator
from core.websocket_client import OrderbookTick, HFTWebSocketClient

logger = logging.getLogger("DualBotTournament")


class DualBotTournamentRunner:
    """
    Manages two competing bots on the exact same live tick stream:
    - Bot 1: Candlestick & Price Action
    - Bot 2: Quantitative & Statistical Math
    """

    def __init__(
        self,
        symbol: str = "SOL-USDT",
        initial_capital_per_bot: float = 200.0,
        use_live_market_data: bool = True,
        base_dir: Optional[str] = None,
    ):
        if base_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.base_dir = base_dir
        self.symbol   = symbol
        self.use_live_market_data = use_live_market_data

        data_dir = os.path.join(base_dir, "data")
        os.makedirs(data_dir, exist_ok=True)

        # 1. Independent Database Managers
        self.db_bot_velas = DatabaseManager(db_path=os.path.join(data_dir, "trades_bot_velas.db"))
        self.db_bot_algoritmos = DatabaseManager(db_path=os.path.join(data_dir, "trades_bot_algoritmos.db"))

        # 2. Bot 1: Velas & Acción de Precio
        self.sim_bot_velas = SubSecondTickSimulator(
            symbol=symbol,
            initial_capital=initial_capital_per_bot,
            use_live_market_data=use_live_market_data,
            strategy_name="candlestick_action",
        )
        self.sim_bot_velas.execution_engine.enable_dynamic_runner = True
        self.sim_bot_velas.execution_engine.enable_partial_tp = True
        self._attach_bot_hooks(self.sim_bot_velas, self.db_bot_velas, "bot_velas", "Bot 1 (Velas)")

        # 3. Bot 2: Matemáticas & Algoritmos Estadísticos
        self.sim_bot_algoritmos = SubSecondTickSimulator(
            symbol=symbol,
            initial_capital=initial_capital_per_bot,
            use_live_market_data=use_live_market_data,
            strategy_name="quant_statistical",
        )
        self.sim_bot_algoritmos.execution_engine.enable_dynamic_runner = True
        self.sim_bot_algoritmos.execution_engine.enable_partial_tp = True
        self._attach_bot_hooks(self.sim_bot_algoritmos, self.db_bot_algoritmos, "bot_algoritmos", "Bot 2 (Algoritmos)")

        # 4. Shared High-Frequency WebSocket Feed
        self.ws_client = HFTWebSocketClient(
            symbol=symbol,
            on_tick_callback=self._handle_shared_tick,
        )
        self.ws_client.use_live_market_data = use_live_market_data

        self.start_time = time.time()
        self.total_ticks_processed = 0

    def _attach_bot_hooks(
        self,
        sim: SubSecondTickSimulator,
        db: DatabaseManager,
        profile_id: str,
        display_name: str,
    ):
        """Attaches isolated trade recording and risk tracking for each bot."""
        def on_trade_open(pos):
            # 1. Macro 4H Regime Gatekeeper (Zero Counter-Trend / Zero Chop Trades)
            try:
                from core.macro_regime import macro_regime_detector, MacroBias
                macro = macro_regime_detector.get_regime(pos.symbol)
                if macro.bias == MacroBias.CHOP_STANDBY:
                    event_logger.log(
                        category="RISK",
                        message=f"🛡️ [{display_name}] Bloqueó {pos.side} en {pos.symbol}: 4H Macro en CHOP_STANDBY (Preservación de Capital)",
                        symbol=pos.symbol,
                        profile_id=profile_id,
                        level="WARNING",
                    )
                    return False
                if (pos.side == "BUY" and macro.bias == MacroBias.BEAR_REGIME) or \
                   (pos.side == "SELL" and macro.bias == MacroBias.BULL_REGIME):
                    event_logger.log(
                        category="RISK",
                        message=f"🛡️ [{display_name}] Bloqueó {pos.side} en {pos.symbol}: Contra-tendencia al Macro 4H ({macro.bias.value})",
                        symbol=pos.symbol,
                        profile_id=profile_id,
                        level="WARNING",
                    )
                    return False
            except Exception as _macro_err:
                logger.debug(f"Macro regime check error: {_macro_err}")

            trade_cost = pos.entry_price * pos.quantity
            sig_info = getattr(sim, "latest_signal", None)
            allowed, reason = sim.risk_guard.check_trade_allowed(
                sim.execution_engine.capital, trade_cost, signal_info=sig_info
            )
            if not allowed:
                event_logger.log(
                    category="RISK",
                    message=f"🛡️ [{display_name}] Bloqueó {pos.side} en {pos.symbol}: {reason}",
                    symbol=pos.symbol,
                    profile_id=profile_id,
                    level="WARNING",
                )
                return False

            sim.risk_guard.daily_trades_count += 1
            is_session, _ = sim.risk_guard.is_institutional_session()
            if not is_session:
                sim.risk_guard.night_trades_count += 1

            event_logger.log(
                category="ORDER",
                message=f"⚔️ [{display_name}] ABRIÓ {pos.side} {pos.quantity:.4f} {pos.symbol} @ ${pos.entry_price:,.2f} | TP: ${pos.tp_price:,.2f} | SL: ${pos.sl_price:,.2f}",
                symbol=pos.symbol,
                profile_id=profile_id,
                level="SUCCESS",
            )
            return True

        def on_trade_close(pos):
            # Registrar resultado en el RiskGuard aislado de cada bot
            sim.risk_guard.record_trade_result(
                pos.pnl, current_balance=sim.execution_engine.capital
            )

            db.save_trade(
                symbol=pos.symbol,
                strategy=sim.strategy_name,
                side=pos.side,
                entry_price=pos.entry_price,
                exit_price=pos.exit_price or 0.0,
                quantity=pos.quantity,
                pnl=pos.pnl,
                exit_reason=getattr(pos, "status", "CLOSED"),
                timestamp_ms=pos.timestamp_ms,
                profile_id=profile_id,
                fee=getattr(pos, "total_fee", 0.0),
            )
            is_win = pos.pnl > 0
            event_logger.log(
                category="ORDER",
                message=f"🏁 [{display_name}] CERRÓ {pos.side} en {pos.symbol} → PnL: ${pos.pnl:+.4f} ({getattr(pos, 'status', '')})",
                symbol=pos.symbol,
                profile_id=profile_id,
                level="SUCCESS" if is_win else "ERROR",
            )

            # Active AI Agent Reflection & Supervision
            try:
                from core.autonomous_trader import autonomous_trader
                autonomous_trader.record_post_trade_reflection(
                    trade_id=getattr(pos, "id", 0),
                    symbol=f"{pos.symbol} [{display_name}]",
                    pnl=pos.pnl,
                    exit_reason=getattr(pos, "status", "CLOSED"),
                    entry_price=pos.entry_price,
                    exit_price=pos.exit_price or 0.0,
                )
            except Exception as _e:
                logger.debug(f"AI Agent tournament reflection error: {_e}")

        sim.execution_engine.on_trade_open = on_trade_open
        sim.execution_engine.on_trade_close = on_trade_close

    async def _handle_shared_tick(self, tick: OrderbookTick):
        """Dispatches each incoming tick to both bots concurrently."""
        self.total_ticks_processed += 1
        results = await asyncio.gather(
            self.sim_bot_velas._handle_tick(tick),
            self.sim_bot_algoritmos._handle_tick(tick),
            return_exceptions=True,
        )
        for i, res in enumerate(results):
            if isinstance(res, Exception):
                bot_name = "Bot Velas" if i == 0 else "Bot Algoritmos"
                logger.error(f"❌ Error en {bot_name} _handle_tick: {res}", exc_info=res)

    def start(self):
        """Starts the tournament live feed in a background daemon thread."""
        self._thread = threading.Thread(target=self._run_async_stream, daemon=True)
        self._thread.start()
        logger.info(f"🏆 Torneo A/B Iniciado en {self.symbol}: Bot Velas vs Bot Algoritmos")

    def _run_async_stream(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def _stream():
            await self.ws_client.start_live_stream(interval_seconds=0.3)

        loop.run_until_complete(_stream())

    def stop(self):
        """Stops the tournament feed."""
        self.ws_client.stop()
        logger.info("🛑 Torneo A/B detenido")

    def get_leaderboard(self) -> Dict[str, Any]:
        """Returns side-by-side performance comparison."""
        stats_velas = self.sim_bot_velas.execution_engine.get_stats()
        stats_algoritmos = self.sim_bot_algoritmos.execution_engine.get_stats()

        # Database persisted history counts
        db_velas_trades = self.db_bot_velas.get_recent_trades(limit=10)
        db_algoritmos_trades = self.db_bot_algoritmos.get_recent_trades(limit=10)

        # Leader determination
        pnl_velas = stats_velas["cum_pnl"]
        pnl_algoritmos = stats_algoritmos["cum_pnl"]

        if pnl_velas > pnl_algoritmos:
            leader = "Bot 1 (Velas & Price Action)"
            leader_diff = round(pnl_velas - pnl_algoritmos, 4)
        elif pnl_algoritmos > pnl_velas:
            leader = "Bot 2 (Matemáticas & Algoritmos)"
            leader_diff = round(pnl_algoritmos - pnl_velas, 4)
        else:
            leader = "Empate Técnico"
            leader_diff = 0.0

        uptime_secs = int(time.time() - self.start_time)

        macro_dict = {}
        try:
            from core.macro_regime import macro_regime_detector
            macro_dict = macro_regime_detector.get_regime(self.symbol).to_dict()
        except Exception as _m_err:
            logger.debug(f"Macro regime check error in get_leaderboard: {_m_err}")

        return {
            "tournament_status": "ACTIVE" if self.ws_client.is_running else "PAUSED",
            "symbol": self.symbol,
            "uptime_seconds": uptime_secs,
            "total_ticks": self.total_ticks_processed,
            "current_leader": leader,
            "leader_advantage_usd": leader_diff,
            "macro_regime": macro_dict,
            "bot_velas": {
                "name": "Bot 1 (Velas & Price Action)",
                "strategy": "candlestick_action",
                "profile_id": "bot_velas",
                "stats": stats_velas,
                "latest_signal": self.sim_bot_velas.latest_signal,
                "open_positions": [
                    {
                        "position_id": p.position_id,
                        "side": p.side,
                        "entry_price": p.entry_price,
                        "tp_price": p.tp_price,
                        "sl_price": p.sl_price,
                        "quantity": p.quantity,
                        "runner_mode": getattr(p, "runner_mode", False),
                    }
                    for p in self.sim_bot_velas.execution_engine.active_positions
                ],
                "recent_trades": db_velas_trades,
            },
            "bot_algoritmos": {
                "name": "Bot 2 (Matemáticas & Algoritmos)",
                "strategy": "quant_statistical",
                "profile_id": "bot_algoritmos",
                "stats": stats_algoritmos,
                "latest_signal": self.sim_bot_algoritmos.latest_signal,
                "open_positions": [
                    {
                        "position_id": p.position_id,
                        "side": p.side,
                        "entry_price": p.entry_price,
                        "tp_price": p.tp_price,
                        "sl_price": p.sl_price,
                        "quantity": p.quantity,
                        "runner_mode": getattr(p, "runner_mode", False),
                    }
                    for p in self.sim_bot_algoritmos.execution_engine.active_positions
                ],
                "recent_trades": db_algoritmos_trades,
            },
        }
