"""
Live trade-validation runner.

This is run_validation.py's live counterpart: instead of stepping through a
finished historical file, it polls your real Google Sheet continuously
during market hours, feeds each new tick through the SAME dual-side engine
(cross-side gate + rejection-trigger + multi-touch level memory), and lets
the SAME trade simulator (10% hard stop / 5% trailing stop) actually open
and close simulated trades as real price moves happen — logging every one
to CSV (and optionally your Google Sheet) as it closes.

Nothing about the reasoning or simulation logic differs from the
historical run — only the tick source and the fact that it runs
continuously instead of finishing when the file ends.

REQUIRES, before this will do anything:
  1. CALL_SHEET_URL and PUT_SHEET_URL set in .env (see .env.example in
     spx_agent_live/) — the /export?format=csv&gid=... links to your live
     Google Sheet, NOT the /edit link.
  2. This script running on a machine with real network access (your VPS)
     — it will not run inside a sandboxed chat environment.
  3. `pip install requests python-dotenv` (see spx_agent_live/requirements.txt)

Run: python run_live_trading.py
"""

from __future__ import annotations

import os
import time
from datetime import datetime, time as dt_time

from dotenv import load_dotenv

from spx_agent import (
    Boss,
    ChartReasoningAgent,
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
from spx_agent.commentary import narrate

load_dotenv()

POLL_SECONDS = int(os.environ.get("POLL_SECONDS", "3"))
TICK_WINDOW = int(os.environ.get("TICK_WINDOW", "30"))
MARKET_OPEN = dt_time(8, 30)
MARKET_CLOSE = dt_time(15, 0)


def market_is_open() -> bool:
    now = datetime.now().time()
    return MARKET_OPEN <= now <= MARKET_CLOSE


def build_google_sheet_connector():
    """
    Imports and constructs the live sheet connector. Kept as a local import
    so this file can still be inspected/tested without spx_agent_live on
    the path — it's only required at actual runtime.
    """
    import sys
    sys.path.insert(0, "spx_agent_live")
    from google_sheet_connector import GoogleSheetConnector

    return GoogleSheetConnector(
        call_sheet_url=os.environ["CALL_SHEET_URL"],
        put_sheet_url=os.environ["PUT_SHEET_URL"],
    )


def main():
    missing = [k for k in ("CALL_SHEET_URL", "PUT_SHEET_URL") if k not in os.environ]
    if missing:
        print(f"Missing required .env values: {', '.join(missing)}")
        print("This script cannot start without your live Google Sheet URLs. See SETUP.md.")
        return

    sheet_connector = build_google_sheet_connector()
    live_chart = LiveDerivedChartConnector(base_timeframe_seconds=15)  # tightest timeframe available live
    engine = DualSideEngine(
        chart_agent=ChartReasoningAgent(),
        data_agent=DataReasoningAgent(),
        boss=Boss(min_confidence_for_trade=float(os.environ.get("MIN_CONFIDENCE", "0.65"))),
        level_memory=LevelMemory(),
    )
    exit_rule = TrailingStopExitRule(ExitRuleParams(
        hard_stop_pct=float(os.environ.get("HARD_STOP_PCT", "10.0")),
        trailing_stop_pct=float(os.environ.get("TRAILING_STOP_PCT", "5.0")),
    ))
    simulator = TradeSimulator(exit_rule=exit_rule)
    logger = CsvTradeLogger(path=os.environ.get("TRADE_LOG_PATH", "live_simulated_trades.csv"))

    tick_buffer: list = []

    print("SPX live rule-validation agent starting."
          + (" Market is open — running now." if market_is_open() else " Waiting for market hours..."))

    try:
        while True:
            if not market_is_open():
                time.sleep(30)
                continue

            new_ticks = sheet_connector.get_ticks()
            for tick in new_ticks:
                tick_buffer.append(tick)
                tick_buffer[:] = tick_buffer[-TICK_WINDOW:]
                live_chart.push_tick(tick)

                if len(tick_buffer) < 3:
                    continue

                call_extraction = live_chart.read_chart(Side.CALL, tick.timestamp)
                put_extraction = live_chart.read_chart(Side.PUT, tick.timestamp)
                dual = engine.decide(tick_buffer, call_extraction, put_extraction, tick.timestamp)

                for decision in (dual.call_decision, dual.put_decision):
                    print(narrate(decision))
                    opened = simulator.on_decision(decision)
                    if opened:
                        tag = " [REJECTION-TRIGGERED]" if decision.rejection_trigger else ""
                        print(f"  >>> OPENED {decision.side.value.upper()}{tag} @ {opened.entry_price:.2f}")

                if dual.call_gated or dual.put_gated:
                    print(f"  >>> GATE: {dual.gate_reason}")

                closed = simulator.on_tick(tick)
                if closed:
                    print(f"  >>> CLOSED {closed.side.value.upper()} @ {closed.exit_price:.2f} "
                          f"({closed.exit_reason}) P&L: {closed.pnl_pct:+.1f}%")
                    logger.log(closed)

            time.sleep(POLL_SECONDS)

    except KeyboardInterrupt:
        print("\nShutting down. Closing any open simulated trades at last known price...")
        if tick_buffer:
            simulator.force_close_all(tick_buffer[-1].timestamp, tick_buffer[-1], reason="manual_stop")
            for trade in simulator.closed_trades:
                if trade.exit_reason == "manual_stop":
                    logger.log(trade)
        summary = logger.summary()
        print("\n--- Session summary ---")
        for k, v in summary.items():
            print(f"{k}: {v}")


if __name__ == "__main__":
    main()
