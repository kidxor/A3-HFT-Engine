"""
A3 AlphaEdge PRO — Market Structure, S/R, Fibonacci & Orderflow Analysis Engine.
Provides high-precision deterministic tools for the Autonomous Trading Agent.
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple


def detect_swing_points(df: pd.DataFrame, window: int = 3) -> Dict[str, List[Dict[str, Any]]]:
    """
    Detects local Swing Highs and Swing Lows using a rolling fractal window.
    """
    if df is None or len(df) < window * 2 + 1:
        return {"swing_highs": [], "swing_lows": []}

    highs = df["high"].values
    lows = df["low"].values
    timestamps = df["timestamp"].values if "timestamp" in df.columns else np.arange(len(df))

    swing_highs = []
    swing_lows = []

    for i in range(window, len(df) - window):
        # Swing High: Highest in local window
        if highs[i] == np.max(highs[i - window : i + window + 1]):
            swing_highs.append({
                "index": i,
                "price": float(highs[i]),
                "timestamp": float(timestamps[i]),
            })
        # Swing Low: Lowest in local window
        if lows[i] == np.min(lows[i - window : i + window + 1]):
            swing_lows.append({
                "index": i,
                "price": float(lows[i]),
                "timestamp": float(timestamps[i]),
            })

    return {"swing_highs": swing_highs, "swing_lows": swing_lows}


def calculate_fibonacci_levels(df: pd.DataFrame, lookback: int = 60) -> Dict[str, float]:
    """
    Calculates key Fibonacci retracement levels from the dominant recent swing.
    """
    if df is None or len(df) < 10:
        return {}

    sub = df.iloc[-min(lookback, len(df)) :]
    swing_high = float(sub["high"].max())
    swing_low = float(sub["low"].min())
    diff = swing_high - swing_low

    if diff <= 0:
        return {
            "swing_high": swing_high,
            "swing_low": swing_low,
            "fib_0": swing_high,
            "fib_1": swing_low,
        }

    # Standard Retracement Levels
    return {
        "swing_high": round(swing_high, 4),
        "swing_low": round(swing_low, 4),
        "fib_0_236": round(swing_high - 0.236 * diff, 4),
        "fib_0_382": round(swing_high - 0.382 * diff, 4),
        "fib_0_500": round(swing_high - 0.500 * diff, 4),  # Golden zone midpoint
        "fib_0_618": round(swing_high - 0.618 * diff, 4),  # Golden ratio
        "fib_0_786": round(swing_high - 0.786 * diff, 4),  # OTE
    }


def detect_support_resistance_zones(
    df: pd.DataFrame, tolerance_pct: float = 0.004, max_zones: int = 6
) -> List[Dict[str, Any]]:
    """
    Clusters swing points into discrete Support & Resistance horizontal zones.
    """
    swings = detect_swing_points(df, window=2)
    all_points = [p["price"] for p in swings["swing_highs"]] + [p["price"] for p in swings["swing_lows"]]

    if not all_points:
        return []

    all_points.sort()
    clusters: List[List[float]] = []

    for p in all_points:
        matched = False
        for c in clusters:
            avg = np.mean(c)
            if abs(p - avg) / avg <= tolerance_pct:
                c.append(p)
                matched = True
                break
        if not matched:
            clusters.append([p])

    # Rank clusters by number of touches
    zones = []
    current_price = float(df["close"].iloc[-1]) if len(df) > 0 else 0.0

    for c in clusters:
        avg_price = float(np.mean(c))
        touches = len(c)
        zone_type = "RESISTANCE" if avg_price > current_price else "SUPPORT"
        zones.append({
            "price": round(avg_price, 4),
            "touches": touches,
            "type": zone_type,
            "distance_pct": round(abs(avg_price - current_price) / current_price * 100, 2) if current_price > 0 else 0.0,
        })

    zones.sort(key=lambda x: x["touches"], reverse=True)
    return zones[:max_zones]


def detect_market_structure(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Identifies trend alignment, Higher Highs/Lows, BOS (Break of Structure) and CHoCH.
    """
    if df is None or len(df) < 50:
        return {
            "trend": "UNKNOWN",
            "structure": "INSUFFICIENT_DATA",
            "bos_detected": False,
            "choch_detected": False,
            "ema_stack_aligned": False,
        }

    close = df["close"]
    ema20 = close.ewm(span=20).mean().iloc[-1]
    ema50 = close.ewm(span=50).mean().iloc[-1]
    ema200 = close.ewm(span=200).mean().iloc[-1] if len(df) >= 200 else close.ewm(span=len(df)).mean().iloc[-1]
    curr_close = close.iloc[-1]

    bullish_stack = (curr_close > ema20 > ema50 > ema200)
    bearish_stack = (curr_close < ema20 < ema50 < ema200)

    swings = detect_swing_points(df, window=3)
    sh = swings["swing_highs"]
    sl = swings["swing_lows"]

    bos = False
    choch = False
    structure = "RANGO_LATERAL"

    if len(sh) >= 2 and len(sl) >= 2:
        higher_highs = sh[-1]["price"] > sh[-2]["price"]
        higher_lows = sl[-1]["price"] > sl[-2]["price"]
        lower_highs = sh[-1]["price"] < sh[-2]["price"]
        lower_lows = sl[-1]["price"] < sl[-2]["price"]

        if higher_highs and higher_lows and bullish_stack:
            structure = "TENDENCIA_ALCISTA_ESTRUCTURADA"
            bos = curr_close > sh[-1]["price"]
        elif lower_highs and lower_lows and bearish_stack:
            structure = "TENDENCIA_BAJISTA_ESTRUCTURADA"
            bos = curr_close < sl[-1]["price"]
        elif higher_highs and not higher_lows:
            choch = True
            structure = "POSIBLE_CAMBIO_DE_CARACTER"

    trend = "BULLISH" if bullish_stack else ("BEARISH" if bearish_stack else "NEUTRAL")

    return {
        "trend": trend,
        "structure": structure,
        "bos_detected": bos,
        "choch_detected": choch,
        "ema_stack_aligned": (bullish_stack or bearish_stack),
        "ema20": round(float(ema20), 4),
        "ema50": round(float(ema50), 4),
        "ema200": round(float(ema200), 4),
        "current_price": round(float(curr_close), 4),
    }


