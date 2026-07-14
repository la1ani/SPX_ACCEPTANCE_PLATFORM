"""
Rule-validation runner.

This is the direct answer to "is the rule correct or wrong": it runs the
full dual-side reasoning engine (cross-side gate + rejection-trigger +
multi-touch level memory) tick by tick, simulates entry/exit using the
exit rule (10% hard stop, 5% trailing from peak), logs every simulated
trade, and prints a summary at the end — win rate, average P&L, and how
many trades exited on the hard stop vs. the trailing stop.

For LIVE use: swap CsvSheetConnector for GoogleSheetConnector (in
spx_agent_live/google_sheet_connector.py) and call this in a polling loop
instead of run_over_history — the reasoning/simulation code underneath is
identical either way, only the tick source changes.

For this run: uses the real SPXW 7515C / 7520P CSV data already in this
conversation, stepping through it tick-by-tick exactly as a live feed
would deliver it, to prove the whole pipeline end-to-end before pointing
it at a live sheet.
"""

from spx_agent import (
    Boss,
    ChartReasoningAgent,
    CsvSheetConnector,
    CsvTradeLogger,
    DataReasoningAgent,
    DualSideEngine,
    ExitRuleParams,
    LevelMemory,
    LiveDerivedChartConnector,
    Side,
    TrailingStopExitRule,
    TradeSimulator,
)

CALL_CSV = "/mnt/user-data/uploads/OPRA_SPXW260714C7515_0__3.csv"
PUT_CSV = "/mnt/user-data/uploads/OPRA_SPXW260714P7520_0__3.csv"


def main():
    sheet_connector = CsvSheetConnector(CALL_CSV, PUT_CSV)
    all_ticks = sheet_connector.get_ticks()
    print(f"Loaded {len(all_ticks)} ticks.\n")

    live_chart = LiveDerivedChartConnector(base_timeframe_seconds=180)  # matches the 3-min source data
    engine = DualSideEngine(
        chart_agent=ChartReasoningAgent(),
        data_agent=DataReasoningAgent(),
        boss=Boss(min_confidence_for_trade=0.65),
        level_memory=LevelMemory(),
    )
    exit_rule = TrailingStopExitRule(ExitRuleParams(hard_stop_pct=10.0, trailing_stop_pct=5.0))
    simulator = TradeSimulator(exit_rule=exit_rule)
    logger = CsvTradeLogger(path="/home/claude/simulated_trades.csv")

    window_size = 15
    trades_opened = 0

    for i, tick in enumerate(all_ticks):
        live_chart.push_tick(tick)
        window = all_ticks[max(0, i - window_size + 1): i + 1]
        if len(window) < 3:
            continue

        call_extraction = live_chart.read_chart(Side.CALL, tick.timestamp)
        put_extraction = live_chart.read_chart(Side.PUT, tick.timestamp)

        dual_decision = engine.decide(window, call_extraction, put_extraction, tick.timestamp)

        for decision in (dual_decision.call_decision, dual_decision.put_decision):
            opened = simulator.on_decision(decision)
            if opened:
                trades_opened += 1
                trigger_tag = " [REJECTION-TRIGGERED]" if decision.rejection_trigger else ""
                print(f"OPEN  {decision.timestamp.strftime('%H:%M:%S')} {decision.side.value.upper()}"
                      f"{trigger_tag} @ {opened.entry_price:.2f} — {decision.final_call.value}")

        closed = simulator.on_tick(tick)
        if closed:
            print(f"CLOSE {closed.exit_timestamp.strftime('%H:%M:%S')} {closed.side.value.upper()} "
                  f"@ {closed.exit_price:.2f} ({closed.exit_reason}) — P&L: {closed.pnl_pct:+.1f}%")
            logger.log(closed)

        if dual_decision.call_gated or dual_decision.put_gated:
            print(f"      GATE {tick.timestamp.strftime('%H:%M:%S')}: {dual_decision.gate_reason}")

    if all_ticks:
        simulator.force_close_all(all_ticks[-1].timestamp, all_ticks[-1])
        for trade in simulator.closed_trades:
            if trade.exit_reason == "session_end":
                logger.log(trade)

    print(f"\n{'=' * 60}")
    print(f"Trades opened: {trades_opened}")
    summary = logger.summary()
    for k, v in summary.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
