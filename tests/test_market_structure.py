import unittest
import numpy as np
import pandas as pd
from core.market_structure import (
    detect_swing_points,
    calculate_fibonacci_levels,
    detect_support_resistance_zones,
    detect_market_structure,
    analyze_l2_microstructure,
    evaluate_confluences_and_conviction,
)


class TestMarketStructure(unittest.TestCase):
    def setUp(self):
        np.random.seed(42)
        n = 100
        returns = np.random.normal(0.001, 0.005, n)
        price = 100.0 * np.exp(np.cumsum(returns))
        highs = price * (1 + np.abs(np.random.normal(0.001, 0.002, n)))
        lows = price * (1 - np.abs(np.random.normal(0.001, 0.002, n)))
        opens = np.roll(price, 1)
        opens[0] = 100.0
        self.df = pd.DataFrame({
            "open": opens,
            "high": highs,
            "low": lows,
            "close": price,
            "volume": np.random.uniform(10, 100, n),
        })

    def test_detect_swing_points(self):
        swings = detect_swing_points(self.df, window=2)
        self.assertIn("swing_highs", swings)
        self.assertIn("swing_lows", swings)
        self.assertGreater(len(swings["swing_highs"]), 0)
        self.assertGreater(len(swings["swing_lows"]), 0)

    def test_calculate_fibonacci_levels(self):
        fibs = calculate_fibonacci_levels(self.df, lookback=50)
        self.assertIn("fib_0_500", fibs)
        self.assertIn("fib_0_618", fibs)
        self.assertIn("fib_0_786", fibs)
        self.assertGreater(fibs["swing_high"], fibs["swing_low"])
        self.assertGreater(fibs["fib_0_500"], fibs["fib_0_618"])

    def test_detect_support_resistance_zones(self):
        zones = detect_support_resistance_zones(self.df, max_zones=5)
        self.assertIsInstance(zones, list)
        if len(zones) > 0:
            self.assertIn("price", zones[0])
            self.assertIn("type", zones[0])
            self.assertIn("touches", zones[0])

    def test_detect_market_structure(self):
        struct = detect_market_structure(self.df)
        self.assertIn(struct["trend"], ["BULLISH", "BEARISH", "NEUTRAL"])
        self.assertIn("structure", struct)
        self.assertIn("ema20", struct)
        self.assertIn("ema50", struct)
        self.assertIn("ema200", struct)

    def test_analyze_l2_microstructure(self):
        mock_ob = {
            "bids": [[100.0, 10.0], [99.9, 20.0]],
            "asks": [[100.1, 5.0], [100.2, 5.0]],
        }
        res = analyze_l2_microstructure(mock_ob)
        self.assertGreater(res["vir"], 1.0)
        self.assertEqual(res["bias"], "BULLISH_PRESSURE")

    def test_evaluate_confluences_and_conviction(self):
        res = evaluate_confluences_and_conviction(
            self.df,
            orderbook={"bids": [[100.0, 50.0]], "asks": [[100.1, 10.0]]},
            adx_val=35.0,
            atr_pct=0.006,
        )
        self.assertIn(res["action"], ["BUY", "SELL", "HOLD"])
        self.assertIn(res["grade"], ["A_PLUS_MAX_CONVICTION", "STANDARD_CONVICTION", "NEUTRAL_WAIT"])
        self.assertIn(res["risk_pct"], [0.08, 0.05, 0.0])


if __name__ == "__main__":
    unittest.main()
