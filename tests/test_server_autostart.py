import unittest
import time
import server
from core.portfolio_runner import MultiProfileEngineManager

class TestServerAutoStart(unittest.TestCase):
    def test_engine_running_defaults_to_true(self):
        self.assertTrue(server.ENGINE_RUNNING)
        self.assertIsNotNone(server.ENGINE_START_TIME)

    def test_portfolio_manager_initial_state(self):
        manager = MultiProfileEngineManager()
        summary = manager.get_combined_summary()
        self.assertIn("total_capital", summary)
        self.assertIn("risk_guard", summary)
        self.assertEqual(summary["total_capital"], 1000.0)

if __name__ == "__main__":
    unittest.main()
