# A3 HFT Engine - Sub-Second Trading System (Linux Native)

An Asynchronous High-Frequency Trading (HFT) and Orderbook Microstructure engine designed for sub-second (2s - 5s) execution on Linux (Ubuntu).

## Quick Start & Manual

For the complete step-by-step guide for beginners, read:
**[MANUAL_DE_USO.md](file:///home/andres/A3-HFT-Engine/MANUAL_DE_USO.md)**

## Commands

### Run HFT Engine:
```bash
python3 server.py
```
Open `http://localhost:8005/` in your browser.

### Run Automated Tests (32 tests):
```bash
python3 -m unittest discover -s tests -v
```

### Run Strategy Effectiveness Test:
```bash
python3 -m unittest tests.test_strategy_effectiveness -v
```
