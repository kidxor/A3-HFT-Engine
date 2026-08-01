"""
Market Data Proxy (MDP)
=======================
A lightweight in-process feed server that polls KuCoin ONCE per symbol per
interval and distributes the cached orderbook to all internal consumers.

Architecture
------------
                    ┌──────────────────────────────────────┐
                    │          A3-HFT-Engine Process        │
                    │                                      │
  KuCoin REST API   │  ┌──────────────┐   ┌────────────┐  │
  (1 req / sym)  ──▶│  │MarketData    │──▶│ Bot SOL    │  │
                    │  │Proxy         │──▶│ Bot BTC    │  │
                    │  │(background   │──▶│ Bot ETH    │  │
                    │  │ poller)      │   └────────────┘  │
                    │  └──────────────┘                    │
                    │       ↓  also exposes                │
                    │  GET /proxy/orderbook?symbol=X        │
                    │  GET /proxy/status                    │
                    └──────────────────────────────────────┘

Benefits
--------
- N bots reading the same symbol = 1 KuCoin request (not N)
- Stale-data resilience: last good snapshot served on API failures
- Rate-limit safe: controlled, predictable request rate
- Observable: /proxy/status shows freshness per symbol
"""

import json
import logging
import threading
import time
import urllib.request
from typing import Dict, Any, List, Optional

logger = logging.getLogger("MarketDataProxy")


DEFAULT_ALL_SYMBOLS = [
    "SOL-USDT", "BTC-USDT", "ETH-USDT", "ADA-USDT",
    "XRP-USDT", "AVAX-USDT", "DOT-USDT", "LINK-USDT",
]


# ---------------------------------------------------------------------------
# Internal snapshot type
# ---------------------------------------------------------------------------

class _Snapshot:
    """Holds the latest orderbook snapshot for one symbol."""
    __slots__ = ("bids", "asks", "timestamp_ms", "fetch_count", "error_count", "last_error")

    def __init__(self):
        self.bids: List[List[float]] = []
        self.asks: List[List[float]] = []
        self.timestamp_ms: float = 0.0
        self.fetch_count: int = 0
        self.error_count: int = 0
        self.last_error: str = ""

    @property
    def age_ms(self) -> float:
        if self.timestamp_ms == 0.0:
            return float("inf")
        return time.time() * 1000.0 - self.timestamp_ms

    @property
    def is_fresh(self) -> bool:
        """True if the snapshot is less than 5 seconds old."""
        return self.age_ms < 5000.0

    def to_kucoin_format(self) -> Dict[str, Any]:
        """Returns data in the same structure as KuCoin's REST response."""
        return {
            "code": "200000",
            "data": {
                "bids": [[str(p), str(v)] for p, v in self.bids],
                "asks": [[str(p), str(v)] for p, v in self.asks],
                "time": int(self.timestamp_ms),
            },
        }


# ---------------------------------------------------------------------------
# Market Data Proxy
# ---------------------------------------------------------------------------

