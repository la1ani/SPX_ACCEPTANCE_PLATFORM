"""
Trade simulator.

Turns boss Decisions into simulated trades using ONLY data already flowing
through the system (the live sheet ticks) — no broker connection, no
account, nothing new to wire up. "Entering" a trade means recording the
current premium price at the instant a trade call fires. "Exiting" means
recording the price when the exit rule (exit_rule.py) fires. This is
exactly what was asked for: a way to test whether the rules are correct,
not a way to place real orders.

One open trade per side at a time — if a new trade signal fires while one
is already open on that side, it's ignored until the current one closes
(no pyramiding, keeps the simulation simple and matches "trade the rule,
not the excitement").
"""

from __future__ import annotations

import uuid
from datetime import datetime

from .exit_rule import TrailingStopExitRule
from .models import Decision, FinalCall, Side, SheetTick, SimulatedTrade

OPEN_CALLS = {FinalCall.TRADE_BULLISH, FinalCall.TRADE_BEARISH, FinalCall.CAUTIOUS_TRADE}


class TradeSimulator:
    def __init__(self, exit_rule: TrailingStopExitRule | None = None):
        self.exit_rule = exit_rule or TrailingStopExitRule()
        self.open_trades: dict[Side, SimulatedTrade] = {}
        self.closed_trades: list[SimulatedTrade] = []

    def on_decision(self, decision: Decision) -> SimulatedTrade | None:
        """
        Call this every time the boss issues a decision for a side. Opens a
        new simulated trade if conditions call for one and none is already
        open on that side. Returns the newly opened trade, if any.
        """
        if decision.side in self.open_trades:
            return None

        if decision.final_call not in OPEN_CALLS:
            return None

        entry_price = self._price_for_decision(decision)
        if entry_price is None:
            return None

        trade = SimulatedTrade(
            trade_id=str(uuid.uuid4())[:8],
            side=decision.side,
            entry_timestamp=decision.timestamp,
            entry_price=entry_price,
            entry_reasoning=decision.narrative,
            peak_price=entry_price,
        )
        self.open_trades[decision.side] = trade
        return trade

    def on_tick(self, tick: SheetTick) -> SimulatedTrade | None:
        closed = None
        for side, trade in list(self.open_trades.items()):
            price = tick.call_price if side == Side.CALL else tick.put_price
            trade.peak_price = self.exit_rule.new_peak(trade.peak_price, price)

            exit_reason = self.exit_rule.check(trade.entry_price, trade.peak_price, price)
            if exit_reason:
                trade.close(tick.timestamp, price, exit_reason)
                self.closed_trades.append(trade)
                del self.open_trades[side]
                closed = trade

        return closed

    def force_close_all(self, timestamp: datetime, last_tick: SheetTick, reason: str = "session_end") -> None:
        for side, trade in list(self.open_trades.items()):
            price = last_tick.call_price if side == Side.CALL else last_tick.put_price
            trade.close(timestamp, price, reason)
            self.closed_trades.append(trade)
        self.open_trades.clear()

    @staticmethod
    def _price_for_decision(decision: Decision) -> float | None:
        evidence = decision.data_verdict.evidence
        return evidence.get("entry_price")
