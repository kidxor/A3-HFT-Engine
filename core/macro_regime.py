"""
A3 Institutional Macro Regime Detector (core/macro_regime.py)
Determines the 4-Hour / Multi-Timeframe Institutional Trend Regime.
Prevents counter-trend trading and chops:
- BULL_REGIME: Only BUY setups permitted.
- BEAR_REGIME: Only SELL setups permitted.
- CHOP_STANDBY: 100% Cash preservation (Zero trades, Zero commissions).
"""

import time
import json
import logging
import urllib.request
from enum import Enum
from dataclasses import dataclass
from typing import Dict, Any, Optional
import pandas as pd
import numpy as np

from strategies.indicators import compute_ema, compute_adx, compute_rsi, compute_atr

logger = logging.getLogger("MacroRegime")


class MacroBias(str, Enum):
    BULL_REGIME = "BULL_REGIME"
    BEAR_REGIME = "BEAR_REGIME"
    CHOP_STANDBY = "CHOP_STANDBY"


@dataclass
class MacroRegimeInfo:
    symbol: str
    bias: MacroBias
    adx: float
    ema20: float
    ema50: float
    last_price: float
    timestamp: float
    description: str
    rsi: float = 50.0

    @property
    def allows_long(self) -> bool:
        return self.bias == MacroBias.BULL_REGIME

    @property
    def allows_short(self) -> bool:
        return self.bias == MacroBias.BEAR_REGIME

    def get(self, key: str, default: Any = None) -> Any:
        d = self.to_dict()
        return d.get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "regime": self.bias.value,
            "bias": self.bias.value,
            "allowed_side": "BUY" if self.allows_long else ("SELL" if self.allows_short else "NONE"),
            "adx_4h": round(self.adx, 1),
            "adx": round(self.adx, 1),
            "rsi_4h": round(self.rsi, 1),
            "ema_20_4h": round(self.ema20, 2),
            "ema_50_4h": round(self.ema50, 2),
            "close_4h": round(self.last_price, 2),
            "reason": self.description,
            "timestamp": self.timestamp,
        }