def analyze_l2_microstructure(orderbook: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Computes Volume Imbalance Ratio (VIR), spread, and orderbook pressure.
    """
    if not orderbook or "bids" not in orderbook or "asks" not in orderbook:
        return {
            "vir": 1.0,
            "bias": "BALANCED",
            "spread_pct": 0.01,
            "bid_depth_usd": 0.0,
            "ask_depth_usd": 0.0,
        }

    bids = orderbook.get("bids", [])[:10]
    asks = orderbook.get("asks", [])[:10]

    bid_vol = sum(float(b[1]) * float(b[0]) for b in bids if len(b) >= 2)
    ask_vol = sum(float(a[1]) * float(a[0]) for a in asks if len(a) >= 2)

    vir = (bid_vol / ask_vol) if ask_vol > 0 else 1.0
    best_bid = float(bids[0][0]) if bids else 0.0
    best_ask = float(asks[0][0]) if asks else 0.0
    mid = (best_bid + best_ask) / 2.0 if (best_bid + best_ask) > 0 else 1.0
    spread_pct = ((best_ask - best_bid) / mid * 100.0) if mid > 0 else 0.0

    if vir >= 1.4:
        bias = "BULLISH_PRESSURE"
    elif vir <= 0.7:
        bias = "BEARISH_PRESSURE"
    else:
        bias = "BALANCED"

    return {
        "vir": round(vir, 2),
        "bias": bias,
        "spread_pct": round(spread_pct, 4),
        "bid_depth_usd": round(bid_vol, 2),
        "ask_depth_usd": round(ask_vol, 2),
    }


def detect_candlestick_patterns(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Detects high-effectiveness candlestick reversal & continuation patterns
    based on '18 Patrones de Velas que Debes Conocer' (Trading FX):
    - Bullish: Martillo (Hammer), Envolvente Alcista (Bullish Engulfing), Estrella Amanecer (Morning Star), Libélula (Dragonfly)
    - Bearish: Estrella Fugaz (Shooting Star), Envolvente Bajista (Bearish Engulfing), Lápida (Gravestone)
    - Risk Guard: Falling Knife detection (cuerpo rojo que cae libre sin mecha de absorción)
    """
    if df is None or len(df) < 2:
        return {
            "patterns": [],
            "has_bullish_pattern": False,
            "has_bearish_pattern": False,
            "is_falling_knife": False,
            "candle_bias": "NEUTRAL",
        }

    c_curr = float(df["close"].iloc[-1])
    o_curr = float(df["open"].iloc[-1])
    h_curr = float(df["high"].iloc[-1])
    l_curr = float(df["low"].iloc[-1])

    c_prev = float(df["close"].iloc[-2])
    o_prev = float(df["open"].iloc[-2])

    body_curr = abs(c_curr - o_curr)
    range_curr = max(0.0001, h_curr - l_curr)
    upper_wick = h_curr - max(o_curr, c_curr)
    lower_wick = min(o_curr, c_curr) - l_curr

    patterns = []
    has_bullish = False
    has_bearish = False

    is_green = c_curr >= o_curr
    is_red = c_curr < o_curr

    # Free-falling candle (knife): strong red candle closing near low, lower wick < 20% of body
    is_falling_knife = is_red and (body_curr >= 0.45 * range_curr) and (lower_wick <= 0.25 * max(0.0001, body_curr))

    # 1. Libélula / Bullish Doji: near-zero body (<= 5% range) with long lower wick
    if body_curr <= 0.05 * range_curr and lower_wick >= 0.65 * range_curr:
        patterns.append("LIBELULA_DOJI")
        has_bullish = True
    # 2. Martillo (Hammer): lower wick >= 1.8x body, body in upper 35% of candle
    elif lower_wick >= 1.8 * max(0.0001, body_curr) and upper_wick <= 0.6 * max(0.0001, body_curr):
        patterns.append("MARTILLO")
        has_bullish = True

    # 3. Envolvente Alcista (Bullish Engulfing): previous red, current green engulfing
    if o_prev > c_prev and is_green and (c_curr >= o_prev) and (o_curr <= c_prev):
        patterns.append("ENVOLVENTE_ALCISTA")
        has_bullish = True

    # 4. Estrella del Amanecer (Morning Star): 3 candles
    if len(df) >= 3:
        c_prev2 = float(df["close"].iloc[-3])
        o_prev2 = float(df["open"].iloc[-3])
        body_prev = abs(c_prev - o_prev)
        if o_prev2 > c_prev2 and body_prev <= 0.35 * abs(o_prev2 - c_prev2) and is_green and c_curr > (c_prev2 + o_prev2) / 2.0:
            patterns.append("ESTRELLA_AMANECER")
            has_bullish = True

    # 5. Estrella Fugaz (Shooting Star): upper wick >= 2x body in upper territory
    if upper_wick >= 1.8 * max(0.0001, body_curr) and lower_wick <= 0.6 * max(0.0001, body_curr):
        patterns.append("ESTRELLA_FUGAZ")
        has_bearish = True

    # 6. Envolvente Bajista (Bearish Engulfing): previous green, current red engulfing
    if c_prev > o_prev and is_red and (o_curr >= c_prev) and (c_curr <= o_prev):
        patterns.append("ENVOLVENTE_BAJISTA")
        has_bearish = True

    # 7. Lápida Doji (Gravestone Doji)
    elif body_curr <= 0.15 * range_curr and upper_wick >= 0.65 * range_curr:
        patterns.append("LAPIDA_DOJI")
        has_bearish = True

    candle_bias = "BULLISH" if has_bullish else ("BEARISH" if has_bearish else ("FALLING_KNIFE" if is_falling_knife else "NEUTRAL"))

    return {
        "patterns": patterns,
        "has_bullish_pattern": has_bullish,
        "has_bearish_pattern": has_bearish,
        "is_falling_knife": is_falling_knife,
        "is_green": is_green,
        "candle_bias": candle_bias,
    }


def evaluate_confluences_and_conviction(
    df: pd.DataFrame, orderbook: Optional[Dict[str, Any]] = None, adx_val: float = 30.0, atr_pct: float = 0.005
) -> Dict[str, Any]:
    """
    Combines Market Structure, S/R, Fibonacci, Candlestick Patterns, and Orderflow to grade setup conviction:
    - 8.0% (A+ Setup: Max Conviction)
    - 5.0% (Standard Setup: Strong Conviction)
    - 0.0% (Neutral: Discard/Wait)
    """
    struct = detect_market_structure(df)
    fibs = calculate_fibonacci_levels(df)
    sr_zones = detect_support_resistance_zones(df)
    l2 = analyze_l2_microstructure(orderbook)
    candle_analysis = detect_candlestick_patterns(df)

    curr_p = struct.get("current_price", 0.0)
    trend = struct.get("trend", "NEUTRAL")
    ema_aligned = struct.get("ema_stack_aligned", False)

    confluences = []
    conviction_score = 0

    # 1. Trend and Stack Confluence (+2 points)
    if ema_aligned and trend in ("BULLISH", "BEARISH"):
        confluences.append(f"Alineación 3-EMA Stack ({trend})")
        conviction_score += 2

    # 2. ADX Trend Strength (+2 points)
    if adx_val >= 30.0:
        confluences.append(f"Fuerza de Tendencia ADX {adx_val:.1f} >= 30")
        conviction_score += 2
    elif adx_val >= 25.0:
        confluences.append(f"Tendencia Moderada ADX {adx_val:.1f} >= 25")
        conviction_score += 1

    # 3. Fibonacci Golden Zone Confluence (+2 points)
    fib_50 = fibs.get("fib_0_500", 0.0)
    fib_618 = fibs.get("fib_0_618", 0.0)
    if curr_p > 0 and fib_50 > 0:
        if abs(curr_p - fib_50) / curr_p <= 0.005 or abs(curr_p - fib_618) / curr_p <= 0.005:
            confluences.append("Rebote en Zona Dorada de Fibonacci (50%-61.8%)")
            conviction_score += 2

    # 4. S/R Zone Confluence (+1 point)
    has_support_touch = False
    has_resistance_touch = False
    for z in sr_zones:
        if z["distance_pct"] <= 0.6 and z["touches"] >= 2:
            confluences.append(f"Zona de {z['type']} probada ({z['touches']} toques) a {z['price']}")
            conviction_score += 1
            if z["type"] == "SUPPORT":
                has_support_touch = True
            elif z["type"] == "RESISTANCE":
                has_resistance_touch = True
            break

    # 5. Candlestick Pattern & Reversal Confluence (+2 or +3 points, from '18 Patrones de Velas')
    has_fib_golden = (curr_p > 0 and fib_50 > 0 and (abs(curr_p - fib_50) / curr_p <= 0.006 or abs(curr_p - fib_618) / curr_p <= 0.006))
    is_reversal_buy = False
    is_reversal_sell = False

    if candle_analysis["has_bullish_pattern"] and not candle_analysis["is_falling_knife"]:
        if has_support_touch or has_fib_golden:
            confluences.append(f"Reversión Alcista en Soporte/Fibonacci ({', '.join(candle_analysis['patterns'])})")
            conviction_score += 3
            is_reversal_buy = True
        elif trend == "BULLISH":
            confluences.append(f"Patrón de Vela Alcista ({', '.join(candle_analysis['patterns'])})")
            conviction_score += 2

    if candle_analysis["has_bearish_pattern"]:
        if has_resistance_touch or has_fib_golden:
            confluences.append(f"Reversión Bajista en Resistencia/Fibonacci ({', '.join(candle_analysis['patterns'])})")
            conviction_score += 3
            is_reversal_sell = True
        elif trend == "BEARISH":
            confluences.append(f"Patrón de Vela Bajista ({', '.join(candle_analysis['patterns'])})")
            conviction_score += 2

    # Anti-Falling Knife Penalty (-3 points to prevent catching falling knives)
    if candle_analysis["is_falling_knife"]:
        conviction_score = max(0, conviction_score - 3)
        is_reversal_buy = False

    # 6. Orderflow Imbalance Confluence (+2 points)
    if (trend == "BULLISH" or is_reversal_buy) and l2["bias"] == "BULLISH_PRESSURE":
        confluences.append(f"Desbalance L2 Comprador Fuerte (VIR {l2['vir']})")
        conviction_score += 2
    elif (trend == "BEARISH" or is_reversal_sell) and l2["bias"] == "BEARISH_PRESSURE":
        confluences.append(f"Desbalance L2 Vendedor Fuerte (VIR {l2['vir']})")
        conviction_score += 2

    # Anti-Chop Protection: Penalize conviction if market structure is a lateral range without reversal pattern
    if struct.get("structure") == "RANGO_LATERAL" and not (is_reversal_buy or is_reversal_sell):
        conviction_score = max(0, conviction_score - 2)

    # Resolve intended action: Reversal setups take priority at inflection points
    if is_reversal_buy:
        candidate_action = "BUY"
    elif is_reversal_sell:
        candidate_action = "SELL"
    elif trend == "BULLISH":
        candidate_action = "BUY"
    elif trend == "BEARISH":
        candidate_action = "SELL"
    else:
        candidate_action = "HOLD"

    # Grade into Conviction Tier (Hardened against low-volatility false breakouts)
    # A+ Setup requires strong confluence (>=6), real volatility (ATR >= 0.20%)
    if conviction_score >= 6 and atr_pct >= 0.0020 and (struct.get("structure") != "RANGO_LATERAL" or is_reversal_buy or is_reversal_sell):
        grade = "A_PLUS_MAX_CONVICTION"
        risk_pct = 0.08  # 8.0%
        action = candidate_action
    elif conviction_score >= 3 and atr_pct >= 0.0008:
        grade = "STANDARD_CONVICTION"
        risk_pct = 0.05  # 5.0%
        action = candidate_action
    else:
        grade = "NEUTRAL_WAIT"
        risk_pct = 0.0
        action = "HOLD"


    return {
        "action": action,
        "grade": grade,
        "risk_pct": risk_pct,
        "conviction_score": conviction_score,
        "confluences": confluences,
        "candles": candle_analysis,
        "structure": struct,
        "fibonacci": fibs,
        "sr_zones": sr_zones,
        "microstructure": l2,
    }
