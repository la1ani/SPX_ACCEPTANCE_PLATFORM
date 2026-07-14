"""
Dual-side engine — the piece that ties call and put together instead of
evaluating them in isolation.

Addresses two gaps identified from live chart review:

1. Cross-side gate: a side's own directional read can be entirely fake if
   the OTHER side's support/resistance is still intact and being actively
   tested (unresolved). Confirmed directly on a live chart: put holding
   support made call's own up-and-down activity fake, regardless of what
   call's own chart/data verdicts said in isolation. This engine checks
   the opposite side's state before trusting either side's directional
   call, and vetoes it back to no-trade when the other side's level is
   still live and unresolved.

2. Rejection-trigger propagation: the moment one side's data agent detects
   "was holding at a level, just stopped holding" (a rejection event, see
   data_agent.py), that event should raise the OTHER side's decision
   immediately — even ahead of that other side's own momentum fully
   confirming — since the rejection event IS the explanation for why the
   other side is about to move. This is the earliest, cheapest entry point
   described throughout the design discussion.

This module keeps per-side state (previous holding_seconds) across calls
so the rejection-transition check in data_agent has something to compare
against.
"""

from __future__ import annotations

from datetime import datetime

from .boss import Boss
from .chart_agent import ChartReasoningAgent
from .data_agent import DataReasoningAgent
from .level_tracker import LevelMemory
from .models import (
    ChartExtraction,
    Decision,
    DualSideDecision,
    FinalCall,
    LevelRead,
    Side,
    SheetTick,
    Zone,
)

OTHER_SIDE = {Side.CALL: Side.PUT, Side.PUT: Side.CALL}


