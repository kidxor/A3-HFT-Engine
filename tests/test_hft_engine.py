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


if __name__ == "__main__":
    unittest.main()
