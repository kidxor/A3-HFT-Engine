import unittest
import os
import pandas as pd
import numpy as np
from core.autonomous_trader import AutonomousTraderAgent, PlaybookLoader


class TestAutonomousTrader(unittest.TestCase):
    def setUp(self):
        self.agent = AutonomousTraderAgent(
            endpoint="http://localhost:11434",
            model="llama3.2:1b",
            db_path=":memory:",
        )
        np.random.seed(42)
        n = 80
        price = 100.0 + np.cumsum(np.random.normal(0.05, 0.3, n))
        self.df = pd.DataFrame({
            "open": price - 0.1,
            "high": price + 0.3,
            "low": price - 0.3,
            "close": price,
            "volume": np.random.uniform(100, 500, n),
        })

    def test_playbook_loader(self):
        loader = PlaybookLoader()
        files = loader.list_files()
        self.assertGreaterEqual(len(files), 4)
        self.assertIn("01_market_structure.md", files)
        self.assertIn("04_risk_and_conviction.md", files)

        content = loader.get_content("01_market_structure.md")
        self.assertIn("Playbook 01", content)

    def test_agent_modes(self):
        self.agent.mode = AutonomousTraderAgent.MODE_ALGORITHMIC
        self.assertEqual(self.agent.mode, "ALGORITHMIC")
        self.agent.mode = AutonomousTraderAgent.MODE_AUTONOMOUS
        self.assertEqual(self.agent.mode, "AUTONOMOUS")
        self.agent.mode = AutonomousTraderAgent.MODE_HYBRID_CONSENSUS
        self.assertEqual(self.agent.mode, "HYBRID_CONSENSUS")

    def test_evaluate_opportunity(self):
        dec = self.agent.evaluate_opportunity(
            symbol="SOL-USDT",
            df_candles=self.df,
            orderbook={"bids": [[100.0, 10.0]], "asks": [[100.1, 10.0]]},
            current_balance=250.0,
            adx_val=32.0,
            atr_val=1.2,
        )
        self.assertIn("action", dec)
        self.assertIn("risk_pct", dec)
        self.assertIn("chain_of_thought", dec)
        self.assertLessEqual(dec["risk_pct"], 0.08)
        self.assertEqual(dec["symbol"], "SOL-USDT")

    def test_post_trade_reflection(self):
        self.agent.record_post_trade_reflection(
            trade_id=1,
            symbol="BTC-USDT",
            pnl=5.25,
            exit_reason="CLOSED_TP",
        )
        status = self.agent.get_status()
        self.assertIn("mode", status)


if __name__ == "__main__":
    unittest.main()