class MacroRegimeDetector:
    """
    Analyzes 4-Hour and Daily market structure to establish the directional bias.
    Acts as the master traffic light for lower timeframe tactical execution.
    """

    def __init__(self, cache_ttl_sec: int = 900):
        self.cache_ttl_sec = cache_ttl_sec
        self._cache: Dict[str, MacroRegimeInfo] = {}
        self._last_fetch: Dict[str, float] = {}

    def fetch_4h_candles(self, symbol: str, limit: int = 100) -> list:
        """Fetch 4-hour historical OHLCV klines from Bybit REST API."""
        bybit_symbol = symbol.replace("-", "").upper()
        url = (
            f"https://api.bybit.com/v5/market/kline"
            f"?category=spot&symbol={bybit_symbol}&interval=240&limit={min(limit, 100)}"
        )
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "A3-Macro-Regime/2.0"})
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode())
            if data.get("retCode") != 0 or not data.get("result", {}).get("list"):
                raise ValueError(f"Bybit error: {data.get('retMsg')}")
            
            candles = []
            for c in reversed(data["result"]["list"]):
                candles.append({
                    "timestamp": float(c[0]),
                    "open": float(c[1]),
                    "high": float(c[2]),
                    "low": float(c[3]),
                    "close": float(c[4]),
                    "volume": float(c[5]),
                })
            return candles
        except Exception as e:
            logger.warning(f"⚠️ Could not fetch 4H candles for {symbol} from Bybit: {e}")
            return []

    def evaluate_df(self, df: pd.DataFrame, symbol: str) -> MacroRegimeInfo:
        """Evaluates a dataframe of candles directly into a MacroRegimeInfo."""
        now = time.time()
        if len(df) < 30:
            return MacroRegimeInfo(
                symbol=symbol,
                bias=MacroBias.CHOP_STANDBY,
                adx=0.0,
                ema20=0.0,
                ema50=0.0,
                last_price=float(df["close"].iloc[-1]) if not df.empty else 0.0,
                timestamp=now,
                description="Datos insuficientes (< 30 velas) — Standby preventivo",
            )

        close_s = df["close"]
        ema_20 = compute_ema(close_s, 20)
        ema_50 = compute_ema(close_s, 50)
        adx_s = compute_adx(df, 14)
        rsi_s = compute_rsi(close_s, 14)

        c_close = float(close_s.iloc[-1])
        c_ema20 = float(ema_20.iloc[-1]) if not pd.isna(ema_20.iloc[-1]) else c_close
        c_ema50 = float(ema_50.iloc[-1]) if not pd.isna(ema_50.iloc[-1]) else c_close
        c_adx   = float(adx_s.iloc[-1]) if not pd.isna(adx_s.iloc[-1]) else 15.0
        c_rsi   = float(rsi_s.iloc[-1]) if not pd.isna(rsi_s.iloc[-1]) else 50.0

        is_bull_alignment = (c_ema20 > c_ema50) and (c_close >= c_ema50 * 0.995)
        is_bear_alignment = (c_ema20 < c_ema50) and (c_close <= c_ema50 * 1.005)
        is_trending_adx   = c_adx >= 20.0

        if is_bull_alignment and is_trending_adx:
            bias = MacroBias.BULL_REGIME
            reason = (
                f"📈 4H Macro Bull Trend (EMA20 ${c_ema20:.2f} > EMA50 ${c_ema50:.2f}, "
                f"ADX {c_adx:.1f}) — Solo compras (LONGS) autorizadas"
            )
        elif is_bear_alignment and is_trending_adx:
            bias = MacroBias.BEAR_REGIME
            reason = (
                f"📉 4H Macro Bear Trend (EMA20 ${c_ema20:.2f} < EMA50 ${c_ema50:.2f}, "
                f"ADX {c_adx:.1f}) — Solo ventas (SHORTS) autorizadas"
            )
        else:
            bias = MacroBias.CHOP_STANDBY
            reason = (
                f"🛡️ 4H Macro Rango/Consolidación (ADX {c_adx:.1f} < 20 o Medias cruzadas) — "
                f"100% Efectivo (CERO comisiones perdidas en ruido)"
            )

        return MacroRegimeInfo(
            symbol=symbol,
            bias=bias,
            adx=c_adx,
            ema20=c_ema20,
            ema50=c_ema50,
            last_price=c_close,
            timestamp=now,
            description=reason,
            rsi=c_rsi,
        )

    def get_regime(
        self,
        symbol: str,
        fallback_15m_df: Optional[pd.DataFrame] = None,
        force_refresh: bool = False,
    ) -> MacroRegimeInfo:
        """
        Returns macro regime status for the symbol.
        Uses cached result if within cache_ttl_sec.
        """
        now = time.time()
        last_time = self._last_fetch.get(symbol, 0.0)

        if not force_refresh and symbol in self._cache and (now - last_time) < self.cache_ttl_sec:
            return self._cache[symbol]

        candles_4h = self.fetch_4h_candles(symbol, limit=100)
        
        if len(candles_4h) >= 30:
            df = pd.DataFrame(candles_4h)
        elif fallback_15m_df is not None and len(fallback_15m_df) >= 60:
            logger.info(f"Using resampled 15m data for {symbol} macro regime")
            df = fallback_15m_df.copy()
        else:
            regime_info = MacroRegimeInfo(
                symbol=symbol,
                bias=MacroBias.CHOP_STANDBY,
                adx=0.0,
                ema20=0.0,
                ema50=0.0,
                last_price=0.0,
                timestamp=now,
                description="Datos 4H insuficientes — Standby preventivo de capital (CERO comisiones)",
            )
            self._cache[symbol] = regime_info
            self._last_fetch[symbol] = now
            return regime_info

        regime_info = self.evaluate_df(df, symbol)
        self._cache[symbol] = regime_info
        self._last_fetch[symbol] = now
        return regime_info


# Global Singleton
macro_regime_detector = MacroRegimeDetector()
