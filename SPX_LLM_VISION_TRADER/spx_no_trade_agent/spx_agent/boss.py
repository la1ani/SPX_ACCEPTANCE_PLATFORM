"""
The boss.

Not a rule engine, not a tie-breaker that "picks a winner" between the two
agents. Its single job is one reasoning question: do the chart-side read
and the data-side read describe the SAME pattern, independently arrived at
from two different kinds of evidence?

Agreement -> confidence. Disagreement or ambiguity -> that mismatch is
itself meaningful and should not be silently resolved — it defaults to
no-trade, because no-trade is the expected, common state, not a fallback
of last resort.
"""

from __future__ import annotations

from datetime import datetime

from .models import Decision, FinalCall, Side, Verdict, Zone

# Zones that, if both agents land on the SAME one, are strong enough to be
# worth reporting as a directional call rather than folding into no-trade.
DIRECTIONAL_ZONES = {Zone.BULLISH, Zone.BEARISH}


class Boss:
    def __init__(self, min_confidence_for_trade: float = 0.65):
        self.min_confidence_for_trade = min_confidence_for_trade

    def decide(
        self,
        side: Side,
        chart_verdict: Verdict,
        data_verdict: Verdict,
        timestamp: datetime | None = None,
    ) -> Decision:
        timestamp = timestamp or datetime.utcnow()
        aligned = chart_verdict.zone == data_verdict.zone
        combined_confidence = (chart_verdict.confidence + data_verdict.confidence) / 2

        if aligned:
            final_call, narrative = self._call_for_aligned_zone(
                chart_verdict.zone, combined_confidence, chart_verdict, data_verdict
            )
        else:
            final_call = FinalCall.NO_TRADE
            narrative = self._disagreement_narrative(chart_verdict, data_verdict)
            combined_confidence = min(combined_confidence, 0.4)  # disagreement caps confidence

        return Decision(
            timestamp=timestamp,
            side=side,
            final_call=final_call,
            confidence=combined_confidence,
            aligned=aligned,
            chart_verdict=chart_verdict,
            data_verdict=data_verdict,
            narrative=narrative,
        )

    # -- internal --------------------------------------------------------

    def _call_for_aligned_zone(
        self, zone: Zone, confidence: float, chart_verdict: Verdict, data_verdict: Verdict
    ) -> tuple[FinalCall, str]:
        if zone in DIRECTIONAL_ZONES and confidence >= self.min_confidence_for_trade:
            final_call = FinalCall.TRADE_BULLISH if zone == Zone.BULLISH else FinalCall.TRADE_BEARISH
            narrative = (
                f"Chart and data agents both independently read {zone.value.upper()} "
                f"(confidence {confidence:.0%}). Chart: \"{chart_verdict.reasoning}\" "
                f"Data: \"{data_verdict.reasoning}\" — this is a genuine, confirmed setup."
            )
            return final_call, narrative

        if zone in DIRECTIONAL_ZONES:
            narrative = (
                f"Chart and data agents both lean {zone.value}, but combined confidence "
                f"({confidence:.0%}) isn't high enough to trust fully — treating as a "
                "cautious/reduced-size trade rather than a full-conviction call."
            )
            return FinalCall.CAUTIOUS_TRADE, narrative

        if zone == Zone.SLOW_MOVING:
            narrative = (
                "Both agents agree this is a slow-moving zone — some directional attempt, "
                "but not enough conviction behind it. Cautious trade at most, not a full entry."
            )
            return FinalCall.CAUTIOUS_TRADE, narrative

        narrative = (
            f"Chart and data agents both independently read consolidation — "
            f"Chart: \"{chart_verdict.reasoning}\" Data: \"{data_verdict.reasoning}\" "
            "No trade: this is chop, not signal."
        )
        return FinalCall.NO_TRADE, narrative

    def _disagreement_narrative(self, chart_verdict: Verdict, data_verdict: Verdict) -> str:
        return (
            f"Chart agent reads {chart_verdict.zone.value} (\"{chart_verdict.reasoning}\") "
            f"but data agent reads {data_verdict.zone.value} (\"{data_verdict.reasoning}\") — "
            "these two independent reads disagree. That disagreement is itself the signal: "
            "no trade until both sides confirm the same pattern."
        )
