import unittest
from core.websocket_client import OrderbookTick
from core.orderbook_engine import OrderbookEngine
from strategies.alpha_edge_strategy import AlphaEdgeStrategy
from core.hft_execution import HFTExecutionEngine


class TestAlphaEdge(unittest.TestCase):
    def test_indicator_computation(self):
        import pandas as pd
        import numpy as np
        strat = AlphaEdgeStrategy()
        np.random.seed(42)
        n = 250
        close = 100 + np.random.randn(n).cumsum() * 0.5
        data = pd.DataFrame({
            'open': close - np.random.uniform(0, 0.3, n),
            'high': close + np.random.uniform(0, 0.5, n),
            'low': close - np.random.uniform(0, 0.5, n),
            'close': close,
            'volume': np.random.uniform(100, 1000, n),
        })
        result = strat.compute_indicators(data)
        self.assertIn('ema_fast', result.columns)
        self.assertIn('ema_slow', result.columns)
        self.assertIn('adx', result.columns)
        self.assertIn('rsi', result.columns)
        self.assertIn('atr', result.columns)

    def test_insufficient_data_returns_neutral(self):
        import pandas as pd
        strat = AlphaEdgeStrategy()
        data = pd.DataFrame({'open': [1]*10, 'high': [2]*10, 'low': [0.5]*10, 'close': [1]*10, 'volume': [100]*10})
        result = strat.evaluate(data, current_balance=1000.0)
        self.assertEqual(result["signal"], "NEUTRAL")

    def test_execution_engine_with_zero_fees(self):
        exec_engine = HFTExecutionEngine(initial_capital=50.0, maker_fee=0.0, slippage_pct=0.0)
        pos = exec_engine.open_position("SOL-USDT", "BUY", 145.00, 0.034, 145.10, 144.90, 1000.0)
        self.assertIsNotNone(pos)
        self.assertEqual(len(exec_engine.active_positions), 1)
        exec_engine.update_positions(current_tick_bid=145.10, current_tick_ask=145.11, timestamp_ms=1050.0)
        self.assertEqual(len(exec_engine.active_positions), 0)
        self.assertEqual(exec_engine.wins, 1)
        self.assertGreater(exec_engine.capital, 50.0)



class TestStrategyRegistry(unittest.TestCase):
    def test_registry_contains_strategies(self):
        from strategies import STRATEGY_REGISTRY, DEFAULT_STRATEGY
        self.assertIn("alpha_edge", STRATEGY_REGISTRY)
        self.assertIn("orderbook_scalper", STRATEGY_REGISTRY)
        self.assertEqual(DEFAULT_STRATEGY, "alpha_edge")

    def test_orderbook_scalper_returns_neutral_without_metrics(self):
        from strategies.orderbook_scalper import OrderbookScalperStrategy
        strat = OrderbookScalperStrategy()
        import pandas as pd
        df = pd.DataFrame({'close': [100]*10})
        result = strat.evaluate(df, current_balance=1000.0, latest_metrics=None)
        self.assertEqual(result["signal"], "NEUTRAL")
        self.assertIn("Sin datos", result["reason"])

    def test_orderbook_scalper_buy_signal(self):
        from strategies.orderbook_scalper import OrderbookScalperStrategy
        strat = OrderbookScalperStrategy(vir_threshold=1.5, target_ticks=10, stop_ticks=5, tick_size=0.01)
        import pandas as pd
        df = pd.DataFrame({'close': [100]*10})
        metrics = {
            "volume_imbalance": 2.5,
            "ofi_delta": 5.0,
            "mid_price": 100.0,
            "spread": 0.02,
            "best_bid": 99.99,
            "best_ask": 100.01,
        }
        result = strat.evaluate(df, current_balance=1000.0, latest_metrics=metrics)
        self.assertEqual(result["signal"], "BUY")
        self.assertGreater(result["position_size"], 0)

    def test_orderbook_scalper_sell_signal(self):
        from strategies.orderbook_scalper import OrderbookScalperStrategy
        strat = OrderbookScalperStrategy(vir_threshold=1.5, target_ticks=10, stop_ticks=5, tick_size=0.01)
        import pandas as pd
        df = pd.DataFrame({'close': [100]*10})
        metrics = {
            "volume_imbalance": 0.4,
            "ofi_delta": -5.0,
            "mid_price": 100.0,
            "spread": 0.02,
            "best_bid": 99.99,
            "best_ask": 100.01,
        }
        result = strat.evaluate(df, current_balance=1000.0, latest_metrics=metrics)
        self.assertEqual(result["signal"], "SELL")
        self.assertGreater(result["position_size"], 0)


if __name__ == "__main__":
    unittest.main()