class DualSideEngine:
    def __init__(
        self,
        chart_agent: ChartReasoningAgent | None = None,
        data_agent: DataReasoningAgent | None = None,
        boss: Boss | None = None,
        level_memory: LevelMemory | None = None,
    ):
        self.chart_agent = chart_agent or ChartReasoningAgent()
        self.data_agent = data_agent or DataReasoningAgent()
        self.boss = boss or Boss()
        self.level_memory = level_memory or LevelMemory()
        self._previous_holding: dict[Side, float | None] = {Side.CALL: None, Side.PUT: None}

    def decide(
        self,
        ticks: list[SheetTick],
        call_extraction: ChartExtraction,
        put_extraction: ChartExtraction,
        timestamp: datetime,
    ) -> DualSideDecision:
        call_nearby = self._closest_level(call_extraction, ticks[-1], Side.CALL)
        put_nearby = self._closest_level(put_extraction, ticks[-1], Side.PUT)

        call_chart_v = self.chart_agent.evaluate(call_extraction)
        put_chart_v = self.chart_agent.evaluate(put_extraction)

        call_data_v = self.data_agent.evaluate(
            ticks, nearby_level=call_nearby, level_side_is_call=True,
            previous_holding_seconds=self._previous_holding[Side.CALL],
        )
        put_data_v = self.data_agent.evaluate(
            ticks, nearby_level=put_nearby, level_side_is_call=False,
            previous_holding_seconds=self._previous_holding[Side.PUT],
        )

        self._previous_holding[Side.CALL] = call_data_v.evidence.get("holding_seconds")
        self._previous_holding[Side.PUT] = put_data_v.evidence.get("holding_seconds")

        self._record_touch_if_any(Side.CALL, call_nearby, call_data_v, timestamp)
        self._record_touch_if_any(Side.PUT, put_nearby, put_data_v, timestamp)

        call_decision = self.boss.decide(Side.CALL, call_chart_v, call_data_v, timestamp)
        put_decision = self.boss.decide(Side.PUT, put_chart_v, put_data_v, timestamp)

        call_decision, call_gated = self._apply_cross_side_gate(
            call_decision, other_data_v=put_data_v, other_nearby=put_nearby
        )
        put_decision, put_gated = self._apply_cross_side_gate(
            put_decision, other_data_v=call_data_v, other_nearby=call_nearby
        )

        call_decision = self._apply_rejection_trigger(
            call_decision, other_side_rejected=put_data_v.evidence.get("rejection_just_occurred", False)
        )
        put_decision = self._apply_rejection_trigger(
            put_decision, other_side_rejected=call_data_v.evidence.get("rejection_just_occurred", False)
        )

        gate_reason = ""
        if call_gated:
            gate_reason += "Call's directional read vetoed — put's level is still live and unresolved. "
        if put_gated:
            gate_reason += "Put's directional read vetoed — call's level is still live and unresolved."

        return DualSideDecision(
            timestamp=timestamp,
            call_decision=call_decision,
            put_decision=put_decision,
            call_gated=call_gated,
            put_gated=put_gated,
            gate_reason=gate_reason.strip(),
        )

    def _apply_cross_side_gate(
        self, decision: Decision, other_data_v, other_nearby: LevelRead | None
    ) -> tuple[Decision, bool]:
        is_directional = decision.final_call in (
            FinalCall.TRADE_BULLISH, FinalCall.TRADE_BEARISH, FinalCall.CAUTIOUS_TRADE
        )
        if not is_directional or other_nearby is None:
            return decision, False

        other_holding = other_data_v.evidence.get("holding_seconds")
        other_is_testing_unresolved = (
            other_data_v.zone == Zone.CONSOLIDATION
            and other_holding is not None
            and other_holding > 0
        )
        if not other_is_testing_unresolved:
            return decision, False

        gated = Decision(
            timestamp=decision.timestamp,
            side=decision.side,
            final_call=FinalCall.NO_TRADE,
            confidence=min(decision.confidence, 0.35),
            aligned=decision.aligned,
            chart_verdict=decision.chart_verdict,
            data_verdict=decision.data_verdict,
            narrative=(
                f"{decision.side.value.upper()} looked {decision.final_call.value}, but the other "
                f"side is currently holding at its own level, unresolved ({other_holding:.0f}s) — "
                "that apparent move has no legitimate cause yet and is being read as fake. No trade."
            ),
            rejection_trigger=False,
        )
        return gated, True

    def _apply_rejection_trigger(self, decision: Decision, other_side_rejected: bool) -> Decision:
        if not other_side_rejected:
            return decision
        if decision.final_call in (FinalCall.TRADE_BULLISH, FinalCall.TRADE_BEARISH):
            decision.rejection_trigger = True
            return decision
        if decision.final_call in (FinalCall.NO_TRADE, FinalCall.CAUTIOUS_TRADE):
            return Decision(
                timestamp=decision.timestamp,
                side=decision.side,
                final_call=FinalCall.CAUTIOUS_TRADE,
                confidence=max(decision.confidence, 0.6),
                aligned=decision.aligned,
                chart_verdict=decision.chart_verdict,
                data_verdict=decision.data_verdict,
                narrative=(
                    f"The other side just showed a rejection event (was holding, now isn't) — "
                    f"that's the entry trigger. Promoting {decision.side.value} to a cautious "
                    "entry ahead of its own momentum confirming. Original read: "
                    f"\"{decision.narrative}\""
                ),
                rejection_trigger=True,
            )
        return decision

    def _record_touch_if_any(self, side: Side, nearby_level, data_verdict, timestamp: datetime) -> None:
        if nearby_level is None:
            return
        holding = data_verdict.evidence.get("holding_seconds")
        if holding is None:
            return
        resolved_as = "pending"
        if data_verdict.evidence.get("rejection_just_occurred"):
            resolved_as = "rejected"
        elif data_verdict.zone in (Zone.BULLISH, Zone.BEARISH) and holding == 0:
            resolved_as = "broke"

        velocity = data_verdict.evidence.get("call_velocity" if side == Side.CALL else "put_velocity", 0.0)
        self.level_memory.record_touch(
            side=side, level=nearby_level, timestamp=timestamp,
            price=data_verdict.evidence.get("entry_price", nearby_level.price),
            velocity_during_approach=velocity, body_ratio=0.0, resolved_as=resolved_as,
        )

    @staticmethod
    def _closest_level(extraction: ChartExtraction, latest_tick: SheetTick, side: Side) -> LevelRead | None:
        if not extraction.levels:
            return None
        price = latest_tick.call_price if side == Side.CALL else latest_tick.put_price
        return min(extraction.levels, key=lambda lv: abs(lv.price - price))
