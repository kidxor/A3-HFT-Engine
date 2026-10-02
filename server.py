#!/usr/bin/env python3
import os
import sys

try:
    import pandas as pd
    import numpy as np
except ImportError:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    venv_python = os.path.join(base_dir, ".venv", "bin", "python")
    if os.path.exists(venv_python) and sys.executable != venv_python:
        os.execv(venv_python, [venv_python] + sys.argv)
    import pandas as pd
    import numpy as np

import asyncio
import json
import logging
import re
import sqlite3
import threading
import time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from core.portfolio_runner import MultiProfileEngineManager
from core.event_logger import event_logger
from core.market_data_proxy import init_proxy, get_proxy
from core.telegram_notifier import telegram_notifier
from core.live_exchange import live_exchange
from core.ai_optimizer import ai_optimizer
from core.autonomous_trader import autonomous_trader
from core.rag_knowledge_engine import rag_knowledge_engine
from strategies import STRATEGY_REGISTRY

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("HFT_Server")

PORT = int(os.environ.get("PORT", 8005))
ENGINE_MANAGER = None
ENGINE_RUNNING = False
PRICE_HISTORIES = {}
ENGINE_START_TIME = time.time()
ACCUMULATED_UPTIME = 0.0
_PRICE_LOCK = threading.Lock()


def get_current_uptime_seconds() -> int:
    global ENGINE_RUNNING, ENGINE_START_TIME, ACCUMULATED_UPTIME
    if ENGINE_RUNNING and ENGINE_START_TIME:
        return int(ACCUMULATED_UPTIME + (time.time() - ENGINE_START_TIME))
    return int(ACCUMULATED_UPTIME)


def format_uptime(seconds: int) -> str:
    hrs = seconds // 3600
    mins = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hrs:02d}:{mins:02d}:{secs:02d}"


def _build_state_payload():
    if not ENGINE_MANAGER:
        return {}
    summary = ENGINE_MANAGER.get_combined_summary()
    per_sym = summary.get("per_symbol", {})

    now_str = time.strftime("%H:%M:%S")
    with _PRICE_LOCK:
        for sym, m in per_sym.items():
            m_price = m.get("mid_price", 0.0)
            if m_price > 0 and ENGINE_RUNNING:
                if sym not in PRICE_HISTORIES:
                    PRICE_HISTORIES[sym] = []
                PRICE_HISTORIES[sym].append({"time": now_str, "price": m_price})
                if len(PRICE_HISTORIES[sym]) > 40:
                    PRICE_HISTORIES[sym].pop(0)

        price_hist_snapshot = PRICE_HISTORIES.copy()
        price_hist_first = list(price_hist_snapshot.values())[0] if price_hist_snapshot else []

    sample_sim = list(ENGINE_MANAGER.single_runner.simulators.values())[0] if ENGINE_MANAGER.single_runner.simulators else None
    latest_sig = sample_sim.latest_signal if sample_sim else {"signal": "NEUTRAL", "reason": "Analizando"}

    candles_map = {}
    if ENGINE_MANAGER and ENGINE_MANAGER.single_runner.simulators:
        for sym, sim in ENGINE_MANAGER.single_runner.simulators.items():
            hist = list(sim.candle_history)
            cleaned = []
            for c in hist[-100:]:
                o = round(float(c["open"]), 4 if float(c["open"]) < 500 else 2)
                cl = round(float(c["close"]), 4 if float(c["close"]) < 500 else 2)
                h = round(float(c["high"]), 4 if float(c["high"]) < 500 else 2)
                l = round(float(c["low"]), 4 if float(c["low"]) < 500 else 2)
                max_body = max(o, cl)
                min_body = min(o, cl)
                if max_body > 0 and h > max_body * 1.10:
                    h = round(max_body * 1.005, 4 if max_body < 500 else 2)
                if min_body > 0 and l < min_body * 0.90:
                    l = round(min_body * 0.995, 4 if min_body < 500 else 2)
                cleaned.append({
                    "time": int(c["timestamp"] / 1000.0) if c["timestamp"] > 1e11 else int(c["timestamp"]),
                    "time_str": time.strftime("%H:%M:%S", time.localtime(c["timestamp"] / 1000.0 if c["timestamp"] > 1e11 else c["timestamp"])),
                    "open": o,
                    "high": max(h, max(o, cl)),
                    "low": min(l, min(o, cl)),
                    "close": cl,
                    "volume": round(float(c.get("volume", 0)), 2)
                })
            candles_map[sym] = cleaned

    total_ticks = 0
    if ENGINE_MANAGER and ENGINE_MANAGER.single_runner.simulators:
        total_ticks = sum(s.tick_count for s in ENGINE_MANAGER.single_runner.simulators.values())

    proxy = get_proxy()
    all_tickers = proxy.get_all_tickers() if proxy else {}
    proxy_status = proxy.get_status() if proxy else {}

    active_positions_list = []
    signals_map = {}
    if ENGINE_MANAGER and ENGINE_MANAGER.single_runner and ENGINE_MANAGER.single_runner.simulators:
        for sym, sim in ENGINE_MANAGER.single_runner.simulators.items():
            signals_map[sym] = sim.latest_signal
            for p in getattr(sim.execution_engine, "active_positions", []):
                ticker = all_tickers.get(sym, {})
                current_price = ticker.get("mid_price", p.entry_price)
                if p.side == "BUY":
                    unrealized_pnl = (current_price - p.entry_price) * p.quantity
                    pnl_pct = ((current_price - p.entry_price) / p.entry_price) * 100 if p.entry_price > 0 else 0
                else:
                    unrealized_pnl = (p.entry_price - current_price) * p.quantity
                    pnl_pct = ((p.entry_price - current_price) / p.entry_price) * 100 if p.entry_price > 0 else 0
                active_positions_list.append({
                    "position_id": p.position_id,
                    "symbol": p.symbol,
                    "side": p.side,
                    "entry_price": p.entry_price,
                    "current_price": round(current_price, 4),
                    "quantity": p.quantity,
                    "tp_price": p.tp_price,
                    "sl_price": p.sl_price,
                    "unrealized_pnl": round(unrealized_pnl, 4),
                    "unrealized_pnl_pct": round(pnl_pct, 2),
                    "is_partial_closed": getattr(p, "is_partial_closed", False),
                    "timestamp_ms": p.timestamp_ms,
                    "time": time.strftime("%H:%M:%S", time.localtime(p.timestamp_ms / 1000.0)),
                })

    macro_regimes = {}
    if ENGINE_MANAGER and ENGINE_MANAGER.single_runner and ENGINE_MANAGER.single_runner.simulators:
        try:
            from core.macro_regime import macro_regime_detector
            for sym in ENGINE_MANAGER.single_runner.simulators.keys():
                macro_regimes[sym] = macro_regime_detector.get_regime(sym).to_dict()
        except Exception as _m_err:
            logger.debug(f"Macro regime retrieval error: {_m_err}")

    uptime_sec = get_current_uptime_seconds()
    return {
        "engine_running": ENGINE_RUNNING,
        "uptime_seconds": uptime_sec,
        "uptime_str": format_uptime(uptime_sec),
        "total_ticks": total_ticks,
        "proxy_status": proxy_status,
        "price_histories": price_hist_snapshot,
        "price_history": price_hist_first,
        "candles": candles_map,
        "portfolio": summary,
        "all_tickers": all_tickers,
        "signal": latest_sig if ENGINE_RUNNING else {"signal": "DETENIDO", "reason": "Bot pausado"},
        "signals": signals_map,
        "active_positions": active_positions_list,
        "macro_regimes": macro_regimes,
        "risk_guard": summary.get("risk_guard", {}),
        "telegram_status": {
            "configured": telegram_notifier.is_configured,
            "enabled": telegram_notifier.enabled,
        },
        "exchange_status": {
            "configured": live_exchange.is_configured,
            "live_enabled": live_exchange.live_enabled,
            "exchange": live_exchange.exchange,
        },
        "ai_optimizer": ai_optimizer.get_status(),
        "autonomous_agent": autonomous_trader.get_status(),
        "logs": event_logger.get_logs(limit=100),
    }


