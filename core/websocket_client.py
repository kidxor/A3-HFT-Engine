"""
HFT WebSocket / Tick Stream Client
===================================
Supports two data sources (selected per-instance):

  1. MarketDataProxy (preferred when available)
     Reads the in-process cached orderbook directly — zero HTTP cost.
     Falls back to KuCoin REST if the proxy snapshot is stale.

  2. KuCoin REST API (direct)
     Used when the proxy is not initialized or unavailable.
     Falls back to simulated data after 10 consecutive failures.

  3. Simulated data (fallback / demo mode)
     Gaussian random-walk orderbook for offline testing.
"""

import asyncio
import json
import logging
import time
import urllib.request
import random
from typing import Callable, Optional, Dict, Any, List

logger = logging.getLogger("HFT_WebSocket")


class OrderbookTick:
    """Represents a microsecond orderbook update tick."""

    def __init__(
        self,
        symbol: str,
        bids: List[List[float]],
        asks: List[List[float]],
        timestamp_ms: float,
    ):
        self.symbol       = symbol
        self.bids         = bids   # [[price, size], ...] sorted descending
        self.asks         = asks   # [[price, size], ...] sorted ascending
        self.timestamp_ms = timestamp_ms

    @property
    def best_bid(self) -> float:
        return self.bids[0][0] if self.bids else 0.0

    @property
    def best_ask(self) -> float:
        return self.asks[0][0] if self.asks else 0.0

    @property
    def mid_price(self) -> float:
        if self.best_bid and self.best_ask:
            return (self.best_bid + self.best_ask) / 2.0
        return self.best_bid or self.best_ask

    @property
    def spread(self) -> float:
        return max(0.0, self.best_ask - self.best_bid)


def _fetch_kucoin_orderbook(url: str, timeout: float = 1.2) -> Optional[Dict[str, Any]]:
    """Direct KuCoin REST fetch (used as fallback when proxy is unavailable)."""
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (A3-HFT-Engine/1.0)"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None


def _parse_kucoin_response(raw: Dict[str, Any], symbol: str, now_ms: float) -> Optional["OrderbookTick"]:
    """Parses a KuCoin-format orderbook response into an OrderbookTick."""
    if not raw or raw.get("code") != "200000":
        return None
    ob = raw.get("data", {})
    bids_raw = ob.get("bids", [])
    asks_raw = ob.get("asks", [])
    if not bids_raw or not asks_raw:
        return None
    bids = [[float(p), float(v)] for p, v in bids_raw]
    asks = [[float(p), float(v)] for p, v in asks_raw]
    return OrderbookTick(symbol, bids, asks, now_ms)


class HFTWebSocketClient:
    """
    Asynchronous tick stream manager.

    Priority order for data sourcing:
      1. In-process MarketDataProxy (if initialized and snapshot is fresh)
      2. Direct KuCoin REST API
      3. Simulated random-walk (demo / offline fallback)
    """

    def __init__(
        self,
        symbol: str = "SOL-USDT",
        on_tick_callback: Optional[Callable[["OrderbookTick"], None]] = None,
    ):
        self.symbol           = symbol
        self.on_tick_callback = on_tick_callback
        self.is_running       = True
        self.use_live_market_data = True

        # Explicit fallback flag (replaced magic number -1)
        self._using_simulated_fallback: bool = False
        self._consecutive_live_fails:   int  = 0

    def stop(self):
        """Signals the stream loop to exit."""
        self.is_running = False

    async def start_live_stream(self, interval_seconds: float = 0.2):
        """
        Unified stream loop.  Tries proxy → KuCoin REST → simulated data,
        in that order.
        """
        logger.info(
            f"🌐 Data stream loop active for {self.symbol} "
            f"(running={self.is_running})"
        )

        kucoin_url = (
            f"https://api.kucoin.com/api/v1/market/orderbook/level2_20"
            f"?symbol={self.symbol}"
        )
        loop = asyncio.get_running_loop()

        # Simulated market baseline prices (demo / fallback mode)
        BASE_PRICES: Dict[str, float] = {
            "SOL-USDT":  145.50,
            "BTC-USDT":  65000.0,
            "ETH-USDT":  3400.0,
            "ADA-USDT":  0.45,
            "XRP-USDT":  0.55,
            "AVAX-USDT": 28.0,
            "DOT-USDT":  6.5,
            "LINK-USDT": 14.0,
        }
        sim_mid   = BASE_PRICES.get(self.symbol, 100.0)
        sim_trend = 0.0

        while True:
            # Instant pause — keeps loop alive while engine is paused
            if not self.is_running:
                await asyncio.sleep(0.2)
                continue

            start_t = time.time()
            now_ms  = start_t * 1000.0
            tick: Optional[OrderbookTick] = None

            if self.use_live_market_data and not self._using_simulated_fallback:
                # ── 1. Try MarketDataProxy (in-process, zero cost) ──────
                try:
                    from core.market_data_proxy import get_proxy
                    proxy = get_proxy()
                    if proxy is not None and proxy.is_ready(self.symbol):
                        raw = proxy.get_orderbook(self.symbol)
                        tick = _parse_kucoin_response(raw, self.symbol, now_ms)
                except ImportError:
                    proxy = None

                # ── 2. Fallback: Direct KuCoin REST ─────────────────────
                if tick is None:
                    raw = await loop.run_in_executor(
                        None, _fetch_kucoin_orderbook, kucoin_url
                    )
                    tick = _parse_kucoin_response(raw, self.symbol, now_ms) if raw else None

                    if tick is not None:
                        self._consecutive_live_fails = 0
                    else:
                        self._consecutive_live_fails += 1
                        if self._consecutive_live_fails >= 10:
                            logger.warning(
                                f"⚠️ KuCoin API unreachable after 10 attempts — "
                                f"switching to simulated data for {self.symbol}"
                            )
                            self._using_simulated_fallback = True

            # ── 3. Simulated random-walk ─────────────────────────────────
            if tick is None:
                if random.random() < 0.25:
                    sim_trend = random.choice([-0.15, 0.15, -0.05, 0.05, 0.0])
                noise   = random.gauss(0.0, 0.03)
                sim_mid = max(1.0, sim_mid + sim_trend * 0.2 + noise)
                spread  = round(random.choice([0.01, 0.01, 0.02]), 2)
                best_bid = round(sim_mid - spread / 2.0, 2)
                best_ask = round(best_bid + spread, 2)

                bid_bias = random.uniform(1.5, 6.0) if sim_trend > 0 else random.uniform(0.1, 0.7)
                ask_bias = random.uniform(1.5, 6.0) if sim_trend < 0 else random.uniform(0.1, 0.7)

                bids = [
                    [round(best_bid - i * 0.01, 2), round(random.uniform(5.0, 50.0) * bid_bias, 2)]
                    for i in range(10)
                ]
                asks = [
                    [round(best_ask + i * 0.01, 2), round(random.uniform(5.0, 50.0) * ask_bias, 2)]
                    for i in range(10)
                ]
                tick = OrderbookTick(self.symbol, bids, asks, now_ms)

            if tick is not None:
                await self._dispatch(tick)

            elapsed    = time.time() - start_t
            sleep_time = max(0.05, interval_seconds - elapsed)
            await asyncio.sleep(sleep_time)

    async def _dispatch(self, tick: "OrderbookTick"):
        """Dispatches tick to callback, supporting both sync and async."""
        if self.on_tick_callback:
            if asyncio.iscoroutinefunction(self.on_tick_callback):
                await self.on_tick_callback(tick)
            else:
                self.on_tick_callback(tick)
