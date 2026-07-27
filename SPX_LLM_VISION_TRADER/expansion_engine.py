"""CALL/PUT opposite-expansion confirmation engine.

This is deliberately level-free. It does not know about support, resistance,
rejection, holding time, indicators, or price location. It answers one
question only: did one option expand and did the other option subsequently
expand in the opposite direction?
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from statistics import median


class Side(str, Enum):
    CALL = "CALL"
    PUT = "PUT"


class Direction(str, Enum):
    UP = "UP"
    DOWN = "DOWN"


class Status(str, Enum):
    NO_TRADE = "NO_TRADE"
    FIRST_SIDE_ARMED = "FIRST_SIDE_ARMED"
    CONFIRMED_CALL = "CONFIRMED_CALL"
    CONFIRMED_PUT = "CONFIRMED_PUT"


@dataclass(frozen=True)
class Candle:
    side: Side
    timeframe_minutes: int
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def full_range(self) -> float:
        return max(self.high - self.low, 1e-9)

    @property
    def body_ratio(self) -> float:
        return self.body / self.full_range

    @property
    def direction(self) -> Direction | None:
        if self.close > self.open:
            return Direction.UP
        if self.close < self.open:
            return Direction.DOWN
        return None


@dataclass(frozen=True)
class Expansion:
    side: Side
    direction: Direction
    timeframe_minutes: int
    timestamp: datetime
    body: float
    baseline_body: float
    expansion_multiple: float


@dataclass
class Decision:
    status: Status
    reason: str
    first: Expansion | None = None
    confirmation: Expansion | None = None
    alert: bool = False


@dataclass
class ExpansionDetector:
    body_multiple: float = 1.5
    minimum_body_ratio: float = 0.60
    baseline_candles: int = 3
    allowed_timeframes: tuple[int, ...] = (3, 15)

    def detect(self, candles: list[Candle]) -> Expansion | None:
        if len(candles) < self.baseline_candles + 1:
            return None
        current = candles[-1]
        if current.timeframe_minutes not in self.allowed_timeframes or current.direction is None:
            return None

        prior = candles[-(self.baseline_candles + 1):-1]
        baseline = median(c.body for c in prior)
        if baseline <= 0:
            positive_bodies = [c.body for c in prior if c.body > 0]
            baseline = median(positive_bodies) if positive_bodies else 0.0
        if baseline <= 0:
            return None

        multiple = current.body / baseline
        if multiple < self.body_multiple or current.body_ratio < self.minimum_body_ratio:
            return None

        # Require the body to continue beyond the previous close. This filters a
        # large candle that merely retraces inside the immediately preceding body.
        previous = prior[-1]
        continued = (
            current.direction is Direction.UP and current.close > previous.close
        ) or (
            current.direction is Direction.DOWN and current.close < previous.close
        )
        if not continued:
            return None

        return Expansion(
            side=current.side,
            direction=current.direction,
            timeframe_minutes=current.timeframe_minutes,
            timestamp=current.timestamp,
            body=current.body,
            baseline_body=baseline,
            expansion_multiple=multiple,
        )


@dataclass
class OppositeExpansionEngine:
    detector: ExpansionDetector = field(default_factory=ExpansionDetector)
    max_confirmation_minutes: int = 45
    armed: Expansion | None = None
    _seen: set[tuple[Side, int, datetime]] = field(default_factory=set)
    _last_alert_pair: tuple[datetime, datetime] | None = None

    @staticmethod
    def _age_minutes(now: datetime, then: datetime) -> float:
        # Vision models occasionally omit the UTC offset. Treat both values as
        # wall-clock chart time rather than crashing the live loop.
        if (now.tzinfo is None) != (then.tzinfo is None):
            now = now.replace(tzinfo=None)
            then = then.replace(tzinfo=None)
        return (now - then).total_seconds() / 60

    @staticmethod
    def _confirms(first: Expansion, second: Expansion) -> bool:
        if first.side is second.side or first.direction is second.direction:
            return False
        return (
            first.side is Side.CALL
            and first.direction is Direction.UP
            and second.side is Side.PUT
            and second.direction is Direction.DOWN
        ) or (
            first.side is Side.PUT
            and first.direction is Direction.DOWN
            and second.side is Side.CALL
            and second.direction is Direction.UP
        ) or (
            first.side is Side.PUT
            and first.direction is Direction.UP
            and second.side is Side.CALL
            and second.direction is Direction.DOWN
        ) or (
            first.side is Side.CALL
            and first.direction is Direction.DOWN
            and second.side is Side.PUT
            and second.direction is Direction.UP
        )

    @staticmethod
    def _trade_status(first: Expansion, second: Expansion) -> Status:
        call_direction = first.direction if first.side is Side.CALL else second.direction
        return Status.CONFIRMED_CALL if call_direction is Direction.UP else Status.CONFIRMED_PUT

    def process(self, candles_by_stream: dict[tuple[Side, int], list[Candle]], now: datetime) -> Decision:
        if self.armed and self._age_minutes(now, self.armed.timestamp) > self.max_confirmation_minutes:
            self.armed = None

        fresh: list[Expansion] = []
        for key, candles in candles_by_stream.items():
            expansion = self.detector.detect(candles)
            if expansion is None:
                continue
            event_key = (expansion.side, expansion.timeframe_minutes, expansion.timestamp)
            if event_key not in self._seen:
                self._seen.add(event_key)
                fresh.append(expansion)

        fresh.sort(key=lambda event: event.timestamp)
        for event in fresh:
            if self.armed and event.timestamp > self.armed.timestamp and self._confirms(self.armed, event):
                pair = (self.armed.timestamp, event.timestamp)
                if pair != self._last_alert_pair:
                    first = self.armed
                    self._last_alert_pair = pair
                    self.armed = None
                    return Decision(
                        status=self._trade_status(first, event),
                        reason=(
                            f"{first.side.value} {first.direction.value} expansion armed first; "
                            f"{event.side.value} {event.direction.value} expansion confirmed later."
                        ),
                        first=first,
                        confirmation=event,
                        alert=True,
                    )

            # A new unconfirmed expansion becomes the current first leg. Same-side
            # continuation refreshes it; contradictory movement cancels the old setup.
            self.armed = event

        if self.armed:
            required_side = Side.PUT if self.armed.side is Side.CALL else Side.CALL
            required_direction = Direction.DOWN if self.armed.direction is Direction.UP else Direction.UP
            return Decision(
                status=Status.FIRST_SIDE_ARMED,
                reason=(
                    f"{self.armed.side.value} {self.armed.direction.value} expansion exists, "
                    f"but {required_side.value} {required_direction.value} expansion is missing. NO TRADE."
                ),
                first=self.armed,
            )

        return Decision(
            status=Status.NO_TRADE,
            reason="No valid opposite CALL/PUT expansion pair. NO TRADE.",
        )