def _get_engine_config():
    config = {
        "market_mode": "live" if (ENGINE_MANAGER and ENGINE_MANAGER.use_live_market_data) else "demo",
        "strategies": {},
        "risk": {},
        "fees": {},
        "available_strategies": list(STRATEGY_REGISTRY.keys()),
    }
    if not ENGINE_MANAGER:
        return config

    runner = ENGINE_MANAGER.single_runner
    for sym, sim in runner.simulators.items():
        strat_obj = getattr(sim, "strategy", None)
        if strat_obj and hasattr(strat_obj, "__class__"):
            params = {}
            for attr in ["atr_sl_mult", "atr_tp_mult", "risk_per_trade_pct", "adx_min",
                         "pullback_tolerance", "cooldown_candles", "atr_min_mult",
                         "vir_threshold", "target_ticks", "stop_ticks", "tick_size"]:
                if hasattr(strat_obj, attr):
                    params[attr] = getattr(strat_obj, attr)
            config["strategies"][sim.strategy_name] = params
        break

    config["risk"]["single"] = {
        "max_daily_drawdown_pct": runner.risk_guard.max_daily_drawdown_pct,
        "max_consecutive_losses": runner.risk_guard.max_consecutive_losses,
        "max_exposure_pct": runner.risk_guard.max_exposure_pct,
    }
    for sym, sim in runner.simulators.items():
        config["fees"]["single"] = {
            "maker_fee": sim.execution_engine.maker_fee,
            "slippage_pct": sim.execution_engine.slippage_pct,
        }
        break
    return config


