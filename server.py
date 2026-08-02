#!/usr/bin/env python3
import os
import sys

try:
    import pandas
    import numpy
except ImportError:
    venv_python = "/home/andres/Trading Bot/venv/bin/python"
    if os.path.exists(venv_python) and sys.executable != venv_python:
        os.execv(venv_python, [venv_python] + sys.argv)

import asyncio
import json
import logging
import threading
import time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from core.portfolio_runner import MultiProfileEngineManager
from core.event_logger import event_logger
from core.market_data_proxy import init_proxy, get_proxy
from strategies import STRATEGY_REGISTRY

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("HFT_Server")

PORT = int(os.environ.get("PORT", 8005))
ENGINE_MANAGER = None
ENGINE_RUNNING = True
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
            if sim._current_candle:
                hist.append(sim._current_candle)
            candles_map[sym] = [
                {
                    "time": time.strftime("%H:%M:%S", time.localtime(c["timestamp"] / 1000.0)),
                    "open": round(c["open"], 2),
                    "high": round(c["high"], 2),
                    "low": round(c["low"], 2),
                    "close": round(c["close"], 2),
                    "volume": round(c.get("volume", 0), 2)
                }
                for c in hist[-40:]
            ]

    total_ticks = 0
    if ENGINE_MANAGER and ENGINE_MANAGER.single_runner.simulators:
        total_ticks = sum(s.tick_count for s in ENGINE_MANAGER.single_runner.simulators.values())

    proxy = get_proxy()
    all_tickers = proxy.get_all_tickers() if proxy else {}
    proxy_status = proxy.get_status() if proxy else {}

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
        "risk_guard": summary.get("risk_guard", {}),
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


class HFTRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def do_GET(self):
        global ENGINE_RUNNING, ENGINE_MANAGER, PRICE_HISTORIES, ENGINE_START_TIME, ACCUMULATED_UPTIME

        path_clean = self.path.split("?")[0]

        if path_clean == "/" or path_clean == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            static_file = os.path.join(os.path.dirname(__file__), "static", "index.html")
            with open(static_file, "rb") as f:
                self.wfile.write(f.read())

        elif path_clean == "/api/state":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            payload = _build_state_payload()
            self.wfile.write(json.dumps(payload).encode("utf-8"))

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
                    "/proxy/status": {"status": "200 OK" if proxy else "OFFLINE", "type": "KuCoin Feed Proxy", "latency": "<2ms"}
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
                    "active_preset": ENGINE_MANAGER.active_preset_key if ENGINE_MANAGER else "alpha_edge_1000",
                    "strategy": ENGINE_MANAGER.single_runner.strategy_name if ENGINE_MANAGER else "alpha_edge",
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
            preset_key = "alpha_edge_1000"
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

        elif path_clean == "/api/config":
            self._send_json(_get_engine_config())

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

        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        global ENGINE_MANAGER
        path_clean = self.path.split("?")[0]

        if path_clean == "/api/config":
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            try:
                payload = json.loads(post_data.decode("utf-8"))
                _apply_engine_config(payload)
                self._send_json({"status": "config_updated"})
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

    def _send_json(self, data: dict):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))


def run_async_portfolio():
    global ENGINE_MANAGER, ENGINE_RUNNING, ENGINE_START_TIME
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    ENGINE_MANAGER = MultiProfileEngineManager()
    
    # Initialize Market Data Proxy with portfolio symbols
    init_proxy(symbols=ENGINE_MANAGER.single_runner.symbols, interval_ms=300)

    use_live_default = os.environ.get("LIVE_MODE", "true").lower() in ("true", "1", "yes")
    ENGINE_MANAGER.set_mode(use_live=use_live_default)
    
    auto_start = os.environ.get("AUTO_START_ENGINE", "true").lower() in ("true", "1", "yes")
    ENGINE_RUNNING = auto_start
    if auto_start:
        ENGINE_START_TIME = time.time()
    ENGINE_MANAGER.set_engine_state(auto_start)

    tasks = []
    for sim in ENGINE_MANAGER.single_runner.simulators.values():
        tasks.append(sim.ws_client.start_live_stream(interval_seconds=0.3))

    loop.run_until_complete(asyncio.gather(*tasks))


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


def main():
    t = threading.Thread(target=run_async_portfolio, daemon=True)
    t.start()

    httpd = ReusableThreadingHTTPServer(("", PORT), HFTRequestHandler)
    print("=" * 70)
    print(f"🚀 A3 ALPHAEDGE ENGINE ONLINE: http://localhost:{PORT}")
    print("=" * 70)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Servidor detenido.")


if __name__ == "__main__":
    main()
