"""
Level tracker — multi-touch memory for a support/resistance level.

Addresses a specific gap identified from live chart review: at short
timeframes, a level typically takes SEVERAL attempts (touch, reject, touch
again, reject again) before it resolves, not one clean touch. Each
individual attempt runs the same rejection-vs-break logic, but they need to
be tracked as ONE ongoing situation at that level, not isolated events —
because repeated failed attempts reinforce the read (more confidence the
level is genuinely holding), not dilute it.

This module holds that memory across calls to the reasoning agents, keyed
by (side, level_type, rounded price) so repeated touches of "the same"
level accumulate in one LevelHistory rather than each looking like a fresh,
unconfirmed level every time.
"""

from __future__ import annotations

from datetime import datetime

from .models import LevelHistory, LevelRead, LevelTouch, LevelType, Side


def _level_key(side: Side, level: LevelRead, price_bucket_pct: float = 0.003) -> tuple:
    bucket = round(level.price / (level.price * price_bucket_pct))
    return (side, level.level_type, level.timeframe_seconds, bucket)


class LevelMemory:
    def __init__(self):
        self._histories: dict[tuple, LevelHistory] = {}

    def record_touch(self, side: Side, level: LevelRead, timestamp: datetime, price: float, velocity_during_approach: float, body_ratio: float, resolved_as: str) -> LevelHistory:
        key = _level_key(side, level)
        history = self._histories.get(key)
        if history is None:
            history = LevelHistory(level_type=level.level_type, price=level.price, timeframe_seconds=level.timeframe_seconds)
            self._histories[key] = history

        history.touches.append(LevelTouch(timestamp=timestamp, price=price, velocity_during_approach=velocity_during_approach, body_ratio=body_ratio, resolved_as=resolved_as))
        return history

    def get_history(self, side: Side, level: LevelRead) -> LevelHistory | None:
        return self._histories.get(_level_key(side, level))

    def confidence_boost_for(self, side: Side, level: LevelRead) -> float:
        history = self.get_history(side, level)
        if history is None:
            return 0.0
        return min(history.rejection_count * 0.05, 0.15)
