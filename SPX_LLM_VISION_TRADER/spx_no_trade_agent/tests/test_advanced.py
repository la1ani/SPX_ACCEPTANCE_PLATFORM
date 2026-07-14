"""
Tests for the four additions that close the gaps identified in the
earlier code audit: exit rule, multi-touch level memory, slow-leak
detection, cross-side gate, and rejection-trigger propagation.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from spx_agent import (
    Candle,
    ChartExtraction,
    ChartReasoningAgent,
    DualSideEngine,
    ExitRuleParams,
    LevelMemory,
    LevelRead,
    LevelType,
    SheetTick,
    Side,
    TrailingStopExitRule,
    Zone,
)
from spx_agent.models import FinalCall


def _candle(ts, o, h, l, c, v=100, tf=180):
    return Candle(timestamp=ts, open=o, high=h, low=l, close=c, volume=v, timeframe_seconds=tf)


def test_hard_stop_fires_at_10_percent_loss():
    rule = TrailingStopExitRule(ExitRuleParams(hard_stop_pct=10.0, trailing_stop_pct=5.0))
    assert rule.check(entry_price=100.0, peak_price=100.0, current_price=89.9) == "hard_stop"
    assert rule.check(entry_price=100.0, peak_price=100.0, current_price=91.0) is None


def test_trailing_stop_fires_5_percent_off_peak():
    rule = TrailingStopExitRule(ExitRuleParams(hard_stop_pct=10.0, trailing_stop_pct=5.0))
    assert rule.check(entry_price=100.0, peak_price=120.0, current_price=113.9) == "trailing_stop"
    assert rule.check(entry_price=100.0, peak_price=120.0, current_price=116.4) is None


def test_trailing_stop_does_not_fire_before_reaching_profit():
    rule = TrailingStopExitRule(ExitRuleParams(hard_stop_pct=10.0, trailing_stop_pct=5.0))
    assert rule.check(entry_price=100.0, peak_price=100.0, current_price=97.0) is None


def test_level_memory_accumulates_rejections_across_touches():
    mem = LevelMemory()
    level = LevelRead(level_type=LevelType.RESISTANCE, price=100.0, timeframe_seconds=180)
    base = datetime(2026, 7, 14, 10, 0, 0)
    mem.record_touch(Side.PUT, level, base, 100.0, velocity_during_approach=0.01, body_ratio=0.1, resolved_as="rejected")
    mem.record_touch(Side.PUT, level, base + timedelta(minutes=5), 100.0, velocity_during_approach=0.01, body_ratio=0.1, resolved_as="rejected")
    history = mem.get_history(Side.PUT, level)
    assert history.rejection_count == 2
    assert history.is_confirmed_weak is True
    assert mem.confidence_boost_for(Side.PUT, level) > 0


def test_level_memory_not_confirmed_weak_after_a_break():
    mem = LevelMemory()
    level = LevelRead(level_type=LevelType.RESISTANCE, price=100.0, timeframe_seconds=180)
    base = datetime(2026, 7, 14, 10, 0, 0)
    mem.record_touch(Side.PUT, level, base, 100.0, velocity_during_approach=0.01, body_ratio=0.1, resolved_as="rejected")
    mem.record_touch(Side.PUT, level, base + timedelta(minutes=5), 101.0, velocity_during_approach=0.5, body_ratio=0.8, resolved_as="broke")
    history = mem.get_history(Side.PUT, level)
    assert history.is_confirmed_weak is False


def test_slow_leak_through_level_reads_as_consolidation_not_break():
    base = datetime(2026, 7, 14, 10, 0, 0)
    resistance = 100.0
    candles = [
        _candle(base, 98.0, 98.6, 97.8, 98.3, tf=180),
        _candle(base + timedelta(minutes=3), 98.3, 99.0, 98.1, 98.6, tf=180),
        _candle(base + timedelta(minutes=6), 98.6, 99.3, 98.4, 98.9, tf=180),
        _candle(base + timedelta(minutes=9), 98.9, 100.5, 98.7, 100.2, tf=180),
    ]
    levels = [LevelRead(level_type=LevelType.RESISTANCE, price=resistance, timeframe_seconds=180)]
    extraction = ChartExtraction(timestamp=base + timedelta(minutes=9), side=Side.CALL, levels=levels, candles_by_timeframe={180: candles})
    verdict = ChartReasoningAgent().evaluate(extraction)
    assert verdict.zone == Zone.CONSOLIDATION


def _flat_extraction(side, base, price=10.0):
    candles = [_candle(base + timedelta(minutes=i * 3), price, price + 0.05, price - 0.05, price, tf=180) for i in range(6)]
    return ChartExtraction(timestamp=base, side=side, levels=[], candles_by_timeframe={180: candles})


def test_cross_side_gate_vetoes_call_when_put_is_holding_support():
    base = datetime(2026, 7, 14, 10, 0, 0)
    engine = DualSideEngine()
    ticks = []
    for i in range(20):
        ticks.append(SheetTick(timestamp=base + timedelta(seconds=i * 3), call_price=25.0 + i * 0.3, put_price=10.0, call_volume=10 + i * 15, put_volume=10))
    call_extraction = _flat_extraction(Side.CALL, base, price=25.0)
    put_extraction = _flat_extraction(Side.PUT, base, price=10.0)
    put_extraction.levels = [LevelRead(level_type=LevelType.SUPPORT, price=10.0, timeframe_seconds=180)]
    dual = engine.decide(ticks, call_extraction, put_extraction, base + timedelta(seconds=57))
    if dual.put_decision.data_verdict.evidence.get("holding_seconds", 0) and dual.put_decision.data_verdict.zone == Zone.CONSOLIDATION:
        assert dual.call_gated is True
        assert dual.call_decision.final_call == FinalCall.NO_TRADE


def test_rejection_trigger_promotes_other_side_early():
    from spx_agent.data_agent import DataReasoningAgent
    base = datetime(2026, 7, 14, 10, 0, 0)
    agent = DataReasoningAgent()
    level = LevelRead(level_type=LevelType.RESISTANCE, price=10.0, timeframe_seconds=180)
    ticks = [SheetTick(timestamp=base + timedelta(seconds=i * 3), call_price=25.0, put_price=10.0, call_volume=10, put_volume=10) for i in range(10)]
    agent.evaluate(ticks, nearby_level=level, level_side_is_call=False, previous_holding_seconds=40.0)
    ticks2 = ticks + [SheetTick(timestamp=base + timedelta(seconds=33), call_price=25.0, put_price=8.0, call_volume=10, put_volume=10)]
    verdict2 = agent.evaluate(ticks2, nearby_level=level, level_side_is_call=False, previous_holding_seconds=40.0)
    assert verdict2.evidence["rejection_just_occurred"] is True


if __name__ == "__main__":
    import inspect
    failures = []
    module = sys.modules[__name__]
    test_fns = [(name, fn) for name, fn in vars(module).items() if name.startswith("test_") and inspect.isfunction(fn)]
    for name, fn in test_fns:
        try:
            fn()
            print(f"PASS  {name}")
        except AssertionError as e:
            failures.append(name)
            print(f"FAIL  {name}: {e}")
        except Exception as e:
            failures.append(name)
            print(f"ERROR {name}: {e!r}")
    print(f"\n{len(test_fns) - len(failures)}/{len(test_fns)} passed")
    if failures:
        sys.exit(1)
