import unittest
import os
from core.telegram_notifier import TelegramNotifier
from core.live_exchange import LiveExchangeClient
from core.portfolio_runner import MultiAssetPortfolioRunner


class TestLiveExchangeAndTelegram(unittest.TestCase):
    def test_telegram_notifier_initialization(self):
        # Unconfigured instance should be in silent mode without throwing errors
        notifier = TelegramNotifier(bot_token="", chat_id="", enabled=False)
        self.assertFalse(notifier.is_configured)
        self.assertFalse(notifier.enabled)
        res = notifier.send_message("Test message")
        self.assertFalse(res)

    def test_telegram_notifier_configured_mode(self):
        notifier = TelegramNotifier(bot_token="test_token", chat_id="test_chat", enabled=True)
        self.assertTrue(notifier.is_configured)
        self.assertTrue(notifier.enabled)
        # Should enqueue message successfully
        res = notifier.send_message("Test queued alert")
        self.assertTrue(res)

    def test_live_exchange_dry_run_mode(self):
        client = LiveExchangeClient(
            exchange="kucoin",
            api_key="mock_key",
            api_secret="mock_secret",
            api_passphrase="mock_passphrase",
            live_enabled=False,
        )
        self.assertFalse(client.live_enabled)
        
        # Test dry-run order
        res = client.place_order(symbol="SOL-USDT", side="BUY", quantity=0.5, price=145.0)
        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("mode"), "DRY_RUN")
        self.assertEqual(res.get("quantity"), 0.5)

    def test_live_exchange_signatures(self):
        client = LiveExchangeClient(
            exchange="kucoin",
            api_key="test_key",
            api_secret="test_secret",
            api_passphrase="test_pass",
        )
        sig, pass_sig = client._sign_kucoin("1700000000000", "GET", "/api/v1/accounts", "")
        self.assertIsInstance(sig, str)
        self.assertGreater(len(sig), 10)
        self.assertIsInstance(pass_sig, str)
        self.assertGreater(len(pass_sig), 10)

        # Test Binance signature
        b_client = LiveExchangeClient(exchange="binance", api_key="k", api_secret="s")
        signed_q = b_client._sign_binance({"symbol": "BTCUSDT", "timestamp": "1700000000000"})
        self.assertIn("signature=", signed_q)

        # Test Bybit v5 signature
        bybit_client = LiveExchangeClient(exchange="bybit", api_key="test_bybit_key", api_secret="test_bybit_secret")
        bybit_sig = bybit_client._sign_bybit("1700000000000", "category=spot&symbol=SOLUSDT")
        self.assertIsInstance(bybit_sig, str)
        self.assertGreater(len(bybit_sig), 20)

    def test_portfolio_runner_integration_with_telegram_and_exchange(self):
        runner = MultiAssetPortfolioRunner(
            symbols=["SOL-USDT"],
            initial_capital=310.0,
            profile_id="test_integration",
        )
        runner.risk_guard.session_filter_enabled = False
        sim = runner.simulators["SOL-USDT"]
        
        # Open simulated position
        pos = sim.execution_engine.open_position(
            symbol="SOL-USDT",
            side="BUY",
            price=150.0,
            quantity=0.1,
            tp_price=160.0,
            sl_price=140.0,
            timestamp_ms=1700000000000,
        )
        self.assertIsNotNone(pos)
        self.assertEqual(len(sim.execution_engine.active_positions), 1)

        # Trigger profit advance: > 70% TP distance (157.5 covers 75% of 150 -> 160)
        sim.execution_engine.update_positions(
            current_tick_bid=157.5,
            current_tick_ask=157.55,
            timestamp_ms=1700000001000,
        )
        self.assertGreater(pos.sl_price, pos.entry_price)  # Secure profit lock active (>= 1.5:1 R:R secured)


if __name__ == "__main__":
    unittest.main()
