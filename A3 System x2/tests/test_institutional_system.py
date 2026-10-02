import unittest
import numpy as np
import pandas as pd
from unittest.mock import patch

from core.macro_regime import MacroRegimeDetector, MacroBias, MacroRegimeInfo
from strategies.institutional_trend import InstitutionalTrendStrategy
from core.hft_execution import HFTExecutionEngine, HFTPosition


class TestInstitutionalSystem(unittest.TestCase):
    """Unit tests for the Institutional Positive Expectancy Engine."""

    def test_macro_regime_synthetic_trends(self):
        detector = MacroRegimeDetector(cache_ttl_sec=0)

        # 1. Synthetic Bullish Series: EMA20 > EMA50, price above EMAs, strong trend
        bull_prices = [100.0 + i * 1.5 for i in range(80)]
        df_bull = pd.DataFrame({
            "timestamp": [1000 + i * 14400000 for i in range(80)],
            "open": bull_prices,
            "high": [p + 1.0 for p in bull_prices],
            "low": [p - 0.5 for p in bull_prices],
            "close": bull_prices,
            "volume": [1000.0] * 80,
        })
        regime_bull = detector.evaluate_df(df_bull, "SOL-USDT")
        self.assertEqual(regime_bull.bias, MacroBias.BULL_REGIME)
        self.assertTrue(regime_bull.allows_long)
        self.assertFalse(regime_bull.allows_short)

        # 2. Synthetic Bearish Series: EMA20 < EMA50, price below EMAs, strong trend
        bear_prices = [200.0 - i * 1.5 for i in range(80)]
        df_bear = pd.DataFrame({
            "timestamp": [1000 + i * 14400000 for i in range(80)],
            "open": bear_prices,
            "high": [p + 0.5 for p in bear_prices],
            "low": [p - 1.0 for p in bear_prices],
            "close": bear_prices,
            "volume": [1000.0] * 80,
        })
        regime_bear = detector.evaluate_df(df_bear, "SOL-USDT")
        self.assertEqual(regime_bear.bias, MacroBias.BEAR_REGIME)
        self.assertFalse(regime_bear.allows_long)
        self.assertTrue(regime_bear.allows_short)

        # 3. Synthetic Chop / Flat Series: Oscillating in a tight 0.5 range (ADX < 20)
        chop_prices = [150.0 + (0.3 if i % 2 == 0 else -0.3) for i in range(80)]
        df_chop = pd.DataFrame({
            "timestamp": [1000 + i * 14400000 for i in range(80)],
            "open": chop_prices,
            "high": [p + 0.2 for p in chop_prices],
            "low": [p - 0.2 for p in chop_prices],
            "close": chop_prices,
            "volume": [50.0] * 80,
        })
        regime_chop = detector.evaluate_df(df_chop, "ETH-USDT")
        self.assertEqual(regime_chop.bias, MacroBias.CHOP_STANDBY)
        self.assertFalse(regime_chop.allows_long)
        self.assertFalse(regime_chop.allows_short)

    def test_institutional_trend_strategy_signals(self):
        strat = InstitutionalTrendStrategy(
            ema_fast=10,
            ema_slow=20,
            adx_min=15.0,
            atr_sl_mult=1.6,
            atr_tp_mult=4.5,
        )

        # Create 15m candles
        base = 100.0
        prices = [base + i * 0.8 for i in range(50)]
        # Simulate a pullback candle near EMA
        prices[-2] = prices[-3] - 0.5
        prices[-1] = prices[-2] + 0.6  # Bullish hammer/rejection wick

        df = pd.DataFrame({
            "timestamp": [1000 + i * 900000 for i in range(50)],
            "open": prices,
            "high": [p + 0.8 for p in prices],
            "low": [p - 0.9 for p in prices],
            "close": prices,
            "volume": [500.0] * 50,
        })

        # Mock Macro Regime to BULL_REGIME
        with patch.object(strat.macro_detector, "get_regime") as mock_regime:
            mock_regime.return_value = MacroRegimeInfo(
                symbol="SOL-USDT",
                bias=MacroBias.BULL_REGIME,
                adx=35.0,
                ema20=120.0,
                ema50=110.0,
                last_price=125.0,
                timestamp=0.0,
                description="4H Strong Bull Trend",
            )
            sig = strat.evaluate(df, "SOL-USDT", vir=0.2)
            # Should evaluate and provide high R:R targets if triggered
            if sig.get("signal") == "BUY":
                risk = sig["entry_price"] - sig["sl_price"]
                reward = sig["tp_price"] - sig["entry_price"]
                self.assertGreaterEqual(reward / risk, 2.5)

        # Mock Macro Regime to CHOP_STANDBY
        with patch.object(strat.macro_detector, "get_regime") as mock_regime:
            mock_regime.return_value = MacroRegimeInfo(
                symbol="SOL-USDT",
                bias=MacroBias.CHOP_STANDBY,
                adx=14.0,
                ema20=120.0,
                ema50=120.0,
                last_price=120.0,
                timestamp=0.0,
                description="4H Chop",
            )
            sig = strat.evaluate(df, "SOL-USDT", vir=0.2)
            self.assertEqual(sig.get("signal"), "NEUTRAL")
            self.assertIn("CHOP_STANDBY", sig.get("reason", ""))

    def test_partial_profit_and_breakeven_execution(self):
        engine = HFTExecutionEngine(initial_capital=200.0, trade_cooldown_seconds=0.0, enable_partial_tp=True)

        # Open Long: entry = 100, SL = 98 (R = 2.0), TP = 109, qty = 1.0
        pos = engine.open_position(
            symbol="SOL-USDT",
            side="BUY",
            entry_price=100.0,
            quantity=1.0,
            tp_price=109.0,
            sl_price=98.0,
            timestamp_ms=1000,
        )
        self.assertIsNotNone(pos)
        self.assertEqual(len(engine.active_positions), 1)

        # 1. Price advances to 104.50 (+1.5R gain). Should trigger partial profit 50%
        engine.update_positions(
            current_tick_bid=104.50,
            current_tick_ask=104.51,
            timestamp_ms=2000,
        )

        # Position should still be active, but 50% closed and SL moved to Break-Even (>= 100.0)
        self.assertEqual(len(engine.active_positions), 1)
        active_pos = engine.active_positions[0]
        self.assertTrue(active_pos.is_partial_closed)
        self.assertAlmostEqual(active_pos.quantity, 0.5, places=4)
        self.assertGreaterEqual(active_pos.sl_price, 100.0)

        # 2. Price retraces back to Break-Even stop (100.0)
        engine.update_positions(
            current_tick_bid=100.0,
            current_tick_ask=100.02,
            timestamp_ms=3000,
        )

        # Trade is now completely closed
        self.assertEqual(len(engine.active_positions), 0)
        # Even after retracing to BE, overall trade capital must be positive!
        self.assertGreater(engine.capital, 200.0)
        stats = engine.get_stats()
        self.assertGreater(stats["cum_pnl"], 0.0)


if __name__ == "__main__":
    unittest.main()
