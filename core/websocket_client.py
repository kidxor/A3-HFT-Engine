import asyncio
import json
import logging
import time
import urllib.request
import random
from typing import Callable, Optional, Dict, Any, List

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("HFT_WebSocket")

class OrderbookTick:
    """Represents a microsecond orderbook update tick."""
    def __init__(self, symbol: str, bids: List[List[float]], asks: List[List[float]], timestamp_ms: float):
        self.symbol = symbol
        self.bids = bids  # List of [price, size] sorted descending
        self.asks = asks  # List of [price, size] sorted ascending
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

def _fetch_kucoin_orderbook(url: str) -> Optional[Dict[str, Any]]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (A3-HFT-Engine/1.0)"})
        with urllib.request.urlopen(req, timeout=1.2) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None

class HFTWebSocketClient:
    """Asynchronous WebSockets & Live Tick Stream Manager for HFT."""
    def __init__(self, symbol: str = "SOL-USDT", on_tick_callback: Optional[Callable[[OrderbookTick], None]] = None):
        self.symbol = symbol
        self.on_tick_callback = on_tick_callback
        self.is_running = True
        self.use_live_market_data = True  # Set to True to fetch real live market data from exchange
        self.tick_fail_count = 0

    def stop(self):
        """Stops the data stream loop."""
        self.is_running = False

    async def start_live_stream(self, interval_seconds: float = 0.2):
        """Unified stream loop supporting 100% Real Live Market Data & Demo Simulation with instant pause/resume."""
        if not hasattr(self, '_stream_started'):
            self._stream_started = True
        logger.info(f"🌐 Data stream loop active for {self.symbol} (running={self.is_running})")

        url = f"https://api.kucoin.com/api/v1/market/orderbook/level2_20?symbol={self.symbol}"
        loop = asyncio.get_running_loop()

        BASE_PRICES = {
            "SOL-USDT": 145.50,
            "BTC-USDT": 65000.0,
            "ETH-USDT": 3400.0,
            "ADA-USDT": 0.45,
            "XRP-USDT": 0.55,
            "AVAX-USDT": 28.0,
            "DOT-USDT": 6.5,
            "LINK-USDT": 14.0
        }
        sim_mid = BASE_PRICES.get(self.symbol, 100.0)
        sim_trend = 0.0
        consecutive_live_fails = 0

        while True:
            # Instant Pause Check — keeps loop alive while paused
            if not self.is_running:
                await asyncio.sleep(0.2)
                continue

            start_t = time.time()
            now_ms = start_t * 1000.0

            if self.use_live_market_data and self.tick_fail_count != -1:
                try:
                    raw_data = await loop.run_in_executor(None, _fetch_kucoin_orderbook, url)
                    if raw_data:
                        orderbook_data = raw_data.get("data", {})
                        bids = [[float(p), float(v)] for p, v in orderbook_data.get("bids", [])]
                        asks = [[float(p), float(v)] for p, v in orderbook_data.get("asks", [])]

                        if bids and asks:
                            tick = OrderbookTick(self.symbol, bids, asks, now_ms)
                            if self.on_tick_callback:
                                if asyncio.iscoroutinefunction(self.on_tick_callback):
                                    await self.on_tick_callback(tick)
                                else:
                                    self.on_tick_callback(tick)
                            consecutive_live_fails = 0
                        else:
                            consecutive_live_fails += 1
                    else:
                        consecutive_live_fails += 1
                except Exception:
                    consecutive_live_fails += 1

                if consecutive_live_fails >= 10:
                    logger.warning(f"⚠️ KuCoin API unreachable — falling back to simulated data for {self.symbol}")
                    self.tick_fail_count = -1
            else:
                # Simulated Market Data Stream (fallback or demo mode)
                if random.random() < 0.25:
                    sim_trend = random.choice([-0.15, 0.15, -0.05, 0.05, 0.0])
                noise = random.gauss(0.0, 0.03)
                sim_mid = max(1.0, sim_mid + sim_trend * 0.2 + noise)
                spread = round(random.choice([0.01, 0.01, 0.02]), 2)
                best_bid = round(sim_mid - (spread / 2.0), 2)
                best_ask = round(best_bid + spread, 2)
                bid_vol_bias = random.uniform(1.5, 6.0) if sim_trend > 0 else random.uniform(0.1, 0.7)
                ask_vol_bias = random.uniform(1.5, 6.0) if sim_trend < 0 else random.uniform(0.1, 0.7)

                bids = []
                asks = []
                for i in range(10):
                    p_bid = round(best_bid - (i * 0.01), 2)
                    p_ask = round(best_ask + (i * 0.01), 2)
                    v_bid = round(random.uniform(5.0, 50.0) * bid_vol_bias, 2)
                    v_ask = round(random.uniform(5.0, 50.0) * ask_vol_bias, 2)
                    bids.append([p_bid, v_bid])
                    asks.append([p_ask, v_ask])

                tick = OrderbookTick(self.symbol, bids, asks, now_ms)
                if self.on_tick_callback:
                    if asyncio.iscoroutinefunction(self.on_tick_callback):
                        await self.on_tick_callback(tick)
                    else:
                        self.on_tick_callback(tick)

            elapsed = time.time() - start_t
            sleep_time = max(0.05, interval_seconds - elapsed)
            await asyncio.sleep(sleep_time)
