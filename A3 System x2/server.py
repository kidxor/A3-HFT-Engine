#!/usr/bin/env python3
"""
A3 System x2 — Servidor de Torneo Dual A/B (Velas vs Matemáticas)
Corre de forma completamente independiente en el puerto 8010 usando ThreadingHTTPServer.
"""

import os
import sys
import json
import time
import asyncio
import logging
import threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Any

# Path setup within A3 System x2
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.dual_runner import DualBotTournamentRunner
from core.event_logger import event_logger

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("A3_System_x2")

PORT = int(os.environ.get("PORT", 8010))

# Global tournament runner instance
TOURNAMENT = None
ASYNC_LOOP = None
ENGINE_RUNNING = True
ENGINE_START_TIME = time.time()


def start_async_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()


class DualTournamentHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler for A3 System x2."""

    def log_message(self, format, *args):
        # Suppress noisy healthcheck polling from console logs
        return

    def _send_json(self, data: Any, status: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/api/leaderboard", "/api/state"):
            if TOURNAMENT:
                self._send_json(TOURNAMENT.get_leaderboard())
            else:
                self._send_json({"error": "Tournament not initialized"}, status=503)

        elif path == "/api/health":
            self._send_json({
                "status": "HEALTHY",
                "system": "A3 System x2",
                "port": PORT,
                "timestamp": time.time(),
            })

        elif path == "/api/logs":
            self._send_json({"logs": event_logger.get_logs(limit=50)})

        elif path in ("/", "/index.html"):
            self._send_dashboard()

        else:
            self.send_error(404, "Endpoint no encontrado")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/reset":
            global TOURNAMENT
            qs = parse_qs(parsed.query)
            cap = float(qs.get("capital", [200.0])[0])
            if TOURNAMENT:
                TOURNAMENT.stop()
            TOURNAMENT = DualBotTournamentRunner(
                symbol="SOL-USDT",
                initial_capital_per_bot=cap,
                use_live_market_data=True,
                base_dir=BASE_DIR,
            )
            TOURNAMENT.db_bot_velas.clear_all_trades()
            TOURNAMENT.db_bot_algoritmos.clear_all_trades()
            TOURNAMENT.start()
            self._send_json({"status": "SUCCESS", "message": f"Torneo reiniciado con ${cap:.2f} USD por bot y bases de datos limpias"})
        else:
            self.send_error(404, "Endpoint POST no encontrado")

    def _send_dashboard(self):
        html_content = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>A3 System x2 — Batalla A/B: Velas vs Matemáticas</title>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Inter:wght@400;500;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-base: #0a0e17;
            --card-bg: #111827;
            --border: #1f2937;
            --accent-velas: #10b981;
            --accent-quant: #3b82f6;
            --text-main: #f3f4f6;
            --text-muted: #9ca3af;
            --danger: #ef4444;
            --gold: #f59e0b;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background-color: var(--bg-base);
            color: var(--text-main);
            font-family: 'Inter', sans-serif;
            padding: 20px;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 16px 24px;
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 12px;
            margin-bottom: 24px;
        }
        .title-group h1 { font-size: 1.5rem; font-weight: 800; }
        .badge {
            background: #1e293b;
            color: #38bdf8;
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 0.8rem;
            font-family: 'JetBrains Mono', monospace;
        }
        .leader-banner {
            background: linear-gradient(135deg, rgba(245, 158, 11, 0.15) 0%, rgba(16, 185, 129, 0.15) 100%);
            border: 1px solid var(--gold);
            border-radius: 12px;
            padding: 16px 24px;
            text-align: center;
            margin-bottom: 24px;
        }
        .leader-banner h2 { font-size: 1.25rem; color: var(--gold); }
        .arena-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 24px;
        }
        .bot-card {
            background: var(--card-bg);
            border-radius: 12px;
            border: 2px solid var(--border);
            padding: 24px;
        }
        .bot-velas { border-color: rgba(16, 185, 129, 0.4); }
        .bot-quant { border-color: rgba(59, 130, 246, 0.4); }
        .bot-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 12px;
            border-bottom: 1px solid var(--border);
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 12px;
            margin-bottom: 20px;
        }
        .stat-box {
            background: #0f172a;
            padding: 12px;
            border-radius: 8px;
            text-align: center;
        }
        .stat-box .label { font-size: 0.75rem; color: var(--text-muted); margin-bottom: 4px; }
        .stat-box .val { font-size: 1.1rem; font-weight: 700; font-family: 'JetBrains Mono', monospace; }
        .signal-box {
            background: #0f172a;
            border-left: 4px solid var(--border);
            padding: 12px 16px;
            border-radius: 6px;
            margin-bottom: 16px;
            font-size: 0.85rem;
        }
        .pos-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.85rem;
            margin-top: 12px;
        }
        .pos-table th, .pos-table td {
            padding: 8px;
            text-align: left;
            border-bottom: 1px solid var(--border);
            font-family: 'JetBrains Mono', monospace;
        }
        .btn-reset {
            background: #334155;
            color: #fff;
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            cursor: pointer;
            font-weight: 600;
        }
        .btn-reset:hover { background: #475569; }
        .green { color: var(--accent-velas); }
        .blue { color: var(--accent-quant); }
        .red { color: var(--danger); }
    </style>
</head>
<body>
    <div class="header">
        <div class="title-group">
            <h1>⚡ A3 System x2 — Batalla A/B en Vivo</h1>
            <div style="margin-top: 4px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
                <span class="badge">Puerto: 8010</span>
                <span class="badge" id="asset-badge">Activo: SOL-USDT (5m)</span>
                <span class="badge" id="ticks-badge">Ticks: 0</span>
                <span class="badge" id="macro-badge" style="background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid #f59e0b;">🛡️ Macro 4H: Sincronizando...</span>
            </div>
        </div>
        <button class="btn-reset" onclick="resetBattle()">🔄 Reiniciar Batalla ($200 c/u)</button>
    </div>

    <div class="leader-banner">
        <h2 id="leader-text">🏆 Líder Actual: Evaluando primeras velas...</h2>
        <p id="leader-sub" style="color: var(--text-muted); font-size: 0.9rem; margin-top: 4px;">Ventaja: $0.00 USD</p>
    </div>

    <div class="arena-grid">
        <!-- BOT 1: VELAS & PRICE ACTION -->
        <div class="bot-card bot-velas">
            <div class="bot-header">
                <div>
                    <h2 class="green">🕯️ Bot 1: Velas & Price Action</h2>
                    <p style="font-size: 0.8rem; color: var(--text-muted);">18 Patrones, Wyckoff, Al Brooks, Bar-by-Bar Runner</p>
                </div>
                <span class="badge" style="border: 1px solid var(--accent-velas);">bot_velas</span>
            </div>

            <div class="stats-grid">
                <div class="stat-box">
                    <div class="label">Capital</div>
                    <div class="val" id="velas-cap">$200.00</div>
                </div>
                <div class="stat-box">
                    <div class="label">PnL Neto</div>
                    <div class="val" id="velas-pnl">$0.00</div>
                </div>
                <div class="stat-box">
                    <div class="label">Win Rate</div>
                    <div class="val" id="velas-winrate">0.0%</div>
                </div>
                <div class="stat-box">
                    <div class="label">Trades / W-L</div>
                    <div class="val" id="velas-trades">0 (0/0)</div>
                </div>
                <div class="stat-box">
                    <div class="label">Profit Factor</div>
                    <div class="val" id="velas-pf">0.0</div>
                </div>
                <div class="stat-box">
                    <div class="label">Ratio Sharpe</div>
                    <div class="val" id="velas-sharpe">0.0</div>
                </div>
            </div>

            <div class="signal-box" id="velas-signal-box">
                <strong>Señal Actual:</strong> <span id="velas-signal">NEUTRAL</span><br>
                <span id="velas-reason" style="color: var(--text-muted);">Iniciando motor de velas...</span>
            </div>

            <h4 style="margin-top: 16px;">Posiciones Activas</h4>
            <div id="velas-positions" style="color: var(--text-muted); font-size: 0.85rem; margin-top: 8px;">Sin posiciones abiertas</div>
        </div>

        <!-- BOT 2: MATEMÁTICAS & ALGORITMOS -->
        <div class="bot-card bot-quant">
            <div class="bot-header">
                <div>
                    <h2 class="blue">📐 Bot 2: Matemáticas & Algoritmos</h2>
                    <p style="font-size: 0.8rem; color: var(--text-muted);">Micro-Price, VIR L2, 3-EMA Stack, ADX >= 28, %B, ATR 1:3</p>
                </div>
                <span class="badge" style="border: 1px solid var(--accent-quant);">bot_algoritmos</span>
            </div>

            <div class="stats-grid">
                <div class="stat-box">
                    <div class="label">Capital</div>
                    <div class="val" id="quant-cap">$200.00</div>
                </div>
                <div class="stat-box">
                    <div class="label">PnL Neto</div>
                    <div class="val" id="quant-pnl">$0.00</div>
                </div>
                <div class="stat-box">
                    <div class="label">Win Rate</div>
                    <div class="val" id="quant-winrate">0.0%</div>
                </div>
                <div class="stat-box">
                    <div class="label">Trades / W-L</div>
                    <div class="val" id="quant-trades">0 (0/0)</div>
                </div>
                <div class="stat-box">
                    <div class="label">Profit Factor</div>
                    <div class="val" id="quant-pf">0.0</div>
                </div>
                <div class="stat-box">
                    <div class="label">Ratio Sharpe</div>
                    <div class="val" id="quant-sharpe">0.0</div>
                </div>
            </div>

            <div class="signal-box" id="quant-signal-box">
                <strong>Señal Actual:</strong> <span id="quant-signal">NEUTRAL</span><br>
                <span id="quant-reason" style="color: var(--text-muted);">Iniciando motor cuantitativo...</span>
            </div>

            <h4 style="margin-top: 16px;">Posiciones Activas</h4>
            <div id="quant-positions" style="color: var(--text-muted); font-size: 0.85rem; margin-top: 8px;">Sin posiciones abiertas</div>
        </div>
    </div>

    <script>
        async function fetchState() {
            try {
                const res = await fetch('/api/leaderboard');
                const data = await res.json();

                document.getElementById('ticks-badge').innerText = `Ticks: ${data.total_ticks}`;
                document.getElementById('leader-text').innerText = `🏆 Líder: ${data.current_leader}`;
                document.getElementById('leader-sub').innerText = `Ventaja acumulada: $${data.leader_advantage_usd.toFixed(4)} USD | Uptime: ${data.uptime_seconds}s`;

                if (data.macro_regime && data.macro_regime.bias) {
                    const mb = document.getElementById('macro-badge');
                    const bias = data.macro_regime.bias;
                    const adx = data.macro_regime.adx || 0;
                    if (bias === 'BULL_REGIME') {
                        mb.style.background = 'rgba(16, 185, 129, 0.2)';
                        mb.style.color = '#34d399';
                        mb.style.borderColor = '#10b981';
                        mb.innerText = `🛡️ Macro 4H: BULL TREND (Solo BUY) | ADX: ${adx}`;
                    } else if (bias === 'BEAR_REGIME') {
                        mb.style.background = 'rgba(239, 68, 68, 0.2)';
                        mb.style.color = '#f87171';
                        mb.style.borderColor = '#ef4444';
                        mb.innerText = `🛡️ Macro 4H: BEAR TREND (Solo SELL) | ADX: ${adx}`;
                    } else {
                        mb.style.background = 'rgba(245, 158, 11, 0.2)';
                        mb.style.color = '#fbbf24';
                        mb.style.borderColor = '#f59e0b';
                        mb.innerText = `🛡️ Macro 4H: CHOP STANDBY (100% Cash) | ADX: ${adx}`;
                    }
                }

                // Bot Velas
                const v = data.bot_velas;
                document.getElementById('velas-cap').innerText = `$${v.stats.capital.toFixed(2)}`;
                const vPnl = v.stats.cum_pnl;
                document.getElementById('velas-pnl').innerText = `${vPnl >= 0 ? '+' : ''}$${vPnl.toFixed(4)}`;
                document.getElementById('velas-pnl').className = `val ${vPnl >= 0 ? 'green' : 'red'}`;
                document.getElementById('velas-winrate').innerText = `${v.stats.win_rate_percent.toFixed(1)}%`;
                document.getElementById('velas-trades').innerText = `${v.stats.total_trades} (${v.stats.wins}/${v.stats.losses})`;
                document.getElementById('velas-pf').innerText = v.stats.profit_factor;
                document.getElementById('velas-sharpe').innerText = v.stats.sharpe_ratio;
                document.getElementById('velas-signal').innerText = v.latest_signal.signal || 'NEUTRAL';
                document.getElementById('velas-reason').innerText = v.latest_signal.reason || '';

                renderPositions('velas-positions', v.open_positions);

                // Bot Algoritmos
                const q = data.bot_algoritmos;
                document.getElementById('quant-cap').innerText = `$${q.stats.capital.toFixed(2)}`;
                const qPnl = q.stats.cum_pnl;
                document.getElementById('quant-pnl').innerText = `${qPnl >= 0 ? '+' : ''}$${qPnl.toFixed(4)}`;
                document.getElementById('quant-pnl').className = `val ${qPnl >= 0 ? 'blue' : 'red'}`;
                document.getElementById('quant-winrate').innerText = `${q.stats.win_rate_percent.toFixed(1)}%`;
                document.getElementById('quant-trades').innerText = `${q.stats.total_trades} (${q.stats.wins}/${q.stats.losses})`;
                document.getElementById('quant-pf').innerText = q.stats.profit_factor;
                document.getElementById('quant-sharpe').innerText = q.stats.sharpe_ratio;
                document.getElementById('quant-signal').innerText = q.latest_signal.signal || 'NEUTRAL';
                document.getElementById('quant-reason').innerText = q.latest_signal.reason || '';

                renderPositions('quant-positions', q.open_positions);

            } catch (e) {
                console.error("Error fetching tournament state:", e);
            }
        }

        function renderPositions(elemId, positions) {
            const el = document.getElementById(elemId);
            if (!positions || positions.length === 0) {
                el.innerHTML = '<span style="color: var(--text-muted);">Sin posiciones abiertas</span>';
                return;
            }
            let html = '<table class="pos-table"><thead><tr><th>Lado</th><th>Entrada</th><th>TP</th><th>SL</th><th>Cant</th><th>Modo</th></tr></thead><tbody>';
            positions.forEach(p => {
                html += `<tr>
                    <td class="${p.side === 'BUY' ? 'green' : 'red'}">${p.side}</td>
                    <td>$${p.entry_price.toFixed(2)}</td>
                    <td>$${p.tp_price > 99999 ? 'RUNNER' : p.tp_price.toFixed(2)}</td>
                    <td>$${p.sl_price.toFixed(2)}</td>
                    <td>${p.quantity}</td>
                    <td>${p.runner_mode ? '🚀 RUNNER' : 'STAND'}</td>
                </tr>`;
            });
            html += '</tbody></table>';
            el.innerHTML = html;
        }

        async function resetBattle() {
            if (confirm("¿Reiniciar la batalla con $200 USD para cada bot?")) {
                await fetch('/api/reset?capital=200', { method: 'POST' });
                fetchState();
            }
        }

        setInterval(fetchState, 1000);
        fetchState();
    </script>
</body>
</html>"""
        body = html_content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


def run_server():
    global TOURNAMENT, ASYNC_LOOP

    logger.info("⚔️ Inicializando A3 System x2 — Duelo Dual A/B...")
    TOURNAMENT = DualBotTournamentRunner(
        symbol="SOL-USDT",
        initial_capital_per_bot=200.0,
        use_live_market_data=True,
        base_dir=BASE_DIR,
    )
    TOURNAMENT.start()

    server_address = ("0.0.0.0", PORT)
    httpd = ReusableThreadingHTTPServer(server_address, DualTournamentHandler)
    logger.info(f"🚀 A3 System x2 Servidor Activo en http://localhost:{PORT}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        TOURNAMENT.stop()
        httpd.server_close()


if __name__ == "__main__":
    run_server()
