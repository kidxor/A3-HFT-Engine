import unittest
from core.event_logger import SystemEventLogger, event_logger

class TestEventLogger(unittest.TestCase):
    def setUp(self):
        event_logger.clear()

    def test_log_creation_and_retrieval(self):
        event_logger.log(category="ORDER", message="Orden de prueba abierta", symbol="SOL-USDT", level="SUCCESS")
        event_logger.log(category="RISK", message="Risk guard aprobado", symbol="BTC-USDT", level="INFO")
        
        logs = event_logger.get_logs()
        self.assertEqual(len(logs), 2)
        self.assertEqual(logs[0]["category"], "ORDER")
        self.assertEqual(logs[0]["symbol"], "SOL-USDT")
        self.assertEqual(logs[1]["category"], "RISK")

    def test_circular_buffer_capacity(self):
        for i in range(200):
            event_logger.log(category="TICK", message=f"Tick {i}", symbol="ETH-USDT")
        
        logs = event_logger.get_logs(limit=200)
        self.assertLessEqual(len(logs), 150)
        self.assertEqual(logs[-1]["message"], "Tick 199")

if __name__ == "__main__":
    unittest.main()