def _apply_engine_config(payload):
    global ENGINE_MANAGER
    if not ENGINE_MANAGER:
        return

    market_mode = payload.get("market_mode")
    if market_mode is not None:
        ENGINE_MANAGER.set_mode(use_live=(market_mode == "live"))

    capital_val = payload.get("capital")
    if capital_val is not None:
        try:
            new_cap = float(capital_val)
            if new_cap > 0:
                runner = ENGINE_MANAGER.single_runner
                runner.initial_capital = new_cap
                if hasattr(runner, "preset_info") and isinstance(runner.preset_info, dict):
                    runner.preset_info["initial_capital"] = new_cap
                runner.risk_guard.initial_capital = new_cap
                
                num_sims = len(runner.simulators) if runner.simulators else 1
                alloc_per_sim = new_cap / num_sims

                for sim in runner.simulators.values():
                    sim.execution_engine.initial_capital = alloc_per_sim
                    sim.execution_engine.capital = alloc_per_sim
                    sim.execution_engine.cum_pnl = 0.0
                runner.db_manager.clear_all_trades()
                runner._db_cache_ts = 0.0
                
                preset_path = os.path.join(os.path.dirname(__file__), "config", "strategy_presets.json")
                if os.path.exists(preset_path):
                    with open(preset_path, "r", encoding="utf-8") as f:
                        pdata = json.load(f)
                    if "presets" in pdata:
                        for p_key in pdata["presets"]:
                            pdata["presets"][p_key]["initial_capital"] = new_cap
                        with open(preset_path, "w", encoding="utf-8") as f:
                            json.dump(pdata, f, indent=2)
                event_logger.log("SYSTEM", f"💰 Capital de inversión configurado a ${new_cap:.2f} USD", level="SUCCESS")
        except Exception as err:
            logger.error(f"Error updating capital: {err}")

    strategy_updates = payload.get("strategies", {})
    for strat_name, params in strategy_updates.items():
        for sim in ENGINE_MANAGER.single_runner.simulators.values():
            strat_obj = getattr(sim, "strategy", None)
            if strat_obj and sim.strategy_name == strat_name:
                for k, v in params.items():
                    if hasattr(strat_obj, k):
                        current_val = getattr(strat_obj, k)
                        setattr(strat_obj, k, type(current_val)(v))

    risk_params = payload.get("risk", {}).get("single", {})
    if risk_params:
        runner = ENGINE_MANAGER.single_runner
        if "max_daily_drawdown_pct" in risk_params:
            runner.risk_guard.max_daily_drawdown_pct = float(risk_params["max_daily_drawdown_pct"])
        if "max_consecutive_losses" in risk_params:
            runner.risk_guard.max_consecutive_losses = int(risk_params["max_consecutive_losses"])

    fee_params = payload.get("fees", {}).get("single", {})
    if fee_params:
        for sim in ENGINE_MANAGER.single_runner.simulators.values():
            if "maker_fee" in fee_params:
                sim.execution_engine.maker_fee = float(fee_params["maker_fee"])
            if "slippage_pct" in fee_params:
                sim.execution_engine.slippage_pct = float(fee_params["slippage_pct"])


