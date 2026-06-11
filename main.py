"""Main orchestrator for the SPX Acceptance Platform.

This script ties together all agents, the database and configuration.  It
runs in an infinite loop (one iteration per minute) performing the
following steps:

1. Read the latest data from the Google Sheet and append it to the
   local SQLite database.
2. Fetch recent data from the database for analysis.
3. Detect support and resistance zones.
4. For each zone, analyse acceptance/rejection and update the database.
5. Compute peak hold time and return‑to‑zone metrics and make a final
   trade decision.
6. Store trade signals in the database and send Telegram alerts when
   confidence thresholds are met.
7. Sleep until the next minute.

Logging is configured to write to ``logs/spx_acceptance.log`` and to
standard output.  Error handling ensures that failures in one
iteration do not crash the entire process.

To run the orchestrator:

    python main.py
"""

from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime
from typing import List, Optional

import pandas as pd

from config import get_settings
from database import (
    init_db,
    insert_market_data,
    fetch_recent_market_data,
    insert_zone,
    insert_acceptance_result,
    insert_trade_signal,
)
from agents.google_sheet_reader import GoogleSheetReader
from agents.zone_detection_agent import ZoneDetectionAgent, Zone
from agents.acceptance_rejection_agent import AcceptanceRejectionAgent, AcceptanceResult
from agents.peak_hold_time_agent import PeakHoldTimeAgent
from agents.return_to_zone_agent import ReturnToZoneAgent
from agents.trade_decision_agent import TradeDecisionAgent
from agents.telegram_agent import TelegramAgent
from agents.google_trade_signal_writer import (
    GoogleTradeSignalWriter,
    SheetSignalRow,
)

def configure_logging() -> None:
    """Configure logging to file and stdout."""
    log_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "spx_acceptance.log")
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # File handler
    fh = logging.FileHandler(log_file)
    fh.setLevel(logging.INFO)
    fh.setFormatter(formatter)
    # Stream handler
    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO)
    sh.setFormatter(formatter)
    logger.addHandler(fh)
    logger.addHandler(sh)


def format_telegram_message(
    zone: Zone,
    acceptance: AcceptanceResult,
    trade_decision: str,
    confidence: int,
    peak_result,
    return_result,
) -> str:
    """Create a formatted Telegram alert message."""
    zone_desc = f"{zone.zone_type.title()} {zone.low:.2f}–{zone.high:.2f}"
    message_lines = [
        "<b>SPX ALERT</b>",
        f"Zone: {zone_desc}",
        f"Decision: {trade_decision}",
        f"Confidence: {confidence}%",
        f"Reason: {acceptance.reason}",
        f"Hold time: {peak_result.hold_time_minutes:.2f} m (acceptance {peak_result.acceptance_score}%)",
        f"Return status: {return_result.status}",
    ]
    if return_result.time_to_return_minutes is not None:
        message_lines.append(f"Time to return: {return_result.time_to_return_minutes:.2f} m")
    return "\n".join(message_lines)


