"""
Chart-reasoning agent.

Reasons over the LLM-extracted chart facts (support/resistance levels,
candle stacking, wick/body shape) at multiple timeframes. This is where the
"wick reaches the level first, body follows slowly (or never)" pattern and
the "multi-timeframe noise trap" live.

Nothing here is a fixed threshold applied blindly — every number below is a
tunable parameter the self-learning loop is meant to adjust over time
(see learning.py). The judgment being formed is: does this candle stacking
show real conviction, or is it a wick fooling us into thinking price has
power it doesn't have?
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Candle, ChartExtraction, LevelRead, Verdict, Zone


@dataclass
class ChartAgentParams:
    """
    Tunable parameters. Defaults are starting points, not gospel — the
    self-learning loop nudges these based on logged outcomes over time.
    """
    body_ratio_conviction: float = 0.55
    body_ratio_wick_only: float = 0.20
    stacking_lookback: int = 4
    stacking_agreement_ratio: float = 0.75
    near_level_pct: float = 0.0015


class ChartReasoningAgent:
    def __init__(self, params: ChartAgentParams | None = None):
        self.params = params or ChartAgentParams()

    def evaluate(self, extraction: ChartExtraction) -> Verdict:
        per_timeframe = {
            tf: self._read_timeframe(candles, extraction.levels, tf)
            for tf, candles in extraction.candles_by_timeframe.items()
        }

        if not per_timeframe:
            return Verdict(
                zone=Zone.CONSOLIDATION,
                confidence=0.3,
                reasoning="No candle data available for any timeframe — treating as no-trade by default since there is nothing to confirm a move.",
                evidence={},
            )

        return self._reconcile_timeframes(per_timeframe)

    def _read_timeframe(self, candles: list[Candle], levels: list[LevelRead], timeframe_seconds: int) -> dict:
        p = self.params
        recent = candles[-p.stacking_lookback:] if len(candles) >= p.stacking_lookback else candles
        directions = [c.direction for c in recent if c.direction != 0]
        conviction_candles = [c for c in recent if c.body_ratio >= p.body_ratio_conviction]
        wick_only_candles = [c for c in recent if c.body_ratio <= p.body_ratio_wick_only]

        stacking_direction = 0
        stacking_conviction = 0.0
        if directions:
            up = sum(1 for d in directions if d > 0)
            down = sum(1 for d in directions if d < 0)
            total = len(directions)
            if up / total >= p.stacking_agreement_ratio:
                stacking_direction = 1
            elif down / total >= p.stacking_agreement_ratio:
                stacking_direction = -1
            stacking_conviction = len(conviction_candles) / max(len(recent), 1)

        level_touch = self._nearest_level_touch(recent, levels, timeframe_seconds)
        slow_leak_level = self._slow_leak_check(recent, levels, timeframe_seconds, stacking_conviction)

        return {
            "timeframe_seconds": timeframe_seconds,
            "stacking_direction": stacking_direction,
            "stacking_conviction": stacking_conviction,
            "wick_only_ratio": len(wick_only_candles) / max(len(recent), 1),
            "level_touch": level_touch,
            "slow_leak_level": slow_leak_level,
            "candle_count": len(recent),
        }

    def _slow_leak_check(self, recent: list[Candle], levels: list[LevelRead], timeframe_seconds: int, stacking_conviction: float) -> LevelRead | None:
        p = self.params
        if len(recent) < 2:
            return None
        tf_levels = [lv for lv in levels if lv.timeframe_seconds == timeframe_seconds]
        start_price, end_price = recent[0].close, recent[-1].close

        for lv in tf_levels:
            crossed = (start_price < lv.price <= end_price) or (start_price > lv.price >= end_price)
            if crossed and stacking_conviction < p.body_ratio_conviction:
                return lv
        return None

    def _nearest_level_touch(self, recent: list[Candle], levels: list[LevelRead], timeframe_seconds: int) -> dict | None:
        p = self.params
        tf_levels = [lv for lv in levels if lv.timeframe_seconds == timeframe_seconds]
        if not tf_levels or not recent:
            return None

        last = recent[-1]
        for lv in tf_levels:
            near = abs(last.high - lv.price) / lv.price <= p.near_level_pct or abs(last.low - lv.price) / lv.price <= p.near_level_pct
            if not near:
                continue

            wick_touched = (last.high >= lv.price - lv.price * p.near_level_pct) or (last.low <= lv.price + lv.price * p.near_level_pct)
            body_followed = last.body_ratio >= p.body_ratio_conviction

            return {"level": lv, "wick_touched": wick_touched, "body_followed": body_followed}
        return None

    def _reconcile_timeframes(self, per_timeframe: dict[int, dict]) -> Verdict:
        timeframes_sorted = sorted(per_timeframe.keys())
        shortest = per_timeframe[timeframes_sorted[0]]
        longest = per_timeframe[timeframes_sorted[-1]]
        evidence = {"per_timeframe": per_timeframe}

        touch = longest.get("level_touch") or shortest.get("level_touch")
        if touch and touch["wick_touched"] and not touch["body_followed"]:
            return Verdict(zone=Zone.CONSOLIDATION, confidence=0.75, reasoning=(f"Wick reached {touch['level'].level_type.value} at {touch['level'].price:.2f} but the body never followed through — classic fakeout signature. No power behind the move."), evidence=evidence)

        slow_leak = longest.get("slow_leak_level") or shortest.get("slow_leak_level")
        if slow_leak:
            return Verdict(zone=Zone.CONSOLIDATION, confidence=0.7, reasoning=(f"Price crossed {slow_leak.level_type.value} at {slow_leak.price:.2f} over several candles, but without real body conviction behind the crossing — a slow-leak fakeout, not a genuine break."), evidence=evidence)

        if shortest["stacking_direction"] != 0 and longest["stacking_direction"] == 0:
            return Verdict(zone=Zone.CONSOLIDATION, confidence=0.65, reasoning=("Short-timeframe candles show a directional wiggle, but the longer timeframe shows no real net movement — this looks like short-term noise round-tripping back to where it started, not a real move."), evidence=evidence)

        if shortest["stacking_direction"] != 0 and shortest["stacking_direction"] == longest["stacking_direction"]:
            direction = shortest["stacking_direction"]
            conviction = (shortest["stacking_conviction"] + longest["stacking_conviction"]) / 2
            zone = Zone.BULLISH if direction > 0 else Zone.BEARISH

            if conviction >= self.params.body_ratio_conviction:
                return Verdict(zone=zone, confidence=min(0.55 + conviction * 0.4, 0.95), reasoning=(f"Candle bodies stack cleanly {'up' if direction > 0 else 'down'} across both the short and long timeframe, with real body conviction behind them — this looks like a genuine directional move."), evidence=evidence)
            return Verdict(zone=Zone.SLOW_MOVING, confidence=0.5, reasoning=(f"Both timeframes lean {'up' if direction > 0 else 'down'}, but candle bodies aren't showing full conviction — this is the cautious, slow-moving case, not a clean setup and not flat chop either."), evidence=evidence)

        return Verdict(zone=Zone.CONSOLIDATION, confidence=0.6, reasoning="No consistent candle stacking direction across timeframes — reads as chop.", evidence=evidence)