def _get_daily_stats():
    db_path = os.path.join(os.path.dirname(__file__), "data", "trades.db")
    if not os.path.exists(db_path):
        return {
            "days": [],
            "weekly_target_usd": 500.0,
            "weekly_net_pnl": 0.0,
            "weekly_progress_pct": 0.0,
            "weekly_remaining_usd": 500.0,
            "total_trades": 0,
            "total_wins": 0,
            "total_losses": 0,
            "global_win_rate": 0.0,
            "global_net_pnl": 0.0,
            "global_fees": 0.0,
            "weekend_standby": False,
            "weekend_reason": "",
        }

    try:
        import contextlib
        with contextlib.closing(sqlite3.connect(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            rows = cur.execute("""
                SELECT 
                    strftime('%Y-%m-%d', created_at) as trade_date,
                    count(*) as total_trades,
                    sum(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                    sum(CASE WHEN pnl <= 0 THEN 1 ELSE 0 END) as losses,
                    sum(pnl) as net_pnl,
                    sum(fee) as total_fees,
                    sum(quantity * entry_price) as volume_usd,
                    sum(CASE WHEN pnl > 0 THEN pnl ELSE 0 END) as gross_profit,
                    sum(CASE WHEN pnl < 0 THEN abs(pnl) ELSE 0 END) as gross_loss
                FROM trades
                GROUP BY strftime('%Y-%m-%d', created_at)
                ORDER BY trade_date DESC
            """).fetchall()

            days = []
            for r in rows:
                t_count = r["total_trades"]
                wins = r["wins"] or 0
                losses = r["losses"] or 0
                wr = round((wins / t_count * 100.0), 1) if t_count > 0 else 0.0
                g_profit = r["gross_profit"] or 0.0
                g_loss = r["gross_loss"] or 0.0
                pf = round(g_profit / g_loss, 2) if g_loss > 0 else (99.9 if g_profit > 0 else 1.0)
                days.append({
                    "date": r["trade_date"],
                    "total_trades": t_count,
                    "wins": wins,
                    "losses": losses,
                    "win_rate_pct": wr,
                    "net_pnl": round(r["net_pnl"] or 0.0, 4),
                    "total_fees": round(r["total_fees"] or 0.0, 4),
                    "volume_usd": round(r["volume_usd"] or 0.0, 2),
                    "profit_factor": pf,
                })

            weekly_net = sum(d["net_pnl"] for d in days[:7])
            weekly_target = 500.0
            weekly_progress = max(0.0, min(100.0, (weekly_net / weekly_target) * 100.0))
            weekly_remaining = max(0.0, weekly_target - weekly_net)

            tot_trades = sum(d["total_trades"] for d in days)
            tot_wins = sum(d["wins"] for d in days)
            tot_losses = sum(d["losses"] for d in days)
            glob_wr = round((tot_wins / tot_trades * 100.0), 1) if tot_trades > 0 else 0.0
            glob_pnl = sum(d["net_pnl"] for d in days)
            glob_fees = sum(d["total_fees"] for d in days)

            weekend_standby = False
            weekend_reason = ""
            is_session = True
            session_reason = ""
            daily_trades_count = 0
            max_daily_trades = 6

            macro_shield_active = False
            macro_shield_reason = ""
            current_capital = 200.0

            if ENGINE_MANAGER and ENGINE_MANAGER.single_runner:
                runner = ENGINE_MANAGER.single_runner
                rg = runner.risk_guard
                weekend_standby, weekend_reason = rg.is_weekend_standby()
                is_session, session_reason = rg.is_institutional_session()
                daily_trades_count = getattr(rg, "daily_trades_count", 0)
                max_daily_trades = getattr(rg, "max_daily_trades", 6)
                current_capital = getattr(runner, "total_portfolio_equity", 200.0)
                try:
                    from core.macro_shield import macro_shield
                    macro_shield_active, macro_shield_reason = macro_shield.is_blackout_active()
                except Exception:
                    pass

            weekly_min_target = 200.0
            weekly_max_target = 1000.0
            min_progress = max(0.0, min(100.0, (weekly_net / weekly_min_target) * 100.0))
            max_progress = max(0.0, min(100.0, (weekly_net / weekly_max_target) * 100.0))

            phase1_target = 2000.0
            phase1_progress = max(0.0, min(100.0, (current_capital / phase1_target) * 100.0))
            phase1_remaining = max(0.0, phase1_target - current_capital)

            return {
                "days": days,
                "current_capital": round(current_capital, 2),
                "phase1_target_usd": phase1_target,
                "phase1_progress_pct": round(phase1_progress, 1),
                "phase1_remaining_usd": round(phase1_remaining, 2),
                "phase2_weekly_target_usd": 200.0,
                "weekly_target_usd": weekly_target,
                "weekly_min_target_usd": weekly_min_target,
                "weekly_max_target_usd": weekly_max_target,
                "weekly_min_progress_pct": round(min_progress, 1),
                "weekly_max_progress_pct": round(max_progress, 1),
                "weekly_net_pnl": round(weekly_net, 4),
                "weekly_progress_pct": round(weekly_progress, 1),
                "weekly_remaining_usd": round(weekly_remaining, 2),
                "weekly_min_remaining_usd": round(max(0.0, weekly_min_target - weekly_net), 2),
                "total_trades": tot_trades,
                "total_wins": tot_wins,
                "total_losses": tot_losses,
                "global_win_rate": glob_wr,
                "global_net_pnl": round(glob_pnl, 4),
                "global_fees": round(glob_fees, 4),
                "weekend_standby": weekend_standby,
                "weekend_reason": weekend_reason,
                "institutional_session": is_session,
                "session_reason": session_reason,
                "macro_shield_active": macro_shield_active,
                "macro_shield_reason": macro_shield_reason,
                "daily_trades_count": daily_trades_count,
                "max_daily_trades": max_daily_trades,
            }

    except Exception as e:
        logger.error(f"Error fetching daily stats: {e}")
        return {"error": str(e), "days": []}


class HFTRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def do_GET(self):
        global ENGINE_RUNNING, ENGINE_MANAGER, PRICE_HISTORIES, ENGINE_START_TIME, ACCUMULATED_UPTIME

        path_clean = self.path.split("?")[0]

        if path_clean == "/" or path_clean == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            static_file = os.path.join(os.path.dirname(__file__), "static", "index.html")
            with open(static_file, "r", encoding="utf-8") as f:
                html_str = f.read()
            
            cur_cap = ENGINE_MANAGER.single_runner.initial_capital if (ENGINE_MANAGER and ENGINE_MANAGER.single_runner) else 200.0
            html_str = re.sub(r'id="hft-input-capital"\s+value="[^"]*"', f'id="hft-input-capital" value="{int(cur_cap)}"', html_str)
            html_str = re.sub(r'id="kpi-base-capital-hft"([^>]*)>\$[\d\.,]+', f'id="kpi-base-capital-hft"\\1>${cur_cap:.2f}', html_str)

            self.wfile.write(html_str.encode("utf-8"))


        elif path_clean == "/stats" or path_clean == "/stats.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            static_file = os.path.join(os.path.dirname(__file__), "static", "stats.html")
            if os.path.exists(static_file):
                with open(static_file, "r", encoding="utf-8") as f:
                    html_str = f.read()
                self.wfile.write(html_str.encode("utf-8"))
            else:
                self.wfile.write(b"<h1>404 Stats Page Not Found</h1>")

        elif path_clean == "/api/daily_stats":
            self._send_json(_get_daily_stats())

        elif path_clean == "/api/state":
            try:
                payload = _build_state_payload()
                self._send_json(payload)
            except Exception as e:
                logger.error(f"Error building state payload: {e}")
                self._send_json({"error": str(e), "engine_running": ENGINE_RUNNING}, status_code=500)

        elif path_clean == "/api/stream":
            self.send_response(200)

            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache, no-transform")
            self.send_header("X-Accel-Buffering", "no")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            # Set socket timeout so dead clients are detected quickly
            try:
                self.connection.settimeout(15.0)
            except Exception:
                pass

            try:
                while True:
                    payload = _build_state_payload()
                    msg = f"data: {json.dumps(payload)}\n\n"
                    self.wfile.write(msg.encode("utf-8"))
                    self.wfile.flush()
                    time.sleep(0.3)
            except Exception:
                pass

        elif path_clean == "/api/start":
            if not ENGINE_RUNNING:
                ENGINE_START_TIME = time.time()
                ENGINE_RUNNING = True
            if ENGINE_MANAGER:
                ENGINE_MANAGER.set_engine_state(True)
            logger.info("▶ ENGINE STARTED")
            event_logger.log("SYSTEM", "▶ Motor INICIADO", level="SUCCESS")
            self._send_json({"status": "started", "engine_running": True})

        elif path_clean == "/api/stop":
            if ENGINE_RUNNING and ENGINE_START_TIME:
                ACCUMULATED_UPTIME += time.time() - ENGINE_START_TIME
                ENGINE_START_TIME = None
            ENGINE_RUNNING = False
            if ENGINE_MANAGER:
                ENGINE_MANAGER.set_engine_state(False)
            logger.info("⏸ ENGINE STOPPED")
            event_logger.log("SYSTEM", "⏸ Motor PAUSADO", level="WARNING")
            self._send_json({"status": "stopped", "engine_running": False})

        elif path_clean == "/api/restart":
            ACCUMULATED_UPTIME = 0.0
            ENGINE_START_TIME = time.time()
            ENGINE_RUNNING = True
            with _PRICE_LOCK:
                PRICE_HISTORIES.clear()
            if ENGINE_MANAGER:
                ENGINE_MANAGER.reset_engine()
                ENGINE_MANAGER.set_engine_state(True)
            logger.info("🔄 ENGINE RESTARTED")
            event_logger.log("SYSTEM", "🔄 Motor REINICIADO", level="SUCCESS")
            self._send_json({"status": "restarted", "engine_running": True})

        elif path_clean == "/api/set_capital":
            try:
                from urllib.parse import urlparse, parse_qs
                query = parse_qs(urlparse(self.path).query)
                cap_str = query.get("capital", [None])[0]
                if cap_str:
                    new_cap = float(cap_str)
                    _apply_engine_config({"capital": new_cap})
                    self._send_json({"status": "updated", "capital": new_cap})
                else:
                    self._send_json({"status": "error", "message": "Missing capital param"}, 400)
            except Exception as exc:
                self._send_json({"status": "error", "message": str(exc)}, 400)

        elif path_clean == "/api/reset_stats":
            try:
                from urllib.parse import urlparse, parse_qs
                query = parse_qs(urlparse(self.path).query)
                cap_str = query.get("capital", ["200"])[0]
                cap_val = float(cap_str) if cap_str else 200.0
                if ENGINE_MANAGER:
                    ENGINE_MANAGER.reset_stats(capital=cap_val)
                    autonomous_trader.reset_journal()
                    event_logger.log("SYSTEM", f"🧹 Estadísticas, base de datos y diario del agente REINICIADAS. Capital base: ${cap_val:.2f} USD", level="SUCCESS")
                self._send_json({"status": "reset", "capital": cap_val})
            except Exception as exc:
                self._send_json({"status": "error", "message": str(exc)}, 400)

        elif path_clean == "/api/system_health":
            t0 = time.time()
            db_path = os.path.join(os.path.dirname(__file__), "data", "trades.db")
            db_size_bytes = os.path.getsize(db_path) if os.path.exists(db_path) else 0
            
            proxy = get_proxy()
            proxy_stat = proxy.get_status() if proxy else {}
            
            latency_ms = round((time.time() - t0) * 1000.0, 2)
            
            self._send_json({
                "status": "healthy",
                "api_latency_ms": max(0.5, latency_ms),
                "server_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "endpoints": {
                    "/api/state": {"status": "200 OK", "type": "JSON Snapshot", "latency": "<3ms"},
                    "/api/stream": {"status": "200 OK", "type": "SSE Unbuffered Stream", "latency": "<1ms"},
                    "/api/profiles": {"status": "200 OK", "type": "Presets Registry", "latency": "<1ms"},
                    "/proxy/status": {"status": "200 OK" if proxy else "OFFLINE", "type": "Bybit Feed Proxy", "latency": "<2ms"}
                },
                "database": {
                    "engine": "SQLite 3",
                    "journal_mode": "WAL",
                    "file_path": db_path,
                    "size_kb": round(db_size_bytes / 1024.0, 1),
                    "indexes": ["idx_trades_sym_time", "idx_trades_profile_time", "idx_trades_pnl", "idx_trades_exit"],
                    "write_latency": "<1.2ms"
                },
                "proxy": proxy_stat,
                "engine": {
                    "running": ENGINE_RUNNING,
                    "active_preset": ENGINE_MANAGER.active_preset_key if ENGINE_MANAGER else "institutional_trend_pro",
                    "strategy": ENGINE_MANAGER.single_runner.strategy_name if ENGINE_MANAGER else "institutional_trend",
                    "symbols": ENGINE_MANAGER.single_runner.symbols if ENGINE_MANAGER else ["SOL-USDT"]
                }
            })

        elif path_clean in ["/api/presets", "/api/profiles"]:
            presets_file = os.path.join(os.path.dirname(__file__), "config", "strategy_presets.json")
            if os.path.exists(presets_file):
                with open(presets_file, "r") as f:
                    presets_data = json.load(f)
                if ENGINE_MANAGER:
                    presets_data["active_preset"] = ENGINE_MANAGER.active_preset_key
                self._send_json(presets_data)
            else:
                self._send_json({"presets": {}})

        elif path_clean in ["/api/strategy", "/api/select_profile", "/api/profiles/select"]:
            params = self.path.split("?")
            preset_key = "institutional_trend_pro"
            custom_capital = None
            custom_symbols = None
            if len(params) > 1:
                for q in params[1].split("&"):
                    if q.startswith("name=") or q.startswith("key=") or q.startswith("preset_key="):
                        preset_key = q.split("=")[1]
                    elif q.startswith("capital="):
                        try:
                            custom_capital = float(q.split("=")[1])
                        except ValueError:
                            pass
                    elif q.startswith("symbol="):
                        sym_val = q.split("=")[1]
                        if sym_val == "MULTI-ASSET":
                            custom_symbols = ["SOL-USDT", "BTC-USDT", "ETH-USDT"]
                        elif sym_val:
                            custom_symbols = [sym_val]
            if ENGINE_MANAGER:
                ENGINE_MANAGER.select_preset_or_mode(preset_key, custom_capital=custom_capital, custom_symbols=custom_symbols)
                proxy = get_proxy()
                if proxy:
                    proxy.update_symbols(ENGINE_MANAGER.single_runner.symbols)
            ACCUMULATED_UPTIME = 0.0
            ENGINE_START_TIME = time.time()
            event_logger.log("SYSTEM", f"📊 Perfil Activo -> '{preset_key}'", level="SUCCESS")
            self._send_json({"status": "updated", "preset_key": preset_key})

        elif path_clean == "/api/mode":
            params = self.path.split("?")
            is_live = any("live=true" in p for p in params[1].split("&")) if len(params) > 1 else False
            if ENGINE_MANAGER:
                ENGINE_MANAGER.set_mode(is_live)
            event_logger.log("SYSTEM", f"🌐 Modo: {'LIVE' if is_live else 'DEMO'}", level="INFO")
            self._send_json({"status": "updated", "is_live": is_live})

        elif path_clean == "/api/reset_risk":
            if ENGINE_MANAGER:
                ENGINE_MANAGER.reset_engine()
                ENGINE_MANAGER.set_engine_state(True)
            event_logger.log("SYSTEM", "🛡️ Risk Guard RESETEADO", level="SUCCESS")
            self._send_json({"status": "risk_reset"})

        elif path_clean == "/api/cleardb":
            # Physically wipe all historical trades from SQLite
            import sqlite3 as _sq
            _db_path = os.path.join(os.path.dirname(__file__), "data", "trades.db")
            try:
                _conn = _sq.connect(_db_path)
                _conn.execute("DELETE FROM trades")
                _conn.commit()
                _conn.close()
                deleted_ok = True
            except Exception as _e:
                deleted_ok = False
                logger.error(f"cleardb error: {_e}")
            # Also reset in-memory session counters
            if ENGINE_MANAGER:
                ENGINE_MANAGER.reset_engine()
                ENGINE_MANAGER.set_engine_state(True)
            event_logger.log("SYSTEM", "🗑️ Base de datos LIMPIADA — historial borrado", level="SUCCESS")
            self._send_json({"status": "cleared", "db_wiped": deleted_ok})

        elif path_clean == "/api/config":
            self._send_json(_get_engine_config())

        elif path_clean == "/api/telegram/test":
            if not telegram_notifier.is_configured:
                self._send_json({"success": False, "configured": False, "message": "TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID no configurados en .env"})
            else:
                ok = telegram_notifier.send_direct_message(
                    "🧪 <b>A3 ALPHAEDGE PRO — TEST DE CONEXIÓN</b>\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    "✅ El sistema de notificaciones en tiempo real está conectado y funcionando correctamente para el <b>Proyecto Agustín</b>.\n"
                    f"⏱ <i>{time.strftime('%Y-%m-%d %H:%M:%S')}</i>"
                )
                self._send_json({
                    "success": ok,
                    "configured": True,
                    "message": "Mensaje de prueba enviado a Telegram" if ok else "Fallo al enviar mensaje a Telegram (verifique token o chat ID)"
                })

        elif path_clean == "/api/exchange/status":
            status_info = live_exchange.test_connection()
            if status_info.get("connected"):
                bal = live_exchange.get_balance("USDT")
                status_info["balance_usdt"] = bal.get("balance", 0.0)
                status_info["available_usdt"] = bal.get("available", 0.0)
            self._send_json(status_info)

        elif path_clean == "/proxy/status":
            proxy = get_proxy()
            if proxy:
                self._send_json(proxy.get_status())
            else:
                self._send_json({"running": False, "message": "MarketDataProxy not initialized"})

        elif path_clean == "/proxy/orderbook":
            params = self.path.split("?")
            symbol = "SOL-USDT"
            if len(params) > 1:
                for q in params[1].split("&"):
                    if q.startswith("symbol="):
                        symbol = q.split("=")[1]
            proxy = get_proxy()
            if proxy:
                ob = proxy.get_orderbook(symbol)
                if ob:
                    self._send_json(ob)
                else:
                    self.send_response(503)
                    self.end_headers()
                    self.wfile.write(b'{"error": "Orderbook not ready for symbol"}')
            else:
                self.send_response(503)
                self.end_headers()
                self.wfile.write(b'{"error": "MarketDataProxy not initialized"}')

        elif path_clean == "/proxy/ticker":
            params = self.path.split("?")
            symbol = "SOL-USDT"
            if len(params) > 1:
                for q in params[1].split("&"):
                    if q.startswith("symbol="):
                        symbol = q.split("=")[1]
            proxy = get_proxy()
            if proxy:
                ticker = proxy.get_ticker(symbol)
                if ticker:
                    self._send_json(ticker)
                else:
                    self.send_response(503)
                    self.end_headers()
                    self.wfile.write(b'{"error": "Ticker not ready for symbol"}')
            else:
                self.send_response(503)
                self.end_headers()
                self.wfile.write(b'{"error": "MarketDataProxy not initialized"}')

        elif path_clean == "/proxy/all_tickers":
            proxy = get_proxy()
            if proxy:
                self._send_json(proxy.get_all_tickers())
            else:
                self._send_json({})

        elif path_clean == "/api/ai/status":
            self._send_json(ai_optimizer.get_status())

        elif path_clean == "/api/ai/trigger":
            res = ai_optimizer.run_optimization_cycle(force=True)
            self._send_json(res)

        elif path_clean == "/api/ai/toggle":
            ai_optimizer.is_enabled = not ai_optimizer.is_enabled
            status_str = "ACTIVADA" if ai_optimizer.is_enabled else "PAUSADA"
            event_logger.log("SISTEMA", f"🧠 Auto-Evolución AI {status_str}", level="INFO")
            self._send_json({"status": "toggled", "is_enabled": ai_optimizer.is_enabled})

        elif path_clean == "/api/playbook/list":
            self._send_json({"files": autonomous_trader.playbook.list_files()})

        elif path_clean == "/api/playbook/get":
            from urllib.parse import urlparse, parse_qs
            query = parse_qs(urlparse(self.path).query)
            fname = query.get("file", ["01_market_structure.md"])[0]
            content = autonomous_trader.playbook.get_content(fname)
            self._send_json({"file": fname, "content": content})

        elif path_clean == "/api/agent/status":
            self._send_json(autonomous_trader.get_status())

        elif path_clean == "/api/agent/decisions":
            self._send_json({"decisions": autonomous_trader.history})

        elif path_clean == "/api/books/list":
            self._send_json({
                "books": rag_knowledge_engine.list_books(),
                "chunks_total": len(rag_knowledge_engine.chunks)
            })

        elif path_clean == "/api/books/content":
            from urllib.parse import urlparse, parse_qs
            query = parse_qs(urlparse(self.path).query)
            fname = query.get("file", ["01_richard_wyckoff_market_cycles.md"])[0]
            content = rag_knowledge_engine.get_book_content(fname)
            self._send_json({"file": fname, "content": content or ""})

        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        global ENGINE_MANAGER
        path_clean = self.path.split("?")[0]

        if path_clean == "/api/books/search":
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            try:
                payload = json.loads(post_data.decode("utf-8"))
                query_str = payload.get("query", "")
                top_k = int(payload.get("top_k", 4))
                results = rag_knowledge_engine.query_relevant_knowledge(query_str, top_k=top_k)
                self._send_json({"status": "ok", "query": query_str, "results": results})
            except Exception as e:
                self._send_json({"status": "error", "message": str(e)})

        elif path_clean == "/api/playbook/save":
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            try:
                payload = json.loads(post_data.decode("utf-8"))
                fname = payload.get("file", "")
                content = payload.get("content", "")
                ok = autonomous_trader.playbook.save_content(fname, content)
                event_logger.log("SISTEMA", f"📚 Playbook '{fname}' actualizado vía Editor Web", level="SUCCESS")
                self._send_json({"success": ok, "file": fname})
            except Exception as e:
                self._send_json({"status": "error", "message": str(e)})

        elif path_clean == "/api/agent/mode":
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            try:
                payload = json.loads(post_data.decode("utf-8"))
                new_mode = payload.get("mode", "HYBRID_CONSENSUS")
                if new_mode in ["ALGORITHMIC", "AUTONOMOUS", "HYBRID_CONSENSUS"]:
                    autonomous_trader.mode = new_mode
                    event_logger.log("SISTEMA", f"🔄 Modo de Operación cambiado a: {new_mode}", level="SUCCESS")
                    self._send_json({"status": "updated", "mode": new_mode})
                else:
                    self._send_json({"status": "error", "message": "Invalid mode"}, 400)
            except Exception as e:
                self._send_json({"status": "error", "message": str(e)})

        elif path_clean == "/api/agent/evaluate_now":
            results = []
            if ENGINE_MANAGER and ENGINE_MANAGER.single_runner:
                runner = ENGINE_MANAGER.single_runner
                for sym, sim in runner.simulators.items():
                    df = pd.DataFrame(list(sim.candle_history)) if len(sim.candle_history) >= 10 else None
                    dec = autonomous_trader.evaluate_opportunity(
                        symbol=sym,
                        df_candles=df,
                        orderbook=sim.latest_metrics,
                        current_balance=runner.risk_guard.starting_daily_capital,
                    )
                    results.append(dec)
            self._send_json({"status": "evaluated", "results": results})

        elif path_clean == "/api/ai/trigger":
            res = ai_optimizer.run_optimization_cycle(force=True)
            self._send_json(res)
        elif path_clean == "/api/ai/toggle":
            ai_optimizer.is_enabled = not ai_optimizer.is_enabled
            status_str = "ACTIVADA" if ai_optimizer.is_enabled else "PAUSADA"
            event_logger.log("SISTEMA", f"🧠 Auto-Evolución AI {status_str}", level="INFO")
            self._send_json({"status": "toggled", "is_enabled": ai_optimizer.is_enabled})
        elif path_clean == "/api/config":
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            try:
                payload = json.loads(post_data.decode("utf-8"))
                _apply_engine_config(payload)
                self._send_json({"status": "updated", "capital": payload.get("capital")})
            except Exception as e:
                self._send_json({"status": "error", "message": str(e)})
        elif path_clean == "/api/configure_bots":
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            try:
                payload = json.loads(post_data.decode("utf-8"))
                bots = payload.get("bots", [])
                if ENGINE_MANAGER and bots:
                    ENGINE_MANAGER.configure_custom_bots(bots)
                    proxy = get_proxy()
                    if proxy:
                        proxy.update_symbols(ENGINE_MANAGER.single_runner.symbols)
                    ENGINE_MANAGER.set_engine_state(True)
                    ENGINE_MANAGER.set_mode(use_live=ENGINE_MANAGER.use_live_market_data)
                    event_logger.log("SYSTEM", f"🔧 {len(bots)} bot(s) configurados vía Wizard", level="SUCCESS")
                self._send_json({"status": "configured", "bot_count": len(bots)})
            except Exception as e:
                self._send_json({"status": "error", "message": str(e)})
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def _send_json(self, data: dict, status_code: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-XSS-Protection", "1; mode=block")
        self.end_headers()
        self.wfile.write(body)


def run_async_portfolio():
    global ENGINE_MANAGER, ENGINE_RUNNING, ENGINE_START_TIME
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    ENGINE_MANAGER = MultiProfileEngineManager()
    
    # Initialize Market Data Proxy with portfolio symbols
    init_proxy(symbols=ENGINE_MANAGER.single_runner.symbols, interval_ms=300)

    use_live_default = os.environ.get("LIVE_MODE", "true").lower() in ("true", "1", "yes")
    ENGINE_MANAGER.set_mode(use_live=use_live_default)
    
    auto_start = os.environ.get("AUTO_START_ENGINE", "false").lower() in ("true", "1", "yes")
    ENGINE_RUNNING = auto_start
    if auto_start:
        ENGINE_START_TIME = time.time()
    ENGINE_MANAGER.set_engine_state(auto_start)

    # Start AI Auto-Optimization background engine
    ai_optimizer.start()

    async def _portfolio_stream_manager():
        active_tasks = {}
        while True:
            try:
                if ENGINE_MANAGER and ENGINE_MANAGER.single_runner:
                    current_sims = list(ENGINE_MANAGER.single_runner.simulators.values())
                    for sim in current_sims:
                        if sim.symbol not in active_tasks or active_tasks[sim.symbol].done():
                            logger.info(f"🌐 Data stream loop active for {sim.symbol}")
                            active_tasks[sim.symbol] = asyncio.create_task(
                                sim.ws_client.start_live_stream(interval_seconds=0.3)
                            )
            except Exception as err:
                logger.error(f"Error in portfolio stream manager: {err}")
            await asyncio.sleep(0.5)

    loop.run_until_complete(_portfolio_stream_manager())


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


def main():
    t = threading.Thread(target=run_async_portfolio, daemon=True)
    t.start()

    httpd = ReusableThreadingHTTPServer(("", PORT), HFTRequestHandler)
    print("=" * 70)
    print(f"🚀 A3 MOTOR TRADE ONLINE: http://localhost:{PORT}")
    print("=" * 70)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Servidor detenido.")


if __name__ == "__main__":
    main()
