import os
import json
import pytest
import numpy as np
import pandas as pd
from core.ai_optimizer import (
    ParameterSafeguards,
    SandboxBacktester,
    LocalLLMAuditor,
    AIOptimizerEngine,
    ai_optimizer,
)


class TestParameterSafeguards:
    def test_sanitize_clamps_values(self):
        unsafe_params = {
            "adx_min": 10.0,       # below 15.0 min
            "atr_tp_mult": 8.0,     # above 6.0 max
            "max_exposure_pct": 0.60, # above 0.50 max
            "cooldown_candles": 20, # above 15 max
        }
        sanitized = ParameterSafeguards.sanitize(unsafe_params)
        assert sanitized["adx_min"] == 15.0
        assert sanitized["atr_tp_mult"] == 6.0
        assert sanitized["max_exposure_pct"] == 0.50
        assert sanitized["cooldown_candles"] == 15

    def test_validate_rejects_sub_floor_tp(self):
        params = {"atr_tp_mult": 1.5, "atr_sl_mult": 1.0, "max_exposure_pct": 0.25}
        valid, msg = ParameterSafeguards.validate(params)
        assert not valid
        assert "piso de seguridad" in msg

    def test_validate_rejects_negative_rr(self):
        params = {"atr_tp_mult": 2.6, "atr_sl_mult": 3.0, "max_exposure_pct": 0.25}
        valid, msg = ParameterSafeguards.validate(params)
        assert not valid
        assert "R:R no rentable" in msg

    def test_validate_accepts_valid_params(self):
        params = {
            "atr_tp_mult": 3.5,
            "atr_sl_mult": 1.8,
            "adx_min": 25.0,
            "max_exposure_pct": 0.25,
            "pullback_tolerance": 0.003,
        }
        valid, msg = ParameterSafeguards.validate(params)
        assert valid
        assert msg == "Parámetros válidos"


class TestSandboxBacktester:
    @pytest.fixture
    def sample_candles(self):
        np.random.seed(42)
        n = 150
        returns = np.random.normal(0.0003, 0.004, n)
        price = 100.0 * np.exp(np.cumsum(returns))
        highs = price * 1.005
        lows = price * 0.995
        opens = np.roll(price, 1)
        opens[0] = 100.0
        return pd.DataFrame({
            "open": opens, "high": highs, "low": lows, "close": price,
            "volume": [100.0] * n, "timestamp": range(n),
        })

    def test_backtester_runs_and_returns_metrics(self, sample_candles):
        bt = SandboxBacktester(maker_fee=0.001, slippage_pct=0.0005)
        params = {
            "ema_fast": 20, "ema_slow": 50, "ema_trend": 100,
            "adx_min": 20.0, "atr_tp_mult": 3.0, "atr_sl_mult": 1.5,
        }
        res = bt.run_backtest(params, sample_candles, initial_capital=1000.0)
        assert "total_trades" in res
        assert "win_rate_pct" in res
        assert "net_pnl" in res
        assert "sharpe_ratio" in res
        assert "profit_factor" in res
        assert isinstance(res["net_pnl"], float)


class TestLocalLLMAuditor:
    def test_auditor_offline_resilience(self):
        # Fake endpoint where nothing is listening
        auditor = LocalLLMAuditor(endpoint="http://127.0.0.1:54321")
        assert not auditor.is_available
        resp = auditor.query_audit_and_hypothesis(
            market_summary={"regime": "TEST"}, current_preset={}
        )
        assert resp is None  # Fails gracefully without raising exception


class TestAIOptimizerEngine:
    def test_engine_optimization_cycle(self, tmp_path):
        preset_file = tmp_path / "strategy_presets.json"
        sample_data = {
            "presets": {
                "alpha_edge_1000": {
                    "adx_min": 30.0,
                    "atr_sl_mult": 2.0,
                    "atr_tp_mult": 4.0,
                    "max_exposure_pct": 0.25,
                }
            },
            "default_preset": "alpha_edge_1000",
        }
        preset_file.write_text(json.dumps(sample_data))

        engine = AIOptimizerEngine(
            presets_path=str(preset_file),
            optimization_interval_seconds=3600.0,
            min_improvement_pct=5.0,
        )

        res = engine.run_optimization_cycle(force=True)
        assert res["status"] in ("APPLIED", "KEPT_CURRENT")
        assert "regime" in res
        assert "hypothesis" in res

        status = engine.get_status()
        assert status["is_enabled"] is True
        assert "current_regime" in status
        assert "accumulated_alpha_usd" in status

    def test_engine_toggle(self):
        opt = AIOptimizerEngine()
        assert opt.is_enabled is True
        opt.is_enabled = False
        assert opt.is_enabled is False
        opt.is_enabled = True
        assert opt.is_enabled is True
