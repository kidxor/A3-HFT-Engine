import time
import logging
from datetime import date, datetime, timezone
from typing import Dict, Any, Tuple

logger = logging.getLogger("RiskGuard")


class RiskGuard:
    """
    Enterprise Risk Management & Global Circuit Breakers (Kill Switch).

    Protections:
    - Weekend Standby     : Pauses trading Friday 22:00 UTC -> Sunday 22:00 UTC.
    - Max Daily Drawdown  : Triggers Emergency Stop if daily PnL drops below 5%.
    - Max Consecutive Losses: Temporarily pauses trading after N losses (cooldown).
    - Max Account Exposure: Limits active trade allocation.
    - Emergency Kill Switch: Manual or automatic override.
    - Automatic Daily Reset: Resets drawdown counter at midnight for 24/7 ops.
    """

    def __init__(
        self,
        initial_capital: float = 200.0,
        max_daily_drawdown_pct: float = 0.05,   # Strict 5% daily protection
        max_consecutive_losses: int = 2,
        max_exposure_pct: float = 0.50,
        cooldown_seconds: float = 3600.0,       # 1 hora de pausa Sniper tras 2 pérdidas consecutivas
        weekend_filter_enabled: bool = True,
        session_filter_enabled: bool = False,
        night_hunter_mode: bool = True,
        max_night_trades: int = 2,
        night_adx_min: float = 28.0,
    ):

        self.initial_capital         = initial_capital
        self.max_daily_drawdown_pct  = max_daily_drawdown_pct
        self.max_consecutive_losses  = max_consecutive_losses
        self.max_exposure_pct        = max_exposure_pct
        self.cooldown_seconds        = cooldown_seconds
        self.weekend_filter_enabled  = weekend_filter_enabled
        self.session_filter_enabled  = session_filter_enabled
        self.night_hunter_mode       = night_hunter_mode
        self.max_night_trades        = max_night_trades
        self.night_trades_count      = 0
        self.night_adx_min           = night_adx_min
        self.max_daily_trades        = 3        # Sniper Discipline: Máximo 3 trades selectivos por día
        self.daily_trades_count      = 0


        self.starting_daily_capital  = initial_capital
        self.daily_pnl               = 0.0
        self.peak_equity             = initial_capital
        self.consecutive_losses      = 0
        self.circuit_breaker_triggered = False
        self.circuit_breaker_reason  = ""
        self.paused_until_timestamp  = 0.0
        self.last_reset_date         = date.today()


    @property
    def is_paused(self) -> bool:
        return time.time() < self.paused_until_timestamp

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_daily_reset(self, current_balance: float = None):
        """Resets daily counters when a new day is detected."""
        today = date.today()
        if today != self.last_reset_date:
            self.last_reset_date        = today
            self.starting_daily_capital = current_balance or self.starting_daily_capital
            self.daily_pnl              = 0.0
            self.consecutive_losses     = 0
            self.circuit_breaker_triggered = False
            self.circuit_breaker_reason = ""
            self.daily_trades_count     = 0
            self.night_trades_count     = 0
            logger.info("📅 RiskGuard: Nuevo día detectado — contadores diarios reseteados.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_institutional_session(self, now_utc=None) -> Tuple[bool, str]:
        """
        Filters trading to the highest-liquidity institutional window (London & Wall Street):
        11:00 UTC to 21:00 UTC (08:00 to 18:00 hs Argentina).
        Prevents trading during low-liquidity Asian madrugada / pre-market chop.
        """
        if not self.session_filter_enabled:
            return True, ""

        if now_utc is None:
            now_utc = datetime.now(timezone.utc)

        hour = now_utc.hour
        if hour < 11 or hour >= 21:
            return False, "Fuera de horario institucional (Wall Street/Londres opera de 11:00 a 21:00 UTC / 08:00 a 18:00 hs Argentina). Standby de protección nocturna activado."

        return True, ""

    def is_weekend_standby(self, now_utc=None) -> Tuple[bool, str]:
        """
        Determines if the current time falls into the Weekend Standby window:
        From Friday 22:00 UTC through Sunday 22:00 UTC (CME Futures / Wall Street closure).
        """
        if not self.weekend_filter_enabled or not self.session_filter_enabled:
            return False, ""

        if now_utc is None:
            now_utc = datetime.now(timezone.utc)

        weekday = now_utc.weekday()  # 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun
        hour = now_utc.hour

        # Friday starting at 22:00 UTC
        if weekday == 4 and hour >= 22:
            return True, "Viernes post-cierre CME (22:00+ UTC). Standby de protección activado."
        # Saturday all day
        elif weekday == 5:
            return True, "Sábado (Libros L2 sin liquidez institucional). Standby de protección activado."
        # Sunday before 22:00 UTC
        elif weekday == 6 and hour < 22:
            return True, "Domingo pre-apertura CME (hasta 22:00 UTC). Standby de protección activado."

        return False, ""

    def check_trade_allowed(
        self,
        current_balance: float,
        requested_trade_cost: float,
        signal_info: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        """
        Evaluates whether a new trade is permitted.
        Returns: (is_allowed: bool, reason: str)
        """
        self._check_daily_reset(current_balance)

        if self.circuit_breaker_triggered:
            return False, f"🚨 CIRCUIT BREAKER: {self.circuit_breaker_reason}"

        # Weekend Standby: strictly block trades during CME weekend closure
        is_weekend, weekend_reason = self.is_weekend_standby()
        if is_weekend:
            return False, f"🟡 STANDBY FIN DE SEMANA: {weekend_reason}"

        # Institutional Session Window (Wall Street & London) vs Night Hunter Mode
        is_session, session_reason = self.is_institutional_session()
        if not is_session:
            if not self.night_hunter_mode:
                return False, f"⏳ ESPERA INSTITUCIONAL: {session_reason}"

            # Night Hunter Mode is active
            if self.night_trades_count >= self.max_night_trades:
                return False, f"🌙 CAZADOR NOCTURNO: Cupo nocturno agotado ({self.night_trades_count}/{self.max_night_trades} trades). Preservando capital hasta las 08:00 hs."

            # Quality & Momentum gate for Night trades: require ADX >= night_adx_min
            if signal_info and isinstance(signal_info, dict):
                indicators = signal_info.get("indicators", {})
                adx = indicators.get("adx", 0.0)
                if adx > 0 and adx < self.night_adx_min:
                    return False, f"🌙 CAZADOR NOCTURNO: ADX bajo ({adx:.1f} < {self.night_adx_min:.1f}) — Mercado nocturno en rango/chop. Esperando impulso real."

        # Macro Economic Shield Window (CPI, NFP, FOMC)
        try:
            from core.macro_shield import macro_shield
            macro_blackout, macro_reason = macro_shield.is_blackout_active()
            if macro_blackout:
                return False, f"🚨 MACRO SHIELD: {macro_reason}"
        except Exception:
            pass

        # Max Daily Trades (Anti-Overtrading / Quality Sniper protection)
        if self.daily_trades_count >= self.max_daily_trades:
            return False, f"🎯 LÍMITE DIARIO ALCANZADO: {self.daily_trades_count}/{self.max_daily_trades} operaciones ejecutadas hoy. Preservando capital."


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

    def check_volatility_spike(self, current_atr: float, avg_atr: float):
        """Rejects trades if current ATR is >= 3.0x average ATR (News / erratic spike guard)."""
        if avg_atr > 0 and current_atr >= (avg_atr * 3.0):
            return False, f"⚠️ VOLATILITY SPIKE GUARD: ATR spike detected ({current_atr:.4f} >= 3x avg {avg_atr:.4f})"
        return True, "ALLOWED"

    def record_trade_result(self, pnl: float, current_balance: float = None):
        """Records completed trade PnL and updates drawdown / consecutive-loss metrics."""
        self._check_daily_reset(current_balance)
        self.daily_pnl += pnl

        if current_balance is not None and current_balance > self.peak_equity:
            self.peak_equity = current_balance

        if pnl < 0:
            self.consecutive_losses += 1
            loss_pct_single = (abs(pnl) / self.starting_daily_capital) if self.starting_daily_capital > 0 else 0.0
            # If a single max-conviction trade lost >= 7.5%, trip circuit breaker immediately
            if loss_pct_single >= 0.075:
                self.trigger_circuit_breaker(
                    f"Pérdida de máxima convicción ({loss_pct_single * 100:.1f}%) activó corte de seguridad inmediato."
                )
            elif self.consecutive_losses >= self.max_consecutive_losses:
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
            self.peak_equity            = new_capital

        self.daily_pnl                 = 0.0
        self.daily_trades_count        = 0
        self.night_trades_count        = 0
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

        is_weekend, weekend_reason = self.is_weekend_standby()
        is_session, session_reason = self.is_institutional_session()
        try:
            from core.macro_shield import macro_shield
            is_macro_blackout, macro_reason = macro_shield.is_blackout_active()
        except Exception:
            is_macro_blackout, macro_reason = False, ""

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
            "weekend_standby":           is_weekend,
            "weekend_reason":            weekend_reason,
            "institutional_session":     is_session,
            "session_reason":            session_reason,
            "macro_shield_active":       is_macro_blackout,
            "macro_shield_reason":       macro_reason,
            "daily_trades_count":        self.daily_trades_count,
            "max_daily_trades":          self.max_daily_trades,
            "night_hunter_mode":         self.night_hunter_mode,
            "night_trades_count":        self.night_trades_count,
            "max_night_trades":          self.max_night_trades,
        }


