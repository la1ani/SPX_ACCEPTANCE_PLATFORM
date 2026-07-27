from datetime import datetime, timedelta

from expansion_engine import (
    Candle,
    Direction,
    ExpansionDetector,
    OppositeExpansionEngine,
    Side,
    Status,
)


BASE = datetime(2026, 7, 26, 10, 0)


def candles(side, timeframe, closes, last_body=None):
    result = []
    for index, close in enumerate(closes):
        open_price = close - 0.2
        if index == len(closes) - 1 and last_body is not None:
            open_price = close - last_body if last_body > 0 else close + abs(last_body)
        result.append(
            Candle(
                side=side,
                timeframe_minutes=timeframe,
                timestamp=BASE + timedelta(minutes=timeframe * index),
                open=open_price,
                high=max(open_price, close) + 0.05,
                low=min(open_price, close) - 0.05,
                close=close,
            )
        )
    return result


def test_call_expands_but_put_does_not_is_no_trade():
    engine = OppositeExpansionEngine()
    streams = {
        (Side.CALL, 3): candles(Side.CALL, 3, [10, 10.2, 10.4, 12.0], last_body=1.2),
        (Side.PUT, 3): candles(Side.PUT, 3, [8, 7.9, 7.8, 7.7], last_body=-0.2),
    }
    decision = engine.process(streams, BASE + timedelta(minutes=9))
    assert decision.status is Status.FIRST_SIDE_ARMED
    assert decision.alert is False
    assert "PUT DOWN expansion is missing" in decision.reason


def test_later_put_down_expansion_confirms_call():
    engine = OppositeExpansionEngine()
    first = {
        (Side.CALL, 3): candles(Side.CALL, 3, [10, 10.2, 10.4, 12.0], last_body=1.2),
        (Side.PUT, 3): candles(Side.PUT, 3, [8, 7.9, 7.8, 7.7], last_body=-0.2),
    }
    assert engine.process(first, BASE + timedelta(minutes=9)).alert is False

    second = dict(first)
    second[(Side.PUT, 3)] = candles(Side.PUT, 3, [8, 7.9, 7.8, 6.0], last_body=-1.2)
    second[(Side.PUT, 3)][-1] = Candle(
        **{**vars(second[(Side.PUT, 3)][-1]), "timestamp": BASE + timedelta(minutes=12)}
    )
    decision = engine.process(second, BASE + timedelta(minutes=10))
    assert decision.status is Status.CONFIRMED_CALL
    assert decision.alert is True


def test_put_up_then_call_down_confirms_put():
    engine = OppositeExpansionEngine()
    first = {
        (Side.PUT, 15): candles(Side.PUT, 15, [5, 5.2, 5.4, 7.0], last_body=1.2),
    }
    assert engine.process(first, BASE + timedelta(minutes=45)).status is Status.FIRST_SIDE_ARMED
    second = dict(first)
    second[(Side.CALL, 3)] = candles(Side.CALL, 3, [10, 9.9, 9.8, 8.0], last_body=-1.2)
    second[(Side.CALL, 3)][-1] = Candle(
        **{**vars(second[(Side.CALL, 3)][-1]), "timestamp": BASE + timedelta(minutes=48)}
    )
    decision = engine.process(second, BASE + timedelta(minutes=46))
    assert decision.status is Status.CONFIRMED_PUT
    assert decision.alert is True


def test_detector_ignores_large_wick_without_body_expansion():
    detector = ExpansionDetector()
    series = candles(Side.CALL, 3, [10, 10.2, 10.4, 10.6], last_body=0.2)
    last = series[-1]
    series[-1] = Candle(
        side=last.side,
        timeframe_minutes=last.timeframe_minutes,
        timestamp=last.timestamp,
        open=10.4,
        high=14.0,
        low=10.3,
        close=10.6,
    )
    assert detector.detect(series) is None
