# Opposite CALL/PUT Expansion System

The former support/resistance, rejection, holding-time, weak-side, trigger-zone,
and level-touch concept is retired from the active live entry point.

The active system watches only closed candles on the CALL and PUT charts:

1. Detect a genuine candle-body expansion on either side using the 3-minute or
   15-minute chart.
2. Store that event as the first leg. Do not issue a trade notification.
3. Wait for the other contract to produce a later candle-body expansion in the
   opposite direction.
4. Notify CALL only for `CALL UP + PUT DOWN`.
5. Notify PUT only for `PUT UP + CALL DOWN`.
6. Any incomplete pair is `NO_TRADE`.

The two legs do not need to happen simultaneously and may come from different
allowed timeframes. A large wick without a large body does not qualify.

Run the live watcher from `SPX_LLM_VISION_TRADER`:

```bash
python main.py
```

Run the focused tests:

```bash
python -m pytest tests/test_expansion_engine.py
```
