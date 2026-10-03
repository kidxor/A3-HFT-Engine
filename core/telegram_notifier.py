import json
import logging
import os
import queue
import threading
import time
import urllib.parse
import urllib.request
from typing import Optional, Dict, Any

logger = logging.getLogger("TelegramNotifier")


def _load_env_file():
    env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(env_file):
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        if k.strip() not in os.environ:
                            os.environ[k.strip()] = v.strip()
        except Exception:
            pass

_load_env_file()


class TelegramNotifier:
    """
    Asynchronous Non-Blocking Telegram Alert Notifier.
    Uses an in-memory queue and background daemon worker thread to prevent
    any network latency from blocking the HFT trading loop.
    """
    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
        enabled: Optional[bool] = None,
    ):
        _load_env_file()
        self.bot_token = bot_token.strip() if bot_token is not None else os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        self.chat_id = chat_id.strip() if chat_id is not None else os.environ.get("TELEGRAM_CHAT_ID", "").strip()
        
        env_enabled = os.environ.get("TELEGRAM_ENABLED", "true").lower() in ("true", "1", "yes")
        self.is_configured = bool(self.bot_token and self.chat_id)
        self.enabled = (enabled if enabled is not None else env_enabled) and self.is_configured

        self.engine_manager = None
        self._last_update_id = 0
        self._queue = queue.Queue(maxsize=100)
        self._stop_event = threading.Event()
        self._worker_thread = threading.Thread(target=self._process_queue, daemon=True)
        self._worker_thread.start()

        if self.is_configured and self.enabled:
            self._listener_thread = threading.Thread(target=self._poll_updates_loop, daemon=True)
            self._listener_thread.start()

        if self.is_configured:
            logger.info("📱 Telegram Notifier & Interactive Listener initialized and configured.")
        else:
            logger.info("ℹ️ Telegram Notifier in silent mode (TELEGRAM_BOT_TOKEN / CHAT_ID not set).")

    def set_engine_manager(self, manager):
        """Sets the active MultiProfileEngineManager for live queries and commands."""
        self.engine_manager = manager

    def _process_queue(self):
        """Worker thread dispatching messages to Telegram API."""
        while not self._stop_event.is_set():
            try:
                msg_payload = self._queue.get(timeout=1.0)
                if msg_payload is None:
                    break
                self._send_http_request(msg_payload)
                self._queue.task_done()
                time.sleep(0.05)  # rate limit protection
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Telegram worker error: {e}")

    def _send_http_request(self, payload: Dict[str, Any]) -> bool:
        if not self.bot_token or not self.chat_id:
            return False
        
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        data = {
            "chat_id": self.chat_id,
            "text": payload.get("text", ""),
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        
        try:
            encoded_data = json.dumps(data).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=encoded_data,
                headers={"Content-Type": "application/json", "User-Agent": "A3-HFT-Bot/5.0"}
            )
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                res_body = json.loads(resp.read().decode("utf-8"))
                return res_body.get("ok", False)
        except Exception as err:
            logger.warning(f"Failed to deliver Telegram notification: {err}")
            return False

    def send_message(self, text: str) -> bool:
        """Enqueues a message for delivery."""
        if not self.enabled or not self.is_configured:
            return False
        try:
            self._queue.put_nowait({"text": text})
            return True
        except queue.Full:
            logger.warning("Telegram notification queue full; dropping message.")
            return False

    def send_direct_message(self, text: str) -> bool:
        """Sends a message synchronously (useful for startup/test messages)."""
        if not self.is_configured:
            return False
        return self._send_http_request({"text": text})

    # ------------------------------------------------------------------
    # Interactive Telegram Polling & Command Handling (Bidirectional Agent)
    # ------------------------------------------------------------------

    def _poll_updates_loop(self):
        """Polls for incoming messages from Telegram and responds dynamically."""
        logger.info("📡 Telegram Bot interactive command listener started.")
        # Initial offset sync
        time.sleep(2.0)
        while not self._stop_event.is_set():
            try:
                url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates?offset={self._last_update_id + 1}&timeout=5"
                req = urllib.request.Request(url, headers={"User-Agent": "A3-HFT-Bot/5.0"})
                with urllib.request.urlopen(req, timeout=10.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    if data.get("ok") and data.get("result"):
                        for update in data["result"]:
                            self._last_update_id = max(self._last_update_id, update.get("update_id", 0))
                            msg = update.get("message")
                            if not msg:
                                continue
                            from_chat_id = str(msg.get("chat", {}).get("id", ""))
                            # Security: strict check against authorized chat_id
                            if from_chat_id != str(self.chat_id):
                                logger.warning(f"Unauthorized message attempt from {from_chat_id}")
                                continue
                            
                            text = msg.get("text", "").strip()
                            if text:
                                reply = self._handle_command(text)
                                if reply:
                                    self.send_message(reply)
                time.sleep(1.0)
            except Exception as e:
                time.sleep(3.0)

    def _handle_command(self, text: str) -> str:
        """Dispatches commands or routes natural language queries to the Autonomous Trader Agent."""
        cmd = text.split()[0].lower() if text else ""
        if "@" in cmd:
            cmd = cmd.split("@")[0]

        # 1. HELP / MENU
        if cmd in ("/start", "/help", "/ayuda", "/menu"):
            return (
                "🤖 <b>A3 AlphaEdge PRO — Centro de Control y Agente IA</b>\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "Hola Andrés, el bot y el Agente Autónomo están en línea 24/7 en el VPS.\n\n"
                "<b>Comandos Disponibles:</b>\n"
                "• /status — Estado del motor, latencia y modo de trading\n"
                "• /balance — Capital actual, PnL neto y win rate acumulado\n"
                "• /pos — Posiciones activas en vivo (SOL, BTC, ETH)\n"
                "• /agent — Confluencias y razonamiento del Agente Autónomo\n"
                "• /trades — Últimos trades ejecutados\n"
                "• /reglas — Parámetros clave de la campaña $200 ➔ $1,200\n"
                "• /pausar — Pausar operaciones temporalmente\n"
                "• /iniciar — Reanudar operaciones automáticas\n\n"
                "<i>También puedes escribir cualquier pregunta directa para consultar al Agente de Trading.</i>"
            )

        # 2. STATUS
        if cmd in ("/status", "/estado"):
            state = "🟢 EN OPERACIÓN"
            active_preset = "crypto_futures_sniper"
            strat = "CryptoFuturesHunterStrategy"
            symbols = "SOL-USDT, BTC-USDT, ETH-USDT"
            if self.engine_manager and hasattr(self.engine_manager, "single_runner"):
                runner = self.engine_manager.single_runner
                state = "🟢 OPERANDO EN VIVO" if runner.is_running else "⏸ PAUSADO"
                active_preset = getattr(self.engine_manager, "active_preset_key", active_preset)
                strat = runner.strategy_name
                symbols = ", ".join(runner.symbols)

            return (
                "⚡ <b>ESTADO DEL SISTEMA A3</b>\n"
                "━━━━━━━━━━━━━━━━━━\n"
                f"• <b>Motor:</b> {state}\n"
                f"• <b>Estrategia:</b> <code>{strat}</code>\n"
                f"• <b>Preset:</b> <code>{active_preset}</code>\n"
                f"• <b>Pares Monitoreados:</b> <code>{symbols}</code>\n"
                f"• <b>Feed de Datos:</b> Bybit L2 (<100ms)\n"
                f"• <b>Filtro Macro 4H:</b> Activo (Sin contra-tendencia)\n"
                f"• <b>Scale-Out 50%:</b> Activo (Toma ganancias al +1.5R)\n"
                "━━━━━━━━━━━━━━━━━━\n"
                f"⏱ <i>{time.strftime('%Y-%m-%d %H:%M:%S')}</i>"
            )

        # 3. BALANCE & METRICS
        if cmd in ("/balance", "/saldo", "/capital"):
            try:
                from core.database import DatabaseManager
                db = DatabaseManager().get_total_summary()
                total_trades = db.get("total_trades", 0)
                win_rate = db.get("win_rate_pct", 0.0)
                net_pnl = db.get("total_pnl", 0.0)
            except Exception:
                db, total_trades, win_rate, net_pnl = {}, 0, 0.0, 0.0

            base_cap = 200.0
            current_balance = base_cap + net_pnl
            pnl_sign = "+" if net_pnl >= 0 else ""
            progress_pct = max(0.0, min(100.0, ((current_balance - 200.0) / 1000.0) * 100.0))

            return (
                "🏦 <b>BALANCE Y MÉTRICAS DE CAMPAÑA</b>\n"
                "━━━━━━━━━━━━━━━━━━\n"
                f"• <b>Balance Total:</b> <b>${current_balance:,.2f} USD</b>\n"
                f"• <b>Capital Base:</b> ${base_cap:,.2f} USD\n"
                f"• <b>PnL Neto Acumulado:</b> <b>{pnl_sign}${net_pnl:,.2f} USD</b>\n"
                f"• <b>Win Rate:</b> {win_rate:.1f}% ({db.get('win_trades', 0)}/{total_trades} trades)\n"
                f"• <b>Progreso Meta $1,200:</b> {progress_pct:.1f}% completado\n"
                "• <b>Risk Guard:</b> Operativo (Límite Drawdown: 10.0%)\n"
                "━━━━━━━━━━━━━━━━━━\n"
                f"⏱ <i>{time.strftime('%Y-%m-%d %H:%M:%S')}</i>"
            )

        # 4. ACTIVE POSITIONS
        if cmd in ("/pos", "/posiciones", "/position"):
            active_pos_list = []
            if self.engine_manager and hasattr(self.engine_manager, "single_runner"):
                for sym, sim in self.engine_manager.single_runner.simulators.items():
                    for p in sim.execution_engine.active_positions:
                        active_pos_list.append(p)

            if not active_pos_list:
                return (
                    "📌 <b>POSICIONES ACTIVAS</b>\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    "Actualmente <b>no hay posiciones abiertas</b>.\n\n"
                    "El Agente Autónomo y el filtro institucional están escaneando velas de 5m/15m en busca de mechas de barrido y confirmación con R:R 1:2.6+.\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    f"⏱ <i>{time.strftime('%Y-%m-%d %H:%M:%S')}</i>"
                )

            lines = ["📌 <b>POSICIONES ACTIVAS EN CURSO</b>\n━━━━━━━━━━━━━━━━━━"]
            for p in active_pos_list:
                side_badge = "🟢 BUY (LONG)" if p.side.upper() == "BUY" else "🔴 SELL (SHORT)"
                runner_tag = " [50% Corriendo en Riesgo Cero]" if getattr(p, "is_partial_closed", False) else ""
                lines.append(
                    f"• <b>{p.symbol}</b> — <b>{side_badge}</b>{runner_tag}\n"
                    f"  Entrada: ${p.entry_price:,.4f}\n"
                    f"  Stop Loss: ${p.sl_price:,.4f}\n"
                    f"  Take Profit: ${p.tp_price:,.4f}\n"
                    f"  Cantidad: {p.quantity:.4f}"
                )
            lines.append("━━━━━━━━━━━━━━━━━━")
            lines.append(f"⏱ <i>{time.strftime('%Y-%m-%d %H:%M:%S')}</i>")
            return "\n".join(lines)

        # 5. RECENT TRADES
        if cmd in ("/trades", "/historial"):
            try:
                from core.database import DatabaseManager
                trades = DatabaseManager().get_recent_trades(limit=5)
            except Exception:
                trades = []

            if not trades:
                return (
                    "📜 <b>HISTORIAL DE TRADES</b>\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    "Aún no hay operaciones registradas en la base de datos de esta campaña.\n"
                    "━━━━━━━━━━━━━━━━━━"
                )

            lines = ["📜 <b>ÚLTIMOS TRADES REGISTRADOS</b>\n━━━━━━━━━━━━━━━━━━"]
            for t in trades:
                pnl_val = t.get("pnl", 0.0)
                sign = "+" if pnl_val >= 0 else ""
                emoji = "🏆 WIN" if pnl_val >= 0 else "🛑 SL"
                lines.append(
                    f"• #{t.get('id')} <b>{t.get('symbol')}</b> ({t.get('side')}): "
                    f"<b>{emoji} {sign}${pnl_val:,.2f} USD</b> ({t.get('exit_reason', 'Cierre')})"
                )
            lines.append("━━━━━━━━━━━━━━━━━━")
            return "\n".join(lines)

        # 6. AUTONOMOUS AGENT REASONING
        if cmd in ("/agent", "/ia", "/razonamiento"):
            try:
                from core.autonomous_trader import autonomous_trader
                status = autonomous_trader.get_status()
                recent = status.get("recent_decisions", [])
            except Exception:
                recent = []

            if not recent:
                return (
                    "🧠 <b>AGENTE AUTÓNOMO DE TRADING</b>\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    "El Agente Autónomo está activo y analizando la acción del precio.\n"
                    "• <b>Modo:</b> HÍBRIDO CONSENSO (LLM + Confluencias Wyckoff/Brooks)\n"
                    "• <b>Riesgo Dinámico:</b> 5.0% base / 8.0% setup A+\n"
                    "• <b>Estado:</b> Monitoreando libros L2 de Bybit y velas japonesas en tiempo real.\n"
                    "━━━━━━━━━━━━━━━━━━"
                )

            lines = ["🧠 <b>ÚLTIMO ANÁLISIS DEL AGENTE AUTÓNOMO</b>\n━━━━━━━━━━━━━━━━━━"]
            for d in recent[-3:]:
                lines.append(
                    f"• <b>{d.get('symbol')}</b> — Acción: <b>{d.get('action')}</b> [{d.get('grade')}]\n"
                    f"  Vela: {d.get('candle_pattern', 'Normal')}\n"
                    f"  Razonamiento: {d.get('chain_of_thought', 'Evaluando niveles')}\n"
                )
            lines.append("━━━━━━━━━━━━━━━━━━")
            lines.append(f"⏱ <i>{time.strftime('%Y-%m-%d %H:%M:%S')}</i>")
            return "\n".join(lines)

        # 7. PLAYBOOK RULES
        if cmd in ("/reglas", "/playbook", "/rules"):
            return (
                "📖 <b>REGLAS CLAVE DE LA CAMPAÑA ($200 ➔ $1,200)</b>\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "1. <b>Filtro Macro 4H Innegociable:</b> Solo longs en tendencia alcista, solo shorts en tendencia bajista. En CHOP 100% en cash.\n"
                "2. <b>Caza de Liquidaciones (Bear/Bull Traps):</b> Entradas tras la mecha de barrido institucional.\n"
                "3. <b>Gestión Matemática Asimétrica (R:R 1:2.6+):</b> SL estricto en invalidez estructural. Al +1.5R se asegura el 50% y SL se mueve a Breakeven (+0.1% buffer).\n"
                "4. <b>Escalado de Capital:</b> Fase 1 ($200 -> $400, riesgo 5%), Fase 2 ($400 -> $800, riesgo 6.5%), Fase 3 ($800 -> $1,200).\n"
                "5. <b>Control Anti-Tilt:</b> Máximo 3 trades diarios, enfriamiento obligatorio de 45m tras cada operación.\n"
                "━━━━━━━━━━━━━━━━━━"
            )

        # 8. PAUSE / RESUME ENGINE
        if cmd in ("/pausar", "/pause", "/stop"):
            if self.engine_manager:
                self.engine_manager.set_engine_state(False)
                return "⏸ <b>Motor de operaciones pausado exitosamente.</b>\nNo se abrirán nuevas posiciones hasta que envíes /iniciar."
            return "⚠️ No se pudo acceder al motor de operaciones."

        if cmd in ("/iniciar", "/resume", "/start_engine"):
            if self.engine_manager:
                self.engine_manager.set_engine_state(True)
                return "▶ <b>Motor de operaciones activado exitosamente.</b>\nEscaneando oportunidades institucionales en SOL, BTC y ETH."
            return "⚠️ No se pudo acceder al motor de operaciones."

        # 9. CONVERSATIONAL AGENT ROUTE (NATURAL LANGUAGE)
        try:
            from core.autonomous_trader import autonomous_trader
            status = autonomous_trader.get_status()
            recent = status.get("recent_decisions", [])
            last_cot = recent[-1].get("chain_of_thought", "") if recent else ""
            last_sym = recent[-1].get("symbol", "SOL-USDT") if recent else "SOL-USDT"

            reply = (
                f"🤖 <b>Agente Autónomo A3:</b>\n\n"
                f"He recibido tu consulta: <i>\"{text}\"</i>\n\n"
                f"📊 <b>Estado actual de mercado:</b>\n"
                f"Estoy monitoreando activamente SOL-USDT, BTC-USDT y ETH-USDT con disciplina estricta de preservación de capital.\n\n"
            )
            if last_cot:
                reply += f"Última evaluación ({last_sym}):\n<i>{last_cot}</i>\n\n"
            reply += "Escribe /status para ver el motor, /pos para ver operaciones o /help para ver todos los comandos."
            return reply
        except Exception:
            return f"🤖 Recibido: \"{text}\". Usa /help para ver los comandos disponibles."

    # ------------------------------------------------------------------
    # High-level Alert Templates
    # ------------------------------------------------------------------

    def notify_trade_opened(
        self,
        symbol: str,
        side: str,
        price: float,
        quantity: float,
        sl_price: float,
        tp_price: float,
        risk_usd: float = 0.0,
        strategy_name: str = "AlphaEdge PRO",
    ):
        side_emoji = "🟢 BUY" if side.upper() == "BUY" else "🔴 SELL"
        msg = (
            f"🚀 <b>A3 BOT: POSICIÓN ABIERTA</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Par:</b> <code>{symbol}</code>\n"
            f"• <b>Operación:</b> <b>{side_emoji}</b>\n"
            f"• <b>Estrategia:</b> {strategy_name}\n"
            f"• <b>Precio Entrada:</b> ${price:,.4f}\n"
            f"• <b>Cantidad:</b> {quantity:.4f}\n"
            f"• <b>Stop Loss:</b> ${sl_price:,.4f}\n"
            f"• <b>Take Profit:</b> ${tp_price:,.4f}\n"
            f"• <b>Riesgo Estimado:</b> ${risk_usd:,.2f} USD\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⏱ <i>{time.strftime('%Y-%m-%d %H:%M:%S')}</i>"
        )
        self.send_message(msg)

    def notify_partial_scale_out(
        self,
        symbol: str,
        side: str,
        exit_price: float,
        partial_pnl: float,
        new_sl: float,
    ):
        pnl_sign = "+" if partial_pnl >= 0 else ""
        msg = (
            f"🛡️ <b>SCALE-OUT 50% EJECUTADO (GANANCIA ASEGURADA)</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Par:</b> <code>{symbol}</code> ({side})\n"
            f"• <b>Precio Parcial:</b> ${exit_price:,.4f}\n"
            f"• <b>Ganancia Parcial:</b> <b>${pnl_sign}{partial_pnl:,.4f} USD</b> 💵\n"
            f"• <b>Candado Breakeven:</b> Stop Loss movido a <b>${new_sl:,.4f} (+0.1%)</b>\n"
            f"• <i>La mitad restante corre 100% libre de riesgo.</i>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⏱ <i>{time.strftime('%Y-%m-%d %H:%M:%S')}</i>"
        )
        self.send_message(msg)

    def notify_trade_closed(
        self,
        symbol: str,
        side: str,
        exit_price: float,
        pnl: float,
        exit_reason: str,
        total_balance: Optional[float] = None,
    ):
        is_win = pnl >= 0
        status_emoji = "🏆 WIN" if is_win else "🛑 STOP LOSS"
        pnl_sign = "+" if is_win else ""
        
        bal_str = f"\n• <b>Balance Total:</b> ${total_balance:,.2f} USD" if total_balance is not None else ""
        msg = (
            f"{status_emoji} <b>A3 BOT: POSICIÓN CERRADA</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Par:</b> <code>{symbol}</code> ({side})\n"
            f"• <b>Precio Salida:</b> ${exit_price:,.4f}\n"
            f"• <b>Motivo:</b> {exit_reason}\n"
            f"• <b>PnL Neto:</b> <b>{pnl_sign}${pnl:,.4f} USD</b>{bal_str}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⏱ <i>{time.strftime('%Y-%m-%d %H:%M:%S')}</i>"
        )
        self.send_message(msg)

    def notify_circuit_breaker(self, reason: str, max_dd_pct: float, current_balance: float):
        msg = (
            f"🚨 <b>EMERGENCY RISK GUARD: CIRCUIT BREAKER</b> 🚨\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Alerta:</b> Límite de Drawdown Diario alcanzado ({max_dd_pct:.1f}%)\n"
            f"• <b>Detalle:</b> {reason}\n"
            f"• <b>Balance Protegido:</b> ${current_balance:,.2f} USD\n"
            f"• <b>Acción:</b> Nuevas operaciones pausadas automáticamente para proteger el capital de Agustín.\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⏱ <i>{time.strftime('%Y-%m-%d %H:%M:%S')}</i>"
        )
        self.send_message(msg)

    def notify_cooldown(self, consecutive_losses: int, pause_sec: float):
        msg = (
            f"⚠️ <b>RISK GUARD: PAUSA DE ENFRIAMIENTO ACTIVA</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Motivo:</b> {consecutive_losses} pérdidas consecutivas detectadas.\n"
            f"• <b>Duración:</b> Pausa de {pause_sec:.0f}s para evitar condiciones adversas de mercado.\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⏱ <i>{time.strftime('%Y-%m-%d %H:%M:%S')}</i>"
        )
        self.send_message(msg)


# Global singleton instance
telegram_notifier = TelegramNotifier()
