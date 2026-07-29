#!/usr/bin/env python3
"""
8-Hour Bollinger Trend Test Runner
Runs SOL-USDT with Bollinger Trend strategy for 8 hours in demo simulation mode.
Logs results every 5 minutes and saves final report.
"""
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))

from engine.tick_simulator import SubSecondTickSimulator
from core.database import DatabaseManager
from core.event_logger import event_logger

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/tmp/test_8h.log")
    ]
)
logger = logging.getLogger("8h_Test")

TEST_DURATION_HOURS = 8
TEST_SYMBOL = "SOL-USDT"
INITIAL_CAPITAL = 1000.0
STRATEGY = "alpha_edge"
LOG_INTERVAL_MINUTES = 5
RESULTS_FILE = "/tmp/test_results_8h.txt"


async def run_test():
    start_time = time.time()
    end_time = start_time + (TEST_DURATION_HOURS * 3600)
    
    logger.info("=" * 70)
    logger.info(f"🚀 8-HOUR TEST STARTED — {STRATEGY} on {TEST_SYMBOL}")
    logger.info(f"   Capital: ${INITIAL_CAPITAL:.2f} | Duration: {TEST_DURATION_HOURS}h")
    logger.info(f"   Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"   End:   {(datetime.now() + timedelta(hours=TEST_DURATION_HOURS)).strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 70)

    simulator = SubSecondTickSimulator(
        symbol=TEST_SYMBOL,
        initial_capital=INITIAL_CAPITAL,
        strategy_name=STRATEGY,
        use_live_market_data=True
    )
    simulator.ws_client.is_running = True

    db = DatabaseManager()

    stream_task = asyncio.create_task(
        simulator.ws_client.start_live_stream(interval_seconds=0.3)
    )

    last_log_time = start_time
    snapshot_count = 0
    results_log = []

    auto_validation_done = False

    try:
        while time.time() < end_time:
            await asyncio.sleep(1.0)
            
            now = time.time()
            metrics = simulator.latest_metrics
            signal = simulator.latest_signal
            stats = simulator.get_summary()
            elapsed_min = (now - start_time) / 60.0
            remaining_min = (end_time - now) / 60.0

            if now - last_log_time >= LOG_INTERVAL_MINUTES * 60:
                last_log_time = now
                snapshot_count += 1
                
                mid = metrics.get("mid_price", 0.0)
                snap = {
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "elapsed_min": round(elapsed_min, 1),
                    "mid_price": round(mid, 2),
                    "capital": stats.get("capital", INITIAL_CAPITAL),
                    "pnl": stats.get("cum_pnl", 0.0),
                    "trades": stats.get("total_trades", 0),
                    "wins": stats.get("wins", 0),
                    "losses": stats.get("losses", 0),
                    "win_rate": stats.get("win_rate_percent", 0.0),
                    "signal": signal.get("signal", "NEUTRAL"),
                    "strategy": stats.get("active_strategy", STRATEGY),
                }
                results_log.append(snap)
                
                line = (f"[{snap['time']}] #{snapshot_count} | "
                        f"Mid: ${mid:.2f} | Capital: ${snap['capital']:.2f} | "
                        f"PnL: ${snap['pnl']:+.4f} | Trades: {snap['trades']} | "
                        f"WR: {snap['win_rate']}% | "
                        f"Remaining: {remaining_min:.0f}min")
                logger.info(line)
                
                with open(RESULTS_FILE, "w") as f:
                    f.write(f"8-HOUR TEST PROGRESS — {STRATEGY} on {TEST_SYMBOL}\n")
                    f.write(f"Started: {datetime.fromtimestamp(start_time).strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"Current: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"Elapsed: {elapsed_min:.0f} min / {TEST_DURATION_HOURS * 60} min\n\n")
                    for r in results_log:
                        f.write(f"[{r['time']}] Mid: ${r['mid_price']:.2f} | "
                                f"Capital: ${r['capital']:.2f} | PnL: ${r['pnl']:+.4f} | "
                                f"Trades: {r['trades']} | WR: {r['win_rate']}%\n")

                # Auto-validation: after 50 trades, check if strategy has edge
                total_trades_val = stats.get("total_trades", 0)
                if total_trades_val >= 50 and not auto_validation_done:
                    auto_validation_done = True
                    cum_pnl = stats.get("cum_pnl", 0.0)
                    win_rate_val = stats.get("win_rate_percent", 0.0)
                    if cum_pnl < 0:
                        logger.warning(f"⚠️ AUTO-VALIDATION: {total_trades_val} trades, PnL ${cum_pnl:+.4f}, WR {win_rate_val}% — Estrategia perdiendo dinero.")
                        logger.warning(f"   Considere desactivar {STRATEGY} y probar otra configuración.")
                    else:
                        logger.info(f"✅ AUTO-VALIDATION: {total_trades_val} trades, PnL ${cum_pnl:+.4f}, WR {win_rate_val}% — Estrategia positiva.")

    except KeyboardInterrupt:
        logger.info("🛑 Test interrupted by user")
    finally:
        simulator.ws_client.is_running = False
        stream_task.cancel()
        try:
            await stream_task
        except asyncio.CancelledError:
            pass

    final_stats = simulator.get_summary()
    final_metrics = simulator.latest_metrics
    total_seconds = time.time() - start_time
    hours = int(total_seconds // 3600)
    mins = int((total_seconds % 3600) // 60)

    report = []
    report.append("=" * 70)
    report.append("📊 8-HOUR TEST — FINAL RESULTS")
    report.append("=" * 70)
    report.append(f"Strategy:   {STRATEGY}")
    report.append(f"Symbol:     {TEST_SYMBOL}")
    report.append(f"Duration:   {hours}h {mins}m")
    report.append(f"Started:    {datetime.fromtimestamp(start_time).strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"Ended:      {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("-" * 70)
    report.append(f"Initial Capital:  ${INITIAL_CAPITAL:.2f}")
    report.append(f"Final Capital:    ${final_stats['capital']:.2f}")
    report.append(f"Net PnL:          ${final_stats['cum_pnl']:+.4f}")
    report.append(f"Return:           {(final_stats['cum_pnl'] / INITIAL_CAPITAL * 100):+.2f}%")
    report.append("-" * 70)
    report.append(f"Total Trades:     {final_stats['total_trades']}")
    report.append(f"Wins:             {final_stats['wins']}")
    report.append(f"Losses:           {final_stats['losses']}")
    report.append(f"Win Rate:         {final_stats['win_rate_percent']}%")
    report.append("-" * 70)
    
    closed = list(simulator.execution_engine.closed_positions)
    if closed:
        pnls = [p.pnl for p in closed]
        fees = [p.total_fee for p in closed]
        avg_win = sum(p for p in pnls if p > 0) / max(1, final_stats['wins'])
        avg_loss = sum(p for p in pnls if p < 0) / max(1, final_stats['losses'])
        profit_factor = abs(sum(p for p in pnls if p > 0) / min(sum(p for p in pnls if p < 0), -0.0001))
        
        report.append(f"Avg Win:           ${avg_win:+.4f}")
        report.append(f"Avg Loss:          ${avg_loss:+.4f}")
        report.append(f"Profit Factor:     {profit_factor:.2f}")
        report.append(f"Total Fees:        ${sum(fees):.4f}")
        report.append(f"Best Trade:        ${max(pnls):+.4f}")
        report.append(f"Worst Trade:       ${min(pnls):+.4f}")
        
        risk_guard = simulator.risk_guard
        report.append("-" * 70)
        report.append(f"Circuit Breaker:   {risk_guard.circuit_breaker_triggered}")
        report.append(f"Peak Equity:       ${risk_guard.peak_equity:.2f}")
        report.append(f"Peak Drawdown:     {risk_guard.get_status()['peak_drawdown_pct']}%")
        
        recent = closed[-5:] if len(closed) >= 5 else closed
        report.append("-" * 70)
        report.append("Last 5 trades:")
        for p in recent:
            report.append(f"  {p.side:4s} | Entry: ${p.entry_price:.2f} | Exit: ${p.exit_price:.2f} | PnL: ${p.pnl:+.4f} | {p.status}")
    
    report.append("=" * 70)
    
    final_report = "\n".join(report)
    logger.info("\n" + final_report)
    
    with open(RESULTS_FILE, "w") as f:
        f.write(final_report)
    logger.info(f"📄 Results saved to {RESULTS_FILE}")


if __name__ == "__main__":
    asyncio.run(run_test())
