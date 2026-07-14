"""
Core data models for the SPX 0DTE call/put reasoning agent.

These are plain, dependency-free dataclasses. Nothing here does I/O or talks
to any external service — that is deliberate: connectors (see connectors.py)
are the only code allowed to touch the outside world (Google Sheet, chart
image, LLM). Everything downstream of a connector operates purely on these
structures, which keeps the reasoning logic testable and swappable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Side(str, Enum):
    CALL = "call"
    PUT = "put"


class Zone(str, Enum):
    """
    The four-way classification both reasoning agents (and the boss) work
    with. This is intentionally NOT binary trade/no-trade — a slow-moving
    zone is a distinct, lower-conviction state from flat consolidation.
    """
    BULLISH = "bullish"
    BEARISH = "bearish"
    CONSOLIDATION = "consolidation"
    SLOW_MOVING = "slow_moving"


class LevelType(str, Enum):
    SUPPORT = "support"
    RESISTANCE = "resistance"


class FinalCall(str, Enum):
    """What the boss actually issues. NO_TRADE is the expected default."""
    NO_TRADE = "no_trade"
    CAUTIOUS_TRADE = "cautious_trade"
    TRADE_BULLISH = "trade_bullish"
    TRADE_BEARISH = "trade_bearish"


@dataclass
class Candle:
    """One OHLCV bar at a given timeframe (e.g. 15s, 1m, 5m, 15m)."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    timeframe_seconds: int

    @property
    def body_size(self) -> float:
        return abs(self.close - self.open)

    @property
    def range_size(self) -> float:
        return max(self.high - self.low, 1e-9)

    @property
    def upper_wick(self) -> float:
        return self.high - max(self.open, self.close)

    @property
    def lower_wick(self) -> float:
        return min(self.open, self.close) - self.low

    @property
    def body_ratio(self) -> float:
        """Body as a fraction of the full range. Low = wick-dominated candle."""
        return self.body_size / self.range_size

    @property
    def direction(self) -> int:
        """+1 bullish candle, -1 bearish candle, 0 doji/flat."""
        if self.close > self.open:
            return 1
        if self.close < self.open:
            return -1
        return 0


@dataclass
class SheetTick:
    """One row of live data coming in from the Google Sheet."""
    timestamp: datetime
    call_price: float
    put_price: float
    call_volume: float
    put_volume: float


@dataclass
class LevelRead:
    """A support/resistance level at a specific timeframe."""
    level_type: LevelType
    price: float
    timeframe_seconds: int


@dataclass
class ChartExtraction:
    """
    Structured facts extracted from the chart image by the LLM/vision step.
    This is the ONLY thing the LLM produces — pure extraction, no judgment.
    Everything below this point in the pipeline is plain Python reasoning.
    """
    timestamp: datetime
    side: Side
    levels: list[LevelRead]
    candles_by_timeframe: dict[int, list[Candle]]
    indicator_notes: str = ""


@dataclass
class Verdict:
    """
    What a single reasoning agent (chart-side or data-side) concludes.
    Both agents produce this same shape so the boss can compare them directly.
    """
    zone: Zone
    confidence: float
    reasoning: str
    evidence: dict = field(default_factory=dict)


@dataclass
class Decision:
    """The boss's final, reconciled call."""
    timestamp: datetime
    side: Side
    final_call: FinalCall
    confidence: float
    aligned: bool
    chart_verdict: Verdict
    data_verdict: Verdict
    narrative: str
    rejection_trigger: bool = False


@dataclass
class LevelTouch:
    """One recorded touch of a level — part of the multi-touch memory for that level."""
    timestamp: datetime
    price: float
    velocity_during_approach: float
    body_ratio: float
    resolved_as: str


@dataclass
class LevelHistory:
    """
    Tracks every touch of a specific support/resistance level over the
    session, so repeated failed attempts reinforce the read instead of
    being treated as isolated new events each time.
    """
    level_type: LevelType
    price: float
    timeframe_seconds: int
    touches: list[LevelTouch] = field(default_factory=list)

    @property
    def rejection_count(self) -> int:
        return sum(1 for t in self.touches if t.resolved_as == "rejected")

    @property
    def break_count(self) -> int:
        return sum(1 for t in self.touches if t.resolved_as == "broke")

    @property
    def is_confirmed_weak(self) -> bool:
        return self.rejection_count >= 2 and self.break_count == 0


@dataclass
class DualSideDecision:
    timestamp: datetime
    call_decision: Decision
    put_decision: Decision
    call_gated: bool
    put_gated: bool
    gate_reason: str


@dataclass
class SimulatedTrade:
    """One simulated (paper, no broker) trade — entry through exit."""
    trade_id: str
    side: Side
    entry_timestamp: datetime
    entry_price: float
    entry_reasoning: str
    exit_timestamp: datetime | None = None
    exit_price: float | None = None
    exit_reason: str | None = None
    peak_price: float = 0.0
    pnl_pct: float | None = None

    def close(self, timestamp: datetime, price: float, reason: str) -> None:
        self.exit_timestamp = timestamp
        self.exit_price = price
        self.exit_reason = reason
        direction = 1 if self.side_is_long else -1
        self.pnl_pct = direction * (price - self.entry_price) / self.entry_price * 100

    @property
    def side_is_long(self) -> bool:
        return True
