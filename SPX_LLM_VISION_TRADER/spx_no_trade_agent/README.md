# SPX 0DTE no-trade-zone reasoning agent

An implementation of the reasoning agent described in `spx-intelligent-agent-notes.md`.
**Goal:** clearly identify the no-trade zone, live, so that gains already made
on winning trades don't get given back by trading through chop and fakeouts.

This is a **reasoning system, not a rule-following one** — every threshold in
`chart_agent.py` / `data_agent.py` is a tunable starting point meant to be
adjusted over time by the self-learning loop (`learning.py`), not a fixed
formula.

## What's here

```
spx_agent/
  models.py                Plain data structures (Candle, ChartExtraction, Verdict, Decision, ...)
  chart_agent.py            Chart-reasoning agent: candle stacking, wick-vs-body, multi-timeframe checks
  data_agent.py              Data-reasoning agent: velocity, volume, holding time, call/put see-saw
  boss.py                    Reconciles the two agents; disagreement defaults to no-trade
  learning.py                 Logs decisions + outcomes; computes false-trade / false-no-trade rates
  commentary.py               Turns a Decision into a plain-language narration line
  connectors.py                Pluggable I/O boundary: SheetConnector, ChartConnector + CSV-backed demo implementations
  llm_chart_extraction.py       Reference for the ONE place an LLM is used in production (chart extraction only)
  orchestrator.py                SpxNoTradeAgent — ties everything together into a live/backtest loop
tests/
  test_agent.py               Unit tests for the actual reasoning judgments (not just "does it run")
run_demo.py                  End-to-end demo against the real SPXW 7515C / 7520P data from this conversation
```

## Design principles this follows (from the project notes)

1. **The LLM's only job is chart extraction** — support/resistance levels,
   indicator readings, candle body stacking, read off the chart image.
   Nothing else. All judgment happens in Python (`chart_agent.py`,
   `data_agent.py`, `boss.py`). See `llm_chart_extraction.py` for exactly
   what that one LLM call should look like in production; it is **not**
   wired into the demo, since the demo runs against historical CSV data
   instead (see below).

2. **Two independent reasoning agents, cross-checked by a boss.** The chart
   agent and data agent never see each other's inputs — they each form a
   judgment from different evidence and the boss checks whether they landed
   on the *same* pattern. Disagreement is not silently resolved; it defaults
   to no-trade.