def main() -> None:
    settings = get_settings()
    configure_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting SPX Acceptance Platform")
    # Initialise database schema
    init_db()
    # Instantiate agents
    sheet_reader = GoogleSheetReader()
    zone_agent = ZoneDetectionAgent()
    acceptance_agent = AcceptanceRejectionAgent()
    peak_agent = PeakHoldTimeAgent()
    return_agent = ReturnToZoneAgent()
    decision_agent = TradeDecisionAgent()
    telegram_agent = TelegramAgent()
    signal_writer = GoogleTradeSignalWriter()
    # Track the most recent timestamp seen to avoid re‑inserting data
    last_timestamp: Optional[pd.Timestamp] = None
    # Main loop
    while True:
        start_time = time.monotonic()
        try:
            # Step 1: read latest data
            try:
                df = sheet_reader.read_latest_rows(limit=1000)
            except Exception as exc:
                logger.error("Failed to read data from Google Sheet: %s", exc)
                df = pd.DataFrame()
            if not df.empty:
                # Filter new rows only
                new_rows_df = df if last_timestamp is None else df[df["timestamp"] > last_timestamp]
                if not new_rows_df.empty:
                    # Insert into market_data
                    rows_to_insert = []
                    for _, row in new_rows_df.iterrows():
                        rows_to_insert.append(
                            (
                                row["timestamp"].isoformat(),
                                float(row["price"]),
                                row.get("signal"),
                                row.get("call_pressure"),
                                row.get("put_pressure"),
                            )
                        )
                    insert_market_data(rows_to_insert)
                    last_timestamp = new_rows_df["timestamp"].max()
                    logger.info("Inserted %d new market rows", len(rows_to_insert))
            # Step 2: fetch recent data for analysis
            recent_rows = fetch_recent_market_data(limit=300)
            if recent_rows:
                df_recent = pd.DataFrame(
                    [dict(row) for row in recent_rows]
                )

                print("DF_RECENT COLUMNS:")
                print(df_recent.columns.tolist())

                df_recent["timestamp"] = pd.to_datetime(
                    df_recent["timestamp"],
                    errors="coerce"
                )

                df_recent["price"] = pd.to_numeric(
                    df_recent["price"],
                    errors="coerce"
                )

                df_recent = df_recent.dropna(
                    subset=["timestamp", "price"]
                )

                df_recent = df_recent.sort_values(
                    "timestamp"
                )

                df_recent = df_recent.reset_index(
                    drop=True
                )
            else:
                df_recent = pd.DataFrame(
                    columns=[
                        "id",
                        "timestamp",
                        "price",
                        "signal",
                        "call_pressure",
                        "put_pressure",
                    ]
                )
            if df_recent.empty:
                logger.info("No data available for analysis. Sleeping...")
                time.sleep(max(0, 60 - (time.monotonic() - start_time)))
                continue
            # Step 3: detect zones
            zones = zone_agent.detect_zones(df_recent)
            if not zones:
                logger.info("No zones detected in recent data.")
            for zone in zones:
                # Persist zone to DB
                zone_id = insert_zone(zone.zone_type, zone.low, zone.high, zone.strength, zone.touches)
                # Step 4: acceptance analysis
                acceptance = acceptance_agent.analyze_zone_touch(df_recent, zone)
                if acceptance is None:
                    continue
                acceptance_id = insert_acceptance_result(
                    zone_id=zone_id,
                    zone_type=acceptance.zone_type,
                    zone_low=acceptance.zone_low,
                    zone_high=acceptance.zone_high,
                    entered_time=acceptance.entered_time,
                    rejection_time=acceptance.rejection_time,
                    returned_time=acceptance.returned_time,
                    decision=acceptance.decision,
                    bias=acceptance.bias,
                    confidence=acceptance.confidence,
                    reason=acceptance.reason,
                )
                # If still waiting, do not proceed further
                if acceptance.decision == "WAITING_FOR_CONFIRMATION":
                    logger.info("Zone analysis awaiting confirmation: %s", acceptance.reason)
                    continue
                # Step 5: peak hold time analysis
                # Determine when to start measuring: from rejection if available, otherwise entry
                decision_time = pd.to_datetime(acceptance.rejection_time or acceptance.entered_time)
                peak_result = peak_agent.analyse(df_recent, acceptance.bias, decision_time)
                # Step 6: return to zone analysis
                rejection_time_dt = pd.to_datetime(acceptance.rejection_time or acceptance.entered_time)
                return_result = return_agent.evaluate(df_recent, zone, rejection_time_dt)
                # Step 7: trade decision
                trade_result = decision_agent.decide(acceptance, peak_result, return_result)
                # Store trade signal
                signal_id = insert_trade_signal(
                    acceptance_id=acceptance_id,
                    hold_time=peak_result.hold_time_minutes,
                    acceptance_score=peak_result.acceptance_score,
                    rejection_score=peak_result.rejection_score,
                    return_status=return_result.status,
                    time_to_return=return_result.time_to_return_minutes,
                    decision=trade_result.decision,
                )
                signal_writer.append(
    SheetSignalRow(
        time=str(acceptance.entered_time),
        price=float(df_recent.iloc[-1]["price"]),
        zone=zone.zone_type.upper(),
        support=f"{zone.low}-{zone.high}" if zone.zone_type == "support" else "",
        resistance=f"{zone.low}-{zone.high}" if zone.zone_type == "resistance" else "",
        acceptance=acceptance.decision,
        rejection=str(acceptance.rejection_time or ""),
        return_time=str(acceptance.returned_time or "NOT_RETURNED"),
        decision=trade_result.decision,
        confidence=trade_result.confidence,
        reason=acceptance.reason,
    )
)
                logger.info(
                    "Generated trade signal %d: %s (conf=%d%%)",
                    signal_id,
                    trade_result.decision,
                    trade_result.confidence,
                )
                # Step 8: send Telegram alert if appropriate
                if trade_result.decision != "WAIT" and trade_result.confidence >= settings.confidence_threshold:
                    try:
                        message = format_telegram_message(
                            zone,
                            acceptance,
                            trade_result.decision,
                            trade_result.confidence,
                            peak_result,
                            return_result,
                        )
                        telegram_agent.send_alert(message)
                    except Exception as exc:
                        logger.error("Failed to send Telegram alert: %s", exc)
        except Exception as exc:
            logger.exception("Unhandled error during main loop: %s", exc)
        # Wait until the next minute
        elapsed = time.monotonic() - start_time
        sleep_time = max(0.0, 60.0 - elapsed)
        time.sleep(sleep_time)


if __name__ == "__main__":
    main()
