#!/usr/bin/env python3
import asyncio
import os
import sys
import time
from engine.tick_simulator import SubSecondTickSimulator

async def main():
    print("=" * 65)
    print("🚀 A3 CORE - SUB-SECOND HIGH FREQUENCY TRADING (HFT) ENGINE")
    print("=" * 65)
    print("📍 Platform: Linux (Ubuntu)")
    print("⚡ Execution Latency: ~5ms (Simulated)")
    print("📊 Strategy: Orderbook Microstructure & Order Flow Imbalance (OFI)")
    print("=" * 65)

    simulator = SubSecondTickSimulator(symbol="SOL-USDT", initial_capital=50.0)

    # Launch stream in background task
    stream_task = asyncio.create_task(simulator.ws_client.start_live_stream(interval_seconds=0.1))

    try:
        for i in range(20):  # Run for 20 telemetry refresh frames (~20s)
            await asyncio.sleep(1.0)
            metrics = simulator.latest_metrics
            signal = simulator.latest_signal
            stats = simulator.get_summary()

            if not metrics:
                continue

            # Clear terminal line or print HUD frame
            print(f"\n--- [TICK #{simulator.tick_count}] {metrics.get('symbol', 'SOL-USDT')} ---")
            print(f"💰 Best Bid: ${metrics.get('best_bid', 0.0):.2f} | Best Ask: ${metrics.get('best_ask', 0.0):.2f} | Spread: ${metrics.get('spread', 0.0):.2f}")
            print(f"🔬 Micro-Price: ${metrics.get('micro_price', 0.0):.4f} | Mid Price: ${metrics.get('mid_price', 0.0):.4f}")
            print(f"🌊 Order Flow Imbalance (OFI): {metrics.get('ofi_delta', 0.0):+.1f} | Volume Imbalance (VIR): {metrics.get('volume_imbalance', 1.0):.2f}x")
            
            sig_str = signal.get('signal', 'NEUTRAL')
            reason = signal.get('reason', '')
            if sig_str == "BUY_MAKER":
                print(f"🟢 SIGNAL: \033[92m{sig_str}\033[0m -> {reason}")
            elif sig_str == "SELL_MAKER":
                print(f"🔴 SIGNAL: \033[91m{sig_str}\033[0m -> {reason}")
            else:
                print(f"⚪ SIGNAL: {sig_str}")

            print(f"📈 Capital: ${stats['capital']:.2f} | PnL: ${stats['cum_pnl']:+.4f} | Win Rate: {stats['win_rate_percent']}% | Trades: {stats['total_trades']}")

    except KeyboardInterrupt:
        print("\n🛑 Stopping HFT Engine...")
    finally:
        simulator.ws_client.is_running = False
        await stream_task

    print("\n" + "=" * 65)
    print("🎉 HFT SIMULATION COMPLETE - FINAL METRICS:")
    final_stats = simulator.get_summary()
    print(f"   Final Capital: ${final_stats['capital']:.2f}")
    print(f"   Net PnL: ${final_stats['cum_pnl']:+.4f}")
    print(f"   Win Rate: {final_stats['win_rate_percent']}% ({final_stats['wins']} W / {final_stats['losses']} L)")
    print(f"   Total Executions: {final_stats['total_trades']}")
    print("=" * 65)

if __name__ == "__main__":
    asyncio.run(main())