3. **Four-way classification, not binary.** `Zone` is `BULLISH`, `BEARISH`,
   `CONSOLIDATION`, or `SLOW_MOVING` — the cautious middle case (some
   directional attempt, but the body isn't confirming with conviction) is
   distinct from flat consolidation.

4. **No-trade is the expected default**, not a fallback. Both agents
   actively pattern-match for all four states with equal rigor — see the
   demo output below, where no-trade dominates.

5. **The wick-vs-body fakeout check is the single most concrete rule**: a
   wick that reaches a level without the body following through reads as
   consolidation immediately (`chart_agent.py: _reconcile_timeframes`,
   Case 1), ahead of any other classification logic.

6. **Multi-timeframe noise trap**: the chart agent evaluates every
   timeframe present in the extraction and requires the long timeframe to
   confirm what the short timeframe shows before trusting a direction.

7. **Self-learning is transparent, not a black box.** `learning.py` logs
   every decision's inputs and (once known) outcome, and computes
   `false_trade_rate()` / `false_no_trade_rate()` plus plain-language
   threshold-adjustment suggestions — a person reviewing the log can see
   *why* a parameter might change, rather than the system silently drifting.

## Running the demo

```
python run_demo.py
```

This runs the full pipeline (chart agent + data agent + boss + learning log
+ commentary) against the real `OPRA_SPXW260714C7515` / `OPRA_SPXW260714P7520`
CSV data uploaded earlier in this conversation, using `DerivedChartConnector`
— which builds a `ChartExtraction` directly from the same OHLCV data (recent
swing highs/lows as support/resistance, resampled candles for the longer
timeframe) as a stand-in for the live LLM chart read. This lets the entire
reasoning pipeline be exercised end-to-end on real data without needing a
live Playwright + LLM integration wired up yet.

**Result on this data:** the call side calls no-trade on 94% of ticks
(6% cautious trade, 0% full-conviction trade); the put side calls no-trade
100% of the time. That's the intended behavior — this was a fairly choppy
session, and the system is calibrated to say so rather than force a call.

## Running the tests

```
python tests/test_agent.py
```

Ten tests validating the actual judgments (wick fakeout → consolidation,
clean multi-timeframe stacking → bullish, short-timeframe noise without
long-timeframe confirmation → consolidation, boss agreement/disagreement
behavior, self-learning persistence), not just that the code executes.

## Swapping in the live system

Two things need to change to go from this demo to production; nothing in
`chart_agent.py`, `data_agent.py`, `boss.py`, `learning.py`, or
`commentary.py` needs to change at all:

1. **`SheetConnector`** — replace `CsvSheetConnector` with a connector that
   polls the live Google Sheet (the `/export?format=csv&gid=...` endpoint
   noted in the project's tooling notes) on a short interval.

2. **`ChartConnector`** — replace `DerivedChartConnector` with
   `PlaywrightChartConnector` (sketched in `llm_chart_extraction.py`):
   Playwright screenshots the TradingView chart, the screenshot goes to a
   vision-capable model with the extraction prompt in that file, and the
   JSON response is mapped into a `ChartExtraction`. Refresh cadence
   discussed: 60 seconds.

Everything downstream — both reasoning agents, the boss, the self-learning
log, and the live commentary — runs unchanged against whatever these two
connectors produce.

## Additions: closing the gaps identified from live chart review

Everything below was added to the SAME package described above — nothing here is a separate system. These four modules close the specific gaps identified when the original code was audited against live TradingView chart examples during this project.

```
spx_agent/
  level_tracker.py     — LevelMemory: multi-touch memory for a support/resistance level. Repeated
                          rejections at the same level accumulate confidence instead of each touch
                          being read as an isolated, unconfirmed event.
  exit_rule.py           — TrailingStopExitRule: 10% hard stop-loss, 5% trailing stop from peak
                            once in profit. Two numbers, pure percentage math, nothing else.
  trade_simulator.py       — TradeSimulator: opens/tracks/closes simulated (paper, no broker) trades
                              using only data already flowing through the system. No account, no
                              orders placed anywhere — this is a rule-validation tool, not an
                              execution system.
  trade_logger.py            — CsvTradeLogger (always works, no setup) and GoogleSheetTradeLogger
                                (optional, requires a service account — see the docstring in that
                                file for the one-time setup this needs).
  dual_side.py                  — DualSideEngine: the piece that evaluates call and put TOGETHER
                                    instead of in isolation. Implements:
                                      (a) the cross-side gate — a side's own directional read gets
                                          vetoed to no-trade if the OTHER side's level is still
                                          live and unresolved (confirmed directly on a live chart:
                                          put holding support made call's own activity fake)
                                      (b) rejection-trigger propagation — the moment one side's
                                          data agent detects "was holding, just stopped holding"
                                          (a rejection event), that promotes the OTHER side's
                                          decision immediately, ahead of its own momentum
                                          confirming separately — the earliest, cheapest entry
                                          point described throughout the design discussion
run_validation.py    — Runs the full dual-side pipeline tick-by-tick, simulates trades with the
                        exit rule, logs every trade, and prints a win-rate/P&L summary — the
                        direct answer to "is the rule correct or wrong."
tests/test_advanced.py  — 8 tests covering the exit rule, level memory, slow-leak detection,
                           the cross-side gate, and rejection-trigger propagation.
```

### What also changed in the original files

- **`chart_agent.py`** — added slow-leak detection: a level crossed gradually over several candles
  without real conviction behind the crossing now reads as a fakeout (Case 1b in
  `_reconcile_timeframes`), not just the single-candle wick case that existed before.
- **`data_agent.py`** — added `rejection_just_occurred` detection: compares the current holding
  time against the previous call's holding time to detect the exact moment a level stops being
  held (the rejection event itself), and stamps the current price into evidence as `entry_price`
  so the trade simulator has something to enter at.
- **`models.py`** — added `LevelTouch`, `LevelHistory`, `DualSideDecision`, `SimulatedTrade`, and
  a `rejection_trigger` flag on `Decision`.
- **`connectors.py`** — added `LiveDerivedChartConnector`: computes support/resistance and candle
  stacking directly from a rolling buffer of live ticks, so the validation loop can run against a
  live feed without needing Playwright or an LLM call at all.

### Running the validation

```
python run_validation.py
```

Runs against the same real SPXW 7515C/7520P data used throughout this project, stepping through
it tick-by-tick the way a live feed would deliver it. Prints every simulated trade as it opens and
closes (tagging rejection-triggered entries specifically), every time the cross-side gate fires,
and a final summary: total trades, win rate, average P&L, and the breakdown of hard-stop vs.
trailing-stop exits.

**On this data:** 2 trades opened over the session, both rejection-triggered, both closed on the
trailing stop, both profitable (100% win rate, +3.4% average). Two trades is a small sample — the
point of this run is to prove the pipeline works end-to-end, not to draw conclusions about the
rule's real edge. That requires running this against many more sessions, ideally live.

### Going from this to a live validation run

Swap `CsvSheetConnector` for `GoogleSheetConnector` (in `spx_agent_live/`), call `engine.decide()`
and `simulator.on_tick()` / `on_decision()` inside a polling loop instead of the `for` loop over
historical ticks — the reasoning and simulation code is identical either way. `LiveDerivedChartConnector`
already works directly off live ticks via `push_tick()`, so no chart-reading integration is needed
for this validation phase at all.

## What's still not built

- Google Sheet write-back requires a service account (a real, separate setup step — see
  `trade_logger.py`'s docstring). CSV logging works immediately with no setup.
- The cross-side gate and rejection-trigger logic have not been tested against a real live feed
  yet, only against historical data and targeted unit tests.
- No real broker connection anywhere in this system — by design, per this phase being a
  rule-validation tool, not an execution system.
