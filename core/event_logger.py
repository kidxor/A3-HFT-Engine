import time
import threading
from collections import deque
from typing import List, Dict, Any, Optional

class SystemEventLogger:
    """
    Thread-safe event logger buffer for real-time live action broadcasting.
    Captures microsecond execution logs, indicator calculations, risk guard checks, and order lifecycle.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, maxlen: int = 150):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(SystemEventLogger, cls).__new__(cls)
                cls._instance.buffer = deque(maxlen=maxlen)
                cls._instance.log_lock = threading.Lock()
                cls._instance.id_counter = 0
                cls._instance.log("SYSTEM", "Motor A3 Enterprise HFT iniciado y listo para recibir órdenes", symbol="SYSTEM", level="SUCCESS")
            return cls._instance

    def log(self, category: str, message: str, symbol: Optional[str] = None, profile_id: Optional[str] = None, level: str = "INFO"):
        """
        Categories: ORDER, SIGNAL, RISK, TICK, SYSTEM
        Levels: INFO, SUCCESS, WARNING, ERROR
        """
        now_str = time.strftime("%H:%M:%S")
        with self.log_lock:
            self.id_counter += 1
            entry = {
                "id": self.id_counter,
                "time": now_str,
                "timestamp_ms": time.time() * 1000.0,
                "category": category.upper(),
                "level": level.upper(),
                "symbol": symbol or "GLOBAL",
                "profile_id": profile_id or "default",
                "message": message
            }
            self.buffer.append(entry)

    def get_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self.log_lock:
            return list(self.buffer)[-limit:]

    def clear(self):
        with self.log_lock:
            self.buffer.clear()

# Global singleton logger handle
event_logger = SystemEventLogger()
