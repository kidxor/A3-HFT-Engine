import time
import logging
from core.database import DatabaseManager

logger = logging.getLogger("AnalyticsEngine")

class AnalyticsEngine:
    """Automated Analytics & Health Audit Manager for Live HFT Portfolio."""
    def __init__(self, db_manager: DatabaseManager = None):
        self.db = db_manager or DatabaseManager()

    def generate_health_report(self) -> str:
        summary = self.db.get_total_summary()
        recent_trades = self.db.get_recent_trades(limit=10)
        
        report_lines = [
            "=================================================================",
            f"📊 AUTONOMOUS HEALTH & PERFORMANCE AUDIT REPORT - {time.strftime('%Y-%m-%d %H:%M:%S')}",
            "=================================================================",
            f"• Total Trades Executed (SQLite): {summary.get('total_trades', 0)}",
            f"• Total Win Rate: {summary.get('win_rate_pct', 0.0)}%",
            f"• Cumulative Realized PnL: ${summary.get('total_pnl', 0.0):+.4f}",
            f"• Average Return per Trade: ${summary.get('avg_pnl', 0.0):+.4f}",
            "-----------------------------------------------------------------",
            "📋 RECENT TRADES AUDIT LOG:"
        ]
        
        if recent_trades:
            for t in recent_trades:
                report_lines.append(f"  [{t['created_at']}] {t['symbol']} {t['side']} | Entry: ${t['entry_price']:.2f} | Exit: ${t['exit_price']:.2f} | PnL: ${t['pnl']:+.4f} ({t['exit_reason']})")
        else:
            report_lines.append("  No new trades recorded during this window (Market in normal trend consolidation).")
            
        report_lines.append("=================================================================")
        report_str = "\n".join(report_lines)
        logger.info("\n" + report_str)
        return report_str

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    engine = AnalyticsEngine()
    print(engine.generate_health_report())
