"""
Main live entry point. Run this on the VPS to start the agent for real.

Reads all configuration from environment variables (set in .env — see
.env.example) so no secrets or URLs are hardcoded in this file.

Run:
    python run_live.py
"""

from __future__ import annotations

import os
import time
from datetime import datetime, time as dt_time

from dotenv import load_dotenv

from google_sheet_connector import GoogleSheetConnector
from playwright_chart_connector import PlaywrightChartConnector
from spx_agent import (
    Boss,
    ChartReasoningAgent,
    DataReasoningAgent,
    SelfLearningLog,
    Side,
    SpxNoTradeAgent,
    narrate,
)

load_dotenv()

POLL_SECONDS = int(os.environ.get("POLL_SECONDS", "3"))
CHART_REFRESH_SECONDS = int(os.environ.get("CHART_REFRESH_SECONDS", "60"))
MARKET_OPEN = dt_time(8, 30)
MARKET_CLOSE = dt_time(15, 0)


def market_is_open() -> bool:
    now = datetime.now().time()
    return MARKET_OPEN <= now <= MARKET_CLOSE


def build_agent(side: Side, sheet_connector, chart_connector, log_path: str) -> SpxNoTradeAgent:
    return SpxNoTradeAgent(
        side=side,
        sheet_connector=sheet_connector,
        chart_connector=chart_connector,
        chart_agent=ChartReasoningAgent(),
        data_agent=DataReasoningAgent(),
        boss=Boss(min_confidence_for_trade=float(os.environ.get("MIN_CONFIDENCE", "0.65"))),
        learning_log=SelfLearningLog(path=log_path),
    )


def main():
    sheet_connector = GoogleSheetConnector(
        call_sheet_url=os.environ["CALL_SHEET_URL"],
        put_sheet_url=os.environ["PUT_SHEET_URL"],
    )
    chart_connector = PlaywrightChartConnector(
        call_chart_url=os.environ["CALL_CHART_URL"],
        put_chart_url=os.environ["PUT_CHART_URL"],
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        storage_state_path=os.environ.get("TRADINGVIEW_SESSION_PATH", "tradingview_session.json"),
    )

    call_agent = build_agent(Side.CALL, sheet_connector, chart_connector, "call_log.jsonl")
    put_agent = build_agent(Side.PUT, sheet_connector, chart_connector, "put_log.jsonl")

    tick_windows: dict[Side, list] = {Side.CALL: [], Side.PUT: []}
    window_size = int(os.environ.get("TICK_WINDOW", "30"))

    print("SPX no-trade-zone agent starting. Waiting for market hours..." if not market_is_open()
          else "SPX no-trade-zone agent live.")

    try:
        while True:
            if not market_is_open():
                time.sleep(30)
                continue

            new_ticks = sheet_connector.get_ticks()
            if new_ticks:
                for side, agent in ((Side.CALL, call_agent), (Side.PUT, put_agent)):
                    tick_windows[side].extend(new_ticks)
                    tick_windows[side] = tick_windows[side][-window_size:]

                    if len(tick_windows[side]) >= 3:
                        decision = agent.step(tick_windows[side])
                        print(narrate(decision))

            time.sleep(POLL_SECONDS)

    except KeyboardInterrupt:
        print("Shutting down.")
    finally:
        chart_connector.close()


if __name__ == "__main__":
    main()
