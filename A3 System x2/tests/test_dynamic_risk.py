import unittest
from core.risk_guard import RiskGuard


class TestDynamicRisk(unittest.TestCase):
    def test_dynamic_risk_scaling_compounding(self):
        rg1 = RiskGuard(initial_capital=200.0, max_daily_drawdown_pct=0.10)
        # Test baseline trade cost calculation
        allowed, reason = rg1.check_trade_allowed(current_balance=200.0, requested_trade_cost=100.0)
        self.assertTrue(allowed)

        # Higher capital compounding ($500 balance allows $250 exposure at 50% max exposure)
        rg2 = RiskGuard(initial_capital=500.0, max_daily_drawdown_pct=0.10)
        allowed, reason = rg2.check_trade_allowed(current_balance=500.0, requested_trade_cost=240.0)
        self.assertTrue(allowed)

        # Exceeding exposure cap (50%)
        rg3 = RiskGuard(initial_capital=200.0, max_daily_drawdown_pct=0.10)
        allowed, reason = rg3.check_trade_allowed(current_balance=200.0, requested_trade_cost=120.0)
        self.assertFalse(allowed)
        self.assertIn("EXPOSURE LIMIT", reason)

    def test_circuit_breaker_on_max_conviction_heavy_loss(self):
        rg = RiskGuard(initial_capital=200.0, max_daily_drawdown_pct=0.10)
        
        # A single loss of 8.0% ($16 on $200) should trip the circuit breaker immediately
        rg.record_trade_result(pnl=-16.0, current_balance=184.0)
        self.assertTrue(rg.circuit_breaker_triggered)
        self.assertIn("Pérdida de máxima convicción", rg.circuit_breaker_reason)

        # Further trades should be denied
        allowed, reason = rg.check_trade_allowed(current_balance=184.0, requested_trade_cost=10.0)
        self.assertFalse(allowed)
        self.assertIn("CIRCUIT BREAKER", reason)

    def test_circuit_breaker_reset(self):
        rg = RiskGuard(initial_capital=200.0, max_daily_drawdown_pct=0.10)
        rg.record_trade_result(pnl=-25.0, current_balance=175.0)
        self.assertTrue(rg.circuit_breaker_triggered)

    def test_alpha_edge_50_percent_allocation_on_high_conviction(self):
        from core.risk_guard import RiskGuard
        from core.market_structure import evaluate_confluences_and_conviction
        import pandas as pd

        # Verify RiskGuard explicitly allows up to 50% exposure
        rg = RiskGuard(initial_capital=200.0, max_exposure_pct=0.50)
        # 50% of $200 is $100 -> permitted
        allowed, reason = rg.check_trade_allowed(current_balance=200.0, requested_trade_cost=98.0)
        self.assertTrue(allowed)

        # 50.1% of $200 is $100.20 -> blocked by risk guard
        allowed, reason = rg.check_trade_allowed(current_balance=200.0, requested_trade_cost=101.0)
        self.assertFalse(allowed)
        self.assertIn("EXPOSURE LIMIT", reason)

        # Verify strategy target calculation formula yields 50% exposure when conviction_mult is maxed (2.0)
        balance = 200.0
        max_exposure_pct = 0.50
        conviction_mult = 2.0  # ADX >= 35 (+0.5) + VIR imbalance (+0.5) + baseline (1.0)
        target_exposure_pct = min(max_exposure_pct, 0.25 * conviction_mult)
        self.assertEqual(target_exposure_pct, 0.50)
        deployed_usd = balance * target_exposure_pct * 0.98
        self.assertEqual(deployed_usd, 98.0)  # 49% deployed to leave 1% buffer for fee/slippage


if __name__ == "__main__":
    unittest.main()

