"""
Unit tests for the core reasoning behaviors — not testing the demo/CSV
plumbing, but the actual judgments each component is supposed to make.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from spx_agent import (
    Boss,
    Candle,
    ChartExtraction,
    ChartReasoningAgent,
    DataAgentParams,
    DataReasoningAgent,
    FinalCall,
    LevelRead,
    LevelType,
    SelfLearningLog,
    SheetTick,
    Side,
    Zone,
)


def _candle(ts, o, h, l, c, v=100, tf=180):
    return Candle(timestamp=ts, open=o, high=h, low=l, close=c, volume=v, timeframe_seconds=tf)


def test_wick_fakeout_reads_as_consolidation():
    base = datetime(2026, 7, 14, 10, 0, 0)
    resistance = 100.0
    candles = [
        _candle(base, 90, 92, 89, 91),
        _candle(base + timedelta(minutes=3), 91, 93, 90, 92),
        _candle(base + timedelta(minutes=6), 92, 94, 91, 93),
        _candle(base + timedelta(minutes=9), 93, 100.1, 92, 93.5),
    ]
    levels = [LevelRead(level_type=LevelType.RESISTANCE, price=resistance, timeframe_seconds=180)]
    extraction = ChartExtraction(
        timestamp=base + timedelta(minutes=9),
        side=Side.CALL,
        levels=levels,
        candles_by_timeframe={180: candles},
    )
    verdict = ChartReasoningAgent().evaluate(extraction)
    assert verdict.zone == Zone.CONSOLIDATION
    assert "body never followed" in verdict.reasoning


def test_clean_stacking_across_timeframes_reads_bullish():
    base = datetime(2026, 7, 14, 10, 0, 0)
    short_tf = [_candle(base + timedelta(minutes=i * 3), 90 + i, 91 + i, 89.8 + i, 90.9 + i) for i in range(6)]
    long_tf = [_candle(base + timedelta(minutes=i * 15), 90 + i * 2, 92 + i * 2, 89.5 + i * 2, 91.8 + i * 2) for i in range(6)]
    extraction = ChartExtraction(timestamp=base + timedelta(minutes=15), side=Side.CALL, levels=[], candles_by_timeframe={180: short_tf, 900: long_tf})
    verdict = ChartReasoningAgent().evaluate(extraction)
    assert verdict.zone == Zone.BULLISH


def test_short_timeframe_noise_without_long_timeframe_confirmation_is_consolidation():
    base = datetime(2026, 7, 14, 10, 0, 0)
    short_tf = [_candle(base + timedelta(minutes=i * 3), 90 + i * 0.3, 90.5 + i * 0.3, 89.9 + i * 0.3, 90.4 + i * 0.3) for i in range(6)]
    long_tf = [_candle(base + timedelta(minutes=i * 15), 90, 90.5, 89.5, 90 + (0.1 if i % 2 == 0 else -0.1)) for i in range(6)]
    extraction = ChartExtraction(timestamp=base + timedelta(minutes=15), side=Side.CALL, levels=[], candles_by_timeframe={180: short_tf, 900: long_tf})
    verdict = ChartReasoningAgent().evaluate(extraction)
    assert verdict.zone == Zone.CONSOLIDATION
    assert "noise" in verdict.reasoning or "round-trip" in verdict.reasoning


def test_data_agent_flat_velocity_reads_consolidation():
    base = datetime(2026, 7, 14, 10, 0, 0)
    ticks = [SheetTick(timestamp=base + timedelta(seconds=i * 3), call_price=25.0, put_price=15.0, call_volume=10, put_volume=10) for i in range(10)]
    verdict = DataReasoningAgent().evaluate(ticks)
    assert verdict.zone == Zone.CONSOLIDATION


def test_data_agent_real_momentum_with_seesaw_reads_directional():
    base = datetime(2026, 7, 14, 10, 0, 0)
    ticks = []
    for i in range(10):
        ticks.append(SheetTick(timestamp=base + timedelta(seconds=i * 3), call_price=25.0 + i * 1.5, put_price=15.0 - i * 1.0, call_volume=10 + i * 20, put_volume=10))
    params = DataAgentParams(velocity_flat_threshold=0.02, volume_spike_multiplier=1.5)
    verdict = DataReasoningAgent(params).evaluate(ticks)
    assert verdict.zone == Zone.BULLISH


def test_boss_agreement_on_bullish_issues_trade():
    from spx_agent.models import Verdict
    chart_v = Verdict(zone=Zone.BULLISH, confidence=0.8, reasoning="chart says bullish")
    data_v = Verdict(zone=Zone.BULLISH, confidence=0.8, reasoning="data says bullish")
    decision = Boss(min_confidence_for_trade=0.65).decide(Side.CALL, chart_v, data_v)
    assert decision.final_call == FinalCall.TRADE_BULLISH
    assert decision.aligned is True


def test_boss_disagreement_defaults_to_no_trade():
    from spx_agent.models import Verdict
    chart_v = Verdict(zone=Zone.BULLISH, confidence=0.9, reasoning="chart says bullish")
    data_v = Verdict(zone=Zone.CONSOLIDATION, confidence=0.9, reasoning="data says nothing is happening")
    decision = Boss().decide(Side.CALL, chart_v, data_v)
    assert decision.final_call == FinalCall.NO_TRADE
    assert decision.aligned is False


def test_boss_agreement_on_consolidation_is_no_trade():
    from spx_agent.models import Verdict
    chart_v = Verdict(zone=Zone.CONSOLIDATION, confidence=0.7, reasoning="chop")
    data_v = Verdict(zone=Zone.CONSOLIDATION, confidence=0.7, reasoning="dead")
    decision = Boss().decide(Side.CALL, chart_v, data_v)
    assert decision.final_call == FinalCall.NO_TRADE
    assert decision.aligned is True


def test_boss_low_confidence_agreement_is_cautious_not_full_trade():
    from spx_agent.models import Verdict
    chart_v = Verdict(zone=Zone.BULLISH, confidence=0.5, reasoning="weak bullish lean")
    data_v = Verdict(zone=Zone.BULLISH, confidence=0.5, reasoning="weak bullish lean")
    decision = Boss(min_confidence_for_trade=0.65).decide(Side.CALL, chart_v, data_v)
    assert decision.final_call == FinalCall.CAUTIOUS_TRADE


def test_learning_log_records_and_computes_false_rates(tmp_path):
    from spx_agent.models import Decision, Verdict
    log_path = tmp_path / "test_log.jsonl"
    log = SelfLearningLog(path=log_path)
    ts = datetime(2026, 7, 14, 10, 0, 0)
    chart_v = Verdict(zone=Zone.CONSOLIDATION, confidence=0.7, reasoning="chop")
    data_v = Verdict(zone=Zone.CONSOLIDATION, confidence=0.7, reasoning="dead")
    decision = Decision(timestamp=ts, side=Side.CALL, final_call=FinalCall.NO_TRADE, confidence=0.7, aligned=True, chart_verdict=chart_v, data_verdict=data_v, narrative="no trade")
    decision_id = log.record_decision(decision)
    log.record_outcome(decision_id, outcome="false_signal", notes="price actually broke out after this")
    assert log.false_no_trade_rate() == 1.0
    log2 = SelfLearningLog(path=log_path)
    assert log2.false_no_trade_rate() == 1.0


if __name__ == "__main__":
    import inspect
    failures = []
    module = sys.modules[__name__]
    test_fns = [(name, fn) for name, fn in vars(module).items() if name.startswith("test_") and inspect.isfunction(fn)]
    for name, fn in test_fns:
        try:
            sig = inspect.signature(fn)
            if "tmp_path" in sig.parameters:
                import tempfile
                with tempfile.TemporaryDirectory() as d:
                    fn(Path(d))
            else:
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
