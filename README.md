# A3 HFT Engine & Pro Terminal v6.0 (Proyecto Agustín)

An Asynchronous High-Frequency Trading (HFT), Orderbook Microstructure, and Autonomous AI Evolution Engine designed for sub-second execution on Linux (Ubuntu), featuring an **Institutional Grade Trading Terminal (100% Viewport Width, TradingView Interactive Chart, Keyboard Hotkeys, Tabbed Dock)**.

---

## 🌟 Key Upgrades in v6.0 Pro

- **Institutional Pro Workstation (UX/UI)**: 100% viewport width layout inspired by TradingView and Hyperliquid. Eliminates wasteful static sidebars and endless vertical scrolling.
- **Precision Numeric Typography**: Integrated `Plus Jakarta Sans` with `JetBrains Mono` tabular figures (`tabular-nums`) to completely eliminate price jitter during live market updates.
- **TradingView-Grade Interactive Chart**: High-density canvas rendering candlesticks with custom crosshair guide lines, dynamic **EMA 20** (Cyan) and **EMA 50** (Amber) overlays, and floating OHLCV metrics.
- **Symbol Switcher & Terminal Hotkeys**:
  - `1`: Switch to **SOL-USDT**
  - `2`: Switch to **BTC-USDT**
  - `3`: Switch to **ETH-USDT**
  - `Space`: Instant Engine Pause / Resume
  - `☰`: Slide-over drawer for advanced tools and profile settings.
- **Macro KPI Ribbon**: Unified high-density top metrics bar showing Equity ($200.00 base), PnL, Win Rate, Drawdown (10% max), Profit Factor, Sharpe, AI Alpha, and Risk Guard status.
- **Institutional Tabbed Dock**:
  - `📌 Active Positions`: Progress bar to TP, 50% scale-out marker (BE lock), floating PnL badges.
  - `📜 Trade History`: Real-time execution ledger.
  - `⚡ HFT Console & Telemetry`: Categorized live events stream with filter tabs (`ALL`, `ORDER`, `SIGNAL`, `RISK`, `L2`).
  - `🤖 Parallel Bots`: Multi-asset card monitoring.
- **Autonomous Local AI Evolution (`AIOptimizerEngine`)**: Background local LLM optimizer (Ollama `llama3.2:1b` @ `http://localhost:11434`) running in-RAM Sandbox simulations at **$0 API cost** with strict safety safeguards.
- **Convicton Capital Exposure**: Configured with **$200.00 USD initial capital**, conviction-based position sizing up to **50% max equity**, 50% scale-out @ 1.5x ATR, and News Spike Guard (3x ATR filter).

---

## 🚀 Quick Start

### 1. Run Server:
```bash
python3 server.py
```
Open **`http://localhost:8005/`** in your browser.

### 2. Run Test Suite (32 Automated Tests):
```bash
python3 -m pytest tests/ -v
```

### 3. Documentation
- **User Manual**: [MANUAL_DE_USO.md](file:///home/andres/A3-Motor-Trade/MANUAL_DE_USO.md)
- **API Reference**: [DOCUMENTACION_API.md](file:///home/andres/A3-Motor-Trade/DOCUMENTACION_API.md)
- **Changelog**: [CHANGELOG.md](file:///home/andres/A3-Motor-Trade/CHANGELOG.md)

---

*A3 Core Systems — Sub-Second Trading Engine v6.0 PRO*
