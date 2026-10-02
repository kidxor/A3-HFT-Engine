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

        self._queue = queue.Queue(maxsize=100)
        self._stop_event = threading.Event()
        self._worker_thread = threading.Thread(target=self._process_queue, daemon=True)
        self._worker_thread.start()

        if self.is_configured:
            logger.info("📱 Telegram Notifier initialized and configured.")
        else:
            logger.info("ℹ️ Telegram Notifier in silent mode (TELEGRAM_BOT_TOKEN / CHAT_ID not set).")

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
