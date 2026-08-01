import time
import logging
from datetime import date
from typing import Dict, Any, Tuple

logger = logging.getLogger("RiskGuard")


class RiskGuard:
    """
    Enterprise Risk Management & Global Circuit Breakers (Kill Switch).

    Protections:
    - Max Daily Drawdown  : Triggers Emergency Stop if daily PnL drops below limit.
    - Max Consecutive Losses: Temporarily pauses trading after N losses (cooldown).
    - Max Account Exposure: Limits active trade allocation.
    - Emergency Kill Switch: Manual or automatic override.
    - Automatic Daily Reset: Resets drawdown counter at midnight for 24/7 ops.
    """

    def __init__(
        self,
        initial_capital: float = 100.0,
        max_daily_drawdown_pct: float = 0.05,
        max_consecutive_losses: int = 3,
        max_exposure_pct: float = 0.25,
        cooldown_seconds: float = 300.0,
    ):
        self.initial_capital         = initial_capital
        self.max_daily_drawdown_pct  = max_daily_drawdown_pct
        self.max_consecutive_losses  = max_consecutive_losses
        self.max_exposure_pct        = max_exposure_pct
        self.cooldown_seconds        = cooldown_seconds

        self.starting_daily_capital  = initial_capital
        self.daily_pnl               = 0.0
        self.peak_equity             = initial_capital
        self.consecutive_losses      = 0
        self.circuit_breaker_triggered = False
        self.circuit_breaker_reason  = ""
        self.paused_until_timestamp  = 0.0
        self.last_reset_date         = date.today()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_daily_reset(self, current_balance: float = None):
        """Resets daily counters when a new day is detected."""
        today = date.today()
        if today != self.last_reset_date:
            new_baseline = current_balance if current_balance is not None else self.initial_capital
            logger.info(
                f"🟢 Risk Guard: New day ({self.last_reset_date} → {today}). "
                f"Resetting daily PnL. Baseline: ${new_baseline:.2f}"
            )
            self.daily_pnl              = 0.0
            self.starting_daily_capital = new_baseline
            self.last_reset_date        = today
            if self.circuit_breaker_triggered and "Daily loss" in self.circuit_breaker_reason:
                self.circuit_breaker_triggered = False
                self.circuit_breaker_reason    = ""
                logger.info("🟢 Risk Guard: Circuit breaker auto-reset for new trading day.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_trade_allowed(self, current_balance: float, requested_trade_cost: float) -> Tuple[bool, str]:
        """
        Evaluates whether a new trade is permitted.
        Returns: (is_allowed: bool, reason: str)
        """
        self._check_daily_reset(current_balance)

        if self.circuit_breaker_triggered:
            return False, f"🚨 CIRCUIT BREAKER: {self.circuit_breaker_reason}"

        current_time = time.time()
        if current_time < self.paused_until_timestamp:
            remaining = int(self.paused_until_timestamp - current_time)
            return False, f"⏳ PAUSED ({self.consecutive_losses} consecutive losses). Cooldown: {remaining}s"

        # Peak equity drawdown
        if current_balance > self.peak_equity:
            self.peak_equity = current_balance
        peak_dd_pct = (
            (self.peak_equity - current_balance) / self.peak_equity
            if self.peak_equity > 0 else 0.0
        )
        if peak_dd_pct >= self.max_daily_drawdown_pct:
            self.trigger_circuit_breaker(
                f"Peak equity drawdown ({peak_dd_pct * 100:.2f}%) exceeded limit "
                f"({self.max_daily_drawdown_pct * 100:.1f}%)"
            )
            return False, "🚨 CIRCUIT BREAKER: Peak equity drawdown limit reached"

        # Daily drawdown
        if self.starting_daily_capital > 0:
            daily_loss_pct = abs(self.daily_pnl) / self.starting_daily_capital if self.daily_pnl < 0 else 0.0
        else:
            daily_loss_pct = 0.0
        if daily_loss_pct >= self.max_daily_drawdown_pct:
            self.trigger_circuit_breaker(
                f"Daily loss ({daily_loss_pct * 100:.2f}%) exceeded limit "
                f"({self.max_daily_drawdown_pct * 100:.1f}%)"
            )
            return False, "🚨 CIRCUIT BREAKER: Daily drawdown limit reached"

        # Exposure limit
        if requested_trade_cost > (current_balance * self.max_exposure_pct):
            return False, (
                f"⚠️ EXPOSURE LIMIT: ${requested_trade_cost:.2f} > "
                f"max ${current_balance * self.max_exposure_pct:.2f}"
            )

        return True, "ALLOWED"

    def record_trade_result(self, pnl: float, current_balance: float = None):
        """Records completed trade PnL and updates drawdown / consecutive-loss metrics."""
        self._check_daily_reset(current_balance)
        self.daily_pnl += pnl

        if current_balance is not None and current_balance > self.peak_equity:
            self.peak_equity = current_balance

        if pnl < 0:
            self.consecutive_losses += 1
            if self.consecutive_losses >= self.max_consecutive_losses:
                if time.time() >= self.paused_until_timestamp:
                    self.paused_until_timestamp = time.time() + self.cooldown_seconds
                    logger.warning(
                        f"⚠️ Risk Guard: {self.consecutive_losses} consecutive losses. "
                        f"Pausing {self.cooldown_seconds}s."
                    )
        else:
            self.consecutive_losses = 0

        # Check daily limit after recording
        if (
            self.daily_pnl < 0
            and self.starting_daily_capital > 0
            and (abs(self.daily_pnl) / self.starting_daily_capital) >= self.max_daily_drawdown_pct
        ):
            loss_pct = (abs(self.daily_pnl) / self.starting_daily_capital) * 100
            self.trigger_circuit_breaker(
                f"Daily loss {loss_pct:.2f}% (Limit: {self.max_daily_drawdown_pct * 100:.1f}%)"
            )

    def trigger_circuit_breaker(self, reason: str):
        """Triggers Emergency Kill Switch."""
        self.circuit_breaker_triggered = True
        self.circuit_breaker_reason    = reason
        logger.error(f"🚨 EMERGENCY KILL SWITCH: {reason}")

    def reset_circuit_breaker(self, new_capital: float = None):
        """Resets circuit breaker and daily counters."""
        if new_capital is not None:
            self.initial_capital        = new_capital
            self.starting_daily_capital = new_capital

        self.daily_pnl                 = 0.0
        self.consecutive_losses        = 0
        self.circuit_breaker_triggered = False
        self.circuit_breaker_reason    = ""
        self.paused_until_timestamp    = 0.0
        logger.info("🟢 Risk Guard circuit breaker reset to normal operation.")

    def get_status(self) -> Dict[str, Any]:
        """Returns risk status for the Web UI dashboard."""
        # Guard: avoid division by zero when starting_daily_capital == 0
        if self.starting_daily_capital > 0:
            daily_pnl_pct = round((self.daily_pnl / self.starting_daily_capital) * 100, 2)
        else:
            daily_pnl_pct = 0.0

        peak_dd_pct = (
            (self.peak_equity - (self.starting_daily_capital + self.daily_pnl))
            / self.peak_equity * 100
            if self.peak_equity > 0 else 0.0
        )

        return {
            "circuit_breaker_triggered": self.circuit_breaker_triggered,
            "reason":                    self.circuit_breaker_reason,
            "daily_pnl":                 round(self.daily_pnl, 4),
            "daily_pnl_pct":             daily_pnl_pct,
            "consecutive_losses":        self.consecutive_losses,
            "max_daily_drawdown_pct":    self.max_daily_drawdown_pct * 100,
            "is_paused":                 time.time() < self.paused_until_timestamp,
            "peak_equity":               round(self.peak_equity, 2),
            "peak_drawdown_pct":         round(max(0.0, peak_dd_pct), 2),
        }
