import unittest
from core.websocket_client import OrderbookTick
from core.orderbook_engine import OrderbookEngine
from core.hft_execution import HFTExecutionEngine


class TestHFTEngine(unittest.TestCase):
    def test_orderbook_metrics_calculation(self):
        engine = OrderbookEngine(depth_levels=5)

        tick1 = OrderbookTick(
            symbol="SOL-USDT",
            bids=[[145.00, 100.0], [144.99, 50.0]],
            asks=[[145.01, 20.0], [145.02, 30.0]],
            timestamp_ms=1000.0,
        )
        metrics1 = engine.process_tick(tick1)
        self.assertEqual(metrics1["best_bid"], 145.00)
        self.assertEqual(metrics1["best_ask"], 145.01)
        self.assertAlmostEqual(metrics1["spread"], 0.01)
        self.assertGreater(metrics1["micro_price"], metrics1["mid_price"])

    def test_hft_execution_engine(self):
        exec_engine = HFTExecutionEngine(initial_capital=50.0, maker_fee=0.0, slippage_pct=0.0)
        pos = exec_engine.open_position("SOL-USDT", "BUY", 145.00, 0.034, 145.10, 144.90, 1000.0)
        self.assertIsNotNone(pos)
        self.assertEqual(len(exec_engine.active_positions), 1)

        exec_engine.update_positions(current_tick_bid=145.10, current_tick_ask=145.11, timestamp_ms=1050.0)
        self.assertEqual(len(exec_engine.active_positions), 0)
        self.assertEqual(exec_engine.wins, 1)
        self.assertGreater(exec_engine.capital, 50.0)

    def test_asymmetric_1_to_3_rr_no_premature_breakeven(self):
        """Validates that a trade does not choke on micro-pullbacks (no early breakeven at 35%)."""
        exec_engine = HFTExecutionEngine(initial_capital=200.0, maker_fee=0.001, slippage_pct=0.0)
        # Entry 100.0, SL 99.0 (risk 1.0), TP 103.0 (reward 3.0 -> 1:3 R:R)
        pos = exec_engine.open_position("SOL-USDT", "BUY", 100.0, 1.0, 103.0, 99.0, 1000.0)

        # Price advances to 101.0 (33% of TP distance). Old system would have moved SL to 100.28!
        exec_engine.update_positions(current_tick_bid=101.0, current_tick_ask=101.01, timestamp_ms=1010.0)
        # Verify SL is NOT moved to breakeven prematurely
        self.assertEqual(pos.sl_price, 99.0)

        # Price pulls back to 100.20 (above original SL, but would be killed by old 100.28 breakeven)
        exec_engine.update_positions(current_tick_bid=100.20, current_tick_ask=100.21, timestamp_ms=1020.0)
        # Position is STILL alive because it wasn't suffocated
        self.assertEqual(len(exec_engine.active_positions), 1)

        # Price completes the 1:3 run to TP at 103.00
        exec_engine.update_positions(current_tick_bid=103.00, current_tick_ask=103.01, timestamp_ms=1030.0)
        self.assertEqual(len(exec_engine.active_positions), 0)
        self.assertEqual(exec_engine.wins, 1)
        self.assertGreater(exec_engine.capital, 202.0)  # Made ~$2.80+ net of fees instead of $0.01!

    def test_dynamic_runner_expansion_and_instant_exit(self):
        """
        Validates Dual-Decision Architecture:
        Opción A: Does NOT truncate at fixed TP if price keeps pumping; lets it run to 106.00.
        Opción B: Sells INSTANTLY the moment price pulls back from peak, locking in big gain.
        """
        exec_engine = HFTExecutionEngine(
            initial_capital=200.0,
            maker_fee=0.001,
            slippage_pct=0.0,
            enable_dynamic_runner=True,
            runner_trail_pct=0.008,
        )
        # Entry 100.0, SL 99.0, initial TP 103.0 (1:3 R:R)
        pos = exec_engine.open_position("SOL-USDT", "BUY", 100.0, 1.0, 103.0, 99.0, 1000.0, allow_runner=True)
        self.assertIsNotNone(pos)
        self.assertTrue(pos.allow_runner)

        # 1. Price advances past 1.2R to 101.50 -> Breakeven moves SL to >= 100.20
        exec_engine.update_positions(current_tick_bid=101.50, current_tick_ask=101.51, timestamp_ms=1010.0)
        self.assertGreaterEqual(pos.sl_price, 100.20)
        self.assertFalse(pos.runner_mode)

        # 2. Price hits initial TP at 103.00 -> Enters RUNNER MODE (Opción A: NO se sale con ganancia mínima!)
        exec_engine.update_positions(current_tick_bid=103.00, current_tick_ask=103.01, timestamp_ms=1020.0)
        self.assertTrue(pos.runner_mode)
        self.assertEqual(len(exec_engine.active_positions), 1)  # Position remains OPEN to catch big run!
        self.assertGreaterEqual(pos.sl_price, 102.20)          # Guaranteed locked profit floor

        # 3. Price keeps surging to 107.00 (+7% move)!
        exec_engine.update_positions(current_tick_bid=107.00, current_tick_ask=107.01, timestamp_ms=1030.0)
        self.assertEqual(pos.highest_price, 107.00)
        # Trailing stop ratchets to: 107.00 * (1 - 0.008) = 106.144
        expected_floor = round(107.00 * (1 - 0.008), 4)
        self.assertAlmostEqual(pos.sl_price, expected_floor, places=2)
        self.assertEqual(len(exec_engine.active_positions), 1)  # Still riding the wave!

        # 4. Price begins to drop (Opción B: Vender AL INSTANTE al primer retroceso)
        exec_engine.update_positions(current_tick_bid=106.10, current_tick_ask=106.11, timestamp_ms=1040.0)
        self.assertEqual(len(exec_engine.active_positions), 0)  # INSTANT EXIT!
        self.assertEqual(exec_engine.wins, 1)
        self.assertEqual(exec_engine.closed_positions[-1].status, "CLOSED_RUNNER_TRAIL")
        # Profit should be ~$5.90+ instead of the original fixed $2.80!
        self.assertGreater(exec_engine.capital, 205.50)

    def test_candle_by_candle_trailing(self):
        """Validates that completed 5m candles ratchet the stop loss under the candle low."""
        exec_engine = HFTExecutionEngine(
            initial_capital=200.0,
            maker_fee=0.001,
            slippage_pct=0.0,
            enable_dynamic_runner=True,
        )
        pos = exec_engine.open_position("SOL-USDT", "BUY", 100.0, 1.0, 103.0, 99.0, 1000.0, allow_runner=True)
        # Activate runner
        exec_engine.update_positions(current_tick_bid=103.00, current_tick_ask=103.01, timestamp_ms=1010.0)
        self.assertTrue(pos.runner_mode)

        # 5m candle closes with low at 104.50
        exec_engine.update_candle_extremes(
            symbol="SOL-USDT",
            candle_low=104.50,
            candle_high=106.00,
            candle_close=105.80,
            is_bullish=True,
        )
        # Stop loss ratchets up to candle low minus 0.1% buffer (~104.39)
        self.assertGreaterEqual(pos.sl_price, 104.30)

        # Price drops below candle low -> Instant exit
        exec_engine.update_positions(current_tick_bid=104.20, current_tick_ask=104.21, timestamp_ms=1020.0)
        self.assertEqual(len(exec_engine.active_positions), 0)
        self.assertEqual(exec_engine.closed_positions[-1].status, "CLOSED_RUNNER_TRAIL")

    def test_instant_reversal_exit(self):
        """Validates that a detected reversal candle triggers an instant exit."""
        exec_engine = HFTExecutionEngine(
            initial_capital=200.0,
            maker_fee=0.001,
            slippage_pct=0.0,
            enable_dynamic_runner=True,
        )
        pos = exec_engine.open_position("SOL-USDT", "BUY", 100.0, 1.0, 103.0, 99.0, 1000.0, allow_runner=True)
        exec_engine.update_positions(current_tick_bid=103.00, current_tick_ask=103.01, timestamp_ms=1010.0)
        self.assertTrue(pos.runner_mode)

        # Reversal detected at 104.50
        exec_engine.close_on_reversal("SOL-USDT", current_price=104.50, timestamp_ms=1020.0)
        self.assertEqual(len(exec_engine.active_positions), 0)
        self.assertEqual(exec_engine.closed_positions[-1].status, "CLOSED_REVERSAL_EXIT")
        self.assertGreater(exec_engine.capital, 204.0)


if __name__ == "__main__":
    unittest.main()

