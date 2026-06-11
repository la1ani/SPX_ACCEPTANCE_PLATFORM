"""
Alignment + Timing Agent

Core rule:
A signal is only safe if the other two instruments confirm the same directional story
within the alignment window.

Bullish alignment:
    CALL BUY + SPY BUY + PUT SELL

Bearish alignment:
    PUT BUY + SPY SELL + CALL SELL

The first signal can come from CALL, PUT, or SPY.
The agent grades every signal based on:
    1. Whether alignment exists
    2. How fast alignment completed
    3. Whether opposite side conflicts
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, Optional


SignalSide = Literal["BUY", "SELL"]
InstrumentType = Literal["SPY", "CALL", "PUT"]
Direction = Literal["BULLISH", "BEARISH", "CONFLICT", "INCOMPLETE"]


@dataclass
class SignalEvent:
    timestamp: datetime
    instrument: InstrumentType
    signal: SignalSide
    symbol: str
    price: Optional[float] = None


@dataclass
class AlignmentResult:
    direction: Direction
    aligned: bool
    grade: str
    score: int
    alignment_minutes: Optional[float]
    trigger: SignalEvent
    spy_signal: Optional[SignalEvent]
    call_signal: Optional[SignalEvent]
    put_signal: Optional[SignalEvent]
    explanation: str


class AlignmentAgent:
    def __init__(self, window_minutes: int = 15):
        self.window_minutes = window_minutes
        self.events: list[SignalEvent] = []

    def add_signal(self, event: SignalEvent) -> AlignmentResult:
        self.events.append(event)
        self.events.sort(key=lambda x: x.timestamp)
        return self.grade_signal(event)

    def grade_signal(self, trigger: SignalEvent) -> AlignmentResult:
        window_start = trigger.timestamp - timedelta(minutes=self.window_minutes)
        window_end = trigger.timestamp + timedelta(minutes=self.window_minutes)

        nearby = [
            e for e in self.events
            if window_start <= e.timestamp <= window_end
        ]

        latest_spy = self._latest(nearby, "SPY")
        latest_call = self._latest(nearby, "CALL")
        latest_put = self._latest(nearby, "PUT")

        bullish = (
            latest_spy and latest_spy.signal == "BUY"
            and latest_call and latest_call.signal == "BUY"
            and latest_put and latest_put.signal == "SELL"
        )

        bearish = (
            latest_spy and latest_spy.signal == "SELL"
            and latest_call and latest_call.signal == "SELL"
            and latest_put and latest_put.signal == "BUY"
        )

        if bullish:
            return self._build_result("BULLISH", trigger, latest_spy, latest_call, latest_put)

        if bearish:
            return self._build_result("BEARISH", trigger, latest_spy, latest_call, latest_put)

        score, explanation = self._partial_score(trigger, latest_spy, latest_call, latest_put)
        return AlignmentResult(
            direction="INCOMPLETE" if score >= 40 else "CONFLICT",
            aligned=False,
            grade=self._grade(score),
            score=score,
            alignment_minutes=None,
            trigger=trigger,
            spy_signal=latest_spy,
            call_signal=latest_call,
            put_signal=latest_put,
            explanation=explanation,
        )

    def _build_result(
        self,
        direction: Direction,
        trigger: SignalEvent,
        spy: SignalEvent,
        call: SignalEvent,
        put: SignalEvent,
    ) -> AlignmentResult:
        times = [spy.timestamp, call.timestamp, put.timestamp]
        alignment_minutes = (max(times) - min(times)).total_seconds() / 60

        speed_score = self._speed_score(alignment_minutes)
        score = min(100, 70 + speed_score)
        grade = self._grade(score)

        explanation = (
            f"{direction} alignment completed in {alignment_minutes:.1f} minutes. "
            f"SPY={spy.signal}, CALL={call.signal}, PUT={put.signal}. "
            f"Signal is valid because all three instruments agree within "
            f"{self.window_minutes} minutes."
        )

        return AlignmentResult(
            direction=direction,
            aligned=True,
            grade=grade,
            score=score,
            alignment_minutes=alignment_minutes,
            trigger=trigger,
            spy_signal=spy,
            call_signal=call,
            put_signal=put,
            explanation=explanation,
        )

    def _partial_score(self, trigger, spy, call, put) -> tuple[int, str]:
        score = 0

        # Trigger direction expectation
        if trigger.instrument == "CALL" and trigger.signal == "BUY":
            expected = {"SPY": "BUY", "CALL": "BUY", "PUT": "SELL"}
            direction = "BULLISH"
        elif trigger.instrument == "PUT" and trigger.signal == "BUY":
            expected = {"SPY": "SELL", "CALL": "SELL", "PUT": "BUY"}
            direction = "BEARISH"
        elif trigger.instrument == "SPY" and trigger.signal == "BUY":
            expected = {"SPY": "BUY", "CALL": "BUY", "PUT": "SELL"}
            direction = "BULLISH"
        elif trigger.instrument == "SPY" and trigger.signal == "SELL":
            expected = {"SPY": "SELL", "CALL": "SELL", "PUT": "BUY"}
            direction = "BEARISH"
        elif trigger.instrument == "CALL" and trigger.signal == "SELL":
            expected = {"SPY": "SELL", "CALL": "SELL", "PUT": "BUY"}
            direction = "BEARISH"
        else:
            expected = {"SPY": "BUY", "CALL": "BUY", "PUT": "SELL"}
            direction = "BULLISH"

        found = {"SPY": spy, "CALL": call, "PUT": put}
        matches = []
        conflicts = []
        missing = []

        for inst, exp_signal in expected.items():
            ev = found[inst]
            if not ev:
                missing.append(inst)
            elif ev.signal == exp_signal:
                matches.append(inst)
            else:
                conflicts.append(inst)

        score = len(matches) * 33
        if conflicts:
            score -= len(conflicts) * 25
        score = max(0, min(100, score))

        explanation = (
            f"Trigger expects {direction} alignment. "
            f"Matched: {matches}. Missing: {missing}. Conflicts: {conflicts}. "
            f"Signal is not fully safe until SPY, CALL, and PUT all align."
        )

        return score, explanation

    def _latest(self, events: list[SignalEvent], instrument: InstrumentType) -> Optional[SignalEvent]:
        filtered = [e for e in events if e.instrument == instrument]
        return max(filtered, key=lambda x: x.timestamp) if filtered else None

    def _speed_score(self, minutes: float) -> int:
        if minutes <= 3:
            return 30
        if minutes <= 6:
            return 25
        if minutes <= 10:
            return 18
        if minutes <= 15:
            return 10
        return 0

    def _grade(self, score: int) -> str:
        if score >= 95:
            return "A+"
        if score >= 85:
            return "A"
        if score >= 75:
            return "B"
        if score >= 60:
            return "C"
        return "NO TRADE"
