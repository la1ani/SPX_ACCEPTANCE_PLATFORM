"""
Exit rule for simulated trades.

Exactly as specified: never lose more than a fixed hard-stop percentage
from entry, and once in profit, let it run but protect gains with a
trailing stop measured from the peak price reached since entry — not from
entry itself, so a big favorable move keeps running until it actually
reverses.

Two simple checks, both percentage-based, no other logic. Defaults:
hard_stop_pct=10.0, trailing_stop_pct=5.0 — matches what was specified.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ExitRuleParams:
    hard_stop_pct: float = 10.0
    trailing_stop_pct: float = 5.0


class TrailingStopExitRule:
    def __init__(self, params: ExitRuleParams | None = None):
        self.params = params or ExitRuleParams()

    def check(self, entry_price: float, peak_price: float, current_price: float) -> str | None:
        p = self.params

        loss_pct = (entry_price - current_price) / entry_price * 100
        if loss_pct >= p.hard_stop_pct:
            return "hard_stop"

        if peak_price > entry_price:
            pullback_pct = (peak_price - current_price) / peak_price * 100
            if pullback_pct >= p.trailing_stop_pct:
                return "trailing_stop"

        return None

    def new_peak(self, peak_price: float, current_price: float) -> float:
        return max(peak_price, current_price)
