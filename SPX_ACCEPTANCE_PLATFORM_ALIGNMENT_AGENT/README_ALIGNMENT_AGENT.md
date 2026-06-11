# SPX Acceptance Platform — Alignment + Timing Agent

This agent does not trade raw buy/sell signals.

It grades every signal based on whether SPY, CALL, and PUT agree within a short time window.

## Bullish Alignment

CALL BUY + SPY BUY + PUT SELL

## Bearish Alignment

PUT BUY + SPY SELL + CALL SELL

## Core rule

If all three do not align within 15 minutes, the signal is weak/no trade.

## Grades

- A+ = all three align very fast
- A = strong alignment
- B = valid but slower
- C = partial/conflict
- NO TRADE = signal not safe

## Test

Run:

```bash
python agents/test_alignment_from_user_data.py
```

## Why this is different

The first signal can come from CALL, PUT, or SPY.

The agent starts grading immediately and continues updating as new signals arrive.
