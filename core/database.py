import sqlite3
import os
import time
import logging
import threading
from typing import List, Dict, Any, Optional

logger = logging.getLogger("DatabaseManager")

class DatabaseManager:
    """
    SQLite Database Manager for persistent trade logging and performance tracking.
    Stored at: /home/andres/A3-HFT-Engine/data/trades.db
    """
    def __init__(self, db_path: str = None):
        if db_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            data_dir = os.path.join(base_dir, "data")
            os.makedirs(data_dir, exist_ok=True)
            db_path = os.path.join(data_dir, "trades.db")
            
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_tables()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_tables(self):
        """Creates trades and daily_metrics tables if they do not exist."""
        conn = self._get_connection()
        try:
            with conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS trades (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        symbol TEXT NOT NULL,
                        strategy TEXT NOT NULL,
                        side TEXT NOT NULL,
                        entry_price REAL NOT NULL,
                        exit_price REAL NOT NULL,
                        quantity REAL NOT NULL,
                        pnl REAL NOT NULL,
                        return_pct REAL NOT NULL,
                        exit_reason TEXT,
                        timestamp_ms INTEGER NOT NULL,
                        profile_id TEXT DEFAULT 'default',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Check if profile_id column exists (for table migration)
                cursor.execute("PRAGMA table_info(trades)")
                columns = [col[1] for col in cursor.fetchall()]
                if "profile_id" not in columns:
                    cursor.execute("ALTER TABLE trades ADD COLUMN profile_id TEXT DEFAULT 'default'")
                if "fee" not in columns:
                    cursor.execute("ALTER TABLE trades ADD COLUMN fee REAL DEFAULT 0.0")
                
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS daily_summary (
                        date TEXT PRIMARY KEY,
                        start_capital REAL NOT NULL,
                        end_capital REAL NOT NULL,
                        total_trades INTEGER NOT NULL,
                        win_rate_pct REAL NOT NULL,
                        total_pnl REAL NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()
        finally:
            conn.close()
        logger.info(f"💾 SQLite Trade Database initialized at: {self.db_path}")

    def save_trade(
        self,
        symbol: str,
        strategy: str,
        side: str,
        entry_price: float,
        exit_price: float,
        quantity: float,
        pnl: float,
        exit_reason: str,
        timestamp_ms: int = None,
        profile_id: str = "default",
        fee: float = 0.0
    ) -> int:
        """Saves a completed trade into SQLite database."""
        if timestamp_ms is None:
            timestamp_ms = int(time.time() * 1000)
            
        return_pct = (exit_price - entry_price) / entry_price if side == "BUY" else (entry_price - exit_price) / entry_price
        
        with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO trades (symbol, strategy, side, entry_price, exit_price, quantity, pnl, return_pct, exit_reason, timestamp_ms, profile_id, fee)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (symbol, strategy, side, entry_price, exit_price, quantity, pnl, return_pct, exit_reason, timestamp_ms, profile_id, fee))
                    conn.commit()
                    trade_id = cursor.lastrowid
                    logger.info(f"💾 Saved Trade #{trade_id} [{symbol} {side}] PnL: ${pnl:+.4f} Fee: ${fee:.4f} ({exit_reason}) Profile: {profile_id}")
                    return trade_id
            finally:
                conn.close()

    def get_recent_trades(self, limit: int = 50, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieves recent trades from the database."""
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                if symbol:
                    cursor.execute("""
                        SELECT * FROM trades WHERE symbol = ? ORDER BY id DESC LIMIT ?
                    """, (symbol, limit))
                else:
                    cursor.execute("""
                        SELECT * FROM trades ORDER BY id DESC LIMIT ?
                    """, (limit,))
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
            finally:
                conn.close()

    def get_total_summary(self) -> Dict[str, Any]:
        """Calculates total all-time metrics from stored trades."""
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_trades,
                        SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as win_trades,
                        SUM(pnl) as total_pnl,
                        AVG(pnl) as avg_pnl
                    FROM trades
                """)
                row = cursor.fetchone()
                total_trades = row["total_trades"] or 0
                win_trades = row["win_trades"] or 0
                total_pnl = row["total_pnl"] or 0.0
                win_rate = (win_trades / total_trades * 100) if total_trades > 0 else 0.0
                
                return {
                    "total_trades": total_trades,
                    "win_trades": win_trades,
                    "win_rate_pct": round(win_rate, 2),
                    "total_pnl": round(total_pnl, 4),
                    "avg_pnl": round(row["avg_pnl"] or 0.0, 4)
                }
            finally:
                conn.close()

    def clear_all_trades(self):
        """Clears all trades and resets SQLite autoincrement ID."""
        with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM trades")
                    try:
                        cursor.execute("DELETE FROM sqlite_sequence WHERE name='trades'")
                    except sqlite3.OperationalError:
                        pass
                    cursor.execute("DELETE FROM daily_summary")
                    conn.commit()
            finally:
                conn.close()
        logger.info(f"🧹 Cleared all historical trade data from {self.db_path}")
