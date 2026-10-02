import unittest
from datetime import datetime, timezone
from core.macro_shield import MacroEconomicShield


class TestMacroShield(unittest.TestCase):
    def setUp(self):
        self.shield = MacroEconomicShield(enabled=True)

    def test_outside_blackout_allowed(self):
        # Monday 10:00 UTC (no news window)
        dt = datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc)
        active, reason = self.shield.is_blackout_active(dt)
        self.assertFalse(active)
        self.assertEqual(reason, "")

    def test_cpi_window_blackout(self):
        # Monday 12:25 UTC (within 12:30 release -15m buffer)
        dt = datetime(2026, 9, 7, 12, 25, tzinfo=timezone.utc)
        active, reason = self.shield.is_blackout_active(dt)
        self.assertTrue(active)
        self.assertIn("ESCUDO MACRO ACTIVO", reason)
        self.assertIn("CPI", reason)

    def test_fomc_window_blackout(self):
        # Wednesday 18:10 UTC (within FOMC 18:00 release window)
        dt = datetime(2026, 9, 9, 18, 10, tzinfo=timezone.utc)
        active, reason = self.shield.is_blackout_active(dt)
        self.assertTrue(active)
        self.assertIn("FOMC", reason)

    def test_manual_blackout(self):
        self.shield.set_manual_blackout(True, "Alerta de Guerra / Discurso Emergencia")
        active, reason = self.shield.is_blackout_active()
        self.assertTrue(active)
        self.assertIn("Alerta de Guerra", reason)
        self.shield.set_manual_blackout(False)
        active, _ = self.shield.is_blackout_active(datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc))
        self.assertFalse(active)


if __name__ == "__main__":
    unittest.main()
