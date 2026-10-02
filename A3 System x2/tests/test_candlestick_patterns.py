import unittest
import pandas as pd
from core.market_structure import detect_candlestick_patterns


class TestCandlestickPatterns(unittest.TestCase):
    def test_hammer_detection(self):
        # Hammer: body approx 1/3, long lower shadow (>= 2x body)
        df = pd.DataFrame({
            "open":  [100.0, 99.0, 93.5],
            "high":  [101.0, 99.5, 95.5],
            "low":   [98.5,  97.0, 90.0],
            "close": [99.0,  97.5, 95.0],
        })
        res = detect_candlestick_patterns(df)
        self.assertTrue(res["has_bullish_pattern"])
        self.assertIn("MARTILLO", res["patterns"])

    def test_bullish_engulfing_detection(self):
        # Bullish Engulfing: previous red, current green engulfing
        df = pd.DataFrame({
            "open":  [100.0, 98.0, 95.0],
            "high":  [100.5, 98.5, 99.0],
            "low":   [98.0,  94.5, 94.0],
            "close": [98.0,  95.0, 98.5],
        })
        res = detect_candlestick_patterns(df)
        self.assertTrue(res["has_bullish_pattern"])
        self.assertIn("ENVOLVENTE_ALCISTA", res["patterns"])

    def test_falling_red_candle_has_no_bullish_pattern(self):
        # Free falling candle: red, close < open, close at low
        df = pd.DataFrame({
            "open":  [100.0, 98.0, 96.0],
            "high":  [100.5, 98.2, 96.1],
            "low":   [97.5,  95.8, 93.0],
            "close": [98.0,  96.0, 93.2],
        })
        res = detect_candlestick_patterns(df)
        self.assertFalse(res["has_bullish_pattern"])
        self.assertTrue(res["is_falling_knife"])

    def test_agent_decision_includes_candle_pattern(self):
        from core.autonomous_trader import autonomous_trader
        # Generate 40 synthetic candles
        df = pd.DataFrame({
            "open":  [100.0 + i * 0.1 for i in range(40)],
            "high":  [100.5 + i * 0.1 for i in range(40)],
            "low":   [99.5 + i * 0.1 for i in range(40)],
            "close": [100.2 + i * 0.1 for i in range(40)],
            "volume": [100.0] * 40,
        })
        dec = autonomous_trader.evaluate_opportunity(
            symbol="BTCUSDT",
            df_candles=df,
            orderbook=None,
            async_llm=False,
        )
        self.assertIn("candle_pattern", dec)
        self.assertIn("Vela:", dec["chain_of_thought"])

    def test_strategy_indicators_include_candle_pattern(self):
        from strategies.alpha_edge_strategy import AlphaEdgeStrategy
        strat = AlphaEdgeStrategy()
        df = pd.DataFrame({
            "open":  [100.0 + i * 0.1 for i in range(150)],
            "high":  [100.5 + i * 0.1 for i in range(150)],
            "low":   [99.5 + i * 0.1 for i in range(150)],
            "close": [100.2 + i * 0.1 for i in range(150)],
            "volume": [100.0] * 150,
        })
        sig = strat.evaluate(df, current_balance=200.0)
        self.assertIn("indicators", sig)
        self.assertIn("candle_pattern", sig["indicators"])

    def test_reversal_long_under_ema200(self):
        """Simulates SOL-like scenario from today: price under EMA 200 forms a Hammer at support."""
        from strategies.alpha_edge_strategy import AlphaEdgeStrategy
        strat = AlphaEdgeStrategy()

        # Build 130 candles: first 100 high (105.0), next 28 falling down to 100.0, last candle is a hammer at 100.0
        opens = [105.0] * 80 + [105.0 - i * 0.18 for i in range(48)] + [96.6, 96.5]
        highs = [o + 0.3 for o in opens]
        lows  = [o - 0.3 for o in opens]
        closes = [o - 0.05 for o in opens]

        # The last candle (index -1) is a clear Hammer at support (low=94.0, close=96.4, open=95.5)
        opens[-1] = 95.5
        highs[-1] = 96.6
        lows[-1] = 94.0    # long lower wick (2.4 points wick vs 0.9 body)
        closes[-1] = 96.4

        df = pd.DataFrame({
            "open": opens, "high": highs, "low": lows, "close": closes, "volume": [1000.0] * len(opens)
        })

        sig = strat.evaluate(df, current_balance=200.0)
        self.assertIn(sig["signal"], ["BUY", "NEUTRAL"])
        if sig["signal"] == "BUY":
            self.assertIn("REVERSAL LONG", sig["reason"])
            # SL must be below the hammer low (94.0)
            self.assertLessEqual(sig["sl_price"], 94.0)
            self.assertGreater(sig["tp_price"], sig["entry_price"])

    def test_reversal_short_at_resistance(self):
        """Simulates price rallying into resistance with Shooting Star / Bearish Engulfing."""
        from strategies.alpha_edge_strategy import AlphaEdgeStrategy
        strat = AlphaEdgeStrategy()

        opens = [95.0] * 80 + [95.0 + i * 0.15 for i in range(48)] + [102.2, 102.5]
        highs = [o + 0.3 for o in opens]
        lows  = [o - 0.3 for o in opens]
        closes = [o + 0.05 for o in opens]

        # Last candle: Shooting star (high=105.0, open=102.6, close=102.4, low=102.2)
        opens[-1] = 102.6
        highs[-1] = 105.0   # long upper wick
        lows[-1] = 102.2
        closes[-1] = 102.4

        df = pd.DataFrame({
            "open": opens, "high": highs, "low": lows, "close": closes, "volume": [1000.0] * len(opens)
        })

        sig = strat.evaluate(df, current_balance=200.0)
        self.assertIn(sig["signal"], ["SELL", "NEUTRAL"])
        if sig["signal"] == "SELL":
            self.assertIn("REVERSAL SHORT", sig["reason"])
            # SL must be above shooting star high (105.0)
            self.assertGreaterEqual(sig["sl_price"], 105.0)


if __name__ == "__main__":
    unittest.main()


