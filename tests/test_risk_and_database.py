import unittest
import os
import tempfile
from core.risk_guard import RiskGuard
from core.database import DatabaseManager
from core.portfolio_runner import MultiAssetPortfolioRunner, MultiProfileEngineManager


class TestRiskAndDatabase(unittest.TestCase):
    def setUp(self):
        self.risk_guard = RiskGuard(
            initial_capital=100.0,
            max_daily_drawdown_pct=0.05,
            max_consecutive_losses=3,
            max_exposure_pct=0.50,
        )
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(suffix=".db")
        self.db = DatabaseManager(db_path=self.temp_db_path)

    def tearDown(self):
        os.close(self.temp_db_fd)
        if os.path.exists(self.temp_db_path):
            os.remove(self.temp_db_path)

    def test_risk_guard_consecutive_losses_cooldown(self):
        allowed, msg = self.risk_guard.check_trade_allowed(100.0, requested_trade_cost=10.0)
        self.assertTrue(allowed)

        self.risk_guard.record_trade_result(-1.0)
        self.risk_guard.record_trade_result(-1.0)
        self.risk_guard.record_trade_result(-1.0)

        allowed, msg = self.risk_guard.check_trade_allowed(97.0, requested_trade_cost=10.0)
        self.assertFalse(allowed)
        self.assertIn("PAUSED", msg)

    def test_risk_guard_max_drawdown_kill_switch(self):
        self.risk_guard.record_trade_result(-6.0)
        self.assertTrue(self.risk_guard.circuit_breaker_triggered)

        allowed, msg = self.risk_guard.check_trade_allowed(94.0, requested_trade_cost=5.0)
        self.assertFalse(allowed)
        self.assertIn("CIRCUIT BREAKER", msg)

    def test_database_save_and_retrieve_trade(self):
        trade_id = self.db.save_trade(
            symbol="SOL-USDT",
            strategy="alpha_edge",
            side="BUY",
            entry_price=100.0,
            exit_price=104.0,
            quantity=1.0,
            pnl=4.0,
            exit_reason="TP",
            profile_id="alpha_edge_1000",
        )
        self.assertGreater(trade_id, 0)

        recent = self.db.get_recent_trades(limit=10)
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]["symbol"], "SOL-USDT")
        self.assertEqual(recent[0]["profile_id"], "alpha_edge_1000")
        self.assertEqual(recent[0]["pnl"], 4.0)

        summary = self.db.get_total_summary()
        self.assertEqual(summary["total_trades"], 1)
        self.assertEqual(summary["win_trades"], 1)
        self.assertEqual(summary["total_pnl"], 4.0)

    def test_portfolio_runner_initialization(self):
        runner = MultiAssetPortfolioRunner(profile_id="test_runner")
        self.assertIn("SOL-USDT", runner.symbols)
        self.assertEqual(runner.initial_capital, 1000.0)
        self.assertEqual(runner.strategy_name, "alpha_edge")

    def test_portfolio_runner_load_preset(self):
        runner = MultiAssetPortfolioRunner(profile_id="test_runner")
        runner.load_preset("alpha_edge_1000")
        self.assertEqual(runner.initial_capital, 1000.0)
        self.assertEqual(runner.preset_info["badge"], "ALPHAEDGE")

    def test_multi_profile_engine_manager(self):
        manager = MultiProfileEngineManager()
        summary = manager.get_combined_summary()
        self.assertEqual(summary["active_mode"], "single")
        self.assertIn("total_capital", summary)

        manager.select_preset_or_mode("alpha_edge_2500")
        summary2 = manager.get_combined_summary()
        self.assertEqual(summary2["active_mode"], "single")


if __name__ == "__main__":
    unittest.main()
