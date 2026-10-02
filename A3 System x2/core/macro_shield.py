"""
A3 AlphaEdge PRO — Macro Economic Shield
Protects capital by imposing automated trading blackout windows around
high-impact US economic releases (CPI, PPI, NFP, FOMC) to avoid erratic spikes and spread widening.
"""

from datetime import datetime, timezone
from typing import Tuple, Dict, Any, List


class MacroEconomicShield:
    """
    Monitors economic calendar high-impact release windows.
    Enforces a +/- 15 minute blackout window to protect stops from being hunted.
    """

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        # High impact recurring UTC release windows (hour, minute, duration_minutes, label)
        # 12:30 UTC: CPI, PPI, NFP, GDP, Core PCE, Retail Sales, Unemployment Claims
        # 18:00 - 18:30 UTC: FOMC Rate Decision & Press Conference (Wednesdays)
        self.scheduled_windows = [
            {"hour": 12, "minute": 30, "pre_buffer_m": 15, "post_buffer_m": 15, "label": "Datos Macro USA (CPI / NFP / Retail Sales / PCE)"},
            {"hour": 18, "minute": 0,  "pre_buffer_m": 15, "post_buffer_m": 45, "label": "Decisión de Tasas FOMC & Rueda de Prensa Fed"},
        ]
        self.manual_blackout = False
        self.manual_blackout_reason = ""

    def is_blackout_active(self, dt: datetime = None) -> Tuple[bool, str]:
        """
        Returns (is_active, reason).
        Checks if current UTC time falls within a high-impact news blackout window.
        """
        if not self.enabled:
            return False, ""

        if self.manual_blackout:
            return True, f"🚨 Veda manual activa: {self.manual_blackout_reason}"

        now = dt or datetime.now(timezone.utc)
        weekday = now.weekday()  # 0=Monday ... 4=Friday

        # News releases only happen on weekdays (Mon-Fri)
        if weekday > 4:
            return False, ""

        now_m_from_midnight = now.hour * 60 + now.minute

        for w in self.scheduled_windows:
            center_m = w["hour"] * 60 + w["minute"]
            start_m = center_m - w["pre_buffer_m"]
            end_m = center_m + w["post_buffer_m"]

            if start_m <= now_m_from_midnight <= end_m:
                remaining_m = end_m - now_m_from_midnight
                return True, (
                    f"🛡️ ESCUDO MACRO ACTIVO: {w['label']}. "
                    f"Operaciones pausadas (Finaliza en ~{remaining_m}m)."
                )

        return False, ""

    def set_manual_blackout(self, active: bool, reason: str = ""):
        """Allows instant emergency blackout trigger from API or Telegram."""
        self.manual_blackout = active
        self.manual_blackout_reason = reason

    def get_status(self) -> Dict[str, Any]:
        is_active, reason = self.is_blackout_active()
        return {
            "enabled": self.enabled,
            "blackout_active": is_active,
            "reason": reason,
            "manual_blackout": self.manual_blackout,
            "scheduled_windows": self.scheduled_windows,
        }


# Global singleton instance
macro_shield = MacroEconomicShield(enabled=True)
