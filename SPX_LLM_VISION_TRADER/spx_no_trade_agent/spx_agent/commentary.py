"""
Live commentary.

Turns a Decision into a short, plain-language line — reasoning made
visible, not a silent binary alert. This is meant to read the way a
trader narrating their own screen would talk, not like a log line.
"""

from __future__ import annotations

from .models import Decision, FinalCall


_CALL_LABEL = {
    FinalCall.NO_TRADE: "NO TRADE",
    FinalCall.CAUTIOUS_TRADE: "CAUTIOUS",
    FinalCall.TRADE_BULLISH: "TRADE — BULLISH",
    FinalCall.TRADE_BEARISH: "TRADE — BEARISH",
}


def narrate(decision: Decision) -> str:
    label = _CALL_LABEL[decision.final_call]
    ts = decision.timestamp.strftime("%H:%M:%S")
    agree = "agree" if decision.aligned else "DISAGREE"
    return (
        f"[{ts}] {decision.side.value.upper()} | {label} "
        f"(confidence {decision.confidence:.0%}, agents {agree}) — {decision.narrative}"
    )
