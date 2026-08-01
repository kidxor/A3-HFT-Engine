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

    Performance settings:
    - WAL journal mode   : concurrent reads + writes without locking
    - cache_size=-64000  : 64 MB in-process page cache
    - synchronous=NORMAL : fsync only at checkpoints (safe + fast)
    - temp_store=MEMORY  : temp tables kept in RAM
    - 4 indexes on trades: eliminates full-table scans for KPI queries
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

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA cache_size=-64000")     # 64 MB page cache
        conn.execute("PRAGMA synchronous=NORMAL")    # safe + fast
        conn.execute("PRAGMA temp_store=MEMORY")     # temp tables in RAM
        return conn

    def _init_tables(self):
        """Creates trades / daily_summary tables and performance indexes."""
        conn = self._get_connection()
        try:
            with conn:
                cur = conn.cursor()

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS trades (
                        id           INTEGER PRIMARY KEY AUTOINCREMENT,
                        symbol       TEXT    NOT NULL,
                        strategy     TEXT    NOT NULL,
                        side         TEXT    NOT NULL,
                        entry_price  REAL    NOT NULL,
                        exit_price   REAL    NOT NULL,
                        quantity     REAL    NOT NULL,
                        pnl          REAL    NOT NULL,
                        return_pct   REAL    NOT NULL,
                        exit_reason  TEXT,
                        timestamp_ms INTEGER NOT NULL,
                        profile_id   TEXT    DEFAULT 'default',
                        fee          REAL    DEFAULT 0.0,
                        created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Schema migrations (idempotent)
                cur.execute("PRAGMA table_info(trades)")
                existing_cols = {col[1] for col in cur.fetchall()}
                if "profile_id" not in existing_cols:
                    cur.execute("ALTER TABLE trades ADD COLUMN profile_id TEXT DEFAULT 'default'")
                if "fee" not in existing_cols:
                    cur.execute("ALTER TABLE trades ADD COLUMN fee REAL DEFAULT 0.0")

                # Performance indexes
                cur.execute("CREATE INDEX IF NOT EXISTS idx_trades_id ON trades (id DESC)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_trades_symbol_strategy ON trades (symbol, strategy)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_trades_pnl ON trades (pnl)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_trades_profile ON trades (profile_id)")

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS daily_summary (
                        date          TEXT PRIMARY KEY,
                        start_capital REAL    NOT NULL,
                        end_capital   REAL    NOT NULL,
                        total_trades  INTEGER NOT NULL,
                        win_rate_pct  REAL    NOT NULL,
                        total_pnl     REAL    NOT NULL,
                        created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()
        finally:
            conn.close()
        logger.info(f"💾 SQLite Trade Database initialized at: {self.db_path}")

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

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
        fee: float = 0.0,
    ) -> int:
        """Saves a completed trade into SQLite database."""
        if timestamp_ms is None:
            timestamp_ms = int(time.time() * 1000)

        if entry_price and entry_price > 0:
            return_pct = (
                (exit_price - entry_price) / entry_price
                if side == "BUY"
                else (entry_price - exit_price) / entry_price
            )
        else:
            return_pct = 0.0

        with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    cur = conn.cursor()
                    cur.execute(
                        """
                        INSERT INTO trades
                            (symbol, strategy, side, entry_price, exit_price,
                             quantity, pnl, return_pct, exit_reason,
                             timestamp_ms, profile_id, fee)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (symbol, strategy, side, entry_price, exit_price,
                         quantity, pnl, return_pct, exit_reason,
                         timestamp_ms, profile_id, fee),
                    )
                    conn.commit()
                    trade_id = cur.lastrowid
                logger.info(
                    f"💾 Trade #{trade_id} [{symbol} {side}] "
                    f"PnL: ${pnl:+.4f} Fee: ${fee:.4f} ({exit_reason}) Profile: {profile_id}"
                )
                return trade_id
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_recent_trades(self, limit: int = 50, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieves recent trades (uses idx_trades_id for O(log n) lookup)."""
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                if symbol:
                    cur.execute(
                        "SELECT * FROM trades WHERE symbol = ? ORDER BY id DESC LIMIT ?",
                        (symbol, limit),
                    )
                else:
                    cur.execute(
                        "SELECT * FROM trades ORDER BY id DESC LIMIT ?",
                        (limit,),
                    )
                return [dict(row) for row in cur.fetchall()]
            finally:
                conn.close()

    def get_total_summary(self) -> Dict[str, Any]:
        """
        All-time KPI aggregation using index-covered query.
        Returns zeros safely when the table is empty (no division-by-zero).
        """
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                cur.execute("""
                    SELECT
                        COUNT(*)                                    AS total_trades,
                        SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END)  AS win_trades,
                        SUM(pnl)                                    AS total_pnl,
                        AVG(pnl)                                    AS avg_pnl
                    FROM trades
                """)
                row = cur.fetchone()
                total_trades = row["total_trades"] or 0
                win_trades   = row["win_trades"]   or 0
                total_pnl    = float(row["total_pnl"] or 0.0)
                avg_pnl      = float(row["avg_pnl"]   or 0.0)
                win_rate     = (win_trades / total_trades * 100.0) if total_trades > 0 else 0.0

                return {
                    "total_trades": total_trades,
                    "win_trades":   win_trades,
                    "win_rate_pct": round(win_rate, 2),
                    "total_pnl":    round(total_pnl, 4),
                    "avg_pnl":      round(avg_pnl, 4),
                }
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def clear_all_trades(self):
        """Clears all trades and resets autoincrement counter."""
        with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    cur = conn.cursor()
                    cur.execute("DELETE FROM trades")
                    try:
                        cur.execute("DELETE FROM sqlite_sequence WHERE name='trades'")
                    except sqlite3.OperationalError:
                        pass
                    cur.execute("DELETE FROM daily_summary")
                    conn.commit()
            finally:
                conn.close()
        logger.info(f"🧹 Cleared all historical trade data from {self.db_path}")