class MarketDataProxy:
    """
    Polls KuCoin's orderbook REST endpoint for configured symbols and
    caches the results in memory.  Internal consumers call get_orderbook()
    directly (no HTTP hop).  External clients can hit /proxy/orderbook.
    """

    KUCOIN_ENDPOINT = (
        "https://api.kucoin.com/api/v1/market/orderbook/level2_20?symbol={symbol}"
    )

    def __init__(
        self,
        symbols: Optional[List[str]] = None,
        interval_ms: int = 300,
        timeout_s: float = 1.5,
    ):
        if not symbols:
            symbols = DEFAULT_ALL_SYMBOLS
        self.symbols     = list(dict.fromkeys(list(symbols) + DEFAULT_ALL_SYMBOLS))
        self.interval_ms = max(100, interval_ms)     # minimum 100ms safety floor
        self.timeout_s   = timeout_s

        self._snapshots: Dict[str, _Snapshot] = {sym: _Snapshot() for sym in self.symbols}
        self._lock    = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        """Starts the background polling thread (non-blocking)."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._poll_loop,
            name="MarketDataProxy",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            f"📡 MarketDataProxy started — tracking {len(self.symbols)} symbols: {self.symbols} "
            f"@ {self.interval_ms}ms interval"
        )

    def stop(self):
        """Signals the polling thread to stop."""
        self._running = False
        logger.info("📡 MarketDataProxy stopped.")

    def update_symbols(self, symbols: List[str]):
        """Hot-swap or add to the symbol list without restarting the proxy."""
        with self._lock:
            all_syms = list(dict.fromkeys(list(symbols) + DEFAULT_ALL_SYMBOLS))
            new_set  = set(all_syms)
            old_set  = set(self._snapshots.keys())

            for sym in new_set - old_set:
                self._snapshots[sym] = _Snapshot()
                logger.info(f"📡 MDP: Added symbol {sym}")

            self.symbols = all_syms

    # ------------------------------------------------------------------
    # Internal polling
    # ------------------------------------------------------------------

    def _fetch_one(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetches one symbol from KuCoin. Returns raw API dict or None."""
        url = self.KUCOIN_ENDPOINT.format(symbol=symbol)
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (A3-HFT-Engine/MDP/1.0)"},
            )
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                return json.loads(resp.read().decode())
        except Exception as exc:
            return {"_error": str(exc)}

    def _poll_loop(self):
        """Background thread: round-robins through symbols, sleeping between fetches."""
        interval_s = self.interval_ms / 1000.0
        logger.info("📡 MDP polling loop started.")

        while self._running:
            loop_start = time.time()

            with self._lock:
                symbols = list(self._snapshots.keys())

            for sym in symbols:
                if not self._running:
                    break

                fetch_start = time.time()
                raw = self._fetch_one(sym)
                fetch_ms = (time.time() - fetch_start) * 1000.0

                with self._lock:
                    if sym not in self._snapshots:
                        continue
                    snap = self._snapshots[sym]
                    snap.fetch_count += 1

                    if raw and "_error" not in raw and raw.get("code") == "200000":
                        ob = raw.get("data", {})
                        bids_raw = ob.get("bids", [])
                        asks_raw = ob.get("asks", [])

                        snap.bids = [[float(p), float(v)] for p, v in bids_raw]
                        snap.asks = [[float(p), float(v)] for p, v in asks_raw]
                        snap.timestamp_ms = time.time() * 1000.0
                        snap.last_error = ""
                    else:
                        snap.error_count += 1
                        snap.last_error = (
                            raw.get("_error", "unknown") if raw else "null response"
                        )
                        if snap.error_count % 10 == 1:
                            logger.warning(
                                f"📡 MDP fetch error for {sym}: {snap.last_error} "
                                f"(errors: {snap.error_count})"
                            )

                # Small sleep between symbol fetches to avoid bursting
                time.sleep(max(0.01, (interval_s / max(1, len(symbols))) - fetch_ms / 1000.0))

            # Wait for the remaining interval
            elapsed = time.time() - loop_start
            remaining = interval_s - elapsed
            if remaining > 0:
                time.sleep(remaining)

        logger.info("📡 MDP polling loop exited.")

    # ------------------------------------------------------------------
    # Consumer API
    # ------------------------------------------------------------------

    def get_orderbook(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Returns the cached orderbook for a symbol in KuCoin format.
        Returns None if the symbol is unknown or has never been fetched.
        """
        with self._lock:
            snap = self._snapshots.get(symbol)
        if snap is None or snap.timestamp_ms == 0.0:
            return None
        return snap.to_kucoin_format()

    def get_best_bid_ask(self, symbol: str):
        """
        Returns (best_bid: float, best_ask: float) or (0.0, 0.0) if unavailable.
        """
        with self._lock:
            snap = self._snapshots.get(symbol)
        if snap is None or not snap.bids or not snap.asks:
            return 0.0, 0.0
        return snap.bids[0][0], snap.asks[0][0]

    def get_ticker(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Returns single-symbol ticker information (price, bid, ask, spread, age)."""
        with self._lock:
            snap = self._snapshots.get(symbol)
        if snap is None or snap.timestamp_ms == 0.0 or not snap.bids or not snap.asks:
            return None
        bid = snap.bids[0][0]
        ask = snap.asks[0][0]
        mid = (bid + ask) / 2.0
        spread = max(0.0, ask - bid)
        return {
            "symbol":       symbol,
            "best_bid":     bid,
            "best_ask":     ask,
            "mid_price":    round(mid, 4),
            "spread":       round(spread, 4),
            "timestamp_ms": snap.timestamp_ms,
            "is_fresh":     snap.is_fresh,
        }

    def get_all_tickers(self) -> Dict[str, Dict[str, Any]]:
        """Returns ticker information for ALL tracked symbols."""
        tickers = {}
        with self._lock:
            symbols = list(self._snapshots.keys())
        for sym in symbols:
            t = self.get_ticker(sym)
            if t:
                tickers[sym] = t
        return tickers

    def is_ready(self, symbol: str) -> bool:
        """True if we have at least one successful fetch for this symbol."""
        with self._lock:
            snap = self._snapshots.get(symbol)
        return snap is not None and snap.timestamp_ms > 0.0

    def get_status(self) -> Dict[str, Any]:
        """Returns proxy health status (used by /proxy/status endpoint)."""
        with self._lock:
            snaps = dict(self._snapshots)

        symbols_status = {}
        for sym, snap in snaps.items():
            symbols_status[sym] = {
                "fresh":        snap.is_fresh,
                "age_ms":       round(snap.age_ms, 0) if snap.timestamp_ms > 0 else None,
                "fetch_count":  snap.fetch_count,
                "error_count":  snap.error_count,
                "last_error":   snap.last_error or None,
                "best_bid":     snap.bids[0][0] if snap.bids else None,
                "best_ask":     snap.asks[0][0] if snap.asks else None,
            }

        return {
            "running":       self._running,
            "interval_ms":   self.interval_ms,
            "symbol_count":  len(self.symbols),
            "symbols":       self.symbols,
            "symbol_status": symbols_status,
        }


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_proxy_instance: Optional[MarketDataProxy] = None


def get_proxy() -> Optional[MarketDataProxy]:
    """Returns the global MarketDataProxy instance (None if not started)."""
    return _proxy_instance


def init_proxy(
    symbols: Optional[List[str]] = None,
    interval_ms: int = 300,
    timeout_s: float = 1.5,
) -> MarketDataProxy:
    """Initializes and starts the global Market Data Proxy singleton."""
    global _proxy_instance
    if _proxy_instance is not None:
        if symbols:
            _proxy_instance.update_symbols(symbols)
        return _proxy_instance

    _proxy_instance = MarketDataProxy(
        symbols=symbols,
        interval_ms=interval_ms,
        timeout_s=timeout_s,
    )
    _proxy_instance.start()
    return _proxy_instance
